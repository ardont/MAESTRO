"""Non-destructive dense + BM25 indexing and import of parser chunks.jsonl."""
import argparse
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models
from .config import COLLECTION_NAME, EMBEDDING_DIM, QDRANT_HOST, QDRANT_PORT, QDRANT_STORAGE_DIR

_cached_qdrant_client = None


def get_qdrant_client() -> QdrantClient:
    """Use the configured backend only. A server outage must not switch databases."""
    global _cached_qdrant_client
    if _cached_qdrant_client is None:
        mode = os.environ.get('QDRANT_MODE', 'server').lower()
        if mode == 'local':
            client = QdrantClient(path=str(QDRANT_STORAGE_DIR))
        elif mode == 'server':
            options = {'timeout': float(os.environ.get('QDRANT_TIMEOUT', '30')),
                       'api_key': os.environ.get('QDRANT_API_KEY') or None}
            url = os.environ.get('QDRANT_URL')
            client = (QdrantClient(url=url, **options) if url else
                      QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, **options))
        else:
            raise ValueError('QDRANT_MODE must be server or local')
        try:
            client.get_collections()
        except Exception:
            client.close()
            raise
        _cached_qdrant_client = client
    return _cached_qdrant_client


def init_collection(client: QdrantClient, recreate: bool = False):
    """Create if absent, validate if present. Never delete knowledge on reindex/startup."""
    if recreate:
        raise ValueError('recreate=True is disabled: use a new QDRANT_COLLECTION for a fresh index')
    if not client.collection_exists(COLLECTION_NAME):
        try:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
                sparse_vectors_config={'bm25': models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
        except Exception:
            # A concurrent initializer may have created it; validate the winner's schema.
            if not client.collection_exists(COLLECTION_NAME):
                raise
    info = client.get_collection(COLLECTION_NAME)
    params = info.config.params
    dense = params.vectors
    if isinstance(dense, dict):
        dense = dense.get('')
    if dense is None or dense.size != EMBEDDING_DIM or dense.distance != models.Distance.COSINE:
        raise ValueError(f'{COLLECTION_NAME}: expected unnamed dense vector, size={EMBEDDING_DIM}, Cosine; '
                         'existing collection is unchanged. Use another QDRANT_COLLECTION.')
    sparse = (params.sparse_vectors or {}).get('bm25')
    if sparse is None or sparse.modifier != models.Modifier.IDF:
        client.update_collection(
            collection_name=COLLECTION_NAME,
            sparse_vectors_config={'bm25': models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        # Adding the slot preserves existing points; import texts again to populate BM25.
    for field in ('category', 'doc_type', 'doc_id', 'document_id', 'document_format', 'source_url'):
        if field not in (info.payload_schema or {}):
            client.create_payload_index(COLLECTION_NAME, field, models.PayloadSchemaType.KEYWORD, wait=True)


def normalize_chunk(chunk: dict) -> dict:
    """Keep every parser payload field, including media and canonical web citations."""
    payload = dict(chunk)
    for key in ('chunk_id', 'doc_id', 'title', 'text'):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f'Missing/non-string {key}')
    UUID(payload['chunk_id'])
    source = payload.get('source_url') or payload.get('url')
    if not isinstance(source, str) or urlsplit(source).scheme not in ('http', 'https'):
        raise ValueError(f"{payload['chunk_id']}: missing HTTP(S) source URL")
    path = urlsplit(source).path.lower()
    if '/filestorage/download' in path or path.endswith(('.pdf', '.docx', '.doc')):
        raise ValueError(f"{payload['chunk_id']}: source must be a knowledge-base page, not a download URL")
    payload['url'] = payload['source_url'] = source
    for key, default in {'category': '', 'doc_type': 'instruction', 'section_header': '',
                         'document_id': None, 'document_format': None, 'download_url': None,
                         'page_number': None, 'page_label': None, 'images': [], 'video_links': []}.items():
        payload.setdefault(key, default)
    for field in ('images', 'video_links'):
        if not isinstance(payload[field], list):
            raise ValueError(f'{field} must be an array')
    # Fail before network writes if metadata contains unsupported Python values/NaN.
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


def upsert_chunks_batch(client: QdrantClient, chunks: list, embeddings: list,
                        sparse_embeddings: list, batch_size: int = 100):
    """Upsert stable UUIDs; keep all other documents and all payload fields."""
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    if not len(chunks) == len(embeddings) == len(sparse_embeddings):
        raise ValueError('chunks, dense embeddings and sparse embeddings must have equal length')
    points = []
    ids = set()
    for chunk, dense, sparse in zip(chunks, embeddings, sparse_embeddings):
        payload = normalize_chunk(chunk)
        if payload['chunk_id'] in ids:
            raise ValueError('Duplicate chunk_id: ' + payload['chunk_id'])
        ids.add(payload['chunk_id'])
        dense = dense.tolist() if hasattr(dense, 'tolist') else list(dense)
        if len(dense) != EMBEDDING_DIM or not all(math.isfinite(v) for v in dense):
            raise ValueError(f'Expected {EMBEDDING_DIM} finite dense values')
        if not isinstance(sparse, models.SparseVector):
            if isinstance(sparse, dict):
                sparse = models.SparseVector(**sparse)
            else:
                sparse = models.SparseVector(indices=list(sparse.indices), values=list(sparse.values))
        if (len(sparse.indices) != len(sparse.values) or len(set(sparse.indices)) != len(sparse.indices)
                or any(i < 0 for i in sparse.indices) or not all(math.isfinite(v) for v in sparse.values)):
            raise ValueError('Invalid sparse vector indices/values')
        points.append(models.PointStruct(id=payload['chunk_id'],
                                        vector={'': dense, 'bm25': sparse}, payload=payload))
    for start in range(0, len(points), batch_size):
        client.upsert(COLLECTION_NAME, points=points[start:start + batch_size], wait=True)


def load_chunks(path: Path) -> list[dict]:
    """Accept parser JSONL or a JSON array/{chunks: [...]}, not the raw articles tree."""
    with path.open(encoding='utf-8-sig') as stream:
        if path.suffix.lower() == '.jsonl':
            chunks = []
            for number, line in enumerate(stream, 1):
                if line.strip():
                    try:
                        chunks.append(json.loads(line))
                    except ValueError as exc:
                        raise ValueError(f'{path}:{number}: invalid JSON') from exc
        else:
            chunks = json.load(stream)
            if isinstance(chunks, dict):
                chunks = chunks.get('chunks')
    if not isinstance(chunks, list) or not chunks:
        raise ValueError('Expected non-empty chunks.jsonl or a JSON array of chunks; use the parser chunks export')
    result = [normalize_chunk(chunk) for chunk in chunks]
    if len({c['chunk_id'] for c in result}) != len(result):
        raise ValueError('Duplicate chunk_id in input')
    return result


def import_chunks(path: Path, batch_size: int = 32, client=None, dense_embedder=None, sparse_embedder=None):
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    chunks = load_chunks(path)  # Validate all input before creating/writing collections.
    client = client if client is not None else get_qdrant_client()
    init_collection(client)
    if dense_embedder is None or sparse_embedder is None:
        from .embedder import get_embedder, get_sparse_embedder
        dense_embedder = dense_embedder if dense_embedder is not None else get_embedder()
        sparse_embedder = sparse_embedder if sparse_embedder is not None else get_sparse_embedder()
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        texts = [chunk['text'] for chunk in batch]
        dense = dense_embedder.get_embeddings_batch(texts, batch_size=batch_size)
        sparse = sparse_embedder.get_sparse_embeddings_batch(texts)
        upsert_chunks_batch(client, batch, dense, sparse, batch_size=batch_size)
        print(f'[QDRANT] Imported {min(start + batch_size, len(chunks))}/{len(chunks)}')
    return len(chunks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='Path to parser chunks.jsonl')
    parser.add_argument('--batch-size', default=32, type=int)
    parser.add_argument('--validate-only', action='store_true', help='Validate JSON without Qdrant or models')
    args = parser.parse_args()
    if args.validate_only:
        print(f'Valid chunks: {len(load_chunks(args.input))}')
    else:
        import_chunks(args.input, batch_size=args.batch_size)
