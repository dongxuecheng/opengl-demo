"""
渲染器模块 - 封装 OpenGL 渲染逻辑
"""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


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
            print(f"⚠️  警告: 边框文件不存在: {border_path}，使用空边框")
            # 创建透明边框
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        else:
            img = Image.open(border_path).convert("RGBA")
            # 确保尺寸匹配
            if img.size != (self.width, self.height):
                img = img.resize((self.width, self.height), Image.LANCZOS)

        self.texture_data = img.tobytes("raw", "RGBA")
        print(f"   ✓ 边框加载: {border_path}")

    def get_texture_data(self):
        """获取边框纹理数据"""
        return self.texture_data


class SubtitleRenderer:
    """字幕渲染器，生成透明背景文字纹理"""

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
            return self.texture_data

        # 创建透明背景图像
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 计算文字位置（底部居中）
        bbox = draw.textbbox((0, 0), text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (self.width - text_width) // 2
        y = self.height - text_height - 100

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
