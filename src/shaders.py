"""
Shader 创建模块 - 管理 GLSL 着色器程序
"""

import os
import re
from pathlib import Path


def create_transition_shader(ctx, transition_source):
    """创建转场 shader 程序，自动补充缺失的辅助函数"""
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


def create_overlay_shader(ctx, overlay_name="subtitle"):
    """创建通用叠加 shader（字幕/边框）"""
    vertex_shader = """
        #version 330
        in vec2 in_vert, in_text;
        out vec2 v_text;
        void main() { gl_Position = vec4(in_vert, 0.0, 1.0); v_text = in_text; }
    """

    fragment_shader = f"""
        #version 330
        uniform sampler2D video_tex;
        uniform sampler2D overlay_tex;
        in vec2 v_text;
        out vec4 f_color;

        void main() {{
            vec4 video = texture(video_tex, v_text);
            vec4 overlay = texture(overlay_tex, v_text);
            f_color.rgb = video.rgb * (1.0 - overlay.a) + overlay.rgb * overlay.a;
            f_color.a = 1.0;
        }}
    """

    return ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_shader)


def load_transitions(transition_files):
    """加载转场效果 GLSL 文件"""
    print("📦 加载转场效果...")
    transitions = []
    for filepath in transition_files:
        if os.path.exists(filepath):
            with open(filepath) as f:
                transitions.append({"name": Path(filepath).stem, "source": f.read()})
            print(f"   ✓ {Path(filepath).name}")
        else:
            print(f"   ⚠️  找不到: {filepath}")

    if not transitions:
        raise FileNotFoundError("❌ 未加载任何转场效果")

    print(f"   共 {len(transitions)} 个转场")
    return transitions
