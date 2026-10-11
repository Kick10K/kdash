"""공통 설정. 숫자 기준을 바꾸고 싶으면 이 파일만 수정하면 됩니다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"            # 날짜별 원천 데이터 (YYYY-MM-DD.json)
FUNDS_CSV = ROOT / "data" / "raw" / "funds.csv"   # 증시자금 시계열
MANUAL_FUNDS_CSV = ROOT / "data" / "manual" / "funds_manual.csv"  # 수동 입력(선택)
OUT_DIR = ROOT / "docs" / "data"           # 대시보드가 읽는 결과물

SECTOR_RULES = ROOT / "sectors" / "sector_rules.csv"     # 대시보드 섹터명 ↔ 네이버 테마 키워드
SECTORS_AUTO = ROOT / "sectors" / "sectors_auto.csv"     # 자동 수집된 종목-섹터 매핑
SECTORS_MANUAL = ROOT / "sectors" / "sectors_manual.csv" # 직접 지정(우선 적용)

INVESTORS = ["사모", "연기금", "투신"]   # 대시보드 3기관
INST_TOTAL = "기관합계"

# ---- 수급 ----
EXCLUDE_NAME_WORDS = ["스팩"]   # 이름에 이 단어가 있으면 순위에서 제외
TOP_N = 40                 # 화면에 보여줄 기관별 상위 N
DETECT_TOP_N = 20          # 동시수급·매집 감지·섹터 출현에 쓰는 상위 N (원래 툴 기준)
STREAK_TOP_N = 30          # 연속 순매수 표 개수
MIN_AMOUNT = 30            # 상위 목록에 넣을 최소 순매수(백만원) - 초소형 노이즈 제거
STREAK_EARLY = (3, 4)      # 기관합계 연속 순매수 '초입' 일수 구간
STREAK_CONFIRM = 5         # '지속 확인' 최소 일수

# ---- 매집 추적 ----
DETECT_SUM_STRENGTH = 0.5  # 3기관 모두 순매수 + 합산강도(%) 이상이면 감지
TRACK_EXPIRE_DAYS = 30     # 마지막 감지 후 이 거래일 동안 재감지 없으면 추적 종료
TRACK_STOP_LOSS = -15.0    # 첫 감지가 대비 이 % 이하로 빠지면 추적 종료(이탈)
NEW_DAYS = 5               # 첫 감지 후 이 거래일 이내는 '신규'
CONFIRM_GAIN = 15.0        # 첫 감지가 대비 +15% 이상 & 이후 수급 유지 → '상승확인'
WARN_LOSS = -8.0           # 첫 감지가 대비 -8% 이하 → '이탈주의'

# ---- 섹터 ----
SECTOR_MAX_MEMBERS = 12    # 섹터별 대표주(시총 상위) 개수
LEAD_EXCESS = 1.0          # 시장 대비 초과수익 +1%p 이상 → 주도, -1%p 이하 → 약세
BUBBLE_WINDOWS = [10, 20, 40]

# ---- 감지 성과 검증 ----
BT_HORIZONS = [5, 10, 20]  # 감지일 종가 매수 후 N거래일 뒤 수익률

# ---- 분석 이력 ----
ANALYSIS_LOOKBACK = 140     # 추적/섹터 계산에 쓰는 과거 거래일 수
FUNDS_CHART_DAYS = 260     # 증시자금 차트 기간(거래일)
MARKET_CHART_DAYS = 120    # 거래대금 차트 기간(거래일)
