import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(override=True)

# DB 연결 정보
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME")
DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 마스킹된 DB URL (로그 출력용)
DB_URL_MASKED = f"postgresql://{DB_USER}:*****@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 환율 API 키
ACCESS_KEY = os.environ.get("EXCHANGERATE_API_KEY")

# 텔레그램
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_IDS = os.environ.get("CHAT_IDS", "").split(",")

# 전략 설정
CHECK_INTERVAL = 200              # 3분 20초
MOVING_AVERAGE_PERIOD = 45        # 볼린저: 2.5시간
SHORT_TERM_PERIOD = 90            # 단기선: 5시간
LONG_TERM_PERIOD = 306            # 장기선: 17시간
JUMP_THRESHOLD = 1.0              # 급변 기준 (1원 이상)
SUMMARY_INTERVAL = 1800           # 30분

# === 이동평균선(크로스) 세부 설정 ===
EPSILON = 0.005                     # 단기/장기 평균선 동등 판단 오차 허용
SPREAD_DIFF_THRESHOLD = 0.12        # 유지 상태 추세 강화/약화 판단 기준
PRICE_GAP_THRESHOLD = 1.0           # 유지 상태 가격 변화 판단 기준
MIN_REPORT_INTERVAL = 900           # 유지 상태 의미 있는 변화 보고 최소 간격(15분)
REMINDER_INTERVAL = 1800            # 유지 상태 리마인드 주기(30분)

# 📊 전략별 점수 가중치
SIGNAL_WEIGHTS = {
    "📊 볼린저 밴드": 21,
    "⚡ 급변 감지": 14,
    "🔁 이동평균선 크로스": 36,
    "📡 예상 범위 이탈": 29
}

# 실행 환경 (로컬/프로덕션)
# 로컬 개발 환경에서는 .env 파일에서 ENVIRONMENT 변수를 설정할 수 있음
# 프로덕션 환경에서는 이 변수를 설정하지 않음
# 기본값은 "production"으로 설정
# ✅ .env 파일이 존재하면 로컬, 없으면 프로덕션
if os.path.exists(".env"):
    ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
else:
    ENVIRONMENT = "production"


# === Decision pipeline defaults ===
COOLDOWN_SECONDS = 600          # 같은 방향 재발송 최소 간격(초) ≈ 3틱
DEBOUNCE_REQUIRED = 2           # 서로 다른 방향 전환 시 연속 동일 판단 필요 틱 수
HYSTERESIS_P_DELTA = 0.05       # 반전/취소 시 추가 요구 확률
HYSTERESIS_AGREE_DELTA = 1      # 반전/취소 시 추가 요구 합의 개수
