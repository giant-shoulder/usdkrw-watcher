# watcher_launcher.py
import asyncio
import traceback
from datetime import datetime

from db.connection import close_db_pool, init_db_pool
from notifier import send_telegram
from run_watcher import run_watcher

PROJECT_NAME = "🧠 USDKRW-WATCHER"
MAX_RETRIES = 100
RETRY_DELAY = 30


async def main():
    retries = 0

    while retries < MAX_RETRIES:
        db_pool = None  # ✅ 반드시 루프 시작 시 초기화
        try:
            print(f"\n🚀 [WATCHER START] {PROJECT_NAME} 실행 (시도 {retries + 1})\n")
            await send_telegram(f"{PROJECT_NAME} 시작됨 (Attempt {retries + 1})", target_chat_ids=["7650730456"])

            db_pool = await init_db_pool()
            await run_watcher(db_pool)

        except Exception as e:
            err_text = (
                f"🔥 *{PROJECT_NAME} - 예외 발생 감지 (watcher)*\n"
                f"> 예외 종류: `{type(e).__name__}`\n"
                f"> 메시지: `{str(e)}`\n"
                f"> 발생 시각: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"> 스택트레이스:\n```{traceback.format_exc()[-500:]}```"
            )
            print(err_text)
            await send_telegram(err_text, target_chat_ids=["7650730456"])

            print("⏱ 재시작까지 대기 중...")
            await asyncio.sleep(RETRY_DELAY)
            retries += 1

        else:
            print("✅ 루프 정상 종료됨")
            break

        finally:
            if db_pool:
                await close_db_pool(db_pool)

    print("🔚 watcher_launcher 종료")



if __name__ == "__main__":
    asyncio.run(main())
