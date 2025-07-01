# 💱 USD/KRW 환율 실시간 모니터링 시스템

국내외 환율 변동에 실시간으로 대응할 수 있도록, USD/KRW 환율을 분석하여 **Telegram 알림**으로 전송하는 시스템입니다.  
볼린저 밴드, 급변 감지, 골든/데드 크로스 등의 전략을 활용하여 **복합 신호 기반 경고**를 제공합니다.

---

## 📦 기능 요약

| 전략 | 설명 |
|------|------|
| 📊 볼린저 밴드 | 일정 시간 이동 평균 ± 2표준편차 돌파 시 경고 |
| ⚡ 급변 감지 | 직전 관측값 대비 1.0원 이상 변동 시 알림 |
| 🔁 크로스 분석 | 단기(5h) vs 장기(17h) 이동평균선 교차점 감지 |
| 🧭 연속 돌파 감지 | 볼린저 밴드 상단/하단 반복 돌파 추적 |
| 🎯 복합 전략 분석 | 2개 이상 전략이 일치할 경우 점수화 및 방향 해석 |
| 📩 텔레그램 알림 | 전략 발생 시 실시간으로 텔레그램 전송 |

---

## 🛠 설치 및 실행 방법

### 1. 레포지토리 클론

```bash
git clone https://github.com/your-username/usdkrw-watcher.git
cd usdkrw-watcher
```

### 2. 가상환경 생성 및 패키지 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`.env` 파일을 생성하고 아래 항목을 채워주세요:

```
ACCESS_KEY=your_exchangerate_host_key
TELEGRAM_TOKEN=your_telegram_bot_token
CHAT_IDS=123456789,987654321
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_PORT=5432
DB_NAME=your_db_name
```

📌 `CHAT_IDS`는 콤마로 구분된 수신자 목록입니다.

### 4. 실행

```bash
python main.py
```

---

## 🗂 프로젝트 구조

```
usdkrw-watcher/
├── main.py                 # 진입점
├── config.py               # 설정 상수 및 환경변수
├── .env                    # 비공개 환경설정
├── fetcher/                # 환율 수집기
├── notifier/               # 텔레그램 알림 시스템
├── strategies/             # 각종 전략 분석
│   ├── utils/              # 전략 보조 유틸
├── utils/                  # 시간 등 범용 유틸
├── db/                     # DB 연결 및 쿼리
├── requirements.txt        # 패키지 목록
```

---

## 📌 향후 개선 예정

- 📊 전략별 backtest 및 리포트 기능  
- 📅 특정 시간대 전략 자동 무시 설정  
- 📉 RSI, MACD 등 기술지표 추가  
- 🧪 테스트 코드 및 CI 파이프라인 추가  

---

## 🧑‍💻 개발자

- 조형우 ([lmulm.tech](lmulm.tech@gmail.com))  
스타트업 대표, 그리고 환율 알리미의 집착자 📈
