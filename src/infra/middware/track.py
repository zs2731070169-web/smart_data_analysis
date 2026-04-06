import uuid
from typing import Callable

from fastapi.requests import Request

from infra.log import task_id_context


async def add_context_id(request: Request, call_next: Callable):
    """
    请求前添加上下文id，用于日志追踪
    :param request:
    :param call_next:
    :return:
    """
    task_id_context.set(uuid.uuid4().hex)
    response = await call_next(request)
    return response
