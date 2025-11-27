#!/usr/bin/env python3
"""
API 客户端测试脚本

使用方法:
    python test_api.py
"""
import requests
import time
import json

# API 配置
API_BASE = "http://localhost:8000"

def test_health():
    """测试健康检查"""
    print("=" * 60)
    print("1. 测试健康检查")
    print("=" * 60)
    
    response = requests.get(f"{API_BASE}/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_list_templates():
    """测试列出模板"""
    print("=" * 60)
    print("2. 测试列出模板")
    print("=" * 60)
    
    response = requests.get(f"{API_BASE}/api/templates")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()

def test_render_video():
    """测试视频渲染"""
    print("=" * 60)
    print("3. 测试视频渲染")
    print("=" * 60)
    
    # 创建渲染任务
    request_data = {
        "template": "classic",
        "image_path": "/app/examples/cover.jpg",  # 需要替换为实际路径
        "video_paths": [
            "/app/examples/v1.mp4",
            "/app/examples/v2.mp4"
        ]
    }
    
    print(f"请求数据: {json.dumps(request_data, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(
            f"{API_BASE}/api/render",
            json=request_data
        )
        
        if response.status_code != 200:
            print(f"❌ 请求失败: {response.status_code}")
            print(f"错误: {response.text}")
            return None
        
        task = response.json()
        task_id = task["task_id"]
        
        print(f"✅ 任务已创建:")
        print(f"   任务ID: {task_id}")
        print(f"   状态: {task['status']}")
        print()
        
        # 轮询任务状态
        print("开始轮询任务状态...")
        print("-" * 60)
        
        while True:
            response = requests.get(f"{API_BASE}/api/status/{task_id}")
            status = response.json()
            
            progress = status.get('progress', 0) * 100
            print(f"状态: {status['status']:12s} | 进度: {progress:5.1f}%", end='\r')
            
            if status["status"] == "completed":
                print()
                print("-" * 60)
                print(f"✅ 渲染完成！")
                print(f"   视频地址: {status['video_url']}")
                print(f"   耗时: {status.get('completed_at', 'N/A')}")
                return task_id
            
            elif status["status"] == "failed":
                print()
                print("-" * 60)
                print(f"❌ 渲染失败:")
                print(f"   错误: {status.get('error', 'Unknown')}")
                return None
            
            time.sleep(2)
    
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 API 服务器")
        print("   请确保服务已启动: python api_server.py")
        return None
    
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return None

def test_list_tasks():
    """测试列出任务"""
    print()
    print("=" * 60)
    print("4. 测试列出任务")
    print("=" * 60)
    
    response = requests.get(f"{API_BASE}/api/tasks")
    print(f"状态码: {response.status_code}")
    
    data = response.json()
    print(f"任务总数: {data['count']}")
    
    if data['tasks']:
        print("\n最近的任务:")
        for task in data['tasks'][:3]:
            print(f"  - {task['task_id'][:8]}... | {task['status']}")
    print()

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("GPU 视频渲染 API 测试脚本")
    print("=" * 60)
    print()
    
    # 1. 健康检查
    test_health()
    
    # 2. 列出模板
    test_list_templates()
    
    # 3. 渲染视频
    print("⚠️  注意: 请确保以下文件存在:")
    print("   - /app/examples/cover.jpg")
    print("   - /app/examples/v1.mp4")
    print("   - /app/examples/v2.mp4")
    print()
    
    choice = input("是否继续测试视频渲染? (y/n): ")
    if choice.lower() == 'y':
        task_id = test_render_video()
        
        if task_id:
            # 4. 列出任务
            test_list_tasks()
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
