import subprocess
import numpy as np
import moderngl
import ffmpeg
import os
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# ================= 配置参数 =================
TRANSITION_FILES = [
    "transitions/ai5.glsl",
    "transitions/ai3.glsl",
    "transitions/ai2.glsl",
]

INPUT_FILES = [f"examples/v{i}.mp4" for i in range(1, 7)]
BGM_FILE = "examples/bgm.mp3"
OUTPUT_TEMP = "temp_video_silent.mp4"
OUTPUT_FINAL = "final_vlog.mp4"

WIDTH, HEIGHT = 1920, 1080
FPS = 25
CLIP_DURATION = 8.0
TRANSITION_DURATION = 2.0

# 字幕配置
FONT_PATH = "fonts/NotoSansSC-Bold.otf"
FONT_SIZE = 72
SUBTITLE_COLOR = (255, 255, 255, 255)  # 白色，完全不透明
SUBTITLE_OUTLINE_COLOR = (0, 0, 0, 200)  # 黑色描边
SUBTITLE_OUTLINE_WIDTH = 3
TYPEWRITER_SPEED = 3  # 每隔几帧显示一个字符（3帧 = 0.12秒/字）
SUBTITLE_DURATION = 6.0  # 字幕总显示时长（秒）

# 边框配置
BORDER_PATH = "border/border.png"

# ================= 计算常量 =================
FRAME_SIZE = WIDTH * HEIGHT * 3
CLIP_FRAMES = int(CLIP_DURATION * FPS)
TRANS_FRAMES = int(TRANSITION_DURATION * FPS)
SOLO_FRAMES = CLIP_FRAMES - TRANS_FRAMES


class VideoReader:
    """FFmpeg 视频解码器，流式读取帧数据"""

    def __init__(self, filename, is_last=False):
        self.filename = filename
        self.last_valid_frame = bytes([0] * FRAME_SIZE)
        self.eof_reached = False

        trim_duration = (
            (TRANS_FRAMES + CLIP_FRAMES) / FPS + 1.0 if is_last else CLIP_DURATION
        )

        self.process = (
            ffmpeg.input(filename, ss=0)
            .filter("setpts", "PTS-STARTPTS")
            .filter("scale", WIDTH, HEIGHT)
            .filter("fps", fps=FPS, round="up")
            .trim(duration=trim_duration)
            .output("pipe:", format="rawvideo", pix_fmt="rgb24")
            .run_async(pipe_stdout=True, quiet=True)
        )

        self._preload_first_frame()

    def _preload_first_frame(self):
        """阻塞式读取首帧，确保视频就绪"""
        print(f"   ⏳ 预读 {self.filename}...", end="", flush=True)
        in_bytes = self.process.stdout.read(FRAME_SIZE)

        if len(in_bytes) == FRAME_SIZE:
            self.first_frame_buffer = in_bytes
            self.last_valid_frame = in_bytes
            print(" 就绪!")
        else:
            print(" 失败!")
            self.first_frame_buffer = None

    def read_frame(self):
        """读取一帧，EOF 后返回最后一帧"""
        if hasattr(self, "first_frame_buffer") and self.first_frame_buffer:
            frame = self.first_frame_buffer
            self.first_frame_buffer = None
            return frame

        in_bytes = self.process.stdout.read(FRAME_SIZE)
        if len(in_bytes) == FRAME_SIZE:
            self.last_valid_frame = in_bytes
            return in_bytes
        else:
            self.eof_reached = True
            return self.last_valid_frame

    def close(self):
        """关闭 FFmpeg 进程"""
        if self.process:
            self.process.stdout.close()
            try:
                self.process.wait(timeout=0.1)
            except:
                pass


class BorderRenderer:
    """边框渲染器，加载 PNG 边框图片"""

    def __init__(self, border_path, width, height):
        self.width = width
        self.height = height
        self.texture_data = None
        self.load_border(border_path)

    def load_border(self, border_path):
        """加载边框图片，转换为 RGBA 格式"""
        if not os.path.exists(border_path):
            raise FileNotFoundError(f"边框文件不存在: {border_path}")

        img = Image.open(border_path).convert("RGBA")

        # 确保尺寸匹配
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height), Image.LANCZOS)

        self.texture_data = img.tobytes("raw", "RGBA")
        print(f"   ✓ 边框加载成功: {border_path} ({self.width}x{self.height})")

    def get_texture_data(self):
        """获取边框纹理数据"""
        return self.texture_data


class SubtitleRenderer:
    """CPU 端字幕渲染器，生成透明背景文字纹理"""

    def __init__(self, font_path, font_size, width, height):
        self.width = width
        self.height = height
        self.font = ImageFont.truetype(font_path, font_size)
        self.current_text = None
        self.texture_data = None

    def render_text(
        self,
        text,
        color=(255, 255, 255, 255),
        outline_color=(0, 0, 0, 200),
        outline_width=3,
    ):
        """渲染文字到 RGBA 图像，仅在文字变化时重新绘制"""
        if text == self.current_text and self.texture_data is not None:
            return self.texture_data  # 缓存命中，不重新绘制

        # 创建透明背景图像
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 计算文字位置（底部居中）
        bbox = draw.textbbox((0, 0), text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (self.width - text_width) // 2
        y = self.height - text_height - 100  # 距离底部 100 像素

        # 绘制描边
        if outline_width > 0:
            for offset_x in range(-outline_width, outline_width + 1):
                for offset_y in range(-outline_width, outline_width + 1):
                    if offset_x != 0 or offset_y != 0:
                        draw.text(
                            (x + offset_x, y + offset_y),
                            text,
                            font=self.font,
                            fill=outline_color,
                        )

        # 绘制主文字
        draw.text((x, y), text, font=self.font, fill=color)

        # 转换为 RGBA 字节数据
        self.texture_data = img.tobytes("raw", "RGBA")
        self.current_text = text
        return self.texture_data

    def clear(self):
        """清除字幕（返回全透明纹理）"""
        if self.current_text is None:
            return self.texture_data

        self.current_text = None
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        self.texture_data = img.tobytes("raw", "RGBA")
        return self.texture_data


def create_shader_program(ctx, transition_source):
    """创建 GLSL shader 程序，自动补充缺失的辅助函数"""
    helpers = []
    if not re.search(r"\bvec4\s+getFromColor\s*\(", transition_source):
        helpers.append("vec4 getFromColor(vec2 uv) { return texture(tex0, uv); }")
    if not re.search(r"\bvec4\s+getToColor\s*\(", transition_source):
        helpers.append("vec4 getToColor(vec2 uv) { return texture(tex1, uv); }")
    if not re.search(r"\bfloat\s+rand\s*\(", transition_source, re.IGNORECASE):
        helpers.append(
            "float rand(vec2 co) { return fract(sin(dot(co.xy, vec2(12.9898, 78.233))) * 43758.5453); }"
        )

    fragment_shader = f"""
        #version 330
        uniform sampler2D tex0, tex1;
        uniform float progress, ratio;
        in vec2 v_text;
        out vec4 f_color;

        {chr(10).join(helpers)}
        {transition_source}

        void main() {{
            if (progress <= 0.0) f_color = texture(tex0, v_text);
            else if (progress >= 1.0) f_color = texture(tex1, v_text);
            else f_color = transition(v_text);
        }}
    """

    vertex_shader = """
        #version 330
        in vec2 in_vert, in_text;
        out vec2 v_text;
        void main() { gl_Position = vec4(in_vert, 0.0, 1.0); v_text = in_text; }
    """

    return ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)


def create_subtitle_shader(ctx):
    """创建字幕叠加 shader，将字幕纹理混合到视频帧上"""
    vertex_shader = """
        #version 330
        in vec2 in_vert, in_text;
        out vec2 v_text;
        void main() { gl_Position = vec4(in_vert, 0.0, 1.0); v_text = in_text; }
    """

    fragment_shader = """
        #version 330
        uniform sampler2D video_tex;     // 视频帧纹理
        uniform sampler2D subtitle_tex;  // 字幕纹理（RGBA）
        in vec2 v_text;
        out vec4 f_color;

        void main() {
            vec4 video = texture(video_tex, v_text);
            vec4 subtitle = texture(subtitle_tex, v_text);
            
            // Alpha 混合：前景（字幕）叠加到背景（视频）
            f_color.rgb = video.rgb * (1.0 - subtitle.a) + subtitle.rgb * subtitle.a;
            f_color.a = 1.0;
        }
    """

    return ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)


def create_border_shader(ctx):
    """创建边框叠加 shader，将边框纹理混合到视频帧上"""
    vertex_shader = """
        #version 330
        in vec2 in_vert, in_text;
        out vec2 v_text;
        void main() { gl_Position = vec4(in_vert, 0.0, 1.0); v_text = in_text; }
    """

    fragment_shader = """
        #version 330
        uniform sampler2D video_tex;   // 视频帧纹理
        uniform sampler2D border_tex;  // 边框纹理（RGBA，中间透明）
        in vec2 v_text;
        out vec4 f_color;

        void main() {
            vec4 video = texture(video_tex, v_text);
            vec4 border = texture(border_tex, v_text);
            
            // Alpha 混合：边框叠加到视频上层
            f_color.rgb = video.rgb * (1.0 - border.a) + border.rgb * border.a;
            f_color.a = 1.0;
        }
    """

    return ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)


def load_transitions():
    """加载所有转场效果 GLSL 文件"""
    print("📦 加载转场效果...")
    transitions = []
    for filepath in TRANSITION_FILES:
        if os.path.exists(filepath):
            with open(filepath) as f:
                transitions.append({"name": Path(filepath).stem, "source": f.read()})
            print(f"   ✓ {Path(filepath).name}")
        else:
            print(f"   ✗ 找不到: {filepath}")

    if not transitions:
        raise FileNotFoundError("❌ 未加载任何转场效果")

    print(f"   共 {len(transitions)} 个转场")
    return transitions


def create_encoder():
    """创建 FFmpeg NVENC 编码器"""
    print("🎥 启动编码器...")
    return (
        ffmpeg.input(
            "pipe:", format="rawvideo", pix_fmt="rgb24", s=f"{WIDTH}x{HEIGHT}", r=FPS
        )
        .output(
            OUTPUT_TEMP,
            vcodec="h264_nvenc",
            pix_fmt="yuv420p",
            bitrate="15M",
            preset="p4",
            rc="cbr",
            **{"rc-lookahead": "32", "spatial-aq": "1", "temporal-aq": "1"},
        )
        .overwrite_output()
        .run_async(pipe_stdin=True, quiet=True)
    )


def merge_audio():
    """合并 BGM 到视频"""
    if not os.path.exists(BGM_FILE):
        os.rename(OUTPUT_TEMP, OUTPUT_FINAL)
        return

    print("🎵 合成 BGM...")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            OUTPUT_TEMP,
            "-ss",
            "0",
            "-stream_loop",
            "-1",
            "-i",
            BGM_FILE,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-fflags",
            "+genpts",
            OUTPUT_FINAL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove(OUTPUT_TEMP)


def main():
    print("🚀 初始化 GPU 环境...")
    ctx = moderngl.create_context(standalone=True, backend="egl")
    tex0, tex1 = ctx.texture((WIDTH, HEIGHT), 3), ctx.texture((WIDTH, HEIGHT), 3)
    fbo = ctx.simple_framebuffer((WIDTH, HEIGHT), components=3)
    fbo.use()
    fbo.clear(0.0, 0.0, 0.0, 1.0)

    # 初始化字幕系统
    print("📝 初始化字幕渲染器...")
    subtitle_renderer = SubtitleRenderer(FONT_PATH, FONT_SIZE, WIDTH, HEIGHT)
    subtitle_tex = ctx.texture((WIDTH, HEIGHT), 4)  # RGBA 纹理
    video_temp_tex = ctx.texture((WIDTH, HEIGHT), 3)  # 临时存储视频帧
    subtitle_fbo = ctx.simple_framebuffer((WIDTH, HEIGHT), components=3)  # 字幕合成 FBO

    # 创建字幕叠加 shader
    subtitle_prog = create_subtitle_shader(ctx)
    subtitle_vbo = ctx.buffer(
        np.array(
            [
                -1,
                -1,
                0,
                0,
                1,
                -1,
                1,
                0,
                -1,
                1,
                0,
                1,
                -1,
                1,
                0,
                1,
                1,
                -1,
                1,
                0,
                1,
                1,
                1,
                1,
            ],
            dtype="f4",
        )
    )
    subtitle_vao = ctx.vertex_array(
        subtitle_prog, [(subtitle_vbo, "2f 2f", "in_vert", "in_text")]
    )
    subtitle_prog["video_tex"].value = 0
    subtitle_prog["subtitle_tex"].value = 1

    # 初始化边框系统
    print("🖼️  初始化边框渲染器...")
    border_renderer = BorderRenderer(BORDER_PATH, WIDTH, HEIGHT)
    border_tex = ctx.texture((WIDTH, HEIGHT), 4)  # RGBA 纹理
    border_tex.write(border_renderer.get_texture_data())
    border_temp_tex = ctx.texture((WIDTH, HEIGHT), 3)  # 临时存储当前帧
    border_fbo = ctx.simple_framebuffer((WIDTH, HEIGHT), components=3)  # 边框合成 FBO

    # 创建边框叠加 shader
    border_prog = create_border_shader(ctx)
    border_vbo = ctx.buffer(
        np.array(
            [
                -1,
                -1,
                0,
                0,
                1,
                -1,
                1,
                0,
                -1,
                1,
                0,
                1,
                -1,
                1,
                0,
                1,
                1,
                -1,
                1,
                0,
                1,
                1,
                1,
                1,
            ],
            dtype="f4",
        )
    )
    border_vao = ctx.vertex_array(
        border_prog, [(border_vbo, "2f 2f", "in_vert", "in_text")]
    )
    border_prog["video_tex"].value = 0
    border_prog["border_tex"].value = 1

    transitions = load_transitions()

    # 创建顶点数据和着色器
    vertices = np.array(
        [-1, -1, 0, 0, 1, -1, 1, 0, -1, 1, 0, 1, -1, 1, 0, 1, 1, -1, 1, 0, 1, 1, 1, 1],
        dtype="f4",
    )
    vbo = ctx.buffer(vertices)

    encoder = create_encoder()
    print("📂 开始渲染...")

    # 初始化着色器程序
    prog = create_shader_program(ctx, transitions[0]["source"])
    vao = ctx.vertex_array(prog, [(vbo, "2f 2f", "in_vert", "in_text")])
    tex0.use(0)
    tex1.use(1)
    prog["tex0"].value = 0
    prog["tex1"].value = 1
    if "ratio" in prog:
        prog["ratio"].value = WIDTH / HEIGHT

    total_frames = 0
    current_vid = None
    current_transition_idx = 0

    for i, input_file in enumerate(INPUT_FILES):
        is_last = i == len(INPUT_FILES) - 1

        # 加载视频
        if current_vid is None:
            current_vid = VideoReader(input_file, is_last=is_last)

        next_vid = (
            VideoReader(INPUT_FILES[i + 1], is_last=(i + 1 == len(INPUT_FILES) - 1))
            if not is_last
            else None
        )

        # 主体播放
        frames_to_play = CLIP_FRAMES if is_last else SOLO_FRAMES
        print(f"   📹 视频 {i+1}/{len(INPUT_FILES)}: {frames_to_play} 帧")

        for frame_idx in range(frames_to_play):
            # 渲染视频帧到主 FBO
            tex0.write(current_vid.read_frame())
            prog["progress"].value = 0.0
            fbo.use()  # 确保使用主 FBO
            vao.render()

            # 字幕叠加（打字机效果）
            subtitle_frame_count = int(SUBTITLE_DURATION * FPS)
            if i == 0 and frame_idx < subtitle_frame_count:
                # 生成完整字幕文本（仅在第一帧）
                if frame_idx == 0:
                    current_date = datetime.now()
                    full_subtitle_text = f"《{current_date.year}年{current_date.month}月{current_date.day}日，长沙卷烟厂安全体验馆留念》"
                    print(f"      💬 字幕: {full_subtitle_text}")

                # 计算当前应显示的字符数（打字机效果）
                chars_to_show = (frame_idx // TYPEWRITER_SPEED) + 1
                display_text = full_subtitle_text[:chars_to_show]

                # 每隔 TYPEWRITER_SPEED 帧更新一次字幕纹理
                if frame_idx % TYPEWRITER_SPEED == 0 or frame_idx == 0:
                    subtitle_data = subtitle_renderer.render_text(
                        display_text,
                        color=SUBTITLE_COLOR,
                        outline_color=SUBTITLE_OUTLINE_COLOR,
                        outline_width=SUBTITLE_OUTLINE_WIDTH,
                    )
                    subtitle_tex.write(subtitle_data)

                # 将视频帧复制到临时纹理
                video_temp_tex.write(fbo.read(components=3))

                # 步骤1: 边框叠加（视频 + 边框）
                border_fbo.use()
                video_temp_tex.use(0)
                border_tex.use(1)
                border_vao.render()

                # 步骤2: 字幕叠加（在边框结果之上）
                border_temp_tex.write(border_fbo.read(components=3))
                subtitle_fbo.use()
                border_temp_tex.use(0)
                subtitle_tex.use(1)
                subtitle_vao.render()

                # 步骤3: 写入最终帧（只写入一次）
                encoder.stdin.write(subtitle_fbo.read(components=3))

                # 恢复主渲染状态
                fbo.use()
                tex0.use(0)
                tex1.use(1)
            else:
                # 无字幕时，先叠加边框再写入
                border_temp_tex.write(fbo.read(components=3))
                border_fbo.use()
                border_temp_tex.use(0)
                border_tex.use(1)
                border_vao.render()
                encoder.stdin.write(border_fbo.read(components=3))

                # 恢复主渲染状态
                fbo.use()
                tex0.use(0)
                tex1.use(1)

            total_frames += 1

        # 转场播放
        if not is_last and next_vid:
            transition = transitions[i % len(transitions)]
            print(f"   ✨ 转场 {i+1}→{i+2}: {transition['name']}")

            # 转场效果切换时重新编译着色器
            if i % len(transitions) != current_transition_idx:
                current_transition_idx = i % len(transitions)
                prog = create_shader_program(ctx, transition["source"])
                vao = ctx.vertex_array(prog, [(vbo, "2f 2f", "in_vert", "in_text")])
                tex0.use(0)
                tex1.use(1)
                prog["tex0"].value = 0
                prog["tex1"].value = 1
                if "ratio" in prog:
                    prog["ratio"].value = WIDTH / HEIGHT

            for j in range(TRANS_FRAMES):
                tex0.write(current_vid.read_frame())
                tex1.write(next_vid.read_frame())
                prog["progress"].value = (j + 1) / TRANS_FRAMES

                # 确保状态正确
                fbo.use()  # 使用主 FBO
                tex0.use(0)  # 绑定 tex0 到单元 0
                tex1.use(1)  # 绑定 tex1 到单元 1

                vao.render()

                # 转场帧也要叠加边框
                border_temp_tex.write(fbo.read(components=3))
                border_fbo.use()
                border_temp_tex.use(0)
                border_tex.use(1)
                border_vao.render()
                encoder.stdin.write(border_fbo.read(components=3))

                # 恢复主渲染状态
                fbo.use()
                tex0.use(0)
                tex1.use(1)

                total_frames += 1

            current_vid.close()
            current_vid = next_vid
        else:
            current_vid.close()

    encoder.stdin.close()
    encoder.wait()

    print(f"📊 总帧数: {total_frames} ({total_frames/FPS:.1f}秒)")
    merge_audio()
    print(f"✅ 完成: {OUTPUT_FINAL}")


if __name__ == "__main__":
    main()
