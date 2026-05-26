import pymysql
from dbutils.pooled_db import PooledDB
from typing import List, Dict, Optional
from datetime import datetime
import json
from .config import MYSQL_CONFIG

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=20,
            mincached=2,
            maxcached=10,
            blocking=True,
            ping=1,
            host=MYSQL_CONFIG["host"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"],
            charset=MYSQL_CONFIG.get("charset", "utf8mb4"),
            autocommit=False
        )
    return _pool


def get_connection():
    return _get_pool().connection()


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # 增加 route_context 列，存储 JSON 字符串，例如 '["都江堰", "青城山"]'
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT '新对话',
                    created_at VARCHAR(50) NOT NULL,
                    updated_at VARCHAR(50) NOT NULL,
                    route_context TEXT DEFAULT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 检查列是否存在，若不存在则添加（兼容旧表）
            cursor.execute("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sessions' AND COLUMN_NAME = 'route_context'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE sessions ADD COLUMN route_context TEXT DEFAULT NULL")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    timestamp VARCHAR(50) NOT NULL,
                    INDEX idx_session_id (session_id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()


def create_session(session_id: str, title: str = "新对话") -> dict:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                (session_id, title, now, now)
            )
        conn.commit()
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now}


def get_session(session_id: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, title, created_at, updated_at, route_context FROM sessions WHERE id = %s",
                           (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "route_context": json.loads(row[4]) if row[4] else None
            }


def get_all_sessions() -> List[dict]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]


def update_session_title(session_id: str, title: str):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE sessions SET title = %s, updated_at = %s WHERE id = %s", (title, now, session_id))
        conn.commit()


def delete_session(session_id: str):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.commit()


def add_message(session_id: str, role: str, content: str):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
                (session_id, role, content, now)
            )
            cursor.execute("UPDATE sessions SET updated_at = %s WHERE id = %s", (now, session_id))
        conn.commit()


def get_messages(session_id: str) -> List[dict]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT role, content, timestamp FROM messages WHERE session_id = %s ORDER BY timestamp",
                (session_id,)
            )
            rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]


# ---------- 会话路线上下文操作 ----------
def get_session_route_context(session_id: str) -> list:
    """返回该会话的地点上下文列表（如 ['起点','终点']），若不存在则返回空列表"""
    session = get_session(session_id)
    if session and session.get("route_context"):
        return session["route_context"]
    return []


def update_session_route_context(session_id: str, context: list):
    """更新会话的地点上下文（存储 JSON 字符串）"""
    context_json = json.dumps(context) if context else None
    now = datetime.now().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE sessions SET route_context = %s, updated_at = %s WHERE id = %s",
                (context_json, now, session_id)
            )
        conn.commit()


def close_pool():
    global _pool
    if _pool:
        _pool.close()
        _pool = None


init_db()