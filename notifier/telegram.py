# Telegram messaging utility
import os
import pytz
from datetime import datetime
from telegram import Bot
from config import TELEGRAM_TOKEN, CHAT_IDS, CHECK_INTERVAL

bot = Bot(token=TELEGRAM_TOKEN)

async def send_start_message():
    msg = (
        "👋 *USD/KRW 환율 모니터링이 재시작되었습니다!*\n\n"
        "📡 *이 시스템은 다음과 같은 환율 변동 상황을 감지해 텔레그램으로 알려드립니다:*\n\n"
        "📊 *알림 발생 조건*\n"
        "• 📈 환율이 갑자기 *크게 오를 때*\n"
        "• 📉 환율이 *급격히 하락할 때*\n"
        "• 📊 환율이 *볼린저 밴드 상단/하단을 돌파*할 때\n"
        "• 🔁 *이동 평균선의 방향성이 바뀔 때* (골든/데드 크로스)\n"
        "• 🎯 *2개 이상의 조건이 동시에 발생할 때* → *복합 경고로 판단하고 신호 방향도 함께 분석합니다*\n\n"
        "📦 *전략 설명*\n"
        "• 📊 볼린저 밴드: 최근 2.5시간 기준, 환율이 평균보다 *너무 높거나 낮은 경우*\n"
        f"• ⚡ 급등락 감지: *직전( {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초 전)보다 1.0원 이상 오르거나 내릴 경우*\n"
        "• 🔁 이동 평균선 교차:\n"
        "   ├─ 🟢 *골든 크로스*: 5시간 단기 평균선이 17시간 장기 평균선을 *상향 돌파*할 때 → 상승 신호\n"
        "   └─ 🔴 *데드 크로스*: 5시간 단기 평균선이 17시간 장기 평균선을 *하향 돌파*할 때 → 하락 신호\n"
        "• 🧭 반복 돌파 감지: 상단/하단을 *여러 번 연속 돌파*할 경우 추가 알림\n"
        "• 🎯 복합 전략: *2가지 이상의 신호가 동시에 발생*하면 점수화해 방향까지 안내\n\n"
        f"⏱️ *환율은 {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초마다 자동 확인됩니다.*\n"
        "🌙 *알림은 주말 및 평일 새벽 2시~7시 사이에는 자동으로 일시 중단됩니다.*"
    )
    await send_telegram(msg)

async def send_telegram(message: str):
    """
    새벽 2~7시 사이에는 알림 전송 안 함.
    여러 수신자(chat_id)에 메시지를 전송함.
    """
    hour = datetime.now(pytz.timezone("Asia/Seoul")).hour
    if 2 <= hour < 7:
        return

    for cid in CHAT_IDS:
        try:
            await bot.send_message(chat_id=cid.strip(), text=message)
        except Exception as e:
            print(f"❌ 전송 실패 ({cid}):", e)