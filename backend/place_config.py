# place_config.py
# 标准地名 → 用于地理编码的精确名称（高德能识别的地址）
PLACE_MAPPING = {
    "都江堰": "都江堰景区",
    "青城山": "青城山景区",
    "黄龙": "黄龙风景名胜区",
    "九寨沟": "九寨沟景区",
    "峨眉山": "峨眉山景区",
    "乐山大佛": "乐山大佛",
    "三星堆": "三星堆博物馆",
    "熊猫基地": "成都大熊猫繁育研究基地",
    "宽窄巷子": "宽窄巷子",
    "锦里": "锦里",
    "武侯祠": "武侯祠",
    "杜甫草堂": "杜甫草堂",
    "都江堰景区": "都江堰",
    "都江堰水利工程": "都江堰",
    "青城前山": "青城山景区",
    "青城后山": "青城山景区",
    "黄龙景区": "黄龙风景名胜区",
    "黄龙风景区": "黄龙风景名胜区",
}

# 别名列表（用于从用户输入中提取标准地名）
STANDARD_PLACES = {
    "都江堰": ["都江堰", "都江堰景区", "都江堰水利工程"],
    "青城山": ["青城山", "青城前山", "青城后山"],
    "黄龙": ["黄龙", "黄龙景区", "黄龙风景区", "黄龙风景名胜区"],
    "九寨沟": ["九寨沟", "九寨沟景区"],
    "峨眉山": ["峨眉山", "峨眉山景区"],
    "乐山大佛": ["乐山大佛", "乐山大佛景区"],
    "三星堆": ["三星堆", "三星堆博物馆"],
    "熊猫基地": ["熊猫基地", "大熊猫基地", "成都熊猫基地"],
    "宽窄巷子": ["宽窄巷子"],
    "锦里": ["锦里"],
    "武侯祠": ["武侯祠"],
    "杜甫草堂": ["杜甫草堂"],
}

DEFAULT_CITY = "成都"
CITY_KEYWORDS = ["成都", "都江堰", "青城山", "黄龙", "九寨沟", "峨眉山"]

def get_standard_place(name: str) -> str:
    """将用户输入的别名转换为标准地名（用于地理编码）"""
    # 直接查映射表
    for key, aliases in STANDARD_PLACES.items():
        if name in aliases or name == key:
            return PLACE_MAPPING.get(key, key)
    # 未匹配则原样返回
    return name

def extract_places_from_query(query: str) -> list:
    """从用户查询中提取出现的所有标准地名（按出现顺序去重）"""
    found = []
    for std_name, aliases in STANDARD_PLACES.items():
        for alias in aliases:
            if alias in query:
                found.append(std_name)
                break
    # 去重保留顺序
    unique = []
    for p in found:
        if p not in unique:
            unique.append(p)
    return unique