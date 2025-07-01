import time
import requests

from config import ACCESS_KEY


def get_usdkrw_rate(retries=3, delay=2):
    """
    환율 API 호출: 실패 시 최대 `retries`만큼 재시도
    :param retries: 최대 재시도 횟수
    :param delay: 실패 후 대기 시간 (초)
    :return: 환율 (float) 또는 None
    """
    if not ACCESS_KEY:
        print("❌ ACCESS_KEY가 설정되지 않았습니다.")
        return None

    url = f"https://api.exchangerate.host/live?access_key={ACCESS_KEY}&currencies=KRW"

    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json()
            rate = data.get("quotes", {}).get("USDKRW")
            if rate is not None:
                return float(rate)
            else:
                print(f"⚠️ 응답에 USDKRW 정보 없음 (시도 {attempt})")
        except Exception as e:
            print(f"❌ API 호출 오류 (시도 {attempt}): {e}")

        if attempt < retries:
            print(f"⏳ {delay}초 후 재시도...")
            time.sleep(delay)

    print("🚫 모든 시도 실패 - 환율 조회 불가")
    return None


