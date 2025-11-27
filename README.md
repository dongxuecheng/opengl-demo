# OpenGL 视频转场渲染器

使用 ModernGL + FFmpeg + GL Transitions 创建专业视频转场效果。

## 整体架构

### 核心流程

本项目采用 **流式处理架构（Streaming Pipeline）**，实现 GPU 加速的实时视频转场渲染：

```
┌─────────────────────────────────────────────────────────────────┐
│                         主渲染循环                               │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────┐    ┌──────────────┐
│  FFmpeg 解码器   │───▶│  GPU 渲染器   │───▶│ NVENC 编码器  │
│  (subprocess)   │    │  (ModernGL)  │    │  (h264_nvenc)│
└─────────────────┘    └──────────────┘    └──────────────┘
         │                     │                    │
    逐帧读取              GLSL 转场效果          逐帧写入
    RGB24 原始帧          OpenGL 合成           H.264 视频流
    1920×1080×3                                  
```

### 三阶段处理流程

#### 1. 视频解码阶段 (VideoReader)
```python
for 每个视频文件:
    └─ FFmpeg 子进程
        ├─ setpts=PTS-STARTPTS  # 时间戳归零，防止黑屏
        ├─ scale=1920x1080      # 统一分辨率
        ├─ fps=25               # 统一帧率
        └─ 输出 RGB24 原始帧流
```

**关键特性**：
- **预加载首帧**：`preload_first_frame()` 阻塞式读取，确保首帧就绪，避免黑屏
- **EOF 处理**：视频结束后重复最后一帧，避免冻结
- **流式传输**：不预加载全部帧，内存占用低（实验证明比预加载快）

#### 2. GPU 渲染阶段 (ModernGL + GLSL)
```python
for 每个视频片段:
    ├─ A. 主体播放（150帧或200帧）
    │   └─ 单纹理渲染: tex0 → GPU → framebuffer → 编码器
    │
    └─ B. 转场效果（50帧，循环使用转场列表）
        └─ 双纹理混合: tex0 + tex1 → GLSL transition() → 编码器
            ├─ progress: 0.0 → 1.0
            └─ 调用 gl-transitions.com 的 GLSL 函数
```

**渲染优化**：
- **静态 Uniform 缓存**：纹理槽位、宽高比等一次性设置
- **最小化帧缓冲操作**：只在必要时清空 framebuffer
- **动态 Shader 编译**：转场效果切换时重新编译着色器
- **GLSL 函数去重**：Regex 检测避免重复定义 `getFromColor()` 等辅助函数

#### 3. 视频编码阶段 (NVENC)
```python
encoder.stdin.write(fbo.read(components=3))  # 逐帧写入
```

**编码参数**：
- `vcodec=h264_nvenc`：NVIDIA 硬件编码器
- `preset=p1`：最快速度（1-7级，p1最快）
- `rc=cbr`：恒定码率模式
- `rc-lookahead=0`：禁用预测，减少延迟
- `bitrate=15M`：高质量输出

### 数据流详解

```
视频 1 (v1.mp4, 8秒/200帧)
  ├─ 帧 1-150:   主体播放 (6秒) ──┐
  └─ 帧 151-200: 转场准备 (2秒)   ├─ Transition 1 (gridflip)
                                  │   进度 0% → 100%
视频 2 (v2.mp4, 8秒/200帧)      │   tex0=v1末尾, tex1=v2开头
  ├─ 帧 1-50:    转场消耗 (2秒) ─┘
  ├─ 帧 51-200:  主体播放 (6秒) ──┐
  └─ 帧 201-250: 转场准备 (2秒)   ├─ Transition 2 (inverted-page-curl)
                                  │
视频 3 (v3.mp4, 8秒/200帧)      │
  ├─ 帧 1-50:    转场消耗 (2秒) ─┘
  ├─ 帧 51-200:  主体播放 (6秒) ──┐
  ...                            │
视频 6 (v6.mp4, 8秒/200帧)      │
  ├─ 帧 1-50:    转场消耗 (2秒) ─┘
  └─ 帧 51-250:  完整播放 (8秒) ──── 无后续转场
```

**最终输出**：1200 帧 = 48 秒视频（25fps）

### 关键技术决策

#### ✅ 流式处理 vs 批量预加载
- **当前架构**：边解码边渲染边编码（13.2s 处理 48s 视频）
- **实验结果**：预加载全部帧（1275 帧，7.39GB）无性能提升，反而增加内存压力
- **结论**：流式处理是最优方案

#### ✅ Python vs C++
- **性能对比**：C++ 理论提升 10-20%（11-12秒）
- **复杂度**：需要重写 615 行代码，集成 GLEW/GLFW/FFmpeg C API
- **结论**：Python 已达到 3.6 倍实时速度，性价比最高

#### ⚡ 性能瓶颈
- **NVENC 编码器**：占用 40-45% 总耗时
- **FFmpeg 解码**：占用 30-35% 总耗时
- **GPU 渲染**：占用 20-25% 总耗时（ModernGL 已优化）

### 扩展优化方向

#### 方案 1: PyAV（推荐，低风险）
- **原理**：替换 `ffmpeg-python`，使用 C 绑定直接调用 `libavcodec`
- **预期提升**：8-12%（13.2s → 11.5-12s）
- **实现成本**：1-2 小时
- **优点**：消除 subprocess 开销，更好的内存管理

#### 方案 2: NVDEC（高级，高风险）
- **原理**：GPU 硬件解码 + CUDA-OpenGL 互操作
- **预期提升**：20-30%（13.2s → 9-10s）
- **实现成本**：1-2 天
- **缺点**：极高复杂度，需要 CUDA 编程，仅支持 NVIDIA

## 项目结构

```
opengl-demo/
├── render.py              # 主渲染脚本
├── transitions/           # 转场效果目录
│   ├── README.md         # 转场效果说明
│   ├── fade.glsl         # 淡入淡出效果
│   └── stereo-viewer.glsl # 立体查看器效果
└── examples/             # 示例视频文件
    ├── v1.mp4 - v6.mp4   # 输入视频
    └── bgm.mp3           # 背景音乐
```

## 使用方法

### 1. 下载转场效果

访问 [GL Transitions](https://gl-transitions.com/) 浏览数百种转场效果：

1. 选择喜欢的转场效果
2. 点击 "View Source" 查看源代码
3. 复制完整的 GLSL 代码
4. 保存为 `.glsl` 文件到 `transitions/` 目录

### 2. 配置转场列表

编辑 `render.py` 中的 `TRANSITION_FILES` 列表：

```python
TRANSITION_FILES = [
    "transitions/fade.glsl",
    "transitions/wipeleft.glsl",
    "transitions/circle.glsl",
    # 添加更多转场...
]
```

**转场使用规则**：
- 转场按顺序循环使用
- 如果有5个转场，6个视频，则：转场1→淡入淡出，转场2→擦除左侧...转场5→圆形，转场6→淡入淡出（循环）
- 可以重复添加同一个转场文件来增加其使用频率

### 3. 配置视频参数

```python
# 视频文件列表
INPUT_FILES = [f"examples/v{i}.mp4" for i in range(1, 7)]

# 背景音乐
BGM_FILE = "examples/bgm.mp3"

# 输出文件
OUTPUT_FINAL = "final_vlog.mp4"

# 渲染参数
WIDTH, HEIGHT = 1920, 1080  # 分辨率
FPS = 25                     # 帧率
CLIP_DURATION = 8.0         # 每个片段时长（秒）
TRANSITION_DURATION = 2.0   # 转场时长（秒）
```

### 4. 配置字幕（可选）

项目支持 **CPU 绘图 + GPU 贴图** 的字幕功能：

```python
# 字幕配置
FONT_PATH = "fonts/NotoSansSC-Bold.otf"  # 字体路径
FONT_SIZE = 72                            # 字体大小
SUBTITLE_COLOR = (255, 255, 255, 255)    # 白色文字
SUBTITLE_OUTLINE_COLOR = (0, 0, 0, 200)  # 黑色描边
SUBTITLE_OUTLINE_WIDTH = 3                # 描边宽度
```

**字幕工作原理**：
- 使用 **Pillow** 在 CPU 端绘制透明背景文字图片
- 仅在文字内容变化时重新绘制（智能缓存）
- 将文字作为 RGBA 纹理上传到 GPU
- 通过 **Alpha 混合** shader 叠加到视频帧上

**在代码中添加字幕**：

```python
# 在主循环的适当位置添加
if i == 0 and frame_idx < int(3.0 * FPS):  # 第一个视频的前3秒
    if frame_idx == 0:  # 只在第一帧渲染文字
        subtitle_data = subtitle_renderer.render_text(
            "欢迎大家收看VLOG",
            color=SUBTITLE_COLOR,
            outline_color=SUBTITLE_OUTLINE_COLOR,
            outline_width=SUBTITLE_OUTLINE_WIDTH
        )
        subtitle_tex.write(subtitle_data)
```

**优势**：
- ✅ 高性能：文字不变时无需重绘
- ✅ 灵活：支持任意中文字体（.otf/.ttf）
- ✅ 优雅：透明背景 + Alpha 混合，无黑边
- ✅ 可控：字体大小、颜色、描边完全可配置

### 5. 运行渲染

```bash
docker run --rm -it \
  --gpus all \
  --device /dev/dri:/dev/dri \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -v $(pwd):/app \
  my-gl-video \
  python3 render.py
```

## 转场效果推荐

### 简单过渡
- **fade** - 淡入淡出（最常用）
- **dissolve** - 溶解效果
- **crosswarp** - 交叉扭曲

### 擦除效果
- **wipeleft/wiperight/wipeup/wipedown** - 四向擦除
- **directionalwipe** - 方向擦除
- **radialwipe** - 径向擦除

### 几何效果
- **circle** - 圆形扩展
- **squares** - 方块效果
- **hexagonalize** - 六边形化

### 创意效果
- **glitch** - 故障效果
- **kaleidoscope** - 万花筒
- **mosaic** - 马赛克

### 3D效果
- **cube** - 立方体翻转
- **page-curl** - 翻页效果
- **stereo-viewer** - 立体查看器（ViewMaster）

## 输出信息

渲染过程会显示详细信息：

```
🚀 初始化 GPU 环境 (EGL)...
📦 加载转场效果...
   ✓ fade.glsl
   ✓ stereo-viewer.glsl
   共加载 2 个转场效果
🎥 启动 FFmpeg 编码器...
📂 开始渲染处理...
   📹 渲染视频 1/6: 149 帧
   ✨ 转场: 1 -> 2 (使用: fade)
   📹 渲染视频 2/6: 150 帧
   ✨ 转场: 2 -> 3 (使用: stereo-viewer)
   ...
🎵 合成 BGM...
✅ 完成: final_vlog.mp4
```

## 技术细节

### 帧数计算
- **非最后视频**: `SOLO_FRAMES = CLIP_FRAMES - TRANS_FRAMES` 
  - 例：8秒片段 - 2秒转场 = 6秒主体播放
- **最后视频**: 完整的 `CLIP_FRAMES`（无后续转场）

### 时长计算
对于6个视频：
```
视频1: 6秒
转场1: 2秒
视频2: 6秒
转场2: 2秒
...
视频6: 8秒
-------------------
总计: 约48秒
```

### GPU加速
- 使用 NVIDIA NVENC 硬件编码器
- ModernGL 在 GPU 上渲染转场效果
- 实时处理，速度快

## 故障排除

### 找不到转场文件
```
✗ 找不到文件: transitions/xxx.glsl
```
检查文件路径和文件名是否正确。

### 转场效果不显示
- 确保转场 GLSL 文件包含 `vec4 transition(vec2 uv)` 函数
- 检查是否有语法错误

### EOF警告
```
⚠️ 警告: 视频 6 在第 175/200 帧处EOF
```
视频源文件太短，代码会自动使用最后一帧填充。

## 许可证

- 项目代码: MIT
- GL Transitions: 各转场效果有各自的许可证，请查看源文件头部
