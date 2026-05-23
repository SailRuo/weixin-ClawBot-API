# iLink Bot API MVP 验证系统

完整的微信 iLink 协议接口验证系统，从登录到消息收发。

## 功能特性

### 🔐 登录流程
- 获取登录二维码
- 轮询扫码状态
- 自动处理登录确认

### 💬 消息交互
- 发送文本消息
- 接收消息（长轮询）
- 正在输入状态
- 获取用户配置

### 🔔 通知接口
- 通知开始接收消息
- 通知停止接收消息

### 📁 文件上传
- 获取上传 URL
- 支持多种媒体类型

### ⚙️ 系统管理
- 实时状态监控
- 操作日志记录
- 消息历史查看

## 快速开始

### 启动服务

```bash
cd ilink-mvp
service.bat
```

脚本会自动：
- 检查 Python 环境
- 解除端口 5000 占用
- 安装依赖
- 启动服务

服务将在 `http://localhost:5000` 启动。

**停止服务**: 按 Ctrl+C

### 手动启动（备选）

```bash
cd ilink-mvp
pip install -r requirements.txt
python app.py
```

## 使用流程

### 步骤 1: 登录
1. 点击"获取二维码"按钮
2. 使用微信扫描显示的二维码
3. 点击"开始轮询"监听登录状态
4. 登录成功后会自动显示 Bot ID 和 User ID

### 步骤 2: 接收消息
1. 点击"开始自动轮询"开始接收消息
2. 接收到的消息会显示在消息列表中
3. 从消息中复制 `from_user_id` 和 `context_token`

### 步骤 3: 发送消息
1. 在"接收用户 ID"中填入 `from_user_id`
2. 在"Context Token"中填入 `context_token`
3. 输入消息内容
4. 点击"发送消息"

### 步骤 4: 测试其他接口
- **获取配置**: 点击获取用户配置和 typing_ticket
- **正在输入**: 发送正在输入状态
- **通知接口**: 测试开始/停止接收消息通知
- **文件上传**: 获取文件上传 URL

## API 接口

### 登录相关
- `POST /api/get_qrcode` - 获取登录二维码
- `POST /api/poll_status` - 轮询登录状态

### 消息相关
- `POST /api/get_config` - 获取用户配置
- `POST /api/send_typing` - 发送输入状态
- `POST /api/send_message` - 发送消息
- `POST /api/get_updates` - 获取消息更新

### 通知相关
- `POST /api/notify_start` - 通知开始接收
- `POST /api/notify_stop` - 通知停止接收

### 文件相关
- `POST /api/get_upload_url` - 获取上传 URL

### 状态相关
- `GET /api/state` - 获取系统状态
- `GET /api/messages` - 获取消息历史
- `POST /api/clear_messages` - 清空消息
- `POST /api/start_polling` - 开始后台轮询
- `POST /api/stop_polling` - 停止后台轮询

## 技术栈

- **后端**: Python Flask
- **前端**: 原生 HTML/CSS/JavaScript
- **通信**: REST API + WebSocket (可选)
- **样式**: CSS Grid + Flexbox

## 注意事项

1. **登录有效期**: bot_token 有效期一般为 24 小时，过期后需重新登录
2. **Context Token**: 发送消息时必须携带正确的 context_token，否则消息会被丢弃
3. **长轮询超时**: getupdates 接口最长保持 35 秒，建议设置合适的超时时间
4. **X-WECHAT-UIN**: 每次请求必须重新生成，不能复用

## 故障排查

### 无法获取二维码
- 检查网络连接
- 确认 ilinkai.weixin.qq.com 可访问

### 登录失败
- 确认二维码未过期
- 检查微信账号状态

### 消息发送失败
- 确认 context_token 正确
- 确认已调用 getconfig 获取 typing_ticket
- 检查 from_user_id 是否为空字符串

## 许可证

MIT License
