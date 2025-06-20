import asyncio
from playwright.async_api import async_playwright

async def debug_save_html():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 접속
        url = "https://www.investing.com/currencies/usd-krw"
        print(f"🌐 페이지 접속 중: {url}")
        await page.goto(url, timeout=30000)

        # 충분한 렌더링 대기
        await page.wait_for_timeout(5000)  # 5초 대기

        # HTML 저장
        content = await page.content()
        file_path = "investing_debug.html"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ HTML 저장 완료 → {file_path}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_save_html())