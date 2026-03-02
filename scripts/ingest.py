#!/usr/bin/env python3
"""
ingest.py — One-time script to build the Qdrant vector index from scraped_data.json.

Run inside Docker:
    docker compose exec api python scripts/ingest.py

Or directly:
    python scripts/ingest.py
"""
import hashlib
import json
import logging
import os
import pickle
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from rank_bm25 import BM25Okapi

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "bdlaws_sections_v1")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
SCRAPED_DATA_PATH = os.path.join(DATA_DIR, "scraped_data.json")
DOCSTORE_PATH = os.path.join(DATA_DIR, "docstore.jsonl")
BM25_PATH = os.path.join(DATA_DIR, "bm25.pkl")

MAX_CHARS_PER_CHUNK = int(os.getenv("MAX_CHARS_PER_CHUNK", "4500"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "600"))
JURISDICTION_DEFAULT = os.getenv("JURISDICTION_DEFAULT", "Bangladesh")
SOURCE_DEFAULT = os.getenv("SOURCE_DEFAULT", "bdlaws.minlaw.gov.bd")
VECTOR_SIZE = 384
BATCH_SIZE = 20


# ── Utilities ─────────────────────────────────────────────────────────────────

def sha256_text(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()

def string_to_uuid(s: str) -> str:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=h[:16]))

def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9]+", text.lower())

def safe_int_year(title: str) -> Optional[int]:
    try:
        return int(title.split(",")[-1].strip())
    except Exception:
        return None

def split_text(text: str, max_chars: int, overlap: int) -> List[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end]
        if end < len(text):
            cut = max(chunk.rfind("."), chunk.rfind(";"), chunk.rfind("\n"))
            if cut > max_chars * 0.6:
                chunk = chunk[: cut + 1]
                end = start + len(chunk)
        chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# ── Build chunks ──────────────────────────────────────────────────────────────

def build_chunks(scraped_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    today = date.today().isoformat()
    for act in scraped_data:
        act_title = act.get("title", "")
        act_no = act.get("Act_No")
        act_link = act.get("link")
        act_year = safe_int_year(act_title)
        act_slug = Path(act_link).name.replace(".html", "") if act_link else "unknown"

        for sec_idx, sec_obj in enumerate(act.get("sub_details", []), start=1):
            if not isinstance(sec_obj, dict):
                continue
            section_title = list(sec_obj.keys())[0]
            section_text = sec_obj[section_title]

            for chunk_i, chunk_text in enumerate(
                split_text(section_text, MAX_CHARS_PER_CHUNK, CHUNK_OVERLAP_CHARS)
            ):
                doc_id = f"bdlaws:{act_slug}:sec-{sec_idx}:chunk-{chunk_i}"
                citation = f"{act_title}"
                if act_no:
                    citation += f" (Act No. {act_no})"
                citation += f", Section {sec_idx}"

                out.append({
                    "doc_id": doc_id,
                    "text": chunk_text,
                    "metadata": {
                        "doc_id": doc_id,
                        "jurisdiction": JURISDICTION_DEFAULT,
                        "source": SOURCE_DEFAULT,
                        "document_type": "law",
                        "act_title": act_title,
                        "act_no": act_no,
                        "act_year": act_year,
                        "act_link": act_link,
                        "section_number": sec_idx,
                        "section_title": section_title,
                        "chunk_index": chunk_i,
                        "citation": citation,
                        "content_hash": sha256_text(chunk_text),
                        "ingested_at": today,
                    },
                })
    return out


# ── Qdrant ────────────────────────────────────────────────────────────────────

def ensure_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        logger.info(f"Collection '{COLLECTION_NAME}' already exists — skipping creation.")
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=qm.VectorParams(size=VECTOR_SIZE, distance=qm.Distance.COSINE),
    )
    logger.info(f"Collection '{COLLECTION_NAME}' created.")

def upsert_qdrant(client: QdrantClient, chunks: List[Dict], vectors: List[List[float]]):
    total = len(chunks)
    for i in range(0, total, BATCH_SIZE):
        batch_c = chunks[i : i + BATCH_SIZE]
        batch_v = vectors[i : i + BATCH_SIZE]
        points = [
            qm.PointStruct(
                id=string_to_uuid(c["doc_id"]),
                vector=v,
                payload={"text": c["text"], **c["metadata"]},
            )
            for c, v in zip(batch_c, batch_v)
        ]
        # Retry up to 3 times on timeout
        for attempt in range(3):
            try:
                client.upsert(collection_name=COLLECTION_NAME, points=points)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                logger.warning(f"  Retry {attempt+1}/3 after error: {e}")
                import time; time.sleep(3)
        logger.info(f"  Uploaded {min(i + BATCH_SIZE, total)}/{total} chunks")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    logger.info(f"Loading scraped data from {SCRAPED_DATA_PATH} ...")
    with open(SCRAPED_DATA_PATH, "r", encoding="utf-8") as f:
        scraped_data = json.load(f)

    logger.info("Building chunks ...")
    chunks = build_chunks(scraped_data)
    logger.info(f"  {len(chunks)} chunks created.")

    logger.info(f"Writing docstore to {DOCSTORE_PATH} ...")
    with open(DOCSTORE_PATH, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    logger.info("Building BM25 index ...")
    corpus = [tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    with open(BM25_PATH, "wb") as f:
        pickle.dump({"bm25": bm25, "chunks": chunks}, f)
    logger.info(f"  BM25 saved to {BM25_PATH}")

    logger.info("Loading embedding model BAAI/bge-small-en-v1.5 ...")
    model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")

    logger.info("Embedding all chunks ...")
    vectors = model.encode(
        [c["text"] for c in chunks],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()

    logger.info(f"Connecting to Qdrant at {QDRANT_URL} ...")
    kwargs = {"url": QDRANT_URL, "timeout": 60}
    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY
    client = QdrantClient(**kwargs)
    ensure_collection(client)

    logger.info("Uploading to Qdrant ...")
    upsert_qdrant(client, chunks, vectors)

    logger.info(f"\n✅ Ingestion complete — {len(chunks)} legal chunks indexed.")


if __name__ == "__main__":
    main()
