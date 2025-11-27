# 🌐 HTTP API 服务文档

## 概述

GPU 加速视频渲染的 HTTP API 服务，支持异步渲染任务管理。

**特性：**
- ✅ 图片 + 视频混合渲染
- ✅ 图片持续 8 秒（独立边框）
- ✅ 每个视频持续 16 秒（统一边框）
- ✅ 异步任务处理
- ✅ RESTful API 设计
- ✅ 任务状态查询

## 快速开始

### 1. 启动服务

#### 使用 Docker（推荐）
```bash
# 构建镜像
docker build -t video-renderer-api .

# 启动服务
docker run --rm -it \
  --gpus all \
  --device /dev/dri:/dev/dri \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -v $(pwd):/app \
  -p 8000:8000 \
  video-renderer-api
```

#### 直接运行
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python api_server.py
# 或
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 访问 API 文档

服务启动后，访问自动生成的 API 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API 端点

### 1. 健康检查

```bash
GET /health
```

**响应示例：**
```json
{
  "status": "healthy",
  "timestamp": "2025-11-27T10:30:00"
}
```

### 2. 列出可用模板

```bash
GET /api/templates
```

**响应示例：**
```json
{
  "templates": [
    {
      "name": "classic",
      "display_name": "Classic",
      "description": "经典风格 - 适合正式场合"
    },
    {
      "name": "modern",
      "display_name": "Modern",
      "description": "现代风格 - 适合年轻化场景"
    },
    {
      "name": "elegant",
      "display_name": "Elegant",
      "description": "优雅风格 - 适合艺术展示"
    }
  ],
  "count": 3
}
```

### 3. 创建渲染任务

```bash
POST /api/render
Content-Type: application/json
```

**请求体：**
```json
{
  "template": "classic",
  "image_path": "/app/examples/cover.jpg",
  "video_paths": [
    "/app/examples/v1.mp4",
    "/app/examples/v2.mp4",
    "/app/examples/v3.mp4"
  ]
}
```

**参数说明：**
- `template`: 模板名称（classic/modern/elegant）
- `image_path`: 图片路径（本机绝对路径）
- `video_paths`: 视频路径列表（1-5个本机绝对路径）

**响应示例：**
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "video_url": null,
  "message": "任务已创建，正在队列中等待处理",
  "created_at": "2025-11-27T10:30:00"
}
```

### 4. 查询任务状态

```bash
GET /api/status/{task_id}
```

**响应示例（处理中）：**
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "processing",
  "video_url": null,
  "error": null,
  "progress": 0.45,
  "created_at": "2025-11-27T10:30:00",
  "completed_at": null
}
```

**响应示例（完成）：**
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "video_url": "http://localhost:8000/videos/a1b2c3d4-e5f6-7890-abcd-ef1234567890.mp4",
  "error": null,
  "progress": 1.0,
  "created_at": "2025-11-27T10:30:00",
  "completed_at": "2025-11-27T10:32:15"
}
```

**状态说明：**
- `pending`: 等待处理
- `processing`: 处理中
- `completed`: 已完成
- `failed`: 失败

### 5. 下载视频

```bash
GET /api/video/{task_id}
```

直接下载渲染完成的视频文件。

### 6. 列出所有任务

```bash
GET /api/tasks?status=completed
```

**参数：**
- `status`: 可选，筛选状态（pending/processing/completed/failed）

**响应示例：**
```json
{
  "tasks": [
    {
      "task_id": "...",
      "status": "completed",
      "created_at": "...",
      "completed_at": "..."
    }
  ],
  "count": 10
}
```

### 7. 删除任务

```bash
DELETE /api/task/{task_id}
```

删除任务记录和关联的视频文件。

**响应示例：**
```json
{
  "message": "任务已删除",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

## 使用示例

### Python 客户端

```python
import requests
import time

# API 地址
API_BASE = "http://localhost:8000"

# 1. 创建渲染任务
response = requests.post(f"{API_BASE}/api/render", json={
    "template": "classic",
    "image_path": "/app/examples/cover.jpg",
    "video_paths": [
        "/app/examples/v1.mp4",
        "/app/examples/v2.mp4",
        "/app/examples/v3.mp4"
    ]
})

task = response.json()
task_id = task["task_id"]
print(f"任务已创建: {task_id}")

# 2. 轮询任务状态
while True:
    response = requests.get(f"{API_BASE}/api/status/{task_id}")
    status = response.json()
    
    print(f"状态: {status['status']} - 进度: {status['progress']*100:.1f}%")
    
    if status["status"] == "completed":
        print(f"✅ 完成！视频地址: {status['video_url']}")
        break
    elif status["status"] == "failed":
        print(f"❌ 失败: {status['error']}")
        break
    
    time.sleep(5)

# 3. 下载视频
video_url = status["video_url"]
print(f"下载视频: {video_url}")
```

### cURL 示例

```bash
# 1. 创建任务
curl -X POST http://localhost:8000/api/render \
  -H "Content-Type: application/json" \
  -d '{
    "template": "classic",
    "image_path": "/app/examples/cover.jpg",
    "video_paths": [
      "/app/examples/v1.mp4",
      "/app/examples/v2.mp4"
    ]
  }'

# 2. 查询状态
curl http://localhost:8000/api/status/{task_id}

# 3. 下载视频
curl -O http://localhost:8000/videos/{task_id}.mp4
```

### JavaScript/Fetch 示例

```javascript
// 1. 创建任务
const response = await fetch('http://localhost:8000/api/render', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    template: 'modern',
    image_path: '/app/examples/cover.jpg',
    video_paths: [
      '/app/examples/v1.mp4',
      '/app/examples/v2.mp4'
    ]
  })
});

const task = await response.json();
const taskId = task.task_id;

// 2. 轮询状态
async function checkStatus(taskId) {
  const response = await fetch(`http://localhost:8000/api/status/${taskId}`);
  const status = await response.json();
  
  console.log(`状态: ${status.status} - 进度: ${status.progress * 100}%`);
  
  if (status.status === 'completed') {
    console.log(`视频地址: ${status.video_url}`);
    return status;
  } else if (status.status === 'failed') {
    throw new Error(status.error);
  }
  
  // 继续轮询
  await new Promise(resolve => setTimeout(resolve, 5000));
  return checkStatus(taskId);
}

await checkStatus(taskId);
```

## 边框配置

### 目录结构

```
templates/
├── classic/
│   ├── config.yaml
│   ├── border.png          # 图片边框
│   ├── border_video.png    # 视频边框（可选）
│   └── bgm.mp3
```

### 边框说明

1. **图片边框** (`border.png`)
   - 用于封面图片（第一帧，8秒）
   - 尺寸: 1920x1080
   - 格式: PNG（透明通道）

2. **视频边框** (`border_video.png`)
   - 用于所有视频片段（16秒/段）
   - 尺寸: 1920x1080
   - 格式: PNG（透明通道）
   - **如果不存在，将使用 `border.png`**

### 创建不同边框

```bash
# 为每个模板准备两套边框
cd templates/classic
cp border.png border_video.png

# 然后使用图像编辑工具编辑 border_video.png
# 使其与 border.png 有所区别
```

## 渲染时长计算

- **图片**: 8 秒（200 帧 @ 25 FPS）
- **每个视频**: 16 秒（400 帧 @ 25 FPS）
- **转场**: 2 秒（50 帧 @ 25 FPS）

**示例：**
- 1 图片 + 1 视频 = 8 + 16 = 24 秒
- 1 图片 + 3 视频 = 8 + 16×3 + 2×2 = 56 秒
- 1 图片 + 5 视频 = 8 + 16×5 + 2×4 = 96 秒

## 性能说明

- **GPU 加速**: 使用 NVIDIA NVENC 硬件编码
- **并发处理**: 支持后台异步任务
- **渲染速度**: ~3-4x 实时速度（依赖 GPU 性能）

## 错误处理

### 常见错误

1. **文件不存在**
   ```json
   {
     "detail": "图片文件不存在: /path/to/image.jpg"
   }
   ```

2. **模板不存在**
   ```json
   {
     "detail": "模板配置文件不存在: templates/xxx/config.yaml"
   }
   ```

3. **渲染失败**
   ```json
   {
     "task_id": "...",
     "status": "failed",
     "error": "GPU 初始化失败"
   }
   ```

## 日志

服务日志输出到标准输出，包含：
- 任务创建/完成/失败
- 渲染进度
- 错误堆栈信息

```bash
# 查看 Docker 日志
docker logs -f <container_id>
```

## 生产部署建议

1. **反向代理**: 使用 Nginx 作为反向代理
2. **HTTPS**: 配置 SSL 证书
3. **持久化存储**: 挂载 `outputs/` 目录
4. **任务队列**: 使用 Celery + Redis 处理高并发
5. **监控**: 集成 Prometheus + Grafana
6. **限流**: 添加 API 访问频率限制

## 相关文档

- [TEMPLATE_GUIDE.md](./TEMPLATE_GUIDE.md) - 模板开发指南
- [README.md](./README.md) - 项目说明
