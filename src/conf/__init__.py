from contextvars import ContextVar

# 初始化一个保存任务id的context
task_id_context = ContextVar("task_id")