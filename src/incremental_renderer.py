"""
增量渲染器 - 支持分段渲染和拼接

基于 ApiVlogRenderer，支持：
- init: 渲染初始图片段落
- append: 追加视频段落（使用配置的转场顺序）
- finalize: 合并所有段落并添加BGM
"""

import cv2
import numpy as np
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.api_renderer import ApiVlogRenderer
from src.session_manager import SessionManager, SegmentInfo
from src.video import VideoReader, create_encoder
from src.shaders import create_transition_shader, load_transitions


class IncrementalRenderer(ApiVlogRenderer):
    """增量渲染器 - 继承自 ApiVlogRenderer"""
    
    def __init__(self, session_id: str, template_name: str):
        """初始化增量渲染器
        
        Args:
            session_id: 会话ID
            template_name: 模板名称
        """
        # 不调用父类初始化（因为不需要完整的文件列表）
        from src.config import TemplateConfig
        
        self.session_id = session_id
        self.config = TemplateConfig(template_name)
        
        # 加载配置参数
        self.WIDTH = self.config.global_config["width"]
        self.HEIGHT = self.config.global_config["height"]
        self.FPS = self.config.global_config["fps"]
        self.IMAGE_DURATION = self.config.global_config["image_duration"]
        self.VIDEO_DURATION = self.config.global_config["video_duration"]
        self.TRANSITION_DURATION = self.config.global_config["transition_duration"]
        
        # 计算帧数
        self.FRAME_SIZE = self.WIDTH * self.HEIGHT * 3
        self.IMAGE_FRAMES = int(self.IMAGE_DURATION * self.FPS)
        self.VIDEO_FRAMES = int(self.VIDEO_DURATION * self.FPS)
        self.TRANS_FRAMES = int(self.TRANSITION_DURATION * self.FPS)
        
        # 加载所有转场效果
        self.transitions = load_transitions(self.config.transitions)
        print(f"🎬 增量渲染器初始化 - 模板: {self.config.name}")
        print(f"   转场数量: {len(self.transitions)}")
    
    def render_init(self, image_path: str):
        """渲染初始图片段落（图片 + 字幕）
        
        Args:
            image_path: 图片路径
        
        Returns:
            segment_index: 段落索引
        """
        print(f"\n🖼️  渲染初始图片段落...")
        print(f"   图片: {image_path}")
        print(f"   时长: {self.IMAGE_DURATION}秒 ({self.IMAGE_FRAMES}帧)")
        
        # 初始化 GPU 环境
        self.setup_gpu()
        self.setup_overlays()
        
        # 获取段落文件路径
        segment_index = 0
        segment_path = SessionManager.get_segment_path(self.session_id, segment_index)
        
        # 创建编码器
        encoder = create_encoder(self.WIDTH, self.HEIGHT, self.FPS, str(segment_path))
        
        # 使用BorderRenderer将图片复合到边框上
        position_config = self.config.config.get("image_position", {})
        composited_img_data = self.image_border_renderer.composite_image_on_border(
            image_path, position_config
        )
        
        # 生成字幕
        now = datetime.now()
        subtitle_template = self.config.subtitle.get("template", "")
        full_subtitle_text = subtitle_template.format(
            year=now.year, month=now.month, day=now.day
        )
        typewriter_speed = self.config.subtitle.get("typewriter_speed", 3)
        subtitle_duration = self.config.subtitle.get("duration", 6.0)
        subtitle_frames = int(subtitle_duration * self.FPS)
        
        print(f"   📝 字幕: {full_subtitle_text}")
        
        # 渲染图片帧（带字幕打字机效果）
        for frame_idx in range(self.IMAGE_FRAMES):
            # 计算字幕文本
            subtitle_text = None
            if frame_idx < subtitle_frames:
                chars_to_show = (frame_idx // typewriter_speed) + 1
                subtitle_text = full_subtitle_text[:chars_to_show]
            
            # 渲染帧（叠加字幕）
            if subtitle_text:
                subtitle_data = self.subtitle_renderer.render_text(
                    subtitle_text,
                    color=tuple(self.config.font["color"]),
                    outline_color=tuple(self.config.font["outline_color"]),
                    outline_width=self.config.font["outline_width"],
                )
                self.subtitle_tex.write(subtitle_data)
                
                self.temp_tex.write(composited_img_data)
                self.subtitle_fbo.use()
                self.temp_tex.use(0)
                self.subtitle_tex.use(1)
                self.subtitle_vao.render()
                final_frame = self.subtitle_fbo.read(components=3)
                
                self.fbo.use()
            else:
                final_frame = composited_img_data
            
            encoder.stdin.write(final_frame)
        
        # 关闭编码器
        encoder.stdin.close()
        encoder.wait()
        
        # 保存最后一帧（用于下次转场）
        last_frame_png = cv2.imencode('.png', 
            np.frombuffer(final_frame, dtype=np.uint8).reshape(self.HEIGHT, self.WIDTH, 3)[::-1]
        )[1].tobytes()
        SessionManager.save_last_frame(self.session_id, last_frame_png)
        
        # 记录段落信息
        segment = SegmentInfo(
            index=segment_index,
            frames=self.IMAGE_FRAMES,
            type='image',
            source_path=image_path
        )
        SessionManager.add_segment(self.session_id, segment)
        
        print(f"   ✅ 图片段落渲染完成 (segment_{segment_index}.h264)")
        return segment_index
    
    def render_append(self, video_path: str) -> int:
        """追加视频段落（转场 + 视频）
        
        Args:
            video_path: 视频路径
        
        Returns:
            segment_index: 新段落索引
        """
        print(f"\n🎥 追加视频段落...")
        print(f"   视频: {video_path}")
        
        # 获取下一个段落索引
        metadata = SessionManager.get_metadata(self.session_id)
        segment_index = len(metadata.segments)
        segment_path = SessionManager.get_segment_path(self.session_id, segment_index)
        
        # 加载上一帧
        last_frame_png = SessionManager.load_last_frame(self.session_id)
        if not last_frame_png:
            raise ValueError("未找到上一帧缓存，无法进行转场")
        
        # 解码上一帧
        last_frame_np = cv2.imdecode(
            np.frombuffer(last_frame_png, dtype=np.uint8), 
            cv2.IMREAD_COLOR
        )
        last_frame_rgb = cv2.cvtColor(last_frame_np, cv2.COLOR_BGR2RGB)[::-1]
        last_frame_bytes = last_frame_rgb.tobytes()
        
        # 创建编码器
        encoder = create_encoder(self.WIDTH, self.HEIGHT, self.FPS, str(segment_path))
        
        # 加载视频
        video_reader = VideoReader(
            video_path,
            self.WIDTH,
            self.HEIGHT,
            self.FPS,
            self.FRAME_SIZE,
            self.VIDEO_DURATION,
        )
        
        # 获取转场效果（按顺序循环）
        transition_index = SessionManager.get_next_transition_index(
            self.session_id, 
            len(self.transitions)
        )
        transition = self.transitions[transition_index]
        print(f"   ✨ 转场 #{transition_index}: {transition['name']}")
        
        # 创建转场着色器
        prog = create_transition_shader(self.ctx, transition["source"])
        vao = self._create_vao(prog)
        self.tex0.use(0)
        self.tex1.use(1)
        prog["tex0"].value = 0
        prog["tex1"].value = 1
        if "ratio" in prog:
            prog["ratio"].value = self.WIDTH / self.HEIGHT
        
        # 渲染转场帧
        print(f"   🔄 渲染转场: {self.TRANS_FRAMES}帧")
        transition_frames = []
        for j in range(self.TRANS_FRAMES):
            self.tex0.write(last_frame_bytes)
            self.tex1.write(video_reader.read_frame())
            prog["progress"].value = (j + 1) / self.TRANS_FRAMES
            
            self.fbo.use()
            self.tex0.use(0)
            self.tex1.use(1)
            vao.render()
            
            # 叠加视频边框
            final_frame = self.render_frame_with_border(use_image_border=False)
            encoder.stdin.write(final_frame)
            transition_frames.append(final_frame)
        
        # 渲染剩余视频帧
        remaining_frames = self.VIDEO_FRAMES - self.TRANS_FRAMES
        print(f"   🎞️  渲染视频: {remaining_frames}帧")
        
        last_video_frame = None
        for _ in range(remaining_frames):
            frame = video_reader.read_frame()
            self.tex0.write(frame)
            
            # 叠加视频边框
            final_frame = self.render_frame_with_border(use_image_border=False)
            encoder.stdin.write(final_frame)
            last_video_frame = final_frame
        
        # 关闭编码器
        encoder.stdin.close()
        encoder.wait()
        video_reader.close()
        
        # 保存最后一帧
        last_frame_png = cv2.imencode('.png',
            np.frombuffer(last_video_frame, dtype=np.uint8).reshape(self.HEIGHT, self.WIDTH, 3)[::-1]
        )[1].tobytes()
        SessionManager.save_last_frame(self.session_id, last_frame_png)
        
        # 记录段落信息
        segment = SegmentInfo(
            index=segment_index,
            frames=self.TRANS_FRAMES + remaining_frames,
            type='video',
            source_path=video_path,
            transition_shader=transition['name']
        )
        SessionManager.add_segment(self.session_id, segment)
        
        print(f"   ✅ 视频段落渲染完成 (segment_{segment_index}.h264)")
        return segment_index
    
    def finalize(self, output_path: Optional[str] = None) -> str:
        """合并所有段落并添加BGM
        
        Args:
            output_path: 输出文件路径（可选，默认保存在会话目录）
        
        Returns:
            最终视频路径
        """
        print(f"\n🎵 最终合成...")
        
        session_path = SessionManager.get_session_path(self.session_id)
        
        # 获取所有段落文件
        segment_files = SessionManager.list_segment_files(self.session_id)
        print(f"   段落数量: {len(segment_files)}")
        
        # 创建 concat 列表
        concat_list = session_path / "concat.txt"
        concat_list.write_text("\n".join([f"file '{f}'" for f in segment_files]))
        
        # 输出路径
        if not output_path:
            output_path = session_path / f"final_{self.session_id}.mp4"
        else:
            output_path = Path(output_path)
        
        # 第一步：使用 concat 协议合并视频段落（无重编码）
        temp_concat = session_path / "temp_concat.mp4"
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "copy",  # 关键：直接复制视频流
            "-movflags", "+faststart",
            str(temp_concat)
        ]
        
        print(f"   🔗 合并段落...")
        subprocess.run(concat_cmd, check=True, capture_output=True)
        
        # 第二步：添加BGM
        bgm_path = self.config.bgm.get("path")
        if bgm_path and Path(bgm_path).exists():
            print(f"   🎵 添加BGM: {bgm_path}")
            
            bgm_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_concat),
                "-stream_loop", "-1",  # 循环BGM
                "-i", bgm_path,
                "-c:v", "copy",  # 视频流直接复制
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",  # 以视频长度为准
                "-movflags", "+faststart",
                str(output_path)
            ]
            
            subprocess.run(bgm_cmd, check=True, capture_output=True)
            temp_concat.unlink()  # 删除临时文件
        else:
            # 没有BGM，直接使用合并后的文件
            print(f"   ⚠️  未配置BGM")
            temp_concat.rename(output_path)
        
        print(f"   ✅ 最终合成完成: {output_path}")
        
        # 更新会话状态
        SessionManager.update_metadata(self.session_id, {
            'status': 'completed',
            'output_path': str(output_path)
        })
        
        return str(output_path)
    
    def cleanup(self):
        """清理 GPU 资源"""
        if hasattr(self, 'ctx'):
            self.ctx.release()
