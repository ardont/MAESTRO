import asyncio
from logging import getLogger

import urllib.parse
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pathlib import Path
from .schemas import LLMSaveRequest
from ..dialog_knowledge import save_dialog_knowledge

logger = getLogger(__name__)
app = FastAPI()
_root = Path(__file__).resolve().parents[3]

@app.get('/media/{file_path:path}')
async def serve_media(file_path: str):
    clean_path = urllib.parse.unquote(file_path).lstrip('/')
    candidate_roots = [
        _root / 'media',
        _root / 'dataset' / 'media',
        _root / 'dataset' / 'knowledgebase_mos_ru' / 'media',
        _root / 'dataset' / 'images',
        Path('/app/media'),
        Path('/app/dataset/media'),
        Path('/app/dataset/knowledgebase_mos_ru/media'),
    ]
    for root in candidate_roots:
        target = root / clean_path
        if target.is_file():
            return FileResponse(target)
    return Response(status_code=404, content="Image not found", media_type="text/plain")

@app.get('/images/{file_path:path}')
async def serve_images(file_path: str):
    return await serve_media(file_path)

# Serialize model work within this worker to avoid concurrent model loads / RAM spikes.
_index_lock = asyncio.Lock()


@app.post('/memory')
async def save_dialog(request: LLMSaveRequest):
    try:
        async with _index_lock:
            return await asyncio.to_thread(save_dialog_knowledge, request)
    except ValueError as exc:
        logger.warning('Invalid summary for dialog %s: %s', request.dialog_id, type(exc).__name__)
        raise HTTPException(status_code=422, detail='Dialogue or model summary is invalid') from exc
    except Exception as exc:
        logger.exception('Knowledge ingestion failed for dialog %s', request.dialog_id)
        raise HTTPException(status_code=503, detail='Knowledge ingestion unavailable; retry later') from exc
