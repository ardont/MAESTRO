from logging import getLogger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .schemas import (Role, LLMSaveRequest, Message)

logger = getLogger(__name__)

app = FastAPI()

app.post('/memory')
async def save_dialog(
        request: LLMSaveRequest,
):
    logger.info('saving dialog %s: %s', request.dialog_id, request.messages)
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
)


