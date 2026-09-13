import asyncio
from logging import getLogger

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .schemas import LLMSaveRequest
from ..dialog_knowledge import save_dialog_knowledge

logger = getLogger(__name__)
app = FastAPI()
_root = Path(__file__).resolve().parents[3]
app.mount('/media', StaticFiles(directory=_root / 'media', check_dir=False), name='knowledge-media')
app.mount('/images', StaticFiles(directory=_root / 'dataset' / 'images', check_dir=False), name='knowledge-images')
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
