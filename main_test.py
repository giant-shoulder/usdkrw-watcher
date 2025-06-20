import asyncio
from telegram import Bot

async def test_send():
    bot = Bot(token='8075724848:AAFx9PQtONyG_9ia_x9HvhHtLn3oHaKRsoI')
    await bot.send_message(chat_id='7650730456', text='✅ 환율 봇 연결 테스트입니다.')

asyncio.run(test_send())