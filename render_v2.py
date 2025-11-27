#!/usr/bin/env python3
"""
GPU 加速视频渲染器 - 模板化重构版本

用法:
    python render_v2.py --template classic
    python render_v2.py --template modern --output my_video.mp4
    python render_v2.py --list  # 列出所有可用模板
"""
import argparse
import numpy as np
import moderngl
import sys
from pathlib import Path

# 导入自定义模块
from src.config import TemplateConfig
from src.renderers import BorderRenderer, SubtitleRenderer
from src.shaders import (
    create_transition_shader,
    create_overlay_shader,
    load_transitions,
)
from src.video import VideoReader, create_encoder, merge_audio


# ================= 全局常量 =================
WIDTH, HEIGHT = 1920, 1080
FPS = 25
CLIP_DURATION = 8.0
TRANSITION_DURATION = 2.0

FRAME_SIZE = WIDTH * HEIGHT * 3
CLIP_FRAMES = int(CLIP_DURATION * FPS)
TRANS_FRAMES = int(TRANSITION_DURATION * FPS)
SOLO_FRAMES = CLIP_FRAMES - TRANS_FRAMES


class VlogRenderer:
    """Vlog 渲染器主类"""

    def __init__(self, template_name: str, input_files: list, output_file: str = None):
        self.config = TemplateConfig(template_name)
        self.input_files = input_files
        self.output_file = output_file or f"output_{template_name}.mp4"
        self.temp_file = f"temp_{template_name}_silent.mp4"

        print(f"🎬 使用模板: {self.config.name}")
        print(f"   {self.config.config.get('description', '')}")

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
        """初始化字幕和边框渲染系统"""
        print("📝 初始化叠加层...")

        # 字幕系统
        font_cfg = self.config.font
        self.subtitle_renderer = SubtitleRenderer(
            font_cfg["path"], font_cfg["size"], WIDTH, HEIGHT
        )
        self.subtitle_tex = self.ctx.texture((WIDTH, HEIGHT), 4)
        self.subtitle_fbo = self.ctx.simple_framebuffer((WIDTH, HEIGHT), components=3)
        self.subtitle_prog = create_overlay_shader(self.ctx, "subtitle")
        self.subtitle_vao = self._create_vao(self.subtitle_prog)
        self.subtitle_prog["video_tex"].value = 0
        self.subtitle_prog["overlay_tex"].value = 1

        # 边框系统
        self.border_renderer = BorderRenderer(self.config.border["path"], WIDTH, HEIGHT)
        self.border_tex = self.ctx.texture((WIDTH, HEIGHT), 4)
        self.border_tex.write(self.border_renderer.get_texture_data())
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
        vbo = self.ctx.buffer(vertices)
        return self.ctx.vertex_array(program, [(vbo, "2f 2f", "in_vert", "in_text")])

    def render_frame_with_overlays(self, has_subtitle=False):
        """
        渲染一帧并叠加边框和字幕
        渲染顺序: 视频 → 边框 → 字幕
        """
        # 步骤1: 边框叠加（视频 + 边框）
        self.temp_tex.write(self.fbo.read(components=3))
        self.border_fbo.use()
        self.temp_tex.use(0)
        self.border_tex.use(1)
        self.border_vao.render()

        if has_subtitle:
            # 步骤2: 字幕叠加（边框结果 + 字幕）
            self.temp_tex.write(self.border_fbo.read(components=3))
            self.subtitle_fbo.use()
            self.temp_tex.use(0)
            self.subtitle_tex.use(1)
            self.subtitle_vao.render()

            # 返回最终帧
            final_frame = self.subtitle_fbo.read(components=3)
        else:
            # 无字幕，直接返回边框结果
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
        current_vid = None

        # 字幕配置
        subtitle_cfg = self.config.subtitle
        full_subtitle_text = self.config.get_subtitle_text()
        subtitle_duration_frames = int(subtitle_cfg["duration"] * FPS)
        typewriter_speed = subtitle_cfg["typewriter_speed"]

        for i, input_file in enumerate(self.input_files):
            is_last = i == len(self.input_files) - 1

            # 加载视频
            if current_vid is None:
                trim_duration = (
                    (TRANS_FRAMES + CLIP_FRAMES) / FPS + 1.0
                    if is_last
                    else CLIP_DURATION
                )
                current_vid = VideoReader(
                    input_file, WIDTH, HEIGHT, FPS, FRAME_SIZE, trim_duration
                )

            next_vid = None
            if not is_last:
                trim_duration = (
                    (TRANS_FRAMES + CLIP_FRAMES) / FPS + 1.0
                    if (i + 1 == len(self.input_files) - 1)
                    else CLIP_DURATION
                )
                next_vid = VideoReader(
                    self.input_files[i + 1],
                    WIDTH,
                    HEIGHT,
                    FPS,
                    FRAME_SIZE,
                    trim_duration,
                )

            # 主体播放
            frames_to_play = CLIP_FRAMES if is_last else SOLO_FRAMES
            print(f"   📹 视频 {i+1}/{len(self.input_files)}: {frames_to_play} 帧")

            # 首帧显示字幕文本
            if i == 0:
                print(f"      💬 字幕: {full_subtitle_text}")

            for frame_idx in range(frames_to_play):
                # 渲染视频帧
                self.tex0.write(current_vid.read_frame())
                prog["progress"].value = 0.0
                self.fbo.use()
                vao.render()

                # 字幕处理（仅第一个视频）
                has_subtitle = i == 0 and frame_idx < subtitle_duration_frames
                if has_subtitle:
                    # 打字机效果
                    chars_to_show = (frame_idx // typewriter_speed) + 1
                    display_text = full_subtitle_text[:chars_to_show]

                    if frame_idx % typewriter_speed == 0 or frame_idx == 0:
                        subtitle_data = self.subtitle_renderer.render_text(
                            display_text,
                            color=tuple(self.config.font["color"]),
                            outline_color=tuple(self.config.font["outline_color"]),
                            outline_width=self.config.font["outline_width"],
                        )
                        self.subtitle_tex.write(subtitle_data)

                # 叠加渲染并写入编码器
                final_frame = self.render_frame_with_overlays(has_subtitle)
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

                    # 转场帧也叠加边框（无字幕）
                    final_frame = self.render_frame_with_overlays(has_subtitle=False)
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


def main():
    parser = argparse.ArgumentParser(
        description="GPU 加速 Vlog 渲染器 - 支持模板化配置"
    )
    parser.add_argument(
        "--template",
        "-t",
        type=str,
        help="模板名称 (classic/modern/elegant)",
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        default=[f"examples/v{i}.mp4" for i in range(1, 7)],
        help="输入视频文件列表",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="输出视频文件名",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="列出所有可用模板",
    )

    args = parser.parse_args()

    # 列出模板
    if args.list:
        templates = TemplateConfig.list_available_templates()
        print("📋 可用模板:")
        for tmpl in templates:
            try:
                cfg = TemplateConfig(tmpl)
                print(f"  • {tmpl}: {cfg.config.get('description', '')}")
            except:
                print(f"  • {tmpl}")
        return

    # 验证参数
    if not args.template:
        print("❌ 错误: 请指定模板名称 (--template)")
        print("   使用 --list 查看可用模板")
        sys.exit(1)

    # 开始渲染
    renderer = VlogRenderer(args.template, args.input, args.output)
    renderer.render()


if __name__ == "__main__":
    main()
