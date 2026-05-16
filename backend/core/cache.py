"""AI 结果 SQLite 持久化缓存 — 基于视频指纹避免重复消耗 AI token。"""

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from config import DB_PATH


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def video_fingerprint(extractor: str, video_id: str) -> str:
    """构建视频指纹: platform:id (如 bilibili:BV1cW9xB3Ec1)。"""
    return f"{extractor}:{video_id}"


# ──── AI 缓存 ────

def _ensure_table():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_cache (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                fingerprint TEXT DEFAULT '',
                video_title TEXT DEFAULT '',
                subtitle_text TEXT DEFAULT '',
                source TEXT DEFAULT '',
                result_json TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # 迁移旧表：先加列，再建索引
        try:
            conn.execute("ALTER TABLE ai_cache ADD COLUMN fingerprint TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_cache_url_hash ON ai_cache(url_hash)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_cache_fingerprint ON ai_cache(fingerprint)
        """)


_ensure_table()


def get_cached(url: str, fingerprint: str = None) -> dict | None:
    """获取缓存的 AI 结果。先按指纹查，再按 URL hash。"""
    h = _url_hash(url)
    tz = timezone(timedelta(hours=8))
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = None
        # 指纹优先
        if fingerprint:
            row = conn.execute(
                "SELECT url, video_title, subtitle_text, source, result_json, created_at, updated_at FROM ai_cache WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            # 同视频但不同 URL：更新 url_hash 映射
            if row:
                old_url = row[0]
                if _url_hash(old_url) != h:
                    conn.execute(
                        "UPDATE ai_cache SET url = ?, url_hash = ?, updated_at = ? WHERE fingerprint = ?",
                        (url, h, datetime.now(tz).isoformat(), fingerprint),
                    )
        # URL hash 兜底
        if not row:
            row = conn.execute(
                "SELECT url, video_title, subtitle_text, source, result_json, created_at, updated_at FROM ai_cache WHERE url_hash = ?",
                (h,),
            ).fetchone()
    if not row:
        return None
    return {
        "url": row[0],
        "video_title": row[1],
        "subtitle_text": row[2],
        "source": row[3],
        "result_json": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


def save_cache(url: str, video_title: str = "", subtitle_text: str = "", source: str = "", result_json: str = "", fingerprint: str = None):
    """保存或更新 AI 结果缓存。有指纹时按指纹去重，避免同视频多 URL 产生多条记录。"""
    h = _url_hash(url)
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        # 有指纹：先查是否已有同指纹记录
        if fingerprint:
            existing = conn.execute("SELECT url_hash FROM ai_cache WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE ai_cache SET url=?, url_hash=?, video_title=?, subtitle_text=?, source=?, result_json=?, updated_at=? WHERE fingerprint=?",
                    (url, h, video_title, subtitle_text, source, result_json, now, fingerprint),
                )
                return
        # 无指纹或指纹未命中：按 url_hash 更新/插入
        existing = conn.execute("SELECT url_hash FROM ai_cache WHERE url_hash = ?", (h,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE ai_cache SET video_title=?, subtitle_text=?, source=?, result_json=?, updated_at=?, fingerprint=COALESCE(NULLIF(?, ''), fingerprint) WHERE url_hash=?",
                (video_title, subtitle_text, source, result_json, now, fingerprint or '', h),
            )
        else:
            conn.execute(
                "INSERT INTO ai_cache (url_hash, url, fingerprint, video_title, subtitle_text, source, result_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (h, url, fingerprint or '', video_title, subtitle_text, source, result_json, now, now),
            )
            conn.execute(
                "DELETE FROM ai_cache WHERE url_hash NOT IN (SELECT url_hash FROM ai_cache ORDER BY updated_at DESC LIMIT 50)"
            )


def list_history(limit: int = 20) -> list[dict]:
    """列出历史学习记录。"""
    with sqlite3.connect(str(DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT url, video_title, source, result_json, created_at FROM ai_cache ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    results = []
    for row in rows:
        try:
            result = json.loads(row[3]) if row[3] else {}
        except json.JSONDecodeError:
            result = {}
        results.append({
            "url": row[0],
            "video_title": row[1] or result.get("title", ""),
            "source": row[2],
            "summary": result.get("summary", ""),
            "notes": result.get("notes", ""),
            "flashcards": result.get("flashcards", []),
            "created_at": row[4],
        })
    return results


def delete_cache(url: str, fingerprint: str = None):
    """删除缓存：按指纹 + URL hash 双重清理。"""
    h = _url_hash(url)
    with sqlite3.connect(str(DB_PATH)) as conn:
        if fingerprint:
            conn.execute("DELETE FROM ai_cache WHERE fingerprint = ?", (fingerprint,))
        conn.execute("DELETE FROM ai_cache WHERE url_hash = ?", (h,))


def delete_whisper_cache(url: str, fingerprint: str = None):
    """删除 Whisper 缓存。"""
    h = _url_hash(url)
    with sqlite3.connect(str(DB_PATH)) as conn:
        if fingerprint:
            conn.execute("DELETE FROM whisper_cache WHERE fingerprint = ?", (fingerprint,))
        conn.execute("DELETE FROM whisper_cache WHERE url_hash = ?", (h,))


# ──── Whisper 转录缓存 ────

def _ensure_whisper_table():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whisper_cache (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                fingerprint TEXT DEFAULT '',
                subtitle_text TEXT NOT NULL,
                language TEXT DEFAULT '',
                raw_text TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        try:
            conn.execute("ALTER TABLE whisper_cache ADD COLUMN raw_text TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE whisper_cache ADD COLUMN fingerprint TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass


_ensure_whisper_table()


def get_whisper_cache(url: str, fingerprint: str = None) -> str | None:
    """获取缓存的 Whisper 转录文本（校正后）。先指纹，再 URL。"""
    h = _url_hash(url)
    with sqlite3.connect(str(DB_PATH)) as conn:
        if fingerprint:
            row = conn.execute(
                "SELECT subtitle_text FROM whisper_cache WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if row:
                return row[0]
        row = conn.execute(
            "SELECT subtitle_text FROM whisper_cache WHERE url_hash = ?",
            (h,),
        ).fetchone()
    return row[0] if row else None


def save_whisper_cache(url: str, subtitle_text: str, language: str = "", raw_text: str = "", fingerprint: str = None):
    """保存 Whisper 转录文本。"""
    h = _url_hash(url)
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        if fingerprint:
            existing = conn.execute("SELECT url_hash FROM whisper_cache WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE whisper_cache SET url=?, url_hash=?, subtitle_text=?, language=?, raw_text=?, created_at=? WHERE fingerprint=?",
                    (url, h, subtitle_text, language, raw_text, now, fingerprint),
                )
                return
        conn.execute(
            "INSERT OR REPLACE INTO whisper_cache (url_hash, url, fingerprint, subtitle_text, language, raw_text, created_at) VALUES (?,?,?,?,?,?,?)",
            (h, url, fingerprint or '', subtitle_text, language, raw_text, now),
        )


# ──── 视频信息缓存（避免重复 yt-dlp 解析） ────

def _ensure_video_info_table():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS video_info_cache (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                fingerprint TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                title TEXT DEFAULT '',
                info_json TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        try:
            conn.execute("ALTER TABLE video_info_cache ADD COLUMN fingerprint TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass


_ensure_video_info_table()


def get_video_info_cache(url: str, fingerprint: str = None) -> dict | None:
    """获取缓存的视频基本信息。先指纹，再 URL。"""
    h = _url_hash(url)
    with sqlite3.connect(str(DB_PATH)) as conn:
        if fingerprint:
            row = conn.execute(
                "SELECT duration, title, info_json FROM video_info_cache WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if row:
                info = json.loads(row[2]) if row[2] else {}
                info["duration"] = row[0]
                info["title"] = row[1]
                return info
        row = conn.execute(
            "SELECT duration, title, info_json FROM video_info_cache WHERE url_hash = ?",
            (h,),
        ).fetchone()
    if not row:
        return None
    info = json.loads(row[2]) if row[2] else {}
    info["duration"] = row[0]
    info["title"] = row[1]
    return info


def save_video_info_cache(url: str, info, fingerprint: str = None):
    """保存视频基本信息到缓存。"""
    h = _url_hash(url)
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).isoformat()

    if hasattr(info, "model_dump"):
        info_dict = info.model_dump()
    elif hasattr(info, "dict"):
        info_dict = info.dict()
    else:
        info_dict = dict(info)

    duration = info_dict.get("duration") or 0
    title = info_dict.get("title") or ""

    with sqlite3.connect(str(DB_PATH)) as conn:
        if fingerprint:
            existing = conn.execute("SELECT url_hash FROM video_info_cache WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE video_info_cache SET url=?, url_hash=?, duration=?, title=?, info_json=?, created_at=? WHERE fingerprint=?",
                    (url, h, duration, title, json.dumps(info_dict, ensure_ascii=False), now, fingerprint),
                )
                return
        conn.execute(
            "INSERT OR REPLACE INTO video_info_cache (url_hash, url, fingerprint, duration, title, info_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (h, url, fingerprint or '', duration, title, json.dumps(info_dict, ensure_ascii=False), now),
        )
