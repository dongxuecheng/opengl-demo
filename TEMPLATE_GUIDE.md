# GPU 加速 Vlog 渲染器 - 模板化重构版

## 📁 项目结构

```
opengl-demo/
├── render_v2.py          # 主程序（模板化）
├── src/                  # 源代码模块
│   ├── config.py         # 配置加载器
│   ├── renderers.py      # 渲染器（字幕、边框）
│   ├── shaders.py        # GLSL 着色器管理
│   └── video.py          # 视频编解码
├── templates/            # 模板目录
│   ├── classic/          # 经典模板
│   │   ├── config.yaml   # 模板配置
│   │   ├── border.png    # 边框图片
│   │   └── bgm.mp3       # 背景音乐
│   ├── modern/           # 现代模板
│   │   ├── config.yaml
│   │   ├── border.png
│   │   └── bgm.mp3
│   └── elegant/          # 优雅模板
│       ├── config.yaml
│       ├── border.png
│       └── bgm.mp3
├── transitions/          # 转场效果库
├── fonts/                # 字体库
└── examples/             # 示例视频
```

## 🚀 快速开始

### 列出所有可用模板
```bash
python render_v2.py --list
```

### 使用指定模板渲染
```bash
# 使用 classic 模板
python render_v2.py --template classic

# 使用 modern 模板
python render_v2.py --template modern

# 使用 elegant 模板并指定输出文件
python render_v2.py --template elegant --output my_vlog.mp4
```

### 自定义输入视频
```bash
python render_v2.py --template classic --input v1.mp4 v2.mp4 v3.mp4
```

## 🎨 创建新模板

### 1. 创建模板目录
```bash
mkdir templates/my_template
```

### 2. 准备资源文件
- `border.png`: 1920x1080 PNG 边框（中间透明）
- `bgm.mp3`: 背景音乐文件
- `config.yaml`: 配置文件（见下方）

### 3. 配置文件示例

```yaml
# templates/my_template/config.yaml
name: "My Template"
description: "我的自定义模板"

border:
  path: "templates/my_template/border.png"

bgm:
  path: "templates/my_template/bgm.mp3"

transitions:
  - "transitions/ai5.glsl"
  - "transitions/mosaic.glsl"

font:
  path: "fonts/NotoSansSC-Bold.otf"
  size: 72
  color: [255, 255, 255, 255]  # RGBA
  outline_color: [0, 0, 0, 200]
  outline_width: 3

subtitle:
  template: "《{year}年{month}月{day}日，标题》"
  typewriter_speed: 3  # 帧/字符
  duration: 6.0  # 秒
```

### 4. 使用新模板
```bash
python render_v2.py --template my_template
```

## 📝 配置说明

### 字体配置
- `path`: 字体文件路径
- `size`: 字号大小
- `color`: [R, G, B, A] 文字颜色
- `outline_color`: 描边颜色
- `outline_width`: 描边宽度（像素）

### 字幕配置
- `template`: 字幕模板，支持变量：`{year}`, `{month}`, `{day}`
- `typewriter_speed`: 打字机速度（每隔 N 帧显示一个字符）
- `duration`: 字幕显示总时长（秒）

### 转场效果
可用转场效果列表（`transitions/` 目录）：
- `ai.glsl`, `ai2.glsl`, ..., `ai7.glsl`
- `mosaic.glsl`
- `gridflip.glsl`
- `perlin.glsl`
- `inverted-page-curl.glsl`
- `stereo-viewer.glsl`

## 🎬 渲染流程

1. **加载配置**: 读取模板 YAML 配置
2. **初始化 GPU**: 创建 ModernGL 上下文和纹理
3. **加载资源**: 边框、字体、转场效果
4. **视频解码**: FFmpeg 流式读取输入视频
5. **GPU 渲染**: 
   - 视频帧 → 边框叠加 → 字幕叠加
   - 转场效果（Shader 插值）
6. **视频编码**: NVENC 硬件加速编码
7. **音频合成**: FFmpeg 合并 BGM

## 🛠️ Docker 运行

```bash
docker run --rm -it --gpus all \
  --device /dev/dri:/dev/dri \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -v $(pwd):/app \
  my-gl-video python3 render_v2.py --template classic
```

## 🔧 架构优势

### 模块化设计
- ✅ **配置分离**: YAML 配置独立于代码
- ✅ **资源隔离**: 每个模板独立资源目录
- ✅ **代码复用**: 核心渲染逻辑模块化

### 易于扩展
- ✅ 添加新模板：仅需创建目录 + 配置文件
- ✅ 修改样式：编辑 YAML 无需改代码
- ✅ 自定义转场：添加 `.glsl` 文件即可

### 维护性
- ✅ 单一职责：每个模块功能明确
- ✅ 低耦合：配置、渲染、视频处理独立
- ✅ 易测试：可单独测试各模块

## 📦 依赖项

```bash
pip install moderngl numpy Pillow ffmpeg-python pyyaml
```

## 🔄 从旧版本迁移

旧版本：
```python
python render.py  # 硬编码配置
```

新版本：
```python
python render_v2.py --template classic  # 模板化配置
```

## 🤝 贡献模板

欢迎贡献新模板！提交 Pull Request 包含：
1. `templates/{name}/config.yaml`
2. `templates/{name}/border.png`
3. `templates/{name}/bgm.mp3`
4. 模板说明文档
