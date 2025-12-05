"""
会话管理器 - 基于文件系统的轻量级会话存储

负责管理增量渲染会话的生命周期：
- 创建会话目录和元数据
- 读写会话状态
- 保存/加载最后一帧缓存
- 管理段落文件
"""

import json
import time
import uuid
import shutil
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict


# 会话根目录
SESSION_DIR = Path("/tmp/autovlog_sessions")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SegmentInfo:
    """段落信息"""
    index: int
    frames: int
    type: str  # 'image', 'video', 'transition'
    source_path: Optional[str] = None
    transition_shader: Optional[str] = None


@dataclass
class SessionMetadata:
    """会话元数据"""
    session_id: str
    template_name: str
    created_at: float
    total_frames: int
    segments: List[Dict]
    status: str  # 'initialized', 'rendering', 'completed', 'error'
    current_transition_index: int = 0  # 当前使用的转场索引
    
    def to_dict(self):
        return asdict(self)
    
    @staticmethod
    def from_dict(data: dict) -> 'SessionMetadata':
        # 不要 pop，直接传入所有字段
        return SessionMetadata(**data)


class SessionManager:
    """文件系统会话管理器"""
    
    @staticmethod
    def create_session(template_name: str) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        session_path = SESSION_DIR / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        (session_path / "segments").mkdir(exist_ok=True)
        
        # 初始化元数据
        metadata = SessionMetadata(
            session_id=session_id,
            template_name=template_name,
            created_at=time.time(),
            total_frames=0,
            segments=[],
            status="initialized",
            current_transition_index=0
        )
        
        SessionManager._save_metadata(session_id, metadata)
        print(f"✅ 会话创建成功: {session_id}")
        return session_id
    
    @staticmethod
    def get_session_path(session_id: str) -> Path:
        """获取会话目录路径"""
        return SESSION_DIR / session_id
    
    @staticmethod
    def get_metadata(session_id: str) -> SessionMetadata:
        """读取会话元数据"""
        path = SESSION_DIR / session_id / "metadata.json"
        if not path.exists():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        
        data = json.loads(path.read_text())
        return SessionMetadata.from_dict(data)
    
    @staticmethod
    def update_metadata(session_id: str, updates: Dict):
        """更新会话元数据"""
        metadata = SessionManager.get_metadata(session_id)
        
        # 更新字段
        for key, value in updates.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
        
        SessionManager._save_metadata(session_id, metadata)
    
    @staticmethod
    def _save_metadata(session_id: str, metadata: SessionMetadata):
        """保存元数据到文件"""
        path = SESSION_DIR / session_id / "metadata.json"
        path.write_text(json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False))
    
    @staticmethod
    def add_segment(session_id: str, segment: SegmentInfo) -> int:
        """添加新段落信息"""
        metadata = SessionManager.get_metadata(session_id)
        segment_dict = asdict(segment)
        metadata.segments.append(segment_dict)
        metadata.total_frames += segment.frames
        
        SessionManager._save_metadata(session_id, metadata)
        return len(metadata.segments) - 1
    
    @staticmethod
    def save_last_frame(session_id: str, frame_data: bytes):
        """保存最后一帧（PNG格式）"""
        path = SESSION_DIR / session_id / "last_frame.png"
        path.write_bytes(frame_data)
    
    @staticmethod
    def load_last_frame(session_id: str) -> Optional[bytes]:
        """加载最后一帧"""
        path = SESSION_DIR / session_id / "last_frame.png"
        if not path.exists():
            return None
        return path.read_bytes()
    
    @staticmethod
    def get_segment_path(session_id: str, segment_index: int) -> Path:
        """获取段落文件路径"""
        return SESSION_DIR / session_id / "segments" / f"segment_{segment_index}.h264"
    
    @staticmethod
    def list_segment_files(session_id: str) -> List[Path]:
        """列出所有段落文件（按顺序）"""
        segments_dir = SESSION_DIR / session_id / "segments"
        return sorted(segments_dir.glob("segment_*.h264"))
    
    @staticmethod
    def get_next_transition_index(session_id: str, total_transitions: int) -> int:
        """获取下一个转场索引（循环使用）"""
        metadata = SessionManager.get_metadata(session_id)
        current_index = metadata.current_transition_index
        
        # 更新到下一个（循环）
        next_index = (current_index + 1) % total_transitions
        SessionManager.update_metadata(session_id, {
            'current_transition_index': next_index
        })
        
        return current_index
    
    @staticmethod
    def cleanup_session(session_id: str, keep_final_video: bool = True):
        """清理会话文件
        
        Args:
            session_id: 会话ID
            keep_final_video: 是否保留最终视频
        """
        session_path = SESSION_DIR / session_id
        if not session_path.exists():
            return
        
        if keep_final_video:
            # 仅删除中间文件，保留 metadata.json 用于状态查询
            items_to_delete = [
                session_path / "segments",
                session_path / "last_frame.png",
                session_path / "concat.txt",
            ]
            for item in items_to_delete:
                if item.exists():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            print(f"🧹 会话清理完成（保留最终视频和元数据）: {session_id}")
        else:
            # 删除整个会话目录
            shutil.rmtree(session_path)
            print(f"🧹 会话完全删除: {session_id}")
    
    @staticmethod
    def list_all_sessions() -> List[str]:
        """列出所有会话ID"""
        return [d.name for d in SESSION_DIR.iterdir() if d.is_dir()]
    
    @staticmethod
    def session_exists(session_id: str) -> bool:
        """检查会话是否存在"""
        return (SESSION_DIR / session_id).exists()
