from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from api.dependiences import get_services
from api.schema.request import ChatRequest
from service.chat_service import ChatService

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def stream_chat(chat_request: ChatRequest, chat_service: ChatService = Depends(get_services)) -> StreamingResponse:
    """
    处理用户发起的对话
    :param chat_request:
    :param chat_service:
    :return:
    """
    chunk = chat_service.stream_chat(chat_request.question)
    return StreamingResponse(
        content=chunk,
        media_type="text/event-stream"
    )
