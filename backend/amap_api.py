import requests
from .config import AMAP_API_KEY

_amap_called = False

def reset_amap_flag():
    global _amap_called
    _amap_called = False

def was_amap_called() -> bool:
    return _amap_called

def _log_call(name: str):
    global _amap_called
    _amap_called = True
    print(f"[高德API] {name}")

def geocode(address: str):
    if not AMAP_API_KEY:
        print("[错误] AMAP_API_KEY 未设置")
        return None

    # 后缀尝试列表
    suffixes = ["", "风景区", "景区", "风景名胜区"]

    for suffix in suffixes:
        test_addr = address + suffix if suffix else address
        url = "https://restapi.amap.com/v3/geocode/geo"
        params = {"key": AMAP_API_KEY, "address": test_addr, "output": "json"}
        try:
            resp = requests.get(url, params=params, timeout=10).json()
            if resp.get("status") == "1" and resp.get("geocodes"):
                loc = resp["geocodes"][0]["location"]
                print(f"[地理编码] {test_addr} -> {loc}")
                _log_call("地理编码")
                return loc
        except Exception as e:
            print(f"[地理编码异常] {test_addr}: {e}")
    print(f"[地理编码失败] 所有尝试均失败: {address}")
    return None

def get_weather(city: str):
    if not AMAP_API_KEY:
        return "未配置Key"
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    params = {"key": AMAP_API_KEY, "city": city, "extensions": "all", "output": "json"}
    try:
        data = requests.get(url, params=params, timeout=10).json()
        if data.get("status") == "1":
            if data.get("forecasts"):
                _log_call("天气预报")
                forecast = data["forecasts"][0]
                casts = forecast.get("casts", [])
                result = f"{city}未来几天天气：\n"
                for c in casts[:5]:
                    result += f"{c['date']} {c['dayweather']} {c['nighttemp']}~{c['daytemp']}℃ {c['daywind']}\n"
                return result.strip()
            elif data.get("lives"):
                _log_call("实时天气")
                w = data["lives"][0]
                return f"{w['weather']} {w['temperature']}℃ {w['winddirection']}{w['windpower']}级"
    except Exception as e:
        print(f"天气失败: {e}")
    return "获取失败"