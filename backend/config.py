import os
from dotenv import load_dotenv

load_dotenv()

AMAP_API_KEY = os.getenv("AMAP_API_KEY", "********")
LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH", "*****************")
# LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH", "***********")
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "***********")

# LoRA 微调参数路径（LlamaFactory 导出目录）
LORA_ADAPTER_PATH = os.getenv("LORA_ADAPTER_PATH", "**************")
USE_LORA = os.getenv("USE_LORA", "true").lower() == "true"   # 是否启用 LoRA

# RAG 相关（已移除 faiss 索引路径）
SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3
TOP_K = 5

# MySQL 向量库配置
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "*********",
    "database": "***********",
    "charset": "utf8mb4"
}

# 生成
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048

