"""
FastAPI HTTP 服务 - GPU 加速视频渲染

功能：
- 接收模板名称、视频列表和图片
- 异步渲染视频
- 返回视频访问地址

启动：
    uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator
import logging

from src.api_renderer import ApiVlogRenderer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="GPU Video Renderer API",
    description="GPU 加速视频渲染服务 - 支持模板化配置",
    version="1.0.0"
)

# 输出目录配置
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# 挂载静态文件服务
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

# 任务状态存储
task_storage = {}


class RenderRequest(BaseModel):
    """渲染请求模型"""
    template: str = Field(..., description="模板名称 (classic/modern/elegant)")
    image_path: str = Field(..., description="图片路径（本机目录路径）")
    video_paths: List[str] = Field(
        ..., 
        min_items=1, 
        max_items=5, 
        description="视频路径列表（1-5个）"
    )
    
    @validator('image_path')
    def validate_image_path(cls, v):
        if not os.path.exists(v):
            raise ValueError(f"图片文件不存在: {v}")
        if not v.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
            raise ValueError(f"不支持的图片格式: {v}")
        return v
    
    @validator('video_paths')
    def validate_video_paths(cls, v):
        for path in v:
            if not os.path.exists(path):
                raise ValueError(f"视频文件不存在: {path}")
            if not path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                raise ValueError(f"不支持的视频格式: {path}")
        return v


class RenderResponse(BaseModel):
    """渲染响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态 (pending/processing/completed/failed)")
    video_url: Optional[str] = Field(None, description="视频访问地址")
    message: str = Field(..., description="状态消息")
    created_at: str = Field(..., description="创建时间")


class TaskStatus(BaseModel):
    """任务状态模型"""
    task_id: str
    status: str
    video_url: Optional[str] = None
    error: Optional[str] = None
    progress: float = 0.0
    created_at: str
    completed_at: Optional[str] = None


async def render_video_task(task_id: str, request: RenderRequest, base_url: str):
    """异步渲染任务"""
    try:
        task_storage[task_id]["status"] = "processing"
        task_storage[task_id]["progress"] = 0.1
        
        logger.info(f"开始渲染任务: {task_id}")
        logger.info(f"模板: {request.template}")
        logger.info(f"图片: {request.image_path}")
        logger.info(f"视频数量: {len(request.video_paths)}")
        
        # 生成输出文件名
        output_filename = f"{task_id}.mp4"
        output_path = OUTPUT_DIR / output_filename
        
        # 创建渲染器
        renderer = ApiVlogRenderer(
            template_name=request.template,
            image_path=request.image_path,
            video_paths=request.video_paths,
            output_file=str(output_path)
        )
        
        # 执行渲染
        await asyncio.to_thread(renderer.render)
        
        # 更新任务状态
        task_storage[task_id]["status"] = "completed"
        task_storage[task_id]["progress"] = 1.0
        task_storage[task_id]["video_url"] = f"{base_url}/videos/{output_filename}"
        task_storage[task_id]["completed_at"] = datetime.now().isoformat()
        
        logger.info(f"任务完成: {task_id}")
        
    except Exception as e:
        logger.error(f"任务失败 {task_id}: {str(e)}", exc_info=True)
        task_storage[task_id]["status"] = "failed"
        task_storage[task_id]["error"] = str(e)
        task_storage[task_id]["completed_at"] = datetime.now().isoformat()


@app.get("/")
async def root():
    """API 根路径"""
    return {
        "service": "GPU Video Renderer API",
        "version": "1.0.0",
        "endpoints": {
            "render": "POST /api/render",
            "status": "GET /api/status/{task_id}",
            "templates": "GET /api/templates",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/templates")
async def list_templates():
    """列出所有可用模板"""
    from src.config import TemplateConfig
    templates = TemplateConfig.list_available_templates()
    
    template_info = []
    for tmpl in templates:
        try:
            cfg = TemplateConfig(tmpl)
            template_info.append({
                "name": tmpl,
                "display_name": cfg.config.get("name", tmpl),
                "description": cfg.config.get("description", "")
            })
        except Exception as e:
            logger.warning(f"加载模板 {tmpl} 失败: {e}")
    
    return {
        "templates": template_info,
        "count": len(template_info)
    }


@app.post("/api/render", response_model=RenderResponse)
async def create_render_task(
    request: RenderRequest, 
    background_tasks: BackgroundTasks
):
    """
    创建渲染任务
    
    - **template**: 模板名称 (classic/modern/elegant)
    - **image_path**: 图片路径（本机绝对路径）
    - **video_paths**: 视频路径列表（1-5个本机绝对路径）
    
    返回任务ID和状态查询地址
    """
    # 生成任务ID
    task_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    
    # 初始化任务状态
    task_storage[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "video_url": None,
        "error": None,
        "progress": 0.0,
        "created_at": created_at,
        "completed_at": None,
        "request": request.dict()
    }
    
    # 获取请求的基础URL
    base_url = "http://localhost:8000"  # 可以从请求头中获取
    
    # 添加后台任务
    background_tasks.add_task(render_video_task, task_id, request, base_url)
    
    return RenderResponse(
        task_id=task_id,
        status="pending",
        video_url=None,
        message="任务已创建，正在队列中等待处理",
        created_at=created_at
    )


@app.get("/api/status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    查询任务状态
    
    - **task_id**: 任务ID
    """
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskStatus(**task_storage[task_id])


@app.get("/api/video/{task_id}")
async def get_video(task_id: str):
    """
    下载视频文件
    
    - **task_id**: 任务ID
    """
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = task_storage[task_id]
    
    if task["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"视频尚未完成，当前状态: {task['status']}"
        )
    
    video_path = OUTPUT_DIR / f"{task_id}.mp4"
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"render_{task_id}.mp4"
    )


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """
    删除任务和关联的视频文件
    
    - **task_id**: 任务ID
    """
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 删除视频文件
    video_path = OUTPUT_DIR / f"{task_id}.mp4"
    if video_path.exists():
        video_path.unlink()
    
    # 删除任务记录
    del task_storage[task_id]
    
    return {"message": "任务已删除", "task_id": task_id}


@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None):
    """
    列出所有任务
    
    - **status**: 可选，筛选状态 (pending/processing/completed/failed)
    """
    tasks = list(task_storage.values())
    
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    
    return {
        "tasks": tasks,
        "count": len(tasks)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
