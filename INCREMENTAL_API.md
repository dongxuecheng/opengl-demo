# 增量渲染 API 文档

## 概述

增量渲染功能允许分段合成视频，而不是一次性传入所有素材。这使得可以：

- 实时添加新视频段落
- 在渲染过程中预览中间结果
- 更灵活地控制视频合成流程

## 核心特性

✅ **无损质量**：使用 FFmpeg concat 协议，无需重新编码  
✅ **转场顺序**：自动按照模板配置循环使用转场效果  
✅ **文件系统存储**：无需 Redis，基于 `/tmp` 的轻量级会话管理  
✅ **自动清理**：使用 FastAPI BackgroundTasks 异步清理中间文件  

## API 端点

### 1. 初始化渲染会话

**POST** `/api/render/init`

渲染首张图片（8秒静态 + 字幕）

**请求参数：**
```json
{
  "template": "classic",
  "image_path": "/app/examples/images/00001.jpg"
}
```

**响应示例：**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "segment_index": 0,
  "status": "initialized",
  "message": "初始图片段落渲染完成"
}
```

---

### 2. 追加视频段落

**POST** `/api/render/append`

追加视频段落（2秒转场 + 16秒视频）

**请求参数：**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "video_path": "/app/examples/videos/video1.mp4"
}
```

**响应示例：**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "segment_index": 1,
  "transition_used": "gridflip",
  "status": "rendering",
  "message": "视频段落追加完成"
}
```

**转场顺序规则：**

根据 `config.yaml` 中模板定义的 `transitions` 列表循环使用。例如 `classic` 模板：

```yaml
transitions:
  - "transitions/gridflip.glsl"           # 第1次 append 使用
  - "transitions/inverted-page-curl.glsl" # 第2次 append 使用
  - "transitions/mosaic.glsl"             # 第3次 append 使用
  - "transitions/perlin.glsl"             # 第4次 append 使用
  - "transitions/stereo-viewer.glsl"      # 第5次 append 使用
  # 第6次 append 回到 gridflip，循环继续...
```

---

### 3. 完成合成

**POST** `/api/render/finalize`

合并所有段落并添加 BGM

**请求参数：**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "output_filename": "my_video.mp4"  // 可选
}
```

**响应示例：**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "video_url": "http://localhost:8001/videos/final_202512051430.mp4",
  "total_segments": 3,
  "status": "completed",
  "message": "视频合成完成"
}
```

**后台清理机制：**
- 响应返回后，BackgroundTasks 自动清理中间文件
- 保留最终视频 `final_*.mp4`
- 删除段落文件 `segment_*.h264`、元数据、缓存帧

---

### 4. 查询会话状态

**GET** `/api/render/status/{session_id}`

查询渲染会话的详细状态

**响应示例：**
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "template": "classic",
  "status": "rendering",
  "total_segments": 2,
  "total_frames": 600,
  "created_at": 1701763200.0,
  "segments": [
    {
      "index": 0,
      "frames": 200,
      "type": "image",
      "source_path": "/app/examples/images/00001.jpg"
    },
    {
      "index": 1,
      "frames": 400,
      "type": "video",
      "source_path": "/app/examples/videos/video1.mp4",
      "transition_shader": "gridflip"
    }
  ]
}
```

---

## 完整使用示例

### Python 示例

```python
import requests

API_BASE = "http://localhost:8001/api"

# 1. 初始化会话
init_resp = requests.post(f"{API_BASE}/render/init", json={
    "template": "classic",
    "image_path": "/app/examples/images/00001.jpg"
})
session_id = init_resp.json()["session_id"]
print(f"会话ID: {session_id}")

# 2. 追加第一段视频
append1 = requests.post(f"{API_BASE}/render/append", json={
    "session_id": session_id,
    "video_path": "/app/examples/videos/video1.mp4"
})
print(f"转场1: {append1.json()['transition_used']}")

# 3. 追加第二段视频
append2 = requests.post(f"{API_BASE}/render/append", json={
    "session_id": session_id,
    "video_path": "/app/examples/videos/video2.mp4"
})
print(f"转场2: {append2.json()['transition_used']}")

# 4. 最终合成
finalize = requests.post(f"{API_BASE}/render/finalize", json={
    "session_id": session_id
})
video_url = finalize.json()["video_url"]
print(f"最终视频: {video_url}")
```

### cURL 示例

```bash
# 1. 初始化
SESSION_ID=$(curl -X POST http://localhost:8001/api/render/init \
  -H "Content-Type: application/json" \
  -d '{"template":"classic","image_path":"/app/examples/images/00001.jpg"}' \
  | jq -r '.session_id')

echo "会话ID: $SESSION_ID"

# 2. 追加视频1
curl -X POST http://localhost:8001/api/render/append \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"video_path\":\"/app/examples/videos/video1.mp4\"}"

# 3. 追加视频2
curl -X POST http://localhost:8001/api/render/append \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"video_path\":\"/app/examples/videos/video2.mp4\"}"

# 4. 最终合成
curl -X POST http://localhost:8001/api/render/finalize \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\"}"

# 5. 查询状态
curl http://localhost:8001/api/render/status/$SESSION_ID
```

---

## 技术实现细节

### 会话文件结构

```
/tmp/autovlog_sessions/{session_id}/
├── metadata.json           # 会话元数据
├── last_frame.png          # 最后一帧缓存（用于转场）
├── segments/
│   ├── segment_0.h264      # 图片段落
│   ├── segment_1.h264      # 视频段落1（转场+视频）
│   └── segment_2.h264      # 视频段落2（转场+视频）
└── final_*.mp4             # 最终输出（清理后保留）
```

### FFmpeg Concat 协议

```bash
# concat.txt
file 'segments/segment_0.h264'
file 'segments/segment_1.h264'
file 'segments/segment_2.h264'

# 合并命令（零编码损失）
ffmpeg -f concat -safe 0 -i concat.txt -c:v copy output.mp4
```

关键参数：
- `-c:v copy`: 直接复制视频流，不重新编码
- `-f concat`: 使用 concat 协议（demuxer 级别）
- 优势：极快（仅 mux 操作）、无质量损失

### 转场索引管理

```python
# 存储在 metadata.json
{
  "current_transition_index": 2  // 下次使用索引3
}

# 获取转场（自动循环）
transition_index = metadata.current_transition_index  # 当前: 2
next_index = (transition_index + 1) % len(transitions)  # 下次: 3

# 如果有5个转场，索引序列: 0 → 1 → 2 → 3 → 4 → 0 → 1 ...
```

---

## 与原有 API 对比

| 特性 | `/api/render` (原有) | `/api/render/init|append|finalize` (增量) |
|------|---------------------|------------------------------------------|
| 使用场景 | 一次性渲染 | 分段渲染 |
| 请求次数 | 1次 | N+2次（init + N×append + finalize） |
| 灵活性 | ❌ 低 | ✅ 高 |
| 实时添加 | ❌ 不支持 | ✅ 支持 |
| 转场控制 | 固定顺序 | 配置顺序循环 |
| 会话管理 | 无 | 文件系统 |
| 清理机制 | 无 | BackgroundTasks |

---

## 运行测试

```bash
# 启动服务
docker-compose up -d

# 运行测试脚本
python test_incremental.py
```

测试脚本验证：
- ✅ 初始化 → 追加 → 追加 → 合成完整流程
- ✅ 转场顺序是否正确循环
- ✅ 会话状态查询
- ✅ 404错误处理

---

## 故障排查

### 问题1：会话不存在 (404)

**原因：** 会话ID无效或已被清理

**解决：** 确保使用 `/render/init` 返回的正确 `session_id`

### 问题2：视频文件不存在

**原因：** 路径错误或文件未挂载到容器

**解决：** 检查 `docker-compose.yml` 的 volume 映射

### 问题3：转场效果异常

**原因：** GLSL shader 文件缺失

**解决：** 确保 `transitions/*.glsl` 文件存在

---

## 性能指标

| 操作 | 平均耗时 |
|------|---------|
| init (图片) | ~3-5秒 |
| append (视频) | ~8-12秒 |
| finalize (BGM) | ~2-4秒 |
| 总流程 (1图+2视频) | ~15-25秒 |

*测试环境：NVIDIA RTX 3090, 1080p@25fps*

---

## 后续优化方向

1. **预览功能**：生成低分辨率预览
2. **WebSocket 进度**：实时推送渲染进度
3. **会话过期**：定时清理超过24小时的会话
4. **并发限制**：限制同时渲染的会话数量
5. **缓存优化**：复用已渲染的段落

---

## 许可证

MIT License
