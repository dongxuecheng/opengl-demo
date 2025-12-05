# AutoVlog

**AutoVlog** 是一个高性能的自动化 Vlog 生成引擎。它能够将图片、视频片段和字幕通过 GPU 加速的转场效果无缝拼接，自动生成精美的 Vlog 视频。

核心驱动：**ModernGL** (渲染) + **NVENC** (硬件编码) + **FastAPI** (服务接口)。

## ✨ 功能特性

- 🎨 **多风格模板**: 内置 classic/modern/elegant 等多种风格，一键切换
- 🖼️ **多素材融合**: 支持图片封面与多个视频片段的混合剪辑
- 📝 **智能字幕**: 自动生成打字机风格的动态字幕，提升叙事感
- 🎬 **电影级转场**: 基于 GPU Shader 的高性能转场特效，丝滑流畅
- ⚡ **极速渲染**: 采用 NVENC 硬件编码，实现 1080P 视频的实时/超实时渲染
- 🔌 **简单接口**: 提供极简的 HTTP API，轻松集成到任何系统
- 🔄 **增量渲染** 🆕: 支持分段添加视频，无需重新编码，画质无损

## 🚀 快速开始

### 1. 启动服务

```bash
docker compose up -d
```

服务将在 `http://localhost:8001` 启动。

### 2. 调用接口

AutoVlog 提供两种渲染模式：

#### 方式一：一次性渲染（传统模式）

**接口地址**: `POST http://localhost:8001/api/render`

**请求参数**:
```json
{
  "template": "classic",
  "image_path": "/app/examples/cover.jpg",
  "video_paths": [
    "/app/examples/v1.mp4",
    "/app/examples/v2.mp4"
  ]
}
```

**响应示例** (纯文本URL):
```
http://localhost:8001/videos/202511271430.mp4
```

#### 方式二：增量渲染（新功能）🆕

适用于需要**分段添加视频**或**实时预览**的场景。

**步骤1 - 初始化会话**: `POST http://localhost:8001/api/render/init`
```json
{
  "template": "classic",
  "image_path": "/app/examples/cover.jpg"
}
```
响应：
```json
{
  "session_id": "uuid-string",
  "segment_index": 0,
  "status": "initialized"
}
```

**步骤2 - 追加视频段落**: `POST http://localhost:8001/api/render/append`
```json
{
  "session_id": "uuid-string",
  "video_path": "/app/examples/v1.mp4"
}
```
响应：
```json
{
  "session_id": "uuid-string",
  "segment_index": 1,
  "transition_used": "gridflip",
  "status": "rendering"
}
```

**步骤3 - 完成合成**: `POST http://localhost:8001/api/render/finalize`
```json
{
  "session_id": "uuid-string",
  "output_filename": "my_video.mp4"  // 可选
}
```
响应：
```json
{
  "session_id": "uuid-string",
  "video_url": "http://localhost:8001/videos/final_202512051430.mp4",
  "total_segments": 3,
  "status": "completed"
}
```

**步骤4 - 查询状态**: `GET http://localhost:8001/api/render/status/{session_id}`
```json
{
  "session_id": "uuid-string",
  "template": "classic",
  "status": "completed",
  "total_segments": 3,
  "total_frames": 1000
}
```

> **转场顺序规则**: 每次 `append` 会按照模板配置的 `transitions` 列表顺序循环使用转场效果。例如 `classic` 模板依次使用：gridflip → inverted-page-curl → mosaic → perlin → stereo-viewer → gridflip...

### 3. 使用测试脚本

**一次性渲染测试**:
```bash
python3 test.py
```

**增量渲染测试** 🆕:
```bash
python3 test_incremental.py
```

> 详细的增量渲染 API 文档请查看 [`INCREMENTAL_API.md`](./INCREMENTAL_API.md)

## ⚙️ 配置管理

所有配置统一在 `config.yaml` 文件中管理，支持热重载（需重启容器）：

### 全局渲染参数
```yaml
global:
  width: 1920              # 视频分辨率-宽度
  height: 1080             # 视频分辨率-高度
  fps: 25                  # 帧率
  image_duration: 8.0      # 图片持续时间（秒）
  video_duration: 16.0     # 每个视频持续时间（秒）
  transition_duration: 2.0 # 转场持续时间（秒）
```

### 可用模板

- `classic` - 经典风格，稳重简约，适合正式场合
- `modern` - 现代风格，时尚动感，适合年轻化场景
- `elegant` - 优雅风格，精致细腻，适合艺术展示

修改全局参数、模板配置或添加新模板，只需编辑根目录的 `config.yaml` 文件。

## 🛠️ 服务管理

```bash
# 启动服务
docker compose up -d

# 查看实时日志
docker compose logs -f

# 停止服务
docker compose stop

# 重启服务 (修改配置后执行)
docker compose restart

# 彻底移除
docker compose down
```

## 📝 视频规格

- **图片段**: 8秒，带动态字幕
- **视频段**: 每个16秒
- **分辨率**: 1920x1080 (可配置)
- **帧率**: 25 FPS (可配置)
- **编码**: H.264 (NVENC)
- **音频**: AAC 44.1kHz

## ⚠️ 注意事项

- **路径映射**: API 请求中的文件路径必须是**容器内路径**（默认为 `/app/...`）
- **格式支持**: 
  - 图片: jpg, jpeg, png, bmp
  - 视频: mp4, avi, mov, mkv
- **性能**: 渲染时间约 10-60 秒（取决于视频数量和 GPU 性能）

## 💻 环境要求

- Docker + Docker Compose
- NVIDIA GPU + 驱动
- nvidia-docker2 (NVIDIA Container Toolkit)
