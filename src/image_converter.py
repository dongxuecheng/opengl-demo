"""
图片转视频工具模块
将静态图片转换为指定时长的视频帧序列
"""
from PIL import Image


def convert_image_to_video(image_path: str, width: int, height: int) -> bytes:
    """
    将图片加载并转换为视频帧数据格式
    
    Args:
        image_path: 图片路径
        width: 目标宽度
        height: 目标高度
    
    Returns:
        bytes: RGB24 格式的图片数据
    """
    img = Image.open(image_path).convert("RGB")
    
    # 调整尺寸
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    
    # 转换为字节数据
    return img.tobytes("raw", "RGB")
