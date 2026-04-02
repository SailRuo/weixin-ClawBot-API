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
    3. **`scaned_but_redirect` (重要)**：此时返回体包含 `redirect_host`，必须将后续请求重定向到此域名。
    4. `confirmed`: 确认登录，返回 `bot_token`。

---

## 4. 基础消息收发 (Messaging)

### 4.1 接收消息：长轮询 (getupdates)
- **Endpoint**: `POST /ilink/bot/getupdates`
- **Body**: `{"get_updates_buf": "", "base_info": {"channel_version": "2.1.3"}}`
- **关键点**：由 `get_updates_buf` 实现游标同步，空字符串表示首次同步。

---

## 5. 多媒体二进制协议详解 (Media Binary Protocol)

对于图片、音视频和文件，微信要求将其加密上传到腾讯 CDN，然后在 `sendmessage` 中引用该 CDN 资源。

### 5.1 核心加密要求
所有上传到 CDN 的二进制流必须使用 **AES-128-ECB** 模式加密。密钥为随机生成的 16 字节原始数据。

### 5.2 CDN 上传全流程
1. **预热**：调用 `POST /ilink/bot/getuploadurl`。
2. **执行上传**：使用 `POST` 方法将加密后的二进制流发送到 `upload_full_url`。
3. **获取凭证**：成功后的 CDN 响应头会包含 `x-encrypted-param`。

### 5.3 多媒体类型 (MessageItem) 结构模版

在 `item_list` 中，不同类型的媒体资源需要填充对应的结构体。

#### 1. 图片 (Type 2)
*   **下行接收**：包含 `image_item`。解密密钥优先从 `aeskey` (Hex) 获取，其次由 `media.aes_key` (Base64) 获取。
*   **上行发送**：需提供 `media` 引用。建议同时提供 `thumb_media`（缩略图）以提升端侧加载体验。

#### 2. 语音 (Type 3)
*   **下行接收**：包含 `voice_item`。自动转换结果在 `text` 字段中。
*   **上行发送 (必填项)**：
    *   `media`: 指向上传好的 SILK 文件。
    *   `encode_type`: 必须设为 `6` (代表 SILK 编码)。

#### 3. 文件 (Type 4)
*   **下行接收**：包含 `file_item`。文件名位于 `file_name`。
*   **上行发送 (必填项)**：
    *   `media`: 文件流引用。
    *   `file_name`: 必须提供文件名（含后缀），否则用户端无法正确打开。

#### 4. 视频 (Type 5)
*   **下行接收**：包含 `video_item`。封面由 `thumb_media` 提供。
*   **上行发送 (必填项)**：
    *   `media`: 视频流引用。
    *   `thumb_media`: **强制要求** 提供封面图，否则视频消息在手机端无法正常预览。
    *   `play_length`: **强制要求** 提供视频总时长（单位：毫秒）。

---

## 6. 指令系统与逻辑路由 (Command System)

iLink 协议本身是纯净的消息通道，**不提供原生的 UI 菜单 (Menu)**。所有的指令（如 `/help`, `/start`）均需在您的智能体逻辑层（应用层）自行实现。

### 6.1 指令识别原理 (Slash Commands)
在解析 `getupdates` 返回的 `item_list` 时，通过字符串匹配检测文本：
```python
def is_command(text):
    return text.strip().startswith('/')
```

### 6.2 路由分发建议
1. **静态指令**：如 `/help` 返回预设的帮助文档。
2. **状态指令**：如 `/time` 计算当前会话剩余存活时长。
3. **拦截机制**：一旦匹配到指令，应用应直接返回回复，并结束当前消息的处理流程，**不要将其发给 AI 接口**。

---

## 7. Python 核心代码片段 (v2.1.3)

### 7.1 AES 加密工具
```python
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

def encrypt_binary(data, aes_key):
    cipher = AES.new(aes_key, AES.MODE_ECB)
    return cipher.encrypt(pad(data, AES.block_size))
```

### 7.2 综合集成示例 (含指令路由)
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

    def _get_headers(self):
        uin = base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {self.bot_token}",
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": "131331",
            "X-WECHAT-UIN": uin
        }

    # 核心路由逻辑：在此定义指令
    def handle_command(self, to_id, text, ctx_token):
        cmd = text.strip().split(' ')[0].lower()
        if cmd == "/help":
            self.send_text(to_id, "🤖 指令列表：\n/help - 查看此帮助\n/time - 查看当前时间", ctx_token)
            return True
        elif cmd == "/time":
            curr_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.send_text(to_id, f"📅 当前时间：{curr_time}", ctx_token)
            return True
        return False

    def start_loop(self, on_message_cb):
        while True:
            try:
                payload = {"get_updates_buf": self.buf, "base_info": {"channel_version": "2.1.3"}}
                res = requests.post(f"{self.base_url}/ilink/bot/getupdates", 
                                    json=payload, headers=self._get_headers(), timeout=40)
                data = res.json()
                self.buf = data.get("get_updates_buf", self.buf)
                
                for msg in data.get("msgs", []):
                    if msg.get("message_type") != 1: continue
                    text = msg["item_list"][0].get("text_item", {}).get("text", "")
                    
                    # 1. 优先尝试指令路由
                    if text.startswith("/") and self.handle_command(msg["from_user_id"], text, msg["context_token"]):
                        continue
                        
                    # 2. 如果不是指令，则回调业务逻辑 (AI 处理等)
                    on_message_cb(msg)
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(1)

    def send_text(self, to_user_id, text, context_token):
        payload = {
            "msg": {
                "from_user_id": "", "to_user_id": to_user_id,
                "client_id": f"bot-{int(time.time()*1000)}",
                "message_type": 2, "message_state": 2,
                "context_token": context_token,
                "item_list": [{"type": 1, "text_item": {"text": text}}]
            },
            "base_info": {"channel_version": "2.1.3"}
        }
        return requests.post(f"{self.base_url}/ilink/bot/sendmessage", json=payload, headers=self._get_headers()).json()
```

---
*文档更新于：2026-04-02 (针对 V2.1.3 指令路由增强版)*
