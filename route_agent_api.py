#!/usr/bin/env python3
"""
路径规划智能体 - FastAPI 版本
提供 HTTP API 接口供前端调用
"""

import asyncio
import os
import json
import logging
import logging.handlers
from typing import Optional, Dict, List, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from dotenv import load_dotenv

# 配置日志 - 同时输出到文件和控制台
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 文件处理器
file_handler = logging.handlers.RotatingFileHandler(
    'route_agent.log', 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'  # 明确指定编码
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# 在Windows下处理控制台编码问题
import sys
if sys.platform.startswith('win'):
    try:
        # 尝试设置控制台为UTF-8
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')
    except:
        # 如果设置失败，就使用错误忽略模式
        console_handler.stream.errors = 'ignore'

# 添加处理器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 防止重复日志
logger.propagate = False

load_dotenv()
amap_api_key = os.getenv("AMAP_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

if not amap_api_key or not openai_api_key:
    raise ValueError("请在 .env 文件中设置 AMAP_API_KEY 和 OPENAI_API_KEY 环境变量")

# FastAPI 应用
app = FastAPI(title="路径规划智能体 API", version="1.0.0")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class RouteRequest(BaseModel):
    user_input: str
    session_id: Optional[str] = None

class CityConfirmation(BaseModel):
    session_id: str
    city_input: str

# 响应模型
class RouteResponse(BaseModel):
    success: bool
    message: str
    need_city_confirmation: bool = False
    session_id: Optional[str] = None

# 全局智能体实例
route_agent = None

# 新增会话状态管理
session_store = {}

class SessionData(BaseModel):
    locations: List[str] = []
    intent_result: Dict = {}
    city_analysis: Dict = {}
    stage: str = "start"  # start, waiting_city, processing

class SimpleRouteAgent:
    """简单路径规划智能体"""
    
    def __init__(self):
        self.amap_client = None
        self.amap_tools = None
        self.llm = None
        self._initialize_llm()
        
    def _initialize_llm(self):
        """初始化语言模型"""
        try:
            self.llm = ChatOpenAI(
                model="gpt-4o",
                openai_api_key=openai_api_key,
                temperature=0.1,
                timeout=30
            )
            logger.info("✅ LLM初始化成功")
        except Exception as e:
            logger.error(f"❌ LLM初始化失败: {e}")
            
    async def initialize(self):
        """初始化MCP客户端"""
        logger.info("🚀 初始化高德地图MCP客户端...")
        
        try:
            self.amap_client = MultiServerMCPClient({
                "amap": {
                    "url": f"https://mcp.amap.com/sse?key={amap_api_key}",
                    "transport": "sse",
                }
            })
            self.amap_tools = await self.amap_client.get_tools()
            logger.info(f"✅ 成功加载 {len(self.amap_tools)} 个高德地图工具")
        except Exception as e:
            logger.error(f"❌ MCP客户端初始化失败: {e}")
            self.amap_tools = []
        
    def get_tool(self, tool_name: str):
        """获取指定工具"""
        if not self.amap_tools:
            return None
        return next((tool for tool in self.amap_tools if tool.name == tool_name), None)

    async def step1_identify_intent(self, user_input: str) -> Dict:
        """步骤1: LLM识别用户意图"""
        logger.info(f"🧠 步骤1: 识别用户意图")
        
        system_prompt = """你是一个路径规划意图识别专家。你的任务是判断用户的意图类型。

请分析用户输入，返回JSON格式：

1. 如果用户想要路径规划（从A到B），返回：
{
  "intent_type": "route_request",
  "locations": ["地点A", "地点B"]
}

2. 如果用户在纠错或指出之前规划的错误，返回：
{
  "intent_type": "correction",
  "correction_info": "用户的纠错内容",
  "suggested_address": "用户建议的正确地址"
}

3. 如果都不是，返回：
{
  "intent_type": "other",
  "reason": "说明原因"
}

注意：
- 纠错通常包含"不对"、"错了"、"应该是"、"在XX区"等表述
- 地点名称保持用户原始表述
- 仔细识别用户是否在指出地址或规划错误"""

        user_message = f"用户输入：{user_input}"

        try:
            # 记录发送给LLM的提示词
            logger.info("📤 发送给LLM的提示词:")
            logger.info(f"SystemMessage: {system_prompt}")
            logger.info(f"HumanMessage: {user_message}")
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ]
            
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            # 记录LLM的响应
            logger.info(f"📥 LLM原始响应: {content}")
            
            # 简单JSON提取
            if '{' in content:
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)
            
            result = json.loads(content)
            
            logger.info(f"✅ 意图识别结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 意图识别失败: {e}")
            return {"intent_type": "other", "reason": "识别过程出错"}

    async def handle_correction(self, correction_info: str, suggested_address: str) -> str:
        """处理用户纠错"""
        logger.info(f"🔧 处理用户纠错: {correction_info}")
        
        # 让LLM从纠错信息中提取准确的地址
        extract_prompt = f"""用户指出了错误："{correction_info}"

请从用户的纠错中提取出准确的地址信息。

用户可能在说：
- 某个地点在某个区域（如"壹方城在宝安区"）
- 某个地点的准确名称（如"应该是宝安壹方城"）

请直接输出完整的地址格式，如：深圳市宝安区壹方城

只要地址，不要解释："""

        try:
            # 记录发送给LLM的提示词
            logger.info("📤 [纠错处理] 发送给LLM的提示词:")
            logger.info(f"SystemMessage: {extract_prompt}")
            
            messages = [
                SystemMessage(content=extract_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            corrected_address = response.content.strip()
            
            # 记录LLM的响应
            logger.info(f"📥 [纠错处理] LLM原始响应: {corrected_address}")
            logger.info(f"🎯 提取的纠正地址: {corrected_address}")
            
            # 验证地址是否存在
            coords = await self.step4_geocode(corrected_address)
            if coords:
                return f"✅ 找到了 {corrected_address} 的位置信息。如需重新规划路径，请告诉我起点和终点。"
            else:
                return f"❌ 抱歉，无法找到 {corrected_address} 的位置信息，请提供更详细的地址。"
                
        except Exception as e:
            logger.error(f"❌ 纠错处理失败: {e}")
            return f"❌ 处理纠错时出现错误: {str(e)}"

    async def step2_confirm_cities(self, locations: List[str], original_user_input: str) -> Dict:
        """步骤2: 确认地点所属城市"""
        logger.info(f"🏙️ 步骤2: 确认城市信息")
        
        system_prompt = f"""用户的原始输入是："{original_user_input}"
从中提取出的地点是："{locations[0]}" 到 "{locations[1]}"

请仔细分析用户的原始输入，判断是否已经包含了城市信息：

1. 如果用户输入中已经明确包含城市信息（如"深圳宝安壹方城"、"北京王府井"等），请返回：
{{
  "need_user_input": false,
  "suggested_city_info": "根据用户输入推断的城市信息",
  "analysis": "分析说明"
}}

2. 如果用户输入中没有明确城市信息，需要询问用户：
{{
  "need_user_input": true,
  "question": "询问用户的具体问题",
  "analysis": "你对这些地点的分析"
}}

注意：
- 优先从用户原始输入中识别城市信息
- 如果地点名称已经包含城市/区域信息，就不要再询问
- 只有在真正无法确定时才询问用户"""

        try:
            # 记录发送给LLM的提示词
            logger.info("📤 [城市确认] 发送给LLM的提示词:")
            logger.info(f"SystemMessage: {system_prompt}")
            
            messages = [
                SystemMessage(content=system_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # 记录LLM的响应
            logger.info(f"📥 [城市确认] LLM原始响应: {response.content}")
            
            result = json.loads(response.content)
            
            logger.info(f"✅ 城市确认分析: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 城市确认失败: {e}")
            return {
                "need_user_input": True, 
                "question": f"请告诉我'{locations[0]}'和'{locations[1]}'分别在哪个城市？",
                "analysis": "无法分析地点归属"
            }

    async def step4_parse_and_format_addresses(self, locations: List[str], user_city_input: str) -> List[str]:
        """步骤4: 解析用户输入并格式化地址"""
        logger.info(f"📍 步骤4: 解析并格式化地址")
        
        system_prompt = f"""用户想要从"{locations[0]}"到"{locations[1]}"的路径规划。
用户的回答是："{user_city_input}"

请直接分析用户的回答，将两个地点补全为"城市市+地点名"的格式。

请用最简单直接的方式回答，只输出两个完整地址，用英文逗号分隔：
格式：城市市地点1,城市市地点2

示例：
- 如果用户说"是"，而地点明显包含城市信息，就根据地点名判断
- 如果用户说"深圳,广州"，就是深圳市{locations[0]},广州市{locations[1]}
- 如果用户说"宝安体育馆在深圳，广州塔在广州"，就分析对应关系

不要用JSON，不要解释，只要最终的两个地址。"""

        try:
            # 记录发送给LLM的提示词
            logger.info("📤 [地址格式化] 发送给LLM的提示词:")
            logger.info(f"SystemMessage: {system_prompt}")
            
            messages = [
                SystemMessage(content=system_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            # 记录LLM的响应
            logger.info(f"📥 [地址格式化] LLM原始响应: {content}")
            logger.info(f"🔍 LLM地址回答: {content}")
            
            # 简单解析LLM的回答
            if ',' in content:
                addresses = [addr.strip() for addr in content.split(',')]
                if len(addresses) == 2:
                    logger.info(f"✅ 地址解析成功: {addresses}")
                    return addresses
            
            # 如果解析失败，再试一次用更简单的prompt
            return await self._simple_retry_format(locations, user_city_input)
                
        except Exception as e:
            logger.error(f"❌ 地址格式化异常: {e}")
            return await self._simple_retry_format(locations, user_city_input)

    async def _simple_retry_format(self, locations: List[str], user_city_input: str) -> List[str]:
        """简单重试地址格式化 - 使用更直接的LLM提示"""
        logger.info(f"🔄 简单重试地址格式化")
        
        simple_prompt = f"""用户要从"{locations[0]}"到"{locations[1]}"。
用户说："{user_city_input}"

请给出两个完整地址，格式：城市市+地点
只要结果，不要解释：

第一个地址：
第二个地址："""

        try:
            # 记录发送给LLM的提示词
            logger.info("📤 [重试地址格式化] 发送给LLM的提示词:")
            logger.info(f"SystemMessage: {simple_prompt}")
            
            messages = [
                SystemMessage(content=simple_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            
            # 记录LLM的响应
            logger.info(f"📥 [重试地址格式化] LLM原始响应: {content}")
            logger.info(f"🔍 重试LLM回答: {content}")
            
            # 提取地址
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            addresses = []
            
            for line in lines:
                if '：' in line:
                    addr = line.split('：')[1].strip()
                    if addr:
                        addresses.append(addr)
                elif ':' in line:
                    addr = line.split(':')[1].strip()
                    if addr:
                        addresses.append(addr)
                elif line and not any(x in line.lower() for x in ['第一', '第二', 'first', 'second']):
                    addresses.append(line)
            
            if len(addresses) >= 2:
                result = addresses[:2]
                logger.info(f"✅ 重试解析成功: {result}")
                return result
            
            logger.error(f"❌ 重试解析失败，无法提取有效地址")
            return []
                
        except Exception as e:
            logger.error(f"❌ 重试地址格式化失败: {e}")
            return []

    async def step4_geocode(self, address: str) -> Optional[str]:
        """步骤4: 地理编码获取经纬度"""
        logger.info(f"🗺️ 地理编码: {address}")
        
        tool = self.get_tool("maps_geo")
        if not tool:
            logger.error("❌ 地理编码工具未找到")
            return None
            
        try:
            result = await tool.ainvoke({"address": address})
            data = json.loads(result)
            
            logger.info(f"🔍 地理编码原始数据: {str(data)[:200]}...")
            
            # 检查API响应 - 修复判断逻辑
            if data.get("status") == "0":
                logger.warning(f"❌ 地理编码API错误: {data}")
                return None
            
            # 提取坐标 - 支持多种数据格式
            location = None
            
            # 尝试从results中获取（AMAP地理编码API的标准响应）
            if data.get("results") and isinstance(data["results"], list) and data["results"]:
                location = data["results"][0].get("location")
            
            # 尝试从geocodes中获取（备用格式）
            elif data.get("geocodes") and isinstance(data["geocodes"], list) and data["geocodes"]:
                location = data["geocodes"][0].get("location")
            
            if location:
                logger.info(f"✅ 地理编码成功: {address} -> {location}")
                return location
                     
            logger.warning(f"❌ 未找到坐标: {address}")
            return None
                
        except Exception as e:
            logger.error(f"❌ 地理编码异常: {e}")
            return None

    async def step5_get_distance(self, start_coords: str, end_coords: str) -> Optional[int]:
        """步骤5: 获取两点距离"""
        logger.info(f"📏 获取距离: {start_coords} -> {end_coords}")
        
        tool = self.get_tool("maps_distance")
        if not tool:
            logger.error("❌ 距离工具未找到")
            return None
        
        try:
            result = await tool.ainvoke({
                "origins": start_coords,
                "destination": end_coords,
                "type": "1"
            })
            data = json.loads(result)
            
            if data.get("results") and data["results"]:
                distance = int(data["results"][0].get("distance", 0))
                logger.info(f"✅ 距离获取成功: {distance}米")
                return distance
                
        except Exception as e:
            logger.error(f"❌ 距离获取失败: {e}")
        
        return None

    async def step6_plan_route(self, start_coords: str, end_coords: str, distance: int) -> Optional[Dict]:
        """步骤6: 根据距离选择路径规划方式"""
        logger.info(f"🚀 步骤6: 路径规划 (距离: {distance}米)")
        
        if distance <= 1000:
            # 距离小于等于1km，使用步行规划
            return await self._plan_walking(start_coords, end_coords)
        else:
            # 距离大于1km，使用公共交通规划
            return await self._plan_transit(start_coords, end_coords)

    async def _plan_walking(self, start_coords: str, end_coords: str) -> Optional[Dict]:
        """步行路径规划"""
        logger.info("🚶 规划步行路线")
        
        tool = self.get_tool("maps_direction_walking")
        if not tool:
            logger.error("❌ 步行规划工具未找到")
            return None
        
        try:
            result = await tool.ainvoke({
                "origin": start_coords,
                "destination": end_coords
            })
            data = json.loads(result)
            
            if data.get("route") and data["route"].get("paths"):
                path = data["route"]["paths"][0]
                return {
                    "type": "walking",
                    "distance": int(path.get("distance", 0)),
                    "duration": int(path.get("duration", 0)) // 60,
                    "steps": path.get("steps", []),
                    "raw_data": data
                }
        except Exception as e:
            logger.error(f"❌ 步行规划失败: {e}")
        
        return None

    async def _plan_transit(self, start_coords: str, end_coords: str) -> Optional[Dict]:
        """公共交通路径规划"""
        logger.info("🚇 规划公共交通路线")
        
        tool = self.get_tool("maps_direction_transit_integrated")
        if not tool:
            logger.error("❌ 公共交通规划工具未找到")
            return None
        
        try:
            result = await tool.ainvoke({
                "origin": start_coords,
                "destination": end_coords,
                "city": "深圳",
                "cityd": "深圳"
            })
            data = json.loads(result)
            
            if data.get("transits") and data["transits"]:
                transit = data["transits"][0]
                return {
                    "type": "transit",
                    "duration": int(transit.get("duration", 0)) // 60,
                    "walking_distance": int(transit.get("walking_distance", 0)),
                    "segments": transit.get("segments", []),
                    "distance": int(data.get("distance", 0)),
                    "raw_data": data
                }
                
        except Exception as e:
            logger.error(f"❌ 公共交通规划失败: {e}")
        
        return None

    def format_route_result(self, route_data: Dict, start_addr: str, end_addr: str, distance: int) -> str:
        """格式化路径规划结果 - 增强版，显示详细步骤"""
        if not route_data:
            return f"❌ 无法获取从 {start_addr} 到 {end_addr} 的路线信息"
        
        response = f"🗺️ **从 {start_addr} 到 {end_addr} 的路线规划**\n\n"
        response += f"📏 **直线距离**: {distance}米\n\n"
        
        def safe_int(value, default=0):
            """安全的整数转换"""
            try:
                return int(float(str(value))) if value else default
            except (ValueError, TypeError):
                return default
        
        def safe_duration_minutes(value, default=0):
            """安全的时间转换为分钟"""
            try:
                duration_seconds = int(float(str(value))) if value else default
                return max(1, duration_seconds // 60)  # 至少1分钟
            except (ValueError, TypeError):
                return default
        
        if route_data["type"] == "walking":
            response += f"## 🚶 步行方案\n"
            response += f"**距离**: {route_data['distance']}米\n"
            response += f"**时间**: 约{route_data['duration']}分钟\n\n"
            
            # 显示详细步行路线
            steps = route_data.get("steps", [])
            if steps:
                response += f"**详细路线** ({len(steps)}个步骤):\n"
                for i, step in enumerate(steps, 1):
                    instruction = step.get("instruction", "继续前行")
                    distance_step = safe_int(step.get("distance", 0))
                    duration_step = safe_duration_minutes(step.get("duration", 0))
                    road_name = step.get("road_name", "")
                    
                    response += f"  **{i}.** {instruction}"
                    if road_name:
                        response += f" (沿{road_name})"
                    response += f" - {distance_step}米"
                    if duration_step > 0:
                        response += f", 约{duration_step}分钟"
                    response += "\n"
        
        elif route_data["type"] == "transit":
            response += f"## 🚇 公共交通方案\n"
            response += f"**总时间**: 约{route_data['duration']}分钟\n"
            response += f"**步行距离**: {route_data['walking_distance']}米\n\n"
            
            # 显示详细公共交通路线
            segments = route_data.get("segments", [])
            if segments:
                response += f"**详细路线**:\n\n"
                
                step_counter = 1
                
                for i, segment in enumerate(segments, 1):
                    # 每个segment可能包含walking + bus两个部分
                    
                    # 1. 步行部分（如果存在）
                    if segment.get("walking"):
                        walking = segment["walking"]
                        walk_distance = safe_int(walking.get("distance", 0))
                        walk_duration = safe_duration_minutes(walking.get("duration", 0))
                        
                        response += f"**{step_counter}. 🚶 步行到站点**\n"
                        response += f"   距离: {walk_distance}米, 时间: 约{walk_duration}分钟\n"
                        
                        # 详细步行步骤
                        walk_steps = walking.get("steps", [])
                        if walk_steps and len(walk_steps) > 0:
                            response += f"   路线: "
                            # 显示主要的几个步骤
                            main_steps = []
                            for step in walk_steps[:2]:  # 前2个主要步骤
                                instruction = step.get("instruction", "")
                                step_distance = safe_int(step.get("distance", 0))
                                if instruction and step_distance > 5:
                                    main_steps.append(f"{instruction}({step_distance}米)")
                            if main_steps:
                                response += " → ".join(main_steps)
                            response += "\n"
                        response += "\n"
                        step_counter += 1
                    
                    # 2. 公交段（如果存在）
                    if segment.get("bus"):
                        bus = segment["bus"]
                        buslines = bus.get("buslines", [])
                        
                        if buslines:
                            busline = buslines[0]  # 取第一条线路
                            line_name = busline.get("name", "未知线路")
                            line_type = busline.get("type", "")
                            
                            # 判断交通工具类型
                            if "地铁" in line_name or line_type == "1":
                                transport_icon = "🚇"
                                transport_type = "地铁"
                            else:
                                transport_icon = "🚌"
                                transport_type = "公交"
                            
                            response += f"**{step_counter}. {transport_icon} 乘坐{transport_type}**\n"
                            response += f"   线路: {line_name}\n"
                            
                            # 起始站和终点站
                            departure_stop = busline.get("departure_stop", {})
                            arrival_stop = busline.get("arrival_stop", {})
                            
                            if departure_stop.get("name"):
                                response += f"   上车站: {departure_stop['name']}\n"
                            if arrival_stop.get("name"):
                                response += f"   下车站: {arrival_stop['name']}\n"
                            
                            # 途经站点数和时间
                            via_num = safe_int(busline.get("via_num", 0))
                            bus_distance = safe_int(busline.get("distance", 0))
                            bus_duration = safe_duration_minutes(busline.get("duration", 0))
                            
                            if via_num > 0:
                                response += f"   途经: {via_num}站\n"
                            if bus_distance > 0:
                                response += f"   距离: {bus_distance}米\n"
                            if bus_duration > 0:
                                response += f"   时间: 约{bus_duration}分钟\n"
                            
                            # 票价信息
                            price = safe_int(busline.get("price", 0))
                            if price > 0:
                                response += f"   票价: {price}元\n"
                            
                            response += "\n"
                            step_counter += 1
                
                # 总结信息
                response += f"**路线总结**:\n"
                walking_parts = sum(1 for s in segments if s.get("walking"))
                transit_parts = sum(1 for s in segments if s.get("bus") and s["bus"].get("buslines"))
                response += f"• 步行段: {walking_parts}个\n"
                response += f"• 乘车段: {transit_parts}个\n"
                if transit_parts > 1:
                    response += f"• 需要换乘: {transit_parts - 1}次\n"
        
        return response

    async def close(self):
        """关闭客户端"""
        pass

# 新增清除会话API端点
@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """清除指定会话的状态"""
    if session_id in session_store:
        del session_store[session_id]
        return {"message": f"会话 {session_id} 已清除"}
    return {"message": f"会话 {session_id} 不存在"}

# 初始化函数
async def init_agent():
    global route_agent
    route_agent = SimpleRouteAgent()
    await route_agent.initialize()

# API 端点
@app.on_event("startup")
async def startup_event():
    await init_agent()

@app.get("/")
async def root():
    return {"message": "路径规划智能体 API 服务运行中"}

@app.post("/route", response_model=RouteResponse)
async def plan_route(request: RouteRequest):
    """路径规划接口"""
    try:
        session_id = request.session_id or "default"
        user_input = request.user_input
        
        # 获取或创建会话状态
        if session_id not in session_store:
            session_store[session_id] = SessionData()
        
        session_data = session_store[session_id]
        
        # 根据会话状态处理请求
        if session_data.stage == "start":
            # 第一次请求：识别意图
            intent_result = await route_agent.step1_identify_intent(user_input)
            
            if intent_result["intent_type"] == "route_request":
                locations = intent_result["locations"]
                if len(locations) != 2:
                    return RouteResponse(
                        success=False,
                        message="❌ 未能正确识别起点和终点"
                    )
                
                # 保存会话状态
                session_data.locations = locations
                session_data.intent_result = intent_result
                session_data.stage = "waiting_city"
                
                # 分析城市信息
                city_analysis = await route_agent.step2_confirm_cities(locations, user_input)
                session_data.city_analysis = city_analysis
                
                # 检查是否需要用户输入城市信息
                if city_analysis.get("need_user_input"):
                    # 需要用户确认城市
                    return RouteResponse(
                        success=True,
                        message=f"🤔 {city_analysis.get('analysis', '')}\n\n❓ {city_analysis.get('question', '')}",
                        need_city_confirmation=True,
                        session_id=session_id
                    )
                else:
                    # LLM已经推断出城市信息，直接处理
                    session_data.stage = "processing"
                    suggested_city_info = city_analysis.get("suggested_city_info", "")
                    
                    # 使用LLM推断的城市信息格式化地址
                    formatted_addresses = await route_agent.step4_parse_and_format_addresses(locations, suggested_city_info)
                    
                    if not formatted_addresses or len(formatted_addresses) != 2:
                        session_data.stage = "start"
                        return RouteResponse(
                            success=False,
                            message="❌ 地址格式化失败，请提供更详细的地址信息"
                        )
                    
                    # 执行完整的路径规划
                    result = await execute_route_planning(route_agent, formatted_addresses, session_data)
                    return result
                
            elif intent_result["intent_type"] == "correction":
                result = await route_agent.handle_correction(intent_result["correction_info"], intent_result["suggested_address"])
                return RouteResponse(
                    success=True,
                    message=result,
                    need_city_confirmation=False
                )
            
            else:
                return RouteResponse(
                    success=False,
                    message=f"❌ 无法识别路径规划需求: {intent_result.get('reason', '未知原因')}"
                )
                
        elif session_data.stage == "waiting_city":
            # 收到城市信息，处理路径规划
            session_data.stage = "processing"
            
            # 使用保存的locations和用户提供的城市信息
            formatted_addresses = await route_agent.step4_parse_and_format_addresses(session_data.locations, user_input)
            
            if not formatted_addresses or len(formatted_addresses) != 2:
                # 重置会话状态
                session_data.stage = "start"
                return RouteResponse(
                    success=False,
                    message="❌ 地址格式化失败，请重新提供清晰的城市信息"
                )
            
            # 执行完整的路径规划
            result = await execute_route_planning(route_agent, formatted_addresses, session_data)
            return result
        
        else:
            # 未知状态，重置
            session_data.stage = "start"
            return RouteResponse(
                success=False,
                message="❌ 会话状态异常，请重新开始"
            )
            
    except Exception as e:
        logger.error(f"API错误: {e}")
        # 重置会话状态
        if request.session_id and request.session_id in session_store:
            session_store[request.session_id].stage = "start"
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/route/confirm-city", response_model=RouteResponse)
async def confirm_city(request: CityConfirmation):
    """确认城市信息接口 - 已废弃，功能合并到主接口"""
    return RouteResponse(
        success=False,
        message="此接口已废弃，请直接在主聊天界面回复城市信息"
    )

async def execute_route_planning(agent: SimpleRouteAgent, formatted_addresses: List[str], session_data: SessionData) -> RouteResponse:
    """执行完整的路径规划流程"""
    try:
        # 地理编码
        start_coords = await agent.step4_geocode(formatted_addresses[0])
        if not start_coords:
            session_data.stage = "start"
            return RouteResponse(
                success=False,
                message=f"❌ 无法找到起点 '{formatted_addresses[0]}' 的位置信息，请检查地址是否正确"
            )
            
        end_coords = await agent.step4_geocode(formatted_addresses[1])
        if not end_coords:
            session_data.stage = "start"
            return RouteResponse(
                success=False,
                message=f"❌ 无法找到终点 '{formatted_addresses[1]}' 的位置信息，请检查地址是否正确"
            )
        
        # 获取距离
        distance = await agent.step5_get_distance(start_coords, end_coords)
        if distance is None:
            session_data.stage = "start"
            return RouteResponse(
                success=False,
                message="❌ 无法获取距离信息"
            )
        
        # 路径规划
        route_data = await agent.step6_plan_route(start_coords, end_coords, distance)
        result = agent.format_route_result(route_data, formatted_addresses[0], formatted_addresses[1], distance)
        
        # 重置会话状态
        session_data.stage = "start"
        session_data.locations = []
        session_data.intent_result = {}
        session_data.city_analysis = {}
        
        return RouteResponse(
            success=True,
            message=result,
            need_city_confirmation=False
        )
        
    except Exception as e:
        session_data.stage = "start"
        logger.error(f"❌ 路径规划执行失败: {e}")
        return RouteResponse(
            success=False,
            message=f"❌ 路径规划过程中发生错误: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 