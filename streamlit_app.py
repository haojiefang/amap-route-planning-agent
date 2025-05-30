#!/usr/bin/env python3
"""
路径规划智能体 - Streamlit 前端界面
简洁的聊天式交互界面
"""

import streamlit as st
import requests
import json
import time
from typing import Dict, Any

# 页面配置
st.set_page_config(
    page_title="🗺️ 路径规划助手",
    page_icon="🗺️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# API 配置
API_BASE_URL = "http://localhost:8000"

def call_api(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """调用 API"""
    try:
        response = requests.post(f"{API_BASE_URL}{endpoint}", json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "❌ 无法连接到API服务，请确保后端服务正在运行"}
    except requests.exceptions.Timeout:
        return {"success": False, "message": "❌ 请求超时，请稍后重试"}
    except Exception as e:
        return {"success": False, "message": f"❌ API调用失败: {str(e)}"}

def format_markdown_result(text: str) -> str:
    """格式化结果为更好的markdown显示"""
    return text

def main():
    # 简洁标题
    st.title("🗺️ 路径规划助手")
    
    # 会话状态管理
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"session_{int(time.time())}"
    
    # 显示对话历史
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 用户输入
    if prompt := st.chat_input("请输入路径规划需求，如：从莲花山到壹方城怎么走"):
        # 显示用户消息
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # 显示思考状态
        with st.chat_message("assistant"):
            with st.spinner("🤔 正在规划路径..."):
                # 调用 API
                api_data = {
                    "user_input": prompt,
                    "session_id": st.session_state.session_id
                }
                
                result = call_api("/route", api_data)
                
                if result.get("success"):
                    response = format_markdown_result(result["message"])
                else:
                    response = result.get("message", "❌ 未知错误")
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
    
    # 简单的清除按钮（放在侧边栏）
    with st.sidebar:
        st.markdown("---")
        if st.button("🗑️ 清除对话", use_container_width=True):
            # 清除服务器端会话状态
            try:
                requests.delete(f"{API_BASE_URL}/session/{st.session_state.session_id}", timeout=5)
            except:
                pass
            
            # 清除本地状态
            st.session_state.messages = []
            st.session_state.session_id = f"session_{int(time.time())}"
            st.rerun()

if __name__ == "__main__":
    main() 