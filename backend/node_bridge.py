import subprocess
import json
import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ===================== 路径配置（自动适配项目结构）=====================
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
AMAP_WEBSERVICE_DIR = os.path.join(PROJECT_ROOT, "amap_webservice")
SCRIPTS_DIR = os.path.join(AMAP_WEBSERVICE_DIR, "scripts")

# ===================== 核心：调用 Node 脚本 =====================
def _run_node_script(script_name: str, **kwargs) -> Optional[Dict[str, Any]]:
    """运行 Node 脚本，传递参数并添加 --json=true，返回解析后的 JSON 字典"""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"错误: Node 脚本不存在: {script_path}")
        return None

    cmd = ["node", script_path, "--json=true"]
    for key, value in kwargs.items():
        if value is not None:
            cmd.append(f"--{key}={value}")

    # 准备环境变量，确保 AMAP_KEY 被传递
    env = os.environ.copy()
    if "AMAP_KEY" not in env:
        env["AMAP_KEY"] = os.getenv("AMAP_KEY", "")
        if not env["AMAP_KEY"]:
            print("[警告] AMAP_KEY 未设置，Node 脚本可能失败")

    try:
        result = subprocess.run(
            cmd,
            cwd=AMAP_WEBSERVICE_DIR,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
            env=env
        )
        if result.returncode != 0:
            print(f"Node 脚本返回码 {result.returncode}")
            print(f"stderr: {result.stderr}")
            return None

        output = result.stdout.strip()
        if not output:
            return None

        # ==============================================
        # 🔥 核心修复：自动提取最后一行合法 JSON（过滤日志）
        # ==============================================
        import re
        lines = output.splitlines()
        json_line = None

        # 从最后一行往前找，找到第一个像 JSON 的行
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                json_line = line
                break

        if not json_line:
            print("❌ 无法从 Node 输出中找到 JSON 数据")
            print("原始输出:\n", output)
            return None

        # 只解析 JSON 行
        data = json.loads(json_line)
        # ==============================================

        if data.get("success") is False:
            print(f"Node 脚本返回错误: {data.get('error')}")
            return None
        return data

    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        print("Node 原始输出:\n", output)
        return None
    except Exception as e:
        print(f"调用 Node 脚本异常: {e}")
        return None

# ===================== 对外接口 =====================

def search_poi(keywords: str, city: str = None, location: str = None, radius: int = None, page: int = 1, offset: int = 10):
    """POI 搜索（餐饮、景点、酒店等）"""
    return _run_node_script(
        "poi-search.js",
        keywords=keywords,
        city=city,
        location=location,
        radius=radius,
        page=page,
        offset=offset
    )

def driving_route(origin: str, destination: str, waypoints: str = None, strategy: int = 10):
    """驾车路线规划"""
    return _run_node_script(
        "route-planning.js",
        type="driving",
        origin=origin,
        destination=destination,
        waypoints=waypoints,
        strategy=strategy
    )

def walking_route(origin: str, destination: str):
    """步行路线规划"""
    return _run_node_script(
        "route-planning.js",
        type="walking",
        origin=origin,
        destination=destination
    )

def riding_route(origin: str, destination: str):
    """骑行路线规划"""
    return _run_node_script(
        "route-planning.js",
        type="riding",
        origin=origin,
        destination=destination
    )

def transit_route(origin: str, destination: str, city: str, strategy: int = 0, nightflag: bool = False):
    """公交/地铁路线规划"""
    return _run_node_script(
        "route-planning.js",
        type="transfer",
        origin=origin,
        destination=destination,
        city=city,
        strategy=strategy,
        nightflag=str(nightflag).lower()
    )

def travel_planner(city: str, interests: list = None, route_type: str = "walking"):
    """智能旅行规划（自动生成一日游/多日游路线）"""
    if interests is None:
        interests = ["景点", "美食", "酒店"]
    interests_str = ",".join(interests)
    return _run_node_script(
        "travel-planner.js",
        city=city,
        interests=interests_str,
        routeType=route_type
    )