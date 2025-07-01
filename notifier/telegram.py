# Telegram messaging utility
import os
import pytz
from datetime import datetime
from telegram import Bot
from config import TELEGRAM_TOKEN, CHAT_IDS, CHECK_INTERVAL

bot = Bot(token=TELEGRAM_TOKEN)

async def send_start_message():
    msg = (
        "👋 USD/KRW 환율 모니터링을 재시작합니다!\n\n"
        "📊 [알림 기준 안내]\n"
        "• 📉 *환율이 평소보다 많이 떨어지거나*\n"
        "• 📈 *갑자기 크게 오르거나*\n"
        "• 🔁 *최근 평균선이 장기 평균선을 뚫고 올라가거나 내려갈 때*\n"
        "➡️ 이런 변화가 생기면 텔레그램으로 바로 알려드려요!\n\n"
        "📦 전략 설명:\n"
        "• 볼린저 밴드: 최근 2.5시간 기준, 평소보다 너무 낮거나 높을 때\n"
        "• 급격한 변동: 바로 직전보다 1원 이상 오르거나 내릴 때\n"
        "• 골든/데드크로스: 단기 평균(5시간)이 장기 평균(17시간)보다 크거나 작아질 때\n"
        "• 조합 전략: 위 조건 중 2가지 이상이 동시에 나타나면 추가 알림 발송\n\n"
        f"⏱️ 확인 주기: {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초마다 체크합니다\n"
        "🌙 *단, 주말 전체와 평일 오전 2시부터 7시까지는 알림이 일시 중단됩니다.*"
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