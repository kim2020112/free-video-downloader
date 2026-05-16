"""视频入库服务 — 编排完整的 URL → 字幕 → AI 处理 → 存储流程。"""

import asyncio
from datetime import datetime
from database import get_db
from core.subtitle import acquire_subtitle, _detect_platform
from core.ai_pipeline import process_video
from core.task_queue import Task, TaskStatus


async def ingest_video(url: str, task: Task = None):
    """完整入库流程。"""

    async def _update_progress(pct: float, msg: str):
        if task:
            task.progress = pct
            task.message = msg

    # 1. 解析视频信息
    await _update_progress(5, "正在解析视频信息...")
    from core.downloader import VideoDownloader
    downloader = VideoDownloader()
    info = await asyncio.get_event_loop().run_in_executor(
        None, downloader.parse_info, url
    )

    platform = _detect_platform(url) or "other"
    video_id = _upsert_video(
        url=url,
        title=info.title,
        platform=platform,
        uploader=info.uploader,
        duration=info.duration,
        thumbnail_url=info.thumbnail,
        description=info.description,
    )

    _update_video_status(video_id, "processing")

    # 2. 获取字幕
    await _update_progress(15, "正在获取字幕...")
    subtitle_result = await acquire_subtitle(url, downloader=downloader)

    if not subtitle_result:
        _update_video_status(video_id, "failed", "无法获取字幕")
        raise Exception("无法获取字幕，该视频可能没有可用的字幕源")

    _save_subtitle(video_id, subtitle_result)

    # 3. AI 处理
    await _update_progress(25, "正在进行 AI 处理...")

    async def _ai_progress(pct, msg):
        await _update_progress(25 + pct * 0.7, msg)

    await process_video(
        video_id=video_id,
        subtitle_text=subtitle_result.full_text,
        video_title=info.title,
        progress_callback=_ai_progress,
    )

    _update_video_status(video_id, "completed")
    return video_id


def _upsert_video(url, title, platform, uploader, duration, thumbnail_url, description) -> int:
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM videos WHERE url = ?", (url,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE videos SET title=?, platform=?, uploader=?, duration=?, thumbnail_url=?, description=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title, platform, uploader, duration, thumbnail_url, description, existing["id"]),
            )
            return existing["id"]
        cursor = conn.execute(
            "INSERT INTO videos (url, title, platform, uploader, duration, thumbnail_url, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, title, platform, uploader, duration, thumbnail_url, description),
        )
        # 保持最多 50 条
        conn.execute(
            "DELETE FROM videos WHERE id NOT IN (SELECT id FROM videos ORDER BY created_at DESC LIMIT 50)"
        )
        return cursor.lastrowid


def _save_subtitle(video_id: int, result):
    import json
    with get_db() as conn:
        conn.execute("DELETE FROM subtitles WHERE video_id = ?", (video_id,))
        conn.execute(
            "INSERT INTO subtitles (video_id, source, language, full_text, segments_json) VALUES (?, ?, ?, ?, ?)",
            (video_id, result.source, result.language, result.full_text, json.dumps(result.segments, ensure_ascii=False)),
        )


def _update_video_status(video_id: int, status: str, error: str = None):
    with get_db() as conn:
        conn.execute(
            "UPDATE videos SET status=?, error_message=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, error, video_id),
        )
