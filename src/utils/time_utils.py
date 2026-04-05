from datetime import datetime, timezone, timedelta

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"
DATETIME_FORMAT = f"{DATE_FORMAT} {TIME_FORMAT}"

def quarter(month_at: int):
    """计算季度"""
    return (month_at - 1) // 3 + 1


def datetime_format(time_at: datetime, format: str) -> str:
    """
    获取格式化时间
    :param format:
    :param time_at:
    :return:
    """
    return time_at.strftime(format=format)

def month():
    """获取当前月份"""
    return now().month

def now() -> datetime:
    """获取当前时间，时区为东八区"""
    return datetime.today()
