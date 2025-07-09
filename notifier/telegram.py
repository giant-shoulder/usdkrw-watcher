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
        "• 📡 *시장 예상 환율 범위를 벗어날 때* (예: 상단 돌파 또는 하단 이탈)\n"
        "• 🎯 *2가지 이상 신호가 동시에 발생*할 때 → *복합 경고와 방향성 안내*\n\n"
        "📦 *전략 해설*\n"
        "• 📊 *볼린저 밴드*: 최근 2.5시간 기준, 환율이 평균보다 *크게 벗어난 경우*\n"
        f"• ⚡ *급등락 감지*: *직전({CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초 전)*보다 *±1.0원 이상 변동* 시\n"
        "• 🔁 *이동 평균선 교차*:\n"
        "   ├─ 🟢 *골든 크로스*: 단기선이 장기선을 *상향 돌파* → 상승 전환 신호\n"
        "   └─ 🔴 *데드 크로스*: 단기선이 장기선을 *하향 돌파* → 하락 전환 신호\n"
        "• 📡 *예상 환율 범위 감지*: 연합인포맥스 등에서 제시한 *당일 고/저 예상 범위*를 초과하면 알림\n"
        "• 🧭 *반복 돌파 감지*: *상단/하단을 여러 번 연속 돌파* 시 과열 또는 과매도 경고\n"
        "• 🎯 *복합 전략 분석*: *2가지 이상 신호가 겹치면 점수를 계산하고 방향까지 안내*\n\n"
        f"⏱️ *환율은 {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초마다 자동 분석됩니다.*\n"
        "🌙 *주말과 평일 새벽 0시~7시에는 알림이 자동으로 중단됩니다.*"
    )
    await send_telegram(msg)

async def send_telegram(message: str):
    """
    새벽 0~7시 사이에는 알림 전송 안 함.
    여러 수신자(chat_id)에 메시지를 전송함.
    """
    if is_sleep_time():
        return

    for cid in CHAT_IDS:
        try:
            await bot.send_message(chat_id=cid.strip(), text=message)
        except Exception as e:
            print(f"❌ 전송 실패 ({cid}):", e)