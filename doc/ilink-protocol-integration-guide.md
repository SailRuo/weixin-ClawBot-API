# 微信 iLink Bot 独立协议集成指南 (v2.1.3)

> 本文档面向想要在自定义智能体（Agent）应用中直接对接微信 Bot 能力、而不使用 OpenClaw 框架的开发者。基于对官方底层协议的逆向分析与实测整理而成。

---

## 1. 协议概览

微信 ClawBot 基于 **iLink (智联)** 协议实现。它是一套基于 HTTP/JSON 的长连接通讯方案，主要通过 **长轮询 (Long-Polling)** 维持消息实时性。

- **官方接口域名**：`https://ilinkai.weixin.qq.com`
- **认证方式**：Bearer Token + 自定义安全 Headers。
- **消息流向**：
    - **下行 (Inbound)**：通过 `getupdates` 接口阻塞监听。
    - **上行 (Outbound)**：通过 `sendmessage` 接口实时发送。

---

## 2. 核心鉴权与 Headers

所有向 iLink 服务器发出的请求都必须携带以下 Headers。**缺失或算法错误将导致 403 Forbidden 或消息投递失败。**

### 2.1 基础 Headers
| Header 名 | 示例值 | 说明 |
| :--- | :--- | :--- |
| `Content-Type` | `application/json` | 固定值 |
| `AuthorizationType` | `ilink_bot_token` | 固定值 |
| `Authorization` | `Bearer <token>` | 登录成功后获取的 `bot_token` |
| `iLink-App-Id` | `bot` | 官方固定值 |
| `iLink-App-ClientVersion` | `131331` | 对应版本 2.1.3 (计算见下文) |
| `X-WECHAT-UIN` | `MTE4Njk5MzE0Mg==` | **动态随机值** (计算见下文) |

### 2.2 关键算法实现 (Python 示例)

#### 客户端版本号计算
协议要求将 `X.Y.Z` 版本号转换为 `uint32`：`(X << 16) | (Y << 8) | Z`。
```python
def get_client_version(version_str="2.1.3"):
    parts = [int(p) for p in version_str.split(".")]
    return (parts[0] << 16) | (parts[1] << 8) | parts[2]
# 2.1.3 -> 131331
```

#### X-WECHAT-UIN 生成
该字段用于防止重放攻击，**每次请求都必须重新生成**。
逻辑：随机 uint32 -> 转为十进制字符串 -> Base64 编码。
```python
import random
import base64

def get_random_uin():
    uint32_val = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(uint32_val).encode()).decode()
```

---

## 3. 登录生命周期 (Login Flow)

登录是一个状态机转换的过程，涉及 **IDC 重定向** 这一关键细节。

### Step 1: 获取登录二维码 (get_bot_qrcode)
- **请求**：`GET /ilink/bot/get_bot_qrcode?bot_type=3`
- **返回**：
    - `qrcode`: 二维码唯一标识。
    - `qrcode_img_content`: **二维码链接** (通常以 `https://liteapp.weixin.qq.com/...` 开头)。

### Step 2: 轮询登录状态 (get_qrcode_status)
- **请求**：`GET /ilink/bot/get_qrcode_status?qrcode=<qrcode>`
- **核心状态处理**：
    1. `wait`: 等待扫码。
    2. `scaned`: 已扫码，等待手机端确认。
    3. **`scaned_but_redirect` (重要)**：
       此时返回体会包含 `redirect_host` (如 `sh.ilinkai.weixin.qq.com`)。
       **必须** 立即将后续的所有轮询和业务请求重定向到这个新域名下。
    4. `confirmed`: 确认登录。
       返回 `bot_token` 和 `baseurl`。**请持久化存储 `bot_token`**。
    5. `expired`: 二维码过期，需从 Step 1 重来。

---

## 4. 基础消息收发 (Messaging)

### 4.1 接收消息：长轮询 (getupdates)
- **Endpoint**: `POST /ilink/bot/getupdates`
- **Body**:
```json
{
  "get_updates_buf": "", // 首次为空，后续使用返回的游标
  "base_info": { "channel_version": "2.1.3" }
}
```
- **关键点**：服务端会 Hold 住请求约 35 秒。若返回空列表但 `ret=0`，属于正常超时，应立即发起下一次请求。

---

## 5. 多媒体二进制协议详解 (Media Binary Protocol)

对于图片、音视频和文件，微信要求将其加密上传到腾讯 CDN，然后在 `sendmessage` 中引用该 CDN 资源。

### 5.1 核心加密要求
所有上传到 CDN 的二进制流必须使用 **AES-128-ECB** 模式加密。
- **密钥 (AesKey)**：随机生成的 16 字节原始数据。
- **填充 (Padding)**：标准 PKCS7 填充。

### 5.2 CDN 上传全流程

1. **预热**：调用 `POST /ilink/bot/getuploadurl`。需提交：
    - `rawsize`: 原文件大小（字节）。
    - `rawfilemd5`: 原文件 MD5（十六进制字符串）。
    - `filesize`: 加密后的密文大小（包含 Padding）。
2. **执行上传**：
    - 使用 `POST` 方法将加密后的二进制流发送到返回的 `upload_full_url`。
    - **Header**: `Content-Type: application/octet-stream`。
3. **获取凭证**：
    - 成功后，CDN 响应头会包含 `x-encrypted-param`。
    - 该字符串即为发送消息时所需的 `encrypt_query_param`。

### 5.3 多媒体类型 (MessageItem) 结构

在 `sendmessage` 的 `item_list` 中，不同媒体类型的结构如下：

#### A. 图片 (IMAGE) - Type: 2
```json
{
  "type": 2,
  "image_item": {
    "media": {
      "encrypt_query_param": "<CDN返回的凭证>",
      "aes_key": "<Base64编码后的16字节密钥>"
    },
    "thumb_media": { /* 同样流程上传缩略图，可选项 */ }
  }
}
```

#### B. 视频 (VIDEO) - Type: 5
```json
{
  "type": 5,
  "video_item": {
    "media": { "encrypt_query_param": "...", "aes_key": "..." },
    "video_size": 12345, // 密文大小
    "play_length": 15000, // 时长（毫秒）
    "video_md5": "<原文件MD5>",
    "thumb_media": { /* 必须上传作为视频封面 */ }
  }
}
```

#### C. 文件 (FILE) - Type: 4
```json
{
  "type": 4,
  "file_item": {
    "media": { "encrypt_query_param": "...", "aes_key": "..." },
    "file_name": "data.pdf",
    "md5": "<原文件MD5>",
    "len": "12345" // 原文件大小字符串
  }
}
```

#### D. 语音 (VOICE) - Type: 3
```json
{
  "type": 3,
  "voice_item": {
    "media": { "encrypt_query_param": "...", "aes_key": "..." },
    "encode_type": 6,   // 编码类型: 6=SILK (建议格式), 5=AMR, 7=MP3
    "sample_rate": 24000, // 采样率，常用 24000 或 16000
    "playtime": 5000     // 时长（毫秒）
  }
}
```

---

## 6. Python 核心代码片段 (v2.1.3)

### 6.1 AES 加密工具
```python
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

def encrypt_binary(data, aes_key):
    # aes_key 为 16 字节二进制原始密钥
    cipher = AES.new(aes_key, AES.MODE_ECB)
    # PKCS7 填充后加密
    return cipher.encrypt(pad(data, AES.block_size))

def get_md5(data):
    return hashlib.md5(data).hexdigest()
```

### 6.2 综合 Bot 类
```python
import requests
import random
import base64
import time

class ILinkBot:
    def __init__(self, bot_token, base_url="https://ilinkai.weixin.qq.com"):
        self.bot_token = bot_token
        self.base_url = base_url.rstrip('/')
        self.buf = ""

    def _get_headers(self, body_payload=""):
        uin = base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {self.bot_token}",
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": "131331",
            "X-WECHAT-UIN": uin
        }

    def poll_messages(self):
        payload = {
            "get_updates_buf": self.buf,
            "base_info": {"channel_version": "2.1.3"}
        }
        res = requests.post(f"{self.base_url}/ilink/bot/getupdates", 
                            json=payload, headers=self._get_headers(), timeout=40)
        data = res.json()
        self.buf = data.get("get_updates_buf", self.buf)
        return data.get("msgs", [])

    def send_raw_message(self, to_user_id, item_list, context_token):
        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": f"bot-{int(time.time()*1000)}",
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token,
                "item_list": item_list
            },
            "base_info": {"channel_version": "2.1.3"}
        }
        res = requests.post(f"{self.base_url}/ilink/bot/sendmessage", 
                             json=payload, headers=self._get_headers())
        return res.json()

    # 快捷发送文本
    def send_text(self, to_user_id, text, context_token):
        item_list = [{"type": 1, "text_item": {"text": text}}]
        return self.send_raw_message(to_user_id, item_list, context_token)
```

---

## 7. 常见限制与风险提示

- **24 小时存活限制**：Token 有效期 24 小时，过期后必须由用户重新扫码。
- **并发控制**：`getupdates` 必须是单实例运行，重复的长轮询会导致旧连接被踢下线。
- **IDC 稳定性**：务必在您的后端实现 IDC Redirect 逻辑，否则跨机房连接可能导致消息延迟显著。

---
*文档更新于：2026-04-02 (针对 V2.1.3 多媒体增强版)*
