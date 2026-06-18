# WeChat iLink Bot API 接口集成文档 (Flask MVP 版本)

本接口文档详细阐述了 `ilink-mvp/app.py` 中实现的全部后台 API。本服务基于 **Flask** 框架开发，采用 **iLink (WeChat Bot)** 协议，并集成了 **AES-128-ECB** 动态加解密、微信 CDN 降级容灾、以及零磁盘流式文件代理等高级机制。

---

## 1. 基础认证与网关请求头

在所有向下游微信官方 API 发起请求的操作中，服务均会自动构建兼容微信官方的标准请求头。若你需要在其他语言或系统中直接调用微信底层 API，请严格遵循以下请求头格式。

### 标准网关请求头 (WeChat iLink API Headers)
| 请求头键 (Header Key) | 说明 | 示例值 / 计算逻辑 |
| :--- | :--- | :--- |
| `Content-Type` | 载荷编码声明 | `application/json` |
| `AuthorizationType` | 授权机制声明 | `ilink_bot_token` |
| `iLink-App-Id` | 微信授权 AppID | `"bot"` |
| `iLink-App-ClientVersion` | 客户端数字版本号 | `"132100"` *(对应 2.4.3 版本，以 0x00MMNNPP 编码)* |
| `X-WECHAT-UIN` | 动态终端唯一标识码 | 随机生成的 `uint32` 的 Base64 编码 |
| `Authorization` | 微信会话口令 | `Bearer <bot_token>` *(仅在已登录且需要授权时携带)* |

> [!NOTE]
> `X-WECHAT-UIN` 是由客户端动态计算的随机数生成的 Base64。计算方式为：先生成一个随机的 `uint32` 整数，将其转换为十进制字符串，然后再对该字符串进行 `Base64` 编码。例如：随机数 `123456789` -> 字符串 `"123456789"` -> Base64 `"MTIzNDU2Nzg5"`。

---

## 2. 核心 API 接口详述

### 2.1 获取登录二维码
* **接口路径**：`POST /api/get_qrcode`
* **接口描述**：初始化登录通道，向微信服务器申请三方微信机器人授权二维码。
* **请求体**：无
* **成功响应 (JSON)**：
  ```json
  {
    "success": true,
    "qrcode": "uuid_string_from_weixin",
    "qrcode_img_content": "https://liteapp.weixin.qq.com/q/xxx",
    "login_status": "waiting"
  }
  ```

---

### 2.2 轮询扫码登录状态
* **接口路径**：`POST /api/poll_status`
* **接口描述**：在获取二维码后进行循环请求，监听用户手机端扫码与确认状态。
* **请求体**：无
* **成功响应 (JSON)**：
  * **状态 1：等待扫码**
    ```json
    { "success": true, "status": "wait", "login_status": "wait" }
    ```
  * **状态 2：已扫码未确认**
    ```json
    { "success": true, "status": "scaned", "login_status": "scaned" }
    ```
  * **状态 3：扫码成功并确认**
    ```json
    {
      "success": true,
      "status": "confirmed",
      "login_status": "confirmed",
      "bot_token": "bearer_token_string",
      "ilink_bot_id": "bot_id_string",
      "ilink_user_id": "user_id_string",
      "base_url": "https://ilinkai.weixin.qq.com"
    }
    ```
  * **状态 4：二维码已过期**
    ```json
    { "success": true, "status": "expired", "login_status": "expired" }
    ```

---

### 2.3 恢复/直接使用已有 Token 登录
* **接口路径**：`POST /api/login_with_token`
* **接口描述**：直接传递已有凭证实现快速会话重连，避免频繁扫码。
* **请求载荷 (JSON)**：
  ```json
  {
    "bot_token": "Bearer Token 字符串",
    "ilink_bot_id": "Bot ID",
    "ilink_user_id": "User ID",
    "base_url": "微信网关 URL (可选)"
  }
  ```
* **成功响应 (JSON)**：
  ```json
  { "success": true }
  ```

---

### 2.4 退出登录
* **接口路径**：`POST /api/logout`
* **接口描述**：注销当前账号，清除后端会话状态、待发缓存与长轮询缓存。
* **请求体**：无
* **成功响应 (JSON)**：
  ```json
  { "success": true }
  ```

---

### 2.5 获取智能体配置
* **接口路径**：`POST /api/get_config`
* **接口描述**：向微信服务器请求当前机器人的配置，最主要用于取得输入状态的 `typing_ticket`。
* **请求载荷 (JSON)**：
  ```json
  {
    "ilink_user_id": "用户加密 ID",
    "context_token": "当前会话上下文 Token"
  }
  ```
* **成功响应 (JSON)**：
  ```json
  {
    "success": true,
    "typing_ticket": "用于输入状态指示的 ticket base64 串"
  }
  ```

---

### 2.6 发送“正在输入”状态指示
* **接口路径**：`POST /api/send_typing`
* **接口描述**：向指定微信用户显示“对方正在输入...”的系统提示。
* **请求载荷 (JSON)**：
  ```json
  {
    "ilink_user_id": "用户加密 ID",
    "status": 1, 
    "typing_ticket": "从 get_config 取得的 ticket (可选)"
  }
  ```
  > [!NOTE]
  > `status` 参数：`1` 代表开启“正在输入”显示，`2` 代表主动取消显示。

---

### 2.7 发送文本或富媒体消息
* **接口路径**：`POST /api/send_message`
* **接口描述**：在当前会话的上下文中向下游微信客户端投递消息（可以是文本，也可以是由 `upload_media` 接口构建好的富媒体项）。
* **请求载荷 (JSON)**：
  ```json
  {
    "to_user_id": "用户加密 ID (必填)",
    "context_token": "微信会话上下文口令 (必填)",
    "text": "纯文本内容 (只有发送纯文本且未提供 item_list 时生效)",
    "item_list": [
      {
        "type": 2, 
        "image_item": {
          "media": {
            "encrypt_query_param": "下载加密参数",
            "aes_key": "Base64 编码的 AES 密钥",
            "encrypt_type": 1
          },
          "mid_size": 24890
        }
      }
    ]
  }
  ```
  > [!IMPORTANT]
  > `item_list` 内单项的 `type` 为**微信官方消息项类型 (MessageItemType)**，定义如下：
  > * `1`：TEXT (文本)
  > * `2`：IMAGE (图片)
  > * `3`：VOICE (语音) —— *注：微信目前对 Bot 上行发送原生语音气泡有限制，建议转文件发送*
  > * `4`：FILE (文件附件)
  > * `5`：VIDEO (视频)
* **成功响应 (JSON)**：
  ```json
  { "success": true }
  ```

---

### 2.8 加密上传文件/图片至微信 CDN
* **接口路径**：`POST /api/upload_media`
* **接口描述**：上传本地媒体文件，进行 AES 加密、向微信申请上传预签名 URL、上传至 CDN 并输出微信标准的富媒体消息体（供 `send_message` 接口使用）。
* **请求类型**：`multipart/form-data`
* **表单参数**：
  * `file`：待上传的文件 (二进制文件流)
  * `media_type`：**上传媒体类型 (UploadMediaType)**。定义为：`1`=IMAGE，`2`=VIDEO，`3`=FILE，`4`=VOICE
  * `to_user_id`：微信接收用户的加密 ID
* **后端核心加解密与对齐实现逻辑**：
  1. **AES 加密**：生成 16 字节随机密钥，使用 **AES-128-ECB**（支持 PKCS7 填充）将明文加密。
  2. **免缩略图对齐**：统一向微信接口传递 `no_need_thumb: true`，消除微信服务器为图片或视频索要缩略图而导致的 CDN 处理挂起。
  3. **地址拼接降级**：若微信接口未返回 `upload_full_url`，后端会自动提取 `upload_param` 并配合微信 C2C 默认 CDN 服务器 (`https://novac2c.cdn.weixin.qq.com/c2c`) 动态拼接出上传 URL。
  4. **两套密钥编码标准完美对齐**：
     * **图片类 (`media_type = 1`)**：生成的 AES 密钥在消息体中编码为：`base64(raw_16_bytes)`。
     * **非图片类 (`media_type = 2/3/4`)**：密钥均统一编码为 `base64(hex_string_of_16_bytes)`。
* **成功响应 (JSON)**：
  ```json
  {
    "success": true,
    "filekey": "随机生成的 16 字节 filekey 十六进制表示",
    "item": {
      "type": 2, 
      "image_item": {
        "media": {
          "encrypt_query_param": "CDN 返回的下载加密查询参数",
          "aes_key": "经过双标对齐转换 of Base64 AES 密钥",
          "encrypt_type": 1
        },
        "mid_size": 28456
      }
    }
  }
  ```

---

### 2.9 动态流式解密与媒体下载代理
* **接口路径**：`GET /api/media`
* **接口描述**：由于前端 `<img>` 标签等无法携带认证 Header，微信 CDN 图片也是强加密状态，此接口专门充当动态下载并流式解密的中转代理。
* **查询参数 (Query Params)**：
  * `param`：微信 CDN 消息解密下载参数（即 `encrypt_query_param`）
  * `url`：微信服务器返回 of 直连 `full_url` 链接 (可选)
  * `key`：**解密 Key**（支持微信发过来的 Hex 字符串密钥，也支持 Base64 格式密钥）
  * `name`：**原始文件名** (提供后，会在下载时自动作为原文件名，可选)
* **成功响应 (Binary Stream)**：解密后的明文多媒体或原始文件二进制字节流。

---

### 2.10 获取系统状态
* **接口路径**：`GET /api/state`
* **接口描述**：实时获取当前系统的会话生命周期参数和运行状态。
* **请求体**：无
* **成功响应 (JSON)**：
  ```json
  {
    "login_status": "confirmed",
    "bot_token": "包含在 Bearer 中的 token 串",
    "ilink_bot_id": "当前机器人唯一ID",
    "ilink_user_id": "当前机器人用户ID",
    "base_url": "当前使用的微信接入网关",
    "message_count": 24,
    "typing_ticket": "当前输入 Ticket 缓存值"
  }
  ```

---

### 2.11 获取新接收消息列表 (轮询终点)
* **接口路径**：`GET /api/messages`
* **接口描述**：前端轮询拉取当前后台长连接轮询线程（`poll_messages`）收录的全部微信用户发来的消息。
* **查询参数**：
  * `since`：当前已在前端展示的消息数量 (偏移量偏移起步索引，例如 `?since=5`)
* **成功响应 (JSON)**：
  ```json
  {
    "success": true,
    "messages": [
      {
        "timestamp": 1782390124.5,
        "message": {
          "from_user_id": "发送用户的加密 ID",
          "to_user_id": "Bot 的 ID",
          "context_token": "当前消息会话的上下文 Token",
          "create_time_ms": 1782390124000,
          "item_list": [
            {
              "type": 2,
              "image_item": {
                "media": {
                  "encrypt_query_param": "微信 CDN 文件的解密下载加密参数",
                  "aes_key": "微信发来的密钥"
                }
              }
            }
          ]
        }
      }
    ],
    "total": 6
  }
  ```

---

## 3. 加解密与多媒体格式规范

### 3.1 AES-128-ECB 与 PKCS7 填充算法
微信 CDN 文件传输均采用 **AES-128-ECB** 模式加密。在 Python 中，必须将字节长度填充为 16 的倍数：

```python
# PKCS7 填充
def pkcs7_pad(data: bytes) -> bytes:
    pad_len = 16 - len(data) % 16
    return data + bytes([pad_len] * pad_len)

# PKCS7 去除填充
def pkcs7_unpad(data: bytes) -> bytes:
    pad_len = data[-1]
    return data[:-pad_len]
```

### 3.2 密钥编码标准对齐 (关键)
* **图片类 (`media_type = 1`)**：在发送消息的 JSON 中，`aes_key` 应编码为 Base64 后的 **原始 16 字节密钥**：
  `base64.b64encode(raw_aes_bytes).decode()`
* **非图片类 (`media_type = 2, 3, 4`)**：在发送消息的 JSON 中，`aes_key` 应编码为 Base64 后的 **十六进制表示字符串 (32个字符)**：
  `base64.b64encode(raw_aes_bytes.hex().encode()).decode()`

### 3.3 原生语音 (SILK 格式) 时长解析
发送原生语音包时，微信服务器要求在 `voice_item` 中填充 `playtime`（毫秒）。
微信原生的 `.silk` 语音包每帧代表 **20 毫秒** 的音频，且每帧前均有 2 字节小端序的帧大小声明。可通过以下算法计算播放时长：

```python
def get_silk_duration(data: bytes) -> int:
    if data.startswith(b"\x02#!SILK_V3"):
        idx = 10
    elif data.startswith(b"#!SILK_V3"):
        idx = 9
    else:
        idx = data.find(b"#!SILK_V3")
        if idx != -1:
            idx += 9
        else:
            idx = 0
            
    frames = 0
    while idx < len(data):
        if idx + 2 > len(data):
            break
        size = int.from_bytes(data[idx:idx+2], byteorder="little")
        if size <= 0 or size > 1000 or idx + 2 + size > len(data):
            break
        idx += 2 + size
        frames += 1
    return frames * 20
```
