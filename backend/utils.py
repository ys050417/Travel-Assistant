import torch
import os
from sentence_transformers import SentenceTransformer
from .config import LOCAL_EMBEDDING_MODEL

_model = None

def get_embedding(text: str):
    global _model
    if _model is None:
        path = os.path.abspath(LOCAL_EMBEDDING_MODEL)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Embedding模型路径不存在: {path}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(path, device=device)
        _model.eval()
        print(f"Embedding模型加载完成，设备: {device}")
    text = text[:800].strip()
    # 标准化输出向量，使余弦相似度 = 点积
    return _model.encode(text, convert_to_numpy=True, normalize_embeddings=True).tolist()