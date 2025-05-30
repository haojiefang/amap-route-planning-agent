# 🗺️ 智能路径规划助手 (amap-route-planning-agent)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-red.svg)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个基于自然语言交互的智能路径规划系统，集成了高德地图API和GPT-4，为用户提供便捷的出行规划服务。

## ✨ 功能特性

### 🎯 核心功能

- **自然语言交互**：支持中文对话式路径规划
- **智能意图识别**：自动识别用户的路径规划需求
- **多城市支持**：支持全国范围内的路径规划
- **多种出行方式**：
  - 🚶‍♂️ 步行导航（距离≤1.5km）
  - 🚇 公共交通（距离>1.5km）
- **实时路况**：基于高德地图实时数据
- **智能纠错**：支持地址错误纠正

### 🚀 技术特性

- **现代化架构**：FastAPI + Streamlit 双服务架构
- **AI驱动**：集成GPT-4进行智能分析
- **MCP协议**：使用Model Context Protocol连接高德地图服务
- **会话管理**：支持多轮对话和上下文记忆
- **容错机制**：完善的错误处理和重试机制

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器
- 高德地图API密钥
- OpenAI API密钥

### 1. 克隆项目

```bash
git clone 
cd amap-route-planning-agent
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

创建 `.env` 文件：

```env
AMAP_API_KEY=your_amap_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

### 5. 启动服务

```bash
python app.py
```

服务启动后访问：

- **前端界面**: http://localhost:8501
- **API文档**: http://localhost:8000/docs

## 📖 使用指南

### 基本用法

1. 打开前端界面 http://localhost:8501
2. 在对话框中输入路径规划需求，例如：
   - "从莲花山到壹方城怎么走"
   - "我想从深圳北站到华强北"
   - "从广州塔到珠江新城地铁站的路线"

### 交互示例

**用户**: 从莲花山到壹方城怎么走

**助手**:

```
🗺️ 路径规划结果

📍 起点：莲花山 (深圳市福田区)
📍 终点：壹方城 (深圳市宝安区)
📏 距离：约15.2公里

🚇 推荐公共交通路线：
1. 步行至莲花山公园站 (3分钟)
2. 乘坐地铁2号线 → 福田站 (8分钟)
3. 换乘地铁1号线 → 宝安中心站 (25分钟)
4. 步行至壹方城 (5分钟)

⏱️ 总用时：约41分钟
💰 预计费用：7元
```

### 高级功能

#### 地址纠错

如果系统识别的地址有误，您可以直接纠正：

**用户**: 不对，我说的是宝安区的壹方城

**助手**: 明白了！我来重新为您规划到宝安区壹方城的路线...

#### 多轮对话

系统支持上下文记忆，可以进行多轮对话：

**用户**: 从莲花山到壹方城怎么走
**助手**: [提供路线规划]
**用户**: 如果开车呢？
**助手**: [提供驾车路线]

## 🔧 API 接口

### 路径规划接口

```http
POST /route
Content-Type: application/json

{
    "user_input": "从莲花山到壹方城怎么走",
    "session_id": "optional_session_id"
}
```

### 城市确认接口

```http
POST /confirm_city
Content-Type: application/json

{
    "session_id": "session_id",
    "city_input": "深圳"
}
```

详细API文档请访问：http://localhost:8000/docs

## 📁 项目结构

```
amap-route-planning-agent/
├── app.py                 # 应用启动器
├── route_agent_api.py     # FastAPI后端主文件
├── streamlit_app.py       # Streamlit前端界面
├── requirements.txt       # 依赖包列表
├── .env.example          # 环境变量模板
├── README.md             # 项目说明文档
└── docs/                 # 文档目录
    └── project_intro.html # 项目介绍页面
```

## 🛠️ 核心组件

### 1. SimpleRouteAgent (route_agent_api.py)

智能路径规划核心类，包含：

- **意图识别**：分析用户输入的真实意图
- **地址解析**：将自然语言转换为具体地址
- **路径规划**：调用高德地图API生成路线
- **结果格式化**：生成用户友好的输出

### 2. Streamlit前端 (streamlit_app.py)

提供简洁的Web界面：

- 聊天式交互界面
- 实时响应显示
- 会话状态管理
- 一键清除功能

### 3. FastAPI后端 (route_agent_api.py)

提供RESTful API服务：

- 异步处理机制
- CORS跨域支持
- 完整的错误处理
- 详细的日志记录

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📋 开发计划

### 近期计划

- [ ] 支持更多出行方式（驾车、骑行）
- [ ] 添加路线偏好设置（最快、最短、最少换乘）

## 📄 许可证

本项目基于 MIT 许可证开源 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [高德地图开放平台](https://lbs.amap.com/) - 提供地图数据和API服务
- [OpenAI](https://openai.com/) - 提供GPT模型支持
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的Python Web框架
- [Streamlit](https://streamlit.io/) - 简洁的数据应用框架

---

⭐ 如果这个项目对您有帮助，请给我们一个星标！

**作者**: haojiefang
