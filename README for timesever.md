# ESP32 电费播报器 - 部署说明

## 时间服务器部署

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务器

```bash
python time_server.py
```

服务器将在 `http://0.0.0.0:5001` 启动

### 3. 测试接口

访问：`http://127.0.0.1:5001/api/time`

返回示例：
```json
{
  "success": true,
  "timestamp": 1709971200,
  "datetime": "2026-03-09 18:00:00",
  "timezone": "Asia/Shanghai"
}
```

### 4. 后台运行（Linux）

使用 nohup：
```bash
nohup python time_server.py > time_server.log 2>&1 &
```

或使用 systemd（推荐）：

创建文件 `/etc/systemd/system/time-server.service`：
```ini
[Unit]
Description=Time Server
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/your/project
ExecStart=/usr/bin/python3 time_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl start time-server
sudo systemctl enable time-server
sudo systemctl status time-server
```

## ESP32 配置

修改 `ESP32_Electric_TTS.ino` 中的配置：

```cpp
// 时间服务器接口
const char* TIME_API = "http://127.0.0.1:5001/api/time";
```

## 功能说明

- ESP32 通过 HTTP 请求从服务器获取北京时间
- 每 30 分钟自动重新同步时间
- 避免了 NTP 协议的复杂性和不稳定性
- 服务器时间准确可靠
