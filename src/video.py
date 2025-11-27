"""
视频处理模块 - FFmpeg 解码和编码
"""
import subprocess
import ffmpeg
import os


class VideoReader:
    """FFmpeg 视频解码器，流式读取帧数据"""

    def __init__(self, filename, width, height, fps, frame_size, trim_duration):
        self.filename = filename
        self.frame_size = frame_size
        self.last_valid_frame = bytes([0] * frame_size)
        self.eof_reached = False

        self.process = (
            ffmpeg.input(filename, ss=0)
            .filter("setpts", "PTS-STARTPTS")
            .filter("scale", width, height)
            .filter("fps", fps=fps, round="up")
            .trim(duration=trim_duration)
            .output("pipe:", format="rawvideo", pix_fmt="rgb24")
            .run_async(pipe_stdout=True, quiet=True)
        )

        self._preload_first_frame()

    def _preload_first_frame(self):
        """阻塞式读取首帧，确保视频就绪"""
        print(f"   ⏳ 预读 {self.filename}...", end="", flush=True)
        in_bytes = self.process.stdout.read(self.frame_size)

        if len(in_bytes) == self.frame_size:
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

        in_bytes = self.process.stdout.read(self.frame_size)
        if len(in_bytes) == self.frame_size:
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


def create_encoder(width, height, fps, output_path):
    """创建 FFmpeg NVENC 编码器"""
    print("🎥 启动编码器...")
    return (
        ffmpeg.input(
            "pipe:", format="rawvideo", pix_fmt="rgb24", s=f"{width}x{height}", r=fps
        )
        .output(
            output_path,
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


def merge_audio(video_path, bgm_path, output_path):
    """合并 BGM 到视频"""
    if not os.path.exists(bgm_path):
        os.rename(video_path, output_path)
        return

    print("🎵 合成 BGM...")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-ss",
            "0",
            "-stream_loop",
            "-1",
            "-i",
            bgm_path,
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
            output_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove(video_path)
