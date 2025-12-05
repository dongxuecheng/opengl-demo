"""
FastAPI HTTP 服务 - GPU 加速视频渲染

同步模式：直接返回视频URL字符串
"""

import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, validator
import logging

from src.api_renderer import ApiVlogRenderer
from src.incremental_renderer import IncrementalRenderer
from src.session_manager import SessionManager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(title="GPU Video Renderer API", version="1.0.0")

# 输出目录配置
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# 挂载静态文件服务
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")


# 自定义异常处理器：修复包含二进制数据和异常对象的验证错误
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    自定义请求验证异常处理器

    解决问题：
    1. 验证错误中包含二进制数据（如上传的文件）时，FastAPI默认的错误序列化
       会尝试将bytes解码为UTF-8，导致UnicodeDecodeError
    2. 验证错误的ctx中包含异常对象，无法被JSON序列化

    解决方案：递归清理错误信息，将所有不可序列化的对象转换为字符串
    """
    logger.info(f"🔧 自定义异常处理器被调用 - 错误数量: {len(exc.errors())}")

    def make_serializable(obj):
        """递归将对象转换为可JSON序列化的格式"""
        if isinstance(obj, bytes):
            # bytes转换为简短的十六进制预览
            preview = obj[:20].hex() if len(obj) > 20 else obj.hex()
            return f"<binary data: {preview}{'...' if len(obj) > 20 else ''}>"
        elif isinstance(obj, Exception):
            # 异常对象转换为字符串
            return f"{type(obj).__name__}: {str(obj)}"
        elif isinstance(obj, dict):
            # 递归处理字典
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            # 递归处理列表和元组
            return [make_serializable(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            # 基本类型直接返回
            return obj
        else:
            # 其他对象转换为字符串表示
            return str(obj)

    errors = []
    for error in exc.errors():
        # 递归清理整个错误字典
        clean_error = make_serializable(error)
        errors.append(clean_error)

    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )


class RenderRequest(BaseModel):
    """渲染请求模型"""

    template: str = Field(..., description="模板名称 (classic/modern/elegant)")
    image_path: str = Field(..., description="图片路径（本机目录路径）")
    video_paths: List[str] = Field(
        ..., min_items=1, max_items=5, description="视频路径列表（1-5个）"
    )

    @validator("image_path")
    def validate_image_path(cls, v):
        if not os.path.exists(v):
            raise ValueError(f"图片文件不存在: {v}")
        if not v.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
            raise ValueError(f"不支持的图片格式: {v}")
        return v

    @validator("video_paths")
    def validate_video_paths(cls, v):
        for path in v:
            if not os.path.exists(path):
                raise ValueError(f"视频文件不存在: {path}")
            if not path.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
                raise ValueError(f"不支持的视频格式: {path}")
        return v


@app.post("/api/render", response_class=PlainTextResponse)
def render_video(request: RenderRequest):
    """
    渲染视频接口

    - **template**: 模板名称 (classic/modern/elegant)
    - **image_path**: 图片路径（容器内绝对路径，如 /app/examples/cover.jpg）
    - **video_paths**: 视频路径列表（1-5个容器内绝对路径）

    返回视频URL字符串（同步阻塞，需等待10-60秒）
    """
    # 按时间命名文件：年月日时分.mp4
    now = datetime.now()
    output_filename = (
        f"{now.year}{now.month:02d}{now.day:02d}{now.hour:02d}{now.minute:02d}.mp4"
    )
    output_path = OUTPUT_DIR / output_filename

    # 获取基础URL
    base_url = os.getenv("API_BASE_URL", "http://localhost:8001")

    try:
        logger.info(f"开始渲染: {output_filename} | 模板: {request.template}")

        # 同步渲染
        renderer = ApiVlogRenderer(
            template_name=request.template,
            image_path=request.image_path,
            video_paths=request.video_paths,
            output_file=str(output_path),
        )
        renderer.render()

        video_url = f"{base_url}/videos/{output_filename}"
        logger.info(f"渲染完成: {output_filename}")

        # 直接返回URL字符串
        return video_url

    except Exception as e:
        logger.error(f"渲染失败 {output_filename}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"渲染失败: {str(e)}")


# ==================== 增量渲染 API ====================

class InitRequest(BaseModel):
    """初始化渲染请求"""
    template: str = Field(..., description="模板名称 (classic/modern/elegant)")
    image_path: str = Field(..., description="图片路径（本机目录路径）")
    
    @validator("image_path")
    def validate_image_path(cls, v):
        if not os.path.exists(v):
            raise ValueError(f"图片文件不存在: {v}")
        if not v.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
            raise ValueError(f"不支持的图片格式: {v}")
        return v


class AppendRequest(BaseModel):
    """追加视频请求"""
    session_id: str = Field(..., description="会话ID")
    video_path: str = Field(..., description="视频路径（本机目录路径）")
    
    @validator("video_path")
    def validate_video_path(cls, v):
        if not os.path.exists(v):
            raise ValueError(f"视频文件不存在: {v}")
        if not v.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
            raise ValueError(f"不支持的视频格式: {v}")
        return v


class FinalizeRequest(BaseModel):
    """完成合成请求"""
    session_id: str = Field(..., description="会话ID")
    output_filename: Optional[str] = Field(None, description="输出文件名（可选）")


@app.post("/api/render/init")
def render_init(request: InitRequest):
    """
    初始化渲染会话 - 渲染首张图片
    
    - **template**: 模板名称 (classic/modern/elegant)
    - **image_path**: 图片路径（容器内绝对路径）
    
    返回：
    ```json
    {
        "session_id": "uuid",
        "segment_index": 0,
        "status": "initialized",
        "message": "初始图片段落渲染完成"
    }
    ```
    """
    try:
        logger.info(f"🎬 初始化渲染会话 | 模板: {request.template}")
        
        # 创建会话
        session_id = SessionManager.create_session(request.template)
        
        # 创建渲染器并渲染初始图片
        renderer = IncrementalRenderer(session_id, request.template)
        segment_index = renderer.render_init(request.image_path)
        renderer.cleanup()
        
        logger.info(f"✅ 会话 {session_id} 初始化完成")
        
        return {
            "session_id": session_id,
            "segment_index": segment_index,
            "status": "initialized",
            "message": "初始图片段落渲染完成"
        }
        
    except Exception as e:
        logger.error(f"初始化失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")


@app.post("/api/render/append")
def render_append(request: AppendRequest):
    """
    追加视频段落
    
    - **session_id**: 会话ID
    - **video_path**: 视频路径（容器内绝对路径）
    
    返回：
    ```json
    {
        "session_id": "uuid",
        "segment_index": 1,
        "transition_used": "gridflip",
        "status": "rendering",
        "message": "视频段落追加完成"
    }
    ```
    """
    try:
        # 验证会话
        if not SessionManager.session_exists(request.session_id):
            raise HTTPException(status_code=404, detail=f"会话不存在: {request.session_id}")
        
        logger.info(f"🎥 追加视频 | 会话: {request.session_id}")
        
        # 获取模板名称
        metadata = SessionManager.get_metadata(request.session_id)
        
        # 创建渲染器并追加视频
        renderer = IncrementalRenderer(request.session_id, metadata.template_name)
        segment_index = renderer.render_append(request.video_path)
        renderer.cleanup()
        
        # 获取使用的转场
        updated_metadata = SessionManager.get_metadata(request.session_id)
        segment_info = updated_metadata.segments[segment_index]
        
        logger.info(f"✅ 会话 {request.session_id} 追加段落 {segment_index}")
        
        return {
            "session_id": request.session_id,
            "segment_index": segment_index,
            "transition_used": segment_info.get('transition_shader'),
            "status": "rendering",
            "message": "视频段落追加完成"
        }
        
    except Exception as e:
        logger.error(f"追加失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"追加失败: {str(e)}")


@app.post("/api/render/finalize")
def render_finalize(request: FinalizeRequest, background_tasks: BackgroundTasks):
    """
    完成合成 - 合并所有段落并添加BGM
    
    - **session_id**: 会话ID
    - **output_filename**: 输出文件名（可选，默认使用会话ID）
    
    返回：
    ```json
    {
        "session_id": "uuid",
        "video_url": "http://localhost:8001/videos/final_xxx.mp4",
        "total_segments": 3,
        "status": "completed",
        "message": "视频合成完成"
    }
    ```
    """
    try:
        # 验证会话
        if not SessionManager.session_exists(request.session_id):
            raise HTTPException(status_code=404, detail=f"会话不存在: {request.session_id}")
        
        logger.info(f"🎵 最终合成 | 会话: {request.session_id}")
        
        # 获取元数据
        metadata = SessionManager.get_metadata(request.session_id)
        
        # 确定输出路径
        if request.output_filename:
            output_path = OUTPUT_DIR / request.output_filename
        else:
            now = datetime.now()
            output_filename = f"final_{now.year}{now.month:02d}{now.day:02d}{now.hour:02d}{now.minute:02d}.mp4"
            output_path = OUTPUT_DIR / output_filename
        
        # 创建渲染器并完成合成
        renderer = IncrementalRenderer(request.session_id, metadata.template_name)
        final_video_path = renderer.finalize(str(output_path))
        renderer.cleanup()
        
        # 后台清理会话文件（保留最终视频）
        background_tasks.add_task(SessionManager.cleanup_session, request.session_id, True)
        
        # 生成视频URL
        base_url = os.getenv("API_BASE_URL", "http://localhost:8001")
        video_url = f"{base_url}/videos/{Path(final_video_path).name}"
        
        logger.info(f"✅ 会话 {request.session_id} 合成完成: {video_url}")
        
        return {
            "session_id": request.session_id,
            "video_url": video_url,
            "total_segments": len(metadata.segments),
            "status": "completed",
            "message": "视频合成完成"
        }
        
    except Exception as e:
        logger.error(f"合成失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"合成失败: {str(e)}")


@app.get("/api/render/status/{session_id}")
def get_render_status(session_id: str):
    """
    查询渲染会话状态
    
    返回：
    ```json
    {
        "session_id": "uuid",
        "template": "classic",
        "status": "rendering",
        "total_segments": 2,
        "total_frames": 600,
        "created_at": 1701763200.0
    }
    ```
    """
    try:
        if not SessionManager.session_exists(session_id):
            raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        
        metadata = SessionManager.get_metadata(session_id)
        
        return {
            "session_id": metadata.session_id,
            "template": metadata.template_name,
            "status": metadata.status,
            "total_segments": len(metadata.segments),
            "total_frames": metadata.total_frames,
            "created_at": metadata.created_at,
            "segments": metadata.segments
        }
        
    except Exception as e:
        logger.error(f"查询状态失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询状态失败: {str(e)}")
