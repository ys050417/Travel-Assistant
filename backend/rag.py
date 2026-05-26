import pymysql
import numpy as np
from typing import List
from .config import MYSQL_CONFIG, SEMANTIC_WEIGHT, KEYWORD_WEIGHT, TOP_K
from .utils import get_embedding

# 缓存
_cache_chunks = None
_cache_vectors = None

def _load_from_mysql():
    """从 MySQL 加载所有片段和向量，并缓存到内存"""
    global _cache_chunks, _cache_vectors
    if _cache_chunks is not None:
        return _cache_chunks, _cache_vectors

    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT content, vector FROM document_vectors")
    rows = cursor.fetchall()
    conn.close()

    chunks = []
    vectors = []
    for content, vec_str in rows:
        chunks.append(content)
        vec = np.array([float(x) for x in vec_str.split(',')], dtype=np.float32)
        vectors.append(vec)

    if vectors:
        _cache_vectors = np.vstack(vectors)
    else:
        _cache_vectors = np.empty((0, 0))
    _cache_chunks = chunks
    print(f"✅ 从 MySQL 加载 {len(chunks)} 条向量，维度 {_cache_vectors.shape[1] if len(chunks) > 0 else 0}")
    return _cache_chunks, _cache_vectors

def keyword_score(query_words: set, chunk: str) -> int:
    """关键词匹配分数（词袋模型）"""
    chunk_lower = chunk.lower()
    return sum(1 for w in query_words if w in chunk_lower)

def semantic_search(query: str, top_k: int = TOP_K) -> List[str]:
    """纯语义检索（余弦相似度）"""
    chunks, vectors = _load_from_mysql()
    if not chunks or vectors.size == 0:
        return []

    q_vec = np.array(get_embedding(query), dtype=np.float32).reshape(1, -1)
    # 查询向量已归一化（utils.get_embedding 已做 normalize_embeddings=True）
    # 文档向量也需要归一化（in.py 构建时已归一化）
    # 直接点积即为余弦相似度
    sims = np.dot(vectors, q_vec.T).flatten()
    top_idx = np.argsort(sims)[-top_k:][::-1]
    return [chunks[i] for i in top_idx if sims[i] > 0]

def keyword_search(query: str, top_k: int = TOP_K) -> List[str]:
    """纯关键词检索"""
    chunks, _ = _load_from_mysql()
    words = set(query.lower().split())
    scored = [(keyword_score(words, c), i) for i, c in enumerate(chunks)]
    scored.sort(reverse=True)
    return [chunks[i] for _, i in scored[:top_k]]

def hybrid_search(query: str, top_k: int = TOP_K) -> List[str]:
    """混合检索：语义分数 + 关键词分数加权"""
    chunks, vectors = _load_from_mysql()
    if not chunks or vectors.size == 0:
        return []

    words = set(query.lower().split())
    q_vec = np.array(get_embedding(query), dtype=np.float32).reshape(1, -1)
    sem_scores = np.dot(vectors, q_vec.T).flatten()
    kw_scores = np.array([keyword_score(words, c) for c in chunks])
    final_scores = SEMANTIC_WEIGHT * sem_scores + KEYWORD_WEIGHT * kw_scores
    top_idx = np.argsort(final_scores)[-top_k:][::-1]
    return [chunks[i] for i in top_idx]

def retrieve_by_mode(query: str, mode: str, top_k: int = TOP_K) -> List[str]:
    """统一检索入口（与之前接口完全一致）"""
    if mode == "none" or not query:
        return []
    try:
        if mode == "semantic":
            return semantic_search(query, top_k)
        elif mode == "keyword":
            return keyword_search(query, top_k)
        else:
            return hybrid_search(query, top_k)
    except Exception as e:
        print(f"RAG 检索异常: {e}")
        return []