from datetime import datetime, time, date, timedelta
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
    운영 환경에서만 알림 발송 제한 시간 적용
    - local 환경: 항상 False (알림 발송 유지)
    - 운영 환경:
        • 월요일: 0시 ~ 7시까지 중지
        • 화~금요일: 2시 ~ 7시까지 중지
        • 주말: 기존 주말 처리 로직 따름 (is_weekend() 별도 사용)
    """
    if ENVIRONMENT == "local":
        return False

    now = now_kst()
    hour = now.hour
    weekday = now.weekday()  # 월=0, 화=1, ... 일=6

    if weekday == 0:  # 월요일
        return 0 <= hour < 7
    elif 1 <= weekday <= 4:  # 화~금
        return 2 <= hour < 7
    else:
        return False

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


def get_recent_completed_30min_block(now: datetime) -> tuple[datetime, datetime]:
    """
    현재 시각 기준으로 가장 최근 완료된 30분 블록 반환

    예:
    - now = 15:29 → (15:00 ~ 15:30)
    - now = 15:31 → (15:00 ~ 15:30) ← 15:30 ~ 16:00은 아직 미완료
    - now = 00:05 → (23:30 ~ 00:00)
    """
    minute = now.minute
    hour = now.hour
    date = now.date()

    # ✅ tz-aware datetime 생성
    base = datetime.combine(date, time.min).replace(tzinfo=TIMEZONE)

    if minute < 30:
        end = base.replace(hour=hour, minute=0)
    else:
        end = base.replace(hour=hour, minute=30)

    start = end - timedelta(minutes=30)

    # ✅ future block 처리
    if end > now:
        end -= timedelta(minutes=30)
        start -= timedelta(minutes=30)

    return start, end

