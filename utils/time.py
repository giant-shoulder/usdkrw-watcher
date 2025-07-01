# utils/time.py

from datetime import datetime
import pytz

def is_weekend():
    """토요일(5), 일요일(6)에는 True 반환"""
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    return now.weekday() >= 5

def is_sleep_time():
    """평일 오전 2시 ~ 7시 사이면 True 반환"""
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    return 2 <= now.hour < 7