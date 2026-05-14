"""ChromaDB 向量存储封装 — 用于 RAG 语义搜索。"""

import asyncio
from typing import Optional
import chromadb
from config import CHROMA_PATH

_client: Optional[chromadb.PersistentClient] = None
COLLECTION_NAME = "video_chunks"


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def _get_collection():
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


async def add_video_chunks(video_id: int, video_title: str, chunks: list[str]):
    collection = _get_collection()
    ids = [f"v{video_id}_c{i}" for i in range(len(chunks))]
    metadatas = [
        {"video_id": video_id, "video_title": video_title, "chunk_index": i}
        for i in range(len(chunks))
    ]
    await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: collection.upsert(ids=ids, documents=chunks, metadatas=metadatas),
    )


async def query_chunks(
    query_text: str,
    n_results: int = 5,
    video_id: Optional[int] = None,
) -> dict:
    collection = _get_collection()
    where = {"video_id": video_id} if video_id else None
    results = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
        ),
    )
    return {
        "documents": results["documents"][0] if results["documents"] else [],
        "metadatas": results["metadatas"][0] if results["metadatas"] else [],
    }
