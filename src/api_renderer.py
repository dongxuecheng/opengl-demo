"""
API 专用渲染器 - 支持图片和视频混合渲染

特性：
- 图片持续 8 秒
- 每个视频持续 16 秒
- 图片使用独立边框
- 视频使用统一边框
"""
import numpy as np
import moderngl
from pathlib import Path
from PIL import Image

from src.config import TemplateConfig
from src.renderers import BorderRenderer, SubtitleRenderer
from src.shaders import create_transition_shader, create_overlay_shader, load_transitions
from src.video import VideoReader, create_encoder, merge_audio
from src.image_converter import convert_image_to_video


# ================= 全局常量 =================
WIDTH, HEIGHT = 1920, 1080
FPS = 25
IMAGE_DURATION = 8.0  # 图片持续时间（秒）
VIDEO_DURATION = 16.0  # 每个视频持续时间（秒）
TRANSITION_DURATION = 2.0

FRAME_SIZE = WIDTH * HEIGHT * 3
IMAGE_FRAMES = int(IMAGE_DURATION * FPS)
VIDEO_FRAMES = int(VIDEO_DURATION * FPS)
TRANS_FRAMES = int(TRANSITION_DURATION * FPS)
SOLO_FRAMES = VIDEO_FRAMES - TRANS_FRAMES


class ApiVlogRenderer:
    """API 专用 Vlog 渲染器"""

    def __init__(
        self, 
        template_name: str, 
        image_path: str, 
        video_paths: list,
        output_file: str = None
    ):
        self.config = TemplateConfig(template_name)
        self.image_path = image_path
        self.video_paths = video_paths
        self.output_file = output_file or f"output_api_{template_name}.mp4"
        self.temp_file = f"temp_api_{template_name}_silent.mp4"

        print(f"🎬 API渲染 - 模板: {self.config.name}")
        print(f"   图片: {image_path}")
        print(f"   视频数量: {len(video_paths)}")

    def setup_gpu(self):
        """初始化 GPU 上下文和纹理"""
        print("🚀 初始化 GPU 环境...")
        self.ctx = moderngl.create_context(standalone=True, backend="egl")
        self.tex0 = self.ctx.texture((WIDTH, HEIGHT), 3)
        self.tex1 = self.ctx.texture((WIDTH, HEIGHT), 3)
        self.fbo = self.ctx.simple_framebuffer((WIDTH, HEIGHT), components=3)
        self.fbo.use()
        self.fbo.clear(0.0, 0.0, 0.0, 1.0)

    def setup_overlays(self):
        """初始化边框渲染系统（图片和视频使用不同边框）"""
        print("📝 初始化叠加层...")

        # 图片边框（使用模板配置的边框）
        self.image_border_renderer = BorderRenderer(
            self.config.border["path"], WIDTH, HEIGHT
        )
        self.image_border_tex = self.ctx.texture((WIDTH, HEIGHT), 4)
        self.image_border_tex.write(self.image_border_renderer.get_texture_data())

        # 视频边框（使用 border_video.png，如果不存在则使用相同的）
        video_border_path = self.config.border["path"].replace("border.png", "border_video.png")
        if not Path(video_border_path).exists():
            print(f"   ⚠️  border_video.png 不存在，使用相同边框")
            video_border_path = self.config.border["path"]
        
        self.video_border_renderer = BorderRenderer(video_border_path, WIDTH, HEIGHT)
        self.video_border_tex = self.ctx.texture((WIDTH, HEIGHT), 4)
        self.video_border_tex.write(self.video_border_renderer.get_texture_data())

        # 边框 FBO 和 Shader
        self.border_fbo = self.ctx.simple_framebuffer((WIDTH, HEIGHT), components=3)
        self.border_prog = create_overlay_shader(self.ctx, "border")
        self.border_vao = self._create_vao(self.border_prog)
        self.border_prog["video_tex"].value = 0
        self.border_prog["overlay_tex"].value = 1

        # 临时纹理
        self.temp_tex = self.ctx.texture((WIDTH, HEIGHT), 3)

    def _create_vao(self, program):
        """创建顶点数组对象（全屏四边形）"""
        vertices = np.array(
            [-1, -1, 0, 0, 1, -1, 1, 0, -1, 1, 0, 1, -1, 1, 0, 1, 1, -1, 1, 0, 1, 1, 1, 1],
            dtype="f4",
        )
        vbo = self.ctx.buffer(vertices)
        return self.ctx.vertex_array(program, [(vbo, "2f 2f", "in_vert", "in_text")])

    def render_frame_with_border(self, use_image_border=False):
        """
        渲染一帧并叠加边框
        
        Args:
            use_image_border: True=使用图片边框，False=使用视频边框
        """
        # 选择边框纹理
        border_tex = self.image_border_tex if use_image_border else self.video_border_tex
        
        # 边框叠加
        self.temp_tex.write(self.fbo.read(components=3))
        self.border_fbo.use()
        self.temp_tex.use(0)
        border_tex.use(1)
        self.border_vao.render()

        # 获取最终帧
        final_frame = self.border_fbo.read(components=3)

        # 恢复主 FBO 状态
        self.fbo.use()
        self.tex0.use(0)
        self.tex1.use(1)

        return final_frame

    def render(self):
        """主渲染循环"""
        self.setup_gpu()
        self.setup_overlays()

        # 加载转场效果
        transitions = load_transitions(self.config.transitions)

        # 创建编码器
        encoder = create_encoder(WIDTH, HEIGHT, FPS, self.temp_file)
        print("📂 开始渲染...")

        # 初始化着色器
        prog = create_transition_shader(self.ctx, transitions[0]["source"])
        vao = self._create_vao(prog)
        self.tex0.use(0)
        self.tex1.use(1)
        prog["tex0"].value = 0
        prog["tex1"].value = 1
        if "ratio" in prog:
            prog["ratio"].value = WIDTH / HEIGHT

        total_frames = 0

        # ========== 第一部分：渲染图片 (8秒，使用图片边框) ==========
        print(f"   🖼️  图片: {IMAGE_FRAMES} 帧 ({IMAGE_DURATION}秒)")
        
        # 加载并预处理图片
        img = Image.open(self.image_path).convert("RGB")
        if img.size != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
        img_data = img.tobytes("raw", "RGB")

        # 渲染图片帧
        for frame_idx in range(IMAGE_FRAMES):
            self.tex0.write(img_data)
            prog["progress"].value = 0.0
            self.fbo.use()
            vao.render()

            # 叠加图片边框
            final_frame = self.render_frame_with_border(use_image_border=True)
            encoder.stdin.write(final_frame)
            total_frames += 1

        # ========== 第二部分：渲染视频序列 (每个16秒，使用视频边框) ==========
        current_vid = None

        for i, video_path in enumerate(self.video_paths):
            is_last = i == len(self.video_paths) - 1

            # 加载当前视频
            if current_vid is None:
                trim_duration = (
                    (TRANS_FRAMES + VIDEO_FRAMES) / FPS + 1.0
                    if is_last
                    else VIDEO_DURATION
                )
                current_vid = VideoReader(
                    video_path, WIDTH, HEIGHT, FPS, FRAME_SIZE, trim_duration
                )

            # 加载下一个视频（用于转场）
            next_vid = None
            if not is_last:
                trim_duration = (
                    (TRANS_FRAMES + VIDEO_FRAMES) / FPS + 1.0
                    if (i + 1 == len(self.video_paths) - 1)
                    else VIDEO_DURATION
                )
                next_vid = VideoReader(
                    self.video_paths[i + 1],
                    WIDTH,
                    HEIGHT,
                    FPS,
                    FRAME_SIZE,
                    trim_duration,
                )

            # 主体播放
            frames_to_play = VIDEO_FRAMES if is_last else SOLO_FRAMES
            print(f"   📹 视频 {i+1}/{len(self.video_paths)}: {frames_to_play} 帧")

            for frame_idx in range(frames_to_play):
                # 渲染视频帧
                self.tex0.write(current_vid.read_frame())
                prog["progress"].value = 0.0
                self.fbo.use()
                vao.render()

                # 叠加视频边框
                final_frame = self.render_frame_with_border(use_image_border=False)
                encoder.stdin.write(final_frame)
                total_frames += 1

            # 转场播放
            if not is_last and next_vid:
                transition = transitions[i % len(transitions)]
                print(f"   ✨ 转场 {i+1}→{i+2}: {transition['name']}")

                # 切换着色器
                prog = create_transition_shader(self.ctx, transition["source"])
                vao = self._create_vao(prog)
                self.tex0.use(0)
                self.tex1.use(1)
                prog["tex0"].value = 0
                prog["tex1"].value = 1
                if "ratio" in prog:
                    prog["ratio"].value = WIDTH / HEIGHT

                for j in range(TRANS_FRAMES):
                    self.tex0.write(current_vid.read_frame())
                    self.tex1.write(next_vid.read_frame())
                    prog["progress"].value = (j + 1) / TRANS_FRAMES

                    self.fbo.use()
                    self.tex0.use(0)
                    self.tex1.use(1)
                    vao.render()

                    # 转场帧使用视频边框
                    final_frame = self.render_frame_with_border(use_image_border=False)
                    encoder.stdin.write(final_frame)
                    total_frames += 1

                current_vid.close()
                current_vid = next_vid
            else:
                current_vid.close()

        encoder.stdin.close()
        encoder.wait()

        print(f"📊 总帧数: {total_frames} ({total_frames/FPS:.1f}秒)")

        # 合并音频
        merge_audio(self.temp_file, self.config.bgm["path"], self.output_file)
        print(f"✅ 完成: {self.output_file}")
