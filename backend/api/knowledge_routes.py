from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from database import get_db

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/videos")
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    platform: Optional[str] = None,
):
    offset = (page - 1) * page_size
    with get_db() as conn:
        conditions = []
        params = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = conn.execute(
            f"SELECT COUNT(*) FROM videos {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM videos {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


@router.get("/videos/{video_id}")
async def get_video(video_id: int):
    with get_db() as conn:
        video = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        subtitles = conn.execute(
            "SELECT * FROM subtitles WHERE video_id = ?", (video_id,)
        ).fetchall()
        ai_outputs = conn.execute(
            "SELECT * FROM ai_outputs WHERE video_id = ?", (video_id,)
        ).fetchall()
    outputs_by_type = {}
    for o in ai_outputs:
        outputs_by_type[o["output_type"]] = o["content"]
    return {
        "video": dict(video),
        "subtitles": [dict(s) for s in subtitles],
        "ai_outputs": outputs_by_type,
    }


@router.delete("/videos/{video_id}")
async def delete_video(video_id: int):
    with get_db() as conn:
        video = conn.execute(
            "SELECT id FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    return {"ok": True}


@router.get("/tags")
async def list_tags():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
    return [dict(r) for r in rows]
