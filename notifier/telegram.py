# Telegram messaging utility
import os
import pytz
from datetime import datetime
from telegram import Bot
from config import TELEGRAM_TOKEN, CHAT_IDS, CHECK_INTERVAL
from utils import is_sleep_time

bot = Bot(token=TELEGRAM_TOKEN)

async def send_start_message():
    if is_sleep_time():
        return
    msg = (
        "👋 *USD/KRW 환율 모니터링을 재시작합니다!*\n\n"
        "📡 *다음과 같은 환율 변동 상황이 감지되면 실시간으로 알려드릴게요:*\n\n"
        "📊 *알림 조건*\n"
        "• 📈 환율이 *급격히 상승*할 때\n"
        "• 📉 환율이 *급격히 하락*할 때\n"
        "• 📊 환율이 *볼린저 밴드 상단 또는 하단을 돌파*할 때\n"
        "• 🔁 *이동 평균선의 흐름이 바뀔 때* (골든/데드 크로스)\n"
        "• 📡 *시장 예상 환율 범위를 벗어날 때*\n"
        "• 🎯 *2가지 이상 신호가 동시에 발생*할 때 → *복합 경고와 방향성 안내*\n\n"
        "📦 *전략 해설*\n"
        f"⏱️ *환율은 {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초마다 자동 분석됩니다.*\n"
        "🌙 *주말과 평일 새벽 0시~7시에는 알림이 자동으로 중단됩니다.*"
    )
    await send_telegram(msg, target_chat_ids=["7650730456"])

async def send_telegram(message: str, target_chat_ids: list[str] | None = None):
    """
    텍스트 전송용 (알림 제한 시간 적용)
    """
    if is_sleep_time():
        return

    recipients = target_chat_ids if target_chat_ids else CHAT_IDS

    for cid in recipients:
        try:
            await bot.send_message(chat_id=cid.strip(), text=message, parse_mode="Markdown")
        except Exception as e:
            print(f"❌ 전송 실패 ({cid}):", e)

# ✅ 이미지 전송용 함수
async def send_photo(photo_buf, caption: str | None = None, target_chat_ids: list[str] | None = None):
    """
    이미지 전송용 (알림 제한 시간 적용)
    :param photo_buf: BytesIO 객체 (예: matplotlib로 생성)
    :param caption: 선택적으로 짧은 설명 첨부 가능 (1024자 제한)
    """
    if is_sleep_time():
        return

    recipients = target_chat_ids if target_chat_ids else CHAT_IDS

    # ✅ 버퍼 비어 있는 경우 체크
    size = photo_buf.getbuffer().nbytes
    if size == 0:
        print("❌ 전송 취소: 버퍼가 비어 있음")
        return

    # ✅ 항상 시작 위치로 이동
    photo_buf.seek(0)

    for cid in recipients:
        try:
            await bot.send_photo(
                chat_id=cid.strip(),
                photo=photo_buf,
                caption=caption if caption else None,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ 사진 전송 실패 ({cid}):", e)
