#!/usr/bin/env python3
"""
测试增量渲染功能

测试流程：
1. 初始化会话 - 渲染首张图片
2. 追加第一段视频
3. 追加第二段视频
4. 最终合成并添加BGM

验证：
- 转场顺序是否按照模板定义循环使用
- 视频质量是否无损
- 文件是否正确清理
"""

import requests
import time
from pathlib import Path

# API 配置
API_BASE = "http://localhost:8001/api"

# 测试资源路径（容器内路径）
TEMPLATE = "classic"
IMAGE_PATH = "/app/examples/images/00001.jpg"
VIDEO_PATHS = [
    "/app/examples/videos/video1.mp4",
    "/app/examples/videos/video2.mp4",
]


def test_incremental_render():
    """测试增量渲染完整流程"""
    
    print("=" * 60)
    print("🧪 增量渲染测试")
    print("=" * 60)
    
    # 步骤1: 初始化会话
    print("\n[1/4] 初始化会话 - 渲染首张图片")
    print(f"   图片: {IMAGE_PATH}")
    print(f"   模板: {TEMPLATE}")
    
    init_response = requests.post(
        f"{API_BASE}/render/init",
        json={
            "template": TEMPLATE,
            "image_path": IMAGE_PATH
        }
    )
    
    if init_response.status_code != 200:
        print(f"❌ 初始化失败: {init_response.text}")
        return
    
    init_data = init_response.json()
    session_id = init_data["session_id"]
    print(f"✅ 初始化成功")
    print(f"   会话ID: {session_id}")
    print(f"   段落索引: {init_data['segment_index']}")
    
    # 步骤2: 追加第一段视频
    print(f"\n[2/4] 追加第一段视频")
    print(f"   视频: {VIDEO_PATHS[0]}")
    
    append1_response = requests.post(
        f"{API_BASE}/render/append",
        json={
            "session_id": session_id,
            "video_path": VIDEO_PATHS[0]
        }
    )
    
    if append1_response.status_code != 200:
        print(f"❌ 追加失败: {append1_response.text}")
        return
    
    append1_data = append1_response.json()
    print(f"✅ 第一段视频追加成功")
    print(f"   段落索引: {append1_data['segment_index']}")
    print(f"   使用转场: {append1_data['transition_used']}")
    
    # 步骤3: 追加第二段视频
    print(f"\n[3/4] 追加第二段视频")
    print(f"   视频: {VIDEO_PATHS[1]}")
    
    append2_response = requests.post(
        f"{API_BASE}/render/append",
        json={
            "session_id": session_id,
            "video_path": VIDEO_PATHS[1]
        }
    )
    
    if append2_response.status_code != 200:
        print(f"❌ 追加失败: {append2_response.text}")
        return
    
    append2_data = append2_response.json()
    print(f"✅ 第二段视频追加成功")
    print(f"   段落索引: {append2_data['segment_index']}")
    print(f"   使用转场: {append2_data['transition_used']}")
    
    # 步骤4: 最终合成
    print(f"\n[4/4] 最终合成 - 添加BGM")
    
    finalize_response = requests.post(
        f"{API_BASE}/render/finalize",
        json={
            "session_id": session_id
        }
    )
    
    if finalize_response.status_code != 200:
        print(f"❌ 合成失败: {finalize_response.text}")
        return
    
    finalize_data = finalize_response.json()
    print(f"✅ 视频合成完成")
    print(f"   视频URL: {finalize_data['video_url']}")
    print(f"   总段落数: {finalize_data['total_segments']}")
    
    # 查询最终状态
    print(f"\n[验证] 查询会话状态")
    status_response = requests.get(f"{API_BASE}/render/status/{session_id}")
    
    if status_response.status_code == 200:
        status_data = status_response.json()
        print(f"   状态: {status_data['status']}")
        print(f"   总帧数: {status_data['total_frames']}")
        print(f"   段落列表:")
        for seg in status_data['segments']:
            print(f"     - 段落 {seg['index']}: {seg['type']} | {seg['frames']}帧")
            if seg.get('transition_shader'):
                print(f"       转场: {seg['transition_shader']}")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    
    print(f"\n📹 最终视频: {finalize_data['video_url']}")
    print("\n💡 验证要点:")
    print("   1. 转场顺序应该循环使用模板定义的转场列表")
    print("   2. 视频应该流畅无卡顿（无重编码损失）")
    print("   3. BGM应该正确添加")
    print("   4. 中间文件应该被自动清理")


def test_status_query():
    """测试状态查询（独立测试）"""
    print("\n" + "=" * 60)
    print("🧪 状态查询测试")
    print("=" * 60)
    
    # 使用一个假的会话ID测试404
    fake_session = "00000000-0000-0000-0000-000000000000"
    response = requests.get(f"{API_BASE}/render/status/{fake_session}")
    
    if response.status_code == 404:
        print(f"✅ 404错误处理正确: {response.json()}")
    else:
        print(f"❌ 应该返回404，实际: {response.status_code}")


if __name__ == "__main__":
    import sys
    
    print("\n🚀 启动增量渲染测试套件\n")
    
    # 检查API是否可用
    try:
        health_check = requests.get(f"{API_BASE.replace('/api', '')}/docs")
        if health_check.status_code == 200:
            print("✅ API服务运行中\n")
        else:
            print(f"⚠️  API服务状态异常: {health_check.status_code}\n")
    except Exception as e:
        print(f"❌ 无法连接到API服务: {e}")
        print("   请确保服务已启动: docker-compose up -d")
        sys.exit(1)
    
    # 运行测试
    try:
        test_incremental_render()
        test_status_query()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
