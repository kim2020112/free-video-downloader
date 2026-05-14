"""AI 处理流水线 — 编排字幕获取后的所有 AI 处理步骤。"""

import asyncio
from typing import Callable, Optional
from database import get_db
from core import ai_client


async def process_video(
    video_id: int,
    subtitle_text: str,
    video_title: str = "",
    progress_callback: Optional[Callable] = None,
):
    """完整 AI 处理流程：总结 → 思维导图 → 笔记 → 向量化。"""
    loop = asyncio.get_event_loop()

    async def _progress(pct: float, msg: str):
        if progress_callback:
            await progress_callback(pct, msg)

    await _progress(10, "正在生成 AI 总结...")
    summary = await loop.run_in_executor(
        None, ai_client.summarize, subtitle_text, video_title
    )
    _save_output(video_id, "summary", summary)

    await _progress(35, "正在生成思维导图...")
    mindmap = await loop.run_in_executor(
        None, ai_client.generate_mindmap, subtitle_text, video_title
    )
    _save_output(video_id, "mindmap", mindmap)

    await _progress(60, "正在生成学习笔记...")
    notes = await loop.run_in_executor(
        None, ai_client.generate_notes, subtitle_text, video_title
    )
    _save_output(video_id, "notes", notes)

    await _progress(80, "正在建立知识索引...")
    try:
        await _vectorize(video_id, subtitle_text, video_title)
    except Exception as e:
        print(f"[向量化] 跳过（非致命）: {e}")

    await _progress(100, "处理完成")


def _save_output(video_id: int, output_type: str, content: str):
    from config import AI_MODEL
    with get_db() as conn:
        conn.execute(
            "DELETE FROM ai_outputs WHERE video_id = ? AND output_type = ?",
            (video_id, output_type),
        )
        conn.execute(
            "INSERT INTO ai_outputs (video_id, output_type, content, model_used) VALUES (?, ?, ?, ?)",
            (video_id, output_type, content, AI_MODEL),
        )


async def _vectorize(video_id: int, text: str, title: str):
    from core.vectorstore import add_video_chunks
    chunks = _chunk_text(text, chunk_size=500, overlap=50)
    await asyncio.wait_for(
        add_video_chunks(video_id, title, chunks),
        timeout=60,
    )


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    paragraphs = text.split("\n")
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > chunk_size and current:
            chunks.append("\n".join(current))
            keep = current[-1:] if len(current[-1]) < overlap else []
            current = keep
            current_len = sum(len(p) for p in current)
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n".join(current))
    return chunks
