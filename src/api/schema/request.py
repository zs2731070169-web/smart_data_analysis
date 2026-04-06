from typing import Annotated

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):

    question: Annotated[str, Field(..., min_length=1, max_length=256, description="用户发起的对话")]