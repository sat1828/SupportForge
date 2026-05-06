#!/usr/bin/env python3
"""
KB Seeder — chunks and embeds all .txt files under data/knowledge_base/.
Run: python scripts/seed_kb.py
"""
import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://supportforge:supportforge_dev@localhost:5432/supportforge")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "seed_script_secret_key_min_32_chars")
os.environ.setdefault("ENVIRONMENT", "development")

KB_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"
CHUNK_SIZE = 400   # tokens (~1600 chars)
CHUNK_OVERLAP = 50


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    words = text.split()
    chunks, current = [], []
    for word in words:
        current.append(word)
        if len(current) >= chunk_size:
            chunks.append(" ".join(current))
            current = current[-CHUNK_OVERLAP:]
    if current:
        chunks.append(" ".join(current))
    return chunks


async def seed():
    from app.database import create_all_tables, AsyncSessionLocal
    from app.models.knowledge_base import KnowledgeBaseChunk
    from app.rag.embedder import embedder
    from app.rag.bm25_index import bm25_index
    from sqlalchemy import select

    print("🚀 Starting KB seeding...")
    await create_all_tables()

    txt_files = list(KB_DIR.glob("*.txt"))
    print(f"📁 Found {len(txt_files)} documents")

    async with AsyncSessionLocal() as db:
        total_chunks = 0
        for doc_path in txt_files:
            doc_name = doc_path.stem
            text = doc_path.read_text(encoding="utf-8")
            chunks = chunk_text(text)

            print(f"  ↳ {doc_name}: {len(chunks)} chunks")
            texts_for_embedding = chunks

            # Batch embed
            embeddings = await embedder.embed_batch(texts_for_embedding)

            for i, (chunk_text_val, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_hash = hashlib.sha256(chunk_text_val.encode()).hexdigest()

                # Skip if exists
                existing = await db.scalar(
                    select(KnowledgeBaseChunk).where(KnowledgeBaseChunk.chunk_hash == chunk_hash)
                )
                if existing:
                    continue

                chunk = KnowledgeBaseChunk(
                    id=uuid.uuid4(),
                    source_file=doc_path.name,
                    doc_type="policy",
                    category=doc_name,
                    language="en",
                    chunk_index=i,
                    chunk_hash=chunk_hash,
                    text=chunk_text_val,
                    embedding=embedding,
                    boost_score=1.0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(chunk)
                total_chunks += 1

        await db.commit()

    # Rebuild BM25
    await bm25_index.rebuild_from_db()

    print(f"\n✅ Seeded {total_chunks} new chunks. BM25 index rebuilt.")


if __name__ == "__main__":
    asyncio.run(seed())
