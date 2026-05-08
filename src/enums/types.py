from enum import Enum


class ErrorTypes(str, Enum):
    """
    错误类型
    """
    TIME = "time"
    METRIC = "metric"
    INTENT = "intent"
    FIELD = "field"
    SYNTAX = "syntax"
