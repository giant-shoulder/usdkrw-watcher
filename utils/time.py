from datetime import datetime, time, date
import pytz
from config import ENVIRONMENT

TIMEZONE = pytz.timezone("Asia/Seoul")

def now_kst() -> datetime:
    """한국 시간 기준 현재 시각 반환"""
    return datetime.now(TIMEZONE)

def is_weekend() -> bool:
    """
    토요일(5), 일요일(6)에는 True 반환
    단, local 환경에서는 항상 False (루프 정상 실행)
    """
    if ENVIRONMENT == "local":
        return False
    return now_kst().weekday() >= 5

def is_sleep_time() -> bool:
    """
    운영 환경에서만 0시~7시 사이 True 반환
    - local 환경은 항상 False (알림 발송 유지)
    """
    if ENVIRONMENT == "local":
        return False

    hour = now_kst().hour
    return 0 <= hour < 7  # 0시 ~ 6시까지는 True

def is_market_open() -> bool:
    """서울 외환시장 운영 시간 (09:00 ~ 15:30) 내인지 확인"""
    now = now_kst()
    return now.weekday() < 5 and time(9, 0) <= now.time() <= time(15, 30)

def is_time_between(start_h: int, start_m: int, end_h: int, end_m: int) -> bool:
    """임의의 시간 범위 내인지 확인 (평일 기준)"""
    now = now_kst()
    start = time(start_h, start_m)
    end = time(end_h, end_m)
    return now.weekday() < 5 and start <= now.time() < end

def is_exact_time(hour: int, minute: int) -> bool:
    """지정된 시각과 정확히 일치하는지 확인"""
    now = now_kst()
    return now.hour == hour and now.minute == minute

def is_scrape_time(last_scraped: date | None = None) -> bool:
    """
    오전 11시대에 해당하며 오늘 아직 스크랩하지 않았다면 True 반환
    """
    now = now_kst()
    today = now.date()

    if now.weekday() >= 5:  # 주말 제외
        return False
    if 11 <= now.hour < 12:
        if last_scraped is None or last_scraped != today:
            return True
    return False