from datetime import datetime, timezone, timedelta

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"
DATETIME_FORMAT = f"{DATE_FORMAT} {TIME_FORMAT}"

def datetime_format(time_at: datetime, format: str) -> str:
    """
    获取格式化时间
    :param format:
    :param time_at:
    :return:
    """
    return time_at.strftime(format=format)


def any_datetime(days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> datetime:
    """
    获取任意东八区时间
    :param days:
    :param hours:
    :param minutes:
    :param seconds:
    :return:
    """
    return (datetime.now(timezone(timedelta(hours=8)))
            + timedelta(days=days, seconds=seconds, minutes=minutes, hours=hours))
