#!/usr/bin/env python3
"""
启动Web服务脚本
同时启动 FastAPI 后端和 Streamlit 前端
"""

import subprocess
import time
import sys
import os
import signal
from threading import Thread

def start_fastapi():
    """启动 FastAPI 后端"""
    print("🚀 启动 FastAPI 后端服务...")
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "route_agent_api:app", 
            "--host", "127.0.0.1", 
            "--port", "8000", 
            "--reload"
        ], check=True)
    except KeyboardInterrupt:
        print("⭐ FastAPI 服务已停止")
    except Exception as e:
        print(f"❌ FastAPI 启动失败: {e}")

def start_streamlit():
    """启动 Streamlit 前端"""
    print("🎨 启动 Streamlit 前端界面...")
    try:
        # 等待 FastAPI 启动
        time.sleep(3)
        subprocess.run([
            sys.executable, "-m", "streamlit", 
            "run", "streamlit_app.py", 
            "--server.port", "8501",
            "--server.address", "127.0.0.1"
        ], check=True)
    except KeyboardInterrupt:
        print("⭐ Streamlit 服务已停止")
    except Exception as e:
        print(f"❌ Streamlit 启动失败: {e}")

def main():
    """主启动函数"""
    print("🗺️ 智能路径规划Web服务启动器")
    print("=" * 50)
    
    # 检查依赖
    print("📦 检查依赖...")
    try:
        import fastapi
        import streamlit
        import requests
        print("✅ 依赖检查通过")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install -r requirements_web.txt")
        return
    
    # 检查环境变量
    if not os.getenv("AMAP_API_KEY") or not os.getenv("OPENAI_API_KEY"):
        print("⚠️ 警告: 请确保在 .env 文件中设置了 AMAP_API_KEY 和 OPENAI_API_KEY")
    
    print("\n🚀 启动服务...")
    print("FastAPI 后端: http://localhost:8000")
    print("Streamlit 前端: http://localhost:8501")
    print("\n按 Ctrl+C 停止服务")
    print("=" * 50)
    
    # 启动后端和前端
    try:
        # 在后台启动 FastAPI
        fastapi_thread = Thread(target=start_fastapi, daemon=True)
        fastapi_thread.start()
        
        # 启动 Streamlit (主进程)
        start_streamlit()
        
    except KeyboardInterrupt:
        print("\n🛑 正在停止服务...")
        print("✅ 服务已停止")

if __name__ == "__main__":
    main() 