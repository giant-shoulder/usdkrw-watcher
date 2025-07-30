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
    현재 시각 기준으로 가장 최근 '완료된' 30분 블록 반환
    - 기준: 각 블록의 end 시각 ±120초(2분 0초) 안에 now가 도달하면 완료로 간주
    - 또는 end + threshold 이후까지 도달했으면 다음 블록이 완료된 것으로 판단

    예:
    - now = 15:28:00 → (15:00 ~ 15:30)
    - now = 15:31:00 → (15:00 ~ 15:30)
    - now = 15:33:00 → (15:30 ~ 16:00)
    """
    threshold_sec = 120

    # ✅ tz-aware 자정 기준
    base = datetime.combine(now.date(), time.min).replace(tzinfo=TIMEZONE)
    minute = now.minute
    hour = now.hour

    # 가장 가까운 0분 or 30분 end 시각 후보
    if minute < 30:
        candidate_end = base.replace(hour=hour, minute=30)
    else:
        candidate_end = base.replace(hour=(hour + 1) % 24, minute=0)
        if hour == 23:
            candidate_end += timedelta(days=1)

    # now가 threshold 범위 안이면 이 블록을 완료로 판단
    time_diff = (now - candidate_end).total_seconds()

    if abs(time_diff) <= threshold_sec:
        start = candidate_end - timedelta(minutes=30)
        return start, candidate_end

    elif time_diff > threshold_sec:
        # 이미 다음 블록도 완료됨
        next_end = candidate_end + timedelta(minutes=30)
        start = next_end - timedelta(minutes=30)
        return start, next_end

    else:
        # 아직 블록 종료 기준에 도달하지 않음 → 전 블록 반환
        end = candidate_end - timedelta(minutes=30)
        start = end - timedelta(minutes=30)
        return start, end



