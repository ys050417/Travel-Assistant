from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from contextlib import asynccontextmanager
import re
import os
from typing import List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import asyncio

from .models import ChatRequest, ChatResponse, SessionOut, MessageOut
from .local_llm import generate_response, load_model
from .rag import retrieve_by_mode, hybrid_search
from .database import (
    create_session, get_session, get_all_sessions, delete_session,
    get_messages, add_message, update_session_title,
    get_session_route_context, update_session_route_context   # 新增导入
)
from .amap_api import geocode, get_weather, reset_amap_flag, was_amap_called
from .node_bridge import driving_route, search_poi, travel_planner
from .config import AMAP_API_KEY
from .place_config import (
    get_standard_place, CITY_KEYWORDS, DEFAULT_CITY, PLACE_MAPPING,
    extract_places_from_query, STANDARD_PLACES
)
from fastapi.staticfiles import StaticFiles

# 不再需要全局 last_place_context

os.makedirs("static/img", exist_ok=True)
_thread_pool = None

PLACE_HTML_FILES = [
    "都江堰.html", "都青线.html", "杜甫草堂.html", "峨眉山.html",
    "伏龙观.html", "佛教.html", "黄龙.html", "金沙遗址.html",
    "九皇山.html", "九寨沟.html", "宽窄巷子.html", "乐山大佛.html",
    "青城山.html", "三星堆.html", "蜀王.html", "望江楼.html",
    "武侯祠.html", "熊猫基地.html",
]

async def run_sync(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_thread_pool, func, *args)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _thread_pool
    _thread_pool = ThreadPoolExecutor(max_workers=20)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, load_model)
    if not AMAP_API_KEY:
        print("⚠️ 高德API密钥未配置，天气和地理编码将不可用")
    yield
    _thread_pool.shutdown(wait=True)
    from .database import close_pool
    close_pool()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

app.mount("/static", StaticFiles(directory="static"), name="static")

def add_place_routes():
    frontend_dir = Path(__file__).parent.parent / "frontend"
    for html_file in PLACE_HTML_FILES:
        file_path = frontend_dir / html_file
        if not file_path.exists():
            continue
        route_path = f"/{html_file.replace('.html', '')}"
        route_path_with_ext = f"/{html_file}"

        @app.get(route_path, response_class=HTMLResponse)
        async def place_page(fp=file_path):
            return FileResponse(fp)

        @app.get(route_path_with_ext, response_class=HTMLResponse)
        async def place_page_with_ext(fp=file_path):
            return FileResponse(fp)

add_place_routes()

@app.get("/")
async def root():
    backend_dir = Path(__file__).parent.resolve()
    frontend_path = backend_dir.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {"error": f"找不到 {frontend_path}"}

# ========== 会话管理 API ==========
@app.get("/sessions", response_model=List[SessionOut])
async def list_sessions():
    return await run_sync(get_all_sessions)

@app.post("/sessions/{session_id}")
async def create_session_api(session_id: str, title: str = "新对话"):
    existing = await run_sync(get_session, session_id)
    if existing:
        return existing
    return await run_sync(create_session, session_id, title)

@app.delete("/sessions/{session_id}")
async def delete_session_api(session_id: str):
    await run_sync(delete_session, session_id)
    return {"status": "success"}

@app.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
async def get_session_messages(session_id: str):
    return await run_sync(get_messages, session_id)

# ========== 景点导览 API ==========
@app.get("/api/places")
async def get_places():
    places = sorted(set(PLACE_MAPPING.values()))
    return {"places": places}

@app.get("/api/place/{place_name}")
async def get_place_detail(place_name: str):
    chunks = await run_sync(hybrid_search, place_name, 8)
    if not chunks:
        return {"name": place_name, "content": "<p>暂无详细介绍，请稍后再试。</p>", "chunks": []}
    content_html = "".join([f"<p>{chunk}</p>" for chunk in chunks])
    return {"name": place_name, "content": content_html, "chunks": chunks}

@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page():
    frontend_path = Path(__file__).parent.parent / "frontend" / "welcome.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return HTMLResponse(content="欢迎页面未找到", status_code=404)

# ========== 辅助函数 ==========
def canonicalize_address(name: str) -> str:
    return get_standard_place(name)

def clean_query(query: str) -> str:
    patterns = [r"规划一条路线", r"帮我规划", r"路线", r"怎么去", r"如何前往", r"求路线"]
    for pat in patterns:
        query = re.sub(pat, "", query)
    query = re.sub(r'[，,。？?！!；;]', ' ', query)
    return query.strip()

def detect_intents(query: str) -> List[str]:
    intents = []
    if re.search(r'怎么去|路线|驾车|到|距离|多远|规划', query):
        intents.append("route")
    if re.search(r'天气|气温|会不会下雨|温度|预报', query):
        intents.append("weather")
    if re.search(r'酒店|住宿|景点|好玩|推荐|旅游|攻略|一日游', query):
        intents.append("travel")
    if not intents:
        intents.append("unknown")
    return intents

def extract_city(query: str, default: str = None) -> str:
    if default is None:
        default = DEFAULT_CITY
    for city in CITY_KEYWORDS:
        if city in query:
            return city
    return default

def extract_interests(query: str) -> List[str]:
    interests = []
    if "景点" in query:
        interests.append("景点")
    if "美食" in query:
        interests.append("美食")
    if "酒店" in query:
        interests.append("酒店")
    if not interests:
        interests = ["景点", "美食"]
    return interests

# ========== 路线处理（绑定会话）==========
async def handle_route_query(session_id: str, query: str) -> tuple[str, str]:
    # 获取当前会话的历史上下文
    route_context = await run_sync(get_session_route_context, session_id)
    clean_q = clean_query(query)
    places = extract_places_from_query(clean_q)

    start = None
    dest = None

    if len(places) == 1:
        dest = places[0]
        if len(route_context) >= 2:
            start = route_context[-2]   # 上一次的起点
        elif len(route_context) == 1:
            start = route_context[-1]   # 上一次的终点作为起点
        else:
            start = "都江堰"
    elif len(places) >= 2:
        start, dest = places[0], places[1]
    else:
        match = re.search(r'从(.+?)到(.+?)(?:$|[\s，,。])', query)
        if match:
            start = match.group(1).strip()
            dest = match.group(2).strip()
        else:
            match = re.search(r'(?:去|到)(.+)', query)
            if match:
                dest = match.group(1).strip()
                start = route_context[-1] if route_context else "都江堰"
            else:
                return "❌ 未能识别起点或终点，请明确说出例如：从都江堰到青城山", None

    start_canon = canonicalize_address(start)
    dest_canon = canonicalize_address(dest)

    start_loc = geocode(start_canon)
    dest_loc = geocode(dest_canon)

    if not start_loc or not dest_loc:
        return f"⚠️ 坐标解析失败：{start} → {dest}，请使用标准地名", None

    result = driving_route(start_loc, dest_loc)
    if result and result.get("success") and result.get("route"):
        route = result["route"]
        try:
            dist_km = round(float(route.get("distance", 0)) / 1000, 2)
            dur_min = round(float(route.get("duration", 0)) / 60)
        except:
            dist_km = 0.0
            dur_min = 0

        steps = route.get("steps", [])
        lines = [f"🚗 驾车路线：{start_canon} → {dest_canon}"]
        lines.append(f"📏 总距离：{dist_km} 公里")
        lines.append(f"⏱ 预计时间：{dur_min} 分钟")
        if steps:
            lines.append("\n🛣️ 行驶步骤：")
            for i, step in enumerate(steps, 1):
                lines.append(f"{i}. {step}")
        else:
            lines.append("\n（未返回详细步骤，请查看地图链接）")

        # 更新会话上下文
        await run_sync(update_session_route_context, session_id, [start_canon, dest_canon])
        map_link = result.get("mapLink")
        return "\n".join(lines), map_link
    else:
        await run_sync(update_session_route_context, session_id, [])
        return f"⚠️ 路线规划失败：{start} → {dest}", None

async def handle_weather_query(session_id: str, query: str) -> str:
    route_context = await run_sync(get_session_route_context, session_id)
    places_to_check = []
    if len(route_context) >= 2:
        places_to_check = route_context[:2]
    else:
        places_to_check = [extract_city(query)]
    unique_places = list(set(places_to_check))
    result_lines = []
    for place in unique_places:
        try:
            weather_info = get_weather(place)
            result_lines.append(f"🌤 {place} 天气：{weather_info}")
        except:
            result_lines.append(f"⚠️ {place} 天气查询失败")
    return "\n".join(result_lines)

async def handle_travel_query(session_id: str, query: str) -> tuple[str, str]:
    city = extract_city(query)
    interests = extract_interests(query)
    result = travel_planner(city, interests, route_type="walking")
    if result and result.get("success"):
        map_link = result.get("mapLink")
        # 旅游规划后上下文设为城市名（可选）
        await run_sync(update_session_route_context, session_id, [city])
        return f"🗺️ 已为您规划 {city} {', '.join(interests)} 行程，共 {len(result.get('pois', []))} 个地点。", map_link
    else:
        return f"❌ 无法规划 {city} 旅游行程", None

# ========== 主聊天接口 ==========
@app.post("/chat", response_model=ChatResponse)
async def chat_api(req: ChatRequest):
    try:
        reset_amap_flag()

        if not await run_sync(get_session, req.session_id):
            await run_sync(create_session, req.session_id)

        messages = [msg.dict() for msg in req.messages]
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if not last_user_msg:
            raise HTTPException(status_code=400, detail="未找到用户消息")

        intents = detect_intents(last_user_msg)

        amap_parts = []
        map_link = None

        for intent in intents:
            if intent == "route":
                info, link = await handle_route_query(req.session_id, last_user_msg)
                amap_parts.append(info)
                if link and not map_link:
                    map_link = link
            elif intent == "weather":
                info = await handle_weather_query(req.session_id, last_user_msg)
                amap_parts.append(info)
            elif intent == "travel":
                info, link = await handle_travel_query(req.session_id, last_user_msg)
                amap_parts.append(info)
                if link and not map_link:
                    map_link = link

        amap_info = "\n\n".join(amap_parts) if amap_parts else "（未调用高德API）"

        if amap_info and (amap_info.startswith("❌") or amap_info.startswith("⚠️")):
            await run_sync(add_message, req.session_id, "user", last_user_msg)
            await run_sync(add_message, req.session_id, "assistant", amap_info)
            return ChatResponse(
                answer=amap_info,
                response_time=0.0,
                retrieved_chunks=None,
                amap_called=was_amap_called(),
                map_link=map_link
            )

        retrieved = []
        if req.retrieval_mode != "none":
            retrieved = await run_sync(retrieve_by_mode, last_user_msg, req.retrieval_mode, req.top_k)

        if amap_info and "失败" not in amap_info and "未调用" not in amap_info and "❌" not in amap_info:
            system_prompt = f"""你是一个旅行助手，必须严格基于以下高德地图API返回的真实数据回答用户问题，绝对禁止编造任何未出现的交通方式（如公交、地铁、步行路线）。

高德实时数据：
{amap_info}

用户问题：{last_user_msg}

请如实回答，仅使用上述数据。如果数据中不包含公交信息，绝对不要自行添加。若数据不完整，回复“根据高德地图，无法提供该路线详情”。
"""
        else:
            system_prompt = f"你是旅行助手，用户问：{last_user_msg}，不知道就说不知道。"

        final_messages = messages.copy()
        final_messages.append({"role": "system", "content": system_prompt})

        answer, elapsed = await generate_response(
            final_messages,
            temperature=req.temperature,
            max_new_tokens=req.max_tokens
        )

        if amap_info and "🚗 驾车路线" in amap_info and ("公交" in answer or "地铁" in answer or "步行" in answer):
            answer = amap_info

        if map_link and "查看地图" not in answer:
            answer += f"\n\n🗺️ 查看地图：{map_link}"

        await run_sync(add_message, req.session_id, "user", last_user_msg)
        await run_sync(add_message, req.session_id, "assistant", answer)

        session = await run_sync(get_session, req.session_id)
        if session and session["title"] == "新对话":
            title = last_user_msg[:18]
            if len(last_user_msg) > 18:
                title += "..."
            await run_sync(update_session_title, req.session_id, title)

        return ChatResponse(
            answer=answer,
            response_time=elapsed,
            retrieved_chunks=retrieved if retrieved else None,
            amap_called=was_amap_called(),
            map_link=map_link
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"服务异常：{str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)