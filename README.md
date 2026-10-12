# 기관 수급 레이더

사모·연기금·투신 수급, 3기관 동시수급, 매집 추적, 섹터 패턴, 증시자금을 날짜별로 보는 대시보드입니다.
PC와 모바일에서 볼 수 있고, 상단에서 날짜를 고르면 모든 화면이 그 날짜 기준으로 바뀝니다.

```
collector/      수집·계산 (Python)
  run.py          실행기
  fetch_krx.py    KRX(pykrx) · 금융투자협회 · 환율 수집
  analyze.py      강도·동시수급·연속수급·매집추적·섹터진단 계산
  build_sectors.py 네이버 테마 → 종목-섹터 자동 매핑
  config.py       모든 기준값 (여기서 숫자 조정)
sectors/        섹터 매핑 (sector_rules.csv, sectors_auto.csv, sectors_manual.csv)
data/raw/       날짜별 원천 데이터 (자동 누적)
docs/           대시보드 (index.html + data/*.js)
```

## 1. 처음 한 번 설정

### Mac에서 실행

계정과 옵션은 `settings.sh`에 저장합니다. 아래 실행 파일들은 이 설정을 자동으로 읽으므로
수집 전에 직접 `source settings.sh`를 실행할 필요는 없습니다.

```zsh
cd /Users/kyungjunkim/Documents/kdash_share
bash setup_mac.sh                  # 처음 한 번: Python 패키지 설치
bash run_daily.sh                  # 설정 읽기 + 최근 누락 데이터 수집 + 계산
bash open_dashboard.sh             # 브라우저에서 대시보드 열기
```

`setup_mac.command`, `run_daily.command`, `open_dashboard.command`를 Finder에서 더블클릭해도 됩니다.
각 `.command`는 같은 이름의 `.sh`를 실행합니다. Python 3.10 이상이 필요하며,
설치된 Python 3.11 등을 찾아 폴더 안 `.venv`에 필요한 패키지를 설치합니다.

계정·텔레그램·업로드 옵션은 **`settings.sh`**에서 수정하세요. 비밀번호 등의 값은 작은따옴표로
감싸세요. 새 복사본에 개인 설정 파일이 없으면 `setup_mac.sh`가 `settings.example.sh`를 복사하므로
계정을 다시 입력해야 합니다. `settings.sh`와 `.venv`는 Git 업로드 대상에서 제외됩니다.

추가 명령:

```zsh
bash run_daily.sh --backfill 70     # 과거 70영업일 수집
bash run_daily.sh --rebuild         # 저장된 원천 데이터로 다시 계산
bash run_daily.sh --sample --no-notify  # 가상 데이터로 화면 시험
.venv/bin/python collector/build_sectors.py  # 섹터 매핑 생성
bash publish_setup.sh              # GitHub 저장소 연결 + 첫 업로드
bash register_task.sh              # 평일 18:40 자동 실행 등록
bash unregister_task.sh            # 자동 실행 등록 해제
```

`publish_setup.command`, `register_task.command`, `unregister_task.command`도 더블클릭할 수 있습니다.
GitHub Pages 설정은 아래 모바일 안내와 같고, Mac의 자동 업로드 설정은 `settings.sh`의
`export PUBLISH=1`입니다. `run_daily.sh`는 수집 프로그램이 오류로 종료되면 업로드를 진행하지 않습니다.
도움말(`--help`), 가상 데이터 시험(`--sample`), 증시자금 응답 확인(`--debug-funds`)도 업로드하지 않습니다.

Mac 자동 실행은 `launchd`를 사용하며 **Mac 시스템 시간대 기준 평일 18:40**에 실행됩니다.
한국 시간 18:40에 실행하려면 Mac의 시간대를 서울로 설정하세요. 등록 직후에는 수집을 시작하지 않습니다.
잠자기 중 지나간 예약은 깨어난 뒤 처리하지만, 전원이 꺼져 있거나 로그아웃한 동안은 실행되지 않습니다.
다음 수집 시 최근 5영업일 중 빠진 날짜를 채웁니다.
자동 실행 기록은 `data/launchd.log`, 오류는 `data/launchd_error.log`에서 확인합니다.
예약은 `~/Library/LaunchAgents/com.kdash.daily.plist`에 저장됩니다.
문서 폴더 접근 거부가 실제로 발생하면 Mac의 개인정보 보호 설정에서 실행 주체의 접근 권한을 확인하세요.
예약 동작 참고: [Apple의 launchd 예약 작업 안내](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html).

### 처음 데이터 준비

1. `bash setup_mac.sh`로 필요한 패키지를 설치합니다.
2. **KRX 계정 만들기**: data.krx.co.kr 무료 회원가입. pykrx 최신 버전은 KRX 로그인이 필요한 데이터에 `KRX_ID`, `KRX_PW` 환경변수를 씁니다.
3. 섹터 매핑 만들기: `.venv/bin/python collector/build_sectors.py`
   (네이버 증권 테마를 읽어 `sectors/sectors_auto.csv` 생성. 월 1회 정도 다시 실행)
4. 과거 데이터 채우기 (추적·섹터 계산에 최소 40거래일 필요):
   ```
   bash run_daily.sh --backfill 70
   ```
   종목 수가 많아 하루치에 1~2분 걸립니다.
5. `docs/index.html`을 더블클릭하면 열립니다. 데이터가 없으면 샘플 화면이 나옵니다.

## 2. 매일 자동 수집 · 모바일

**설정 파일**: `settings.sh`에 KRX 계정, 텔레그램, 업로드 여부를 적습니다. (GitHub에 올라가지 않음)

**자동 실행 등록**: `register_task.command`를 한 번 더블클릭 → Mac 시스템 시간대 기준
평일 18:40에 `run_daily.sh`가 실행됩니다. 잠자기 중 놓친 실행은 깨어난 뒤 처리합니다.
전원이 꺼져 있거나 로그아웃한 동안은 실행되지 않으며, 다음 수집 때 최근 5영업일 중 빠진 날짜를 채웁니다.
(KRX 당일 확정 투자자별 수급은 18시 이후에 나옵니다.)

**모바일 (GitHub Pages)**
1. Git 설치 (git-scm.com), GitHub 가입, 새 저장소 만들기 (Public, 빈 저장소)
2. `publish_setup.command` 실행 → 저장소 주소 붙여넣기 → GitHub 인증이 필요하면 안내에 따라 로그인
3. GitHub 저장소 Settings → Pages → Branch `main`, 폴더 `/docs` → Save
4. `settings.sh`에서 `export PUBLISH=1`로 바꾸고 저장
5. 휴대폰에서 `https://<아이디>.github.io/<저장소이름>/` 접속 (홈 화면에 추가 권장)

Public 저장소라 주소를 아는 사람은 볼 수 있습니다. 올라가는 것은 공개 시장 데이터와 계산 결과이며,
계정·토큰이 든 `settings.sh`는 올라가지 않습니다.

**업로드 후 웹 화면 갱신**: GitHub Pages 배포가 끝나면 화면 상단의 `최신 데이터`를 누르세요.
페이지와 날짜별 데이터를 다시 읽어 최신 거래일을 표시합니다. 최신 날짜를 볼 때는 주소에 날짜를
고정하지 않으므로 이후 새로고침에도 최신 날짜가 선택됩니다. 과거 날짜를 직접 선택하면
주소의 `#dYYYYMMDD`가 해당 날짜를 유지합니다.

## 3. 계산 기준 (config.py 에서 변경)

| 항목 | 기준 |
|---|---|
| 매수강도 | 순매수 ÷ 시가총액 × 100 |
| 3기관 합산강도 | 사모 + 연기금 + 투신 강도 |
| 3기관 동시수급 | 세 기관 순매수 상위20(강도순)에 모두 포함 |
| 연속수급 | 기관합계 순매수 3–4일 = 초입, 5일 이상 = 지속 확인 |
| 매집 감지 | 동시수급 또는 세 기관 모두 순매수 & 합산강도 0.6% 이상 |
| 추적 종료 | 마지막 감지 후 30거래일 무감지, 또는 첫 감지가 대비 -15% |
| 추적 상태 | 신규 / 상승확인 / 이탈주의 / 매집진행 / 재점화 후보 / 추적연장 |
| 섹터 | 시총 상위 12종목 동일가중 지수, 시장(코스피/코스닥) 대비 초과수익 |
| 상승확산 | 섹터 종목 중 20일 이동평균 위에 있는 비율 |
| 패턴진단 | 1개월·1주·3일 수익률 + 확산 + 20일선 위치로 강한지속/상승피로/건강한 눌림/하락전환 위험 등 |
| 시장 위험도 | 반대매매 비중·급증, 미수금·신용 급증, 예탁금 이탈을 점수화 |

섹터 패턴은 상대강도(RS)·시장폭(breadth)·20일선 추세를 함께 보는 주도주/섹터 로테이션 방식을,
매집 추적은 기관 동시 순매수 감지 → 반복 재감지 → 사후 가격·수급 검증 흐름을 따랐습니다.

## 4. 섹터 직접 지정

대시보드의 섹터 드롭다운에서 바꾸면 브라우저에 저장되고, 추적 섹션 아래 "직접 지정 섹터 내보내기"에서
CSV 내용을 복사해 `sectors/sectors_manual.csv`에 붙이면 다음 계산부터 반영됩니다.
`sectors/sector_rules.csv`에서 대시보드 섹터명과 네이버 테마 키워드의 연결을 편집할 수 있습니다.

## 5. 증시자금이 안 나올 때

금융투자협회(FreeSIS) 응답 형식은 바뀔 수 있습니다. `python collector/run.py --debug-funds` 로 원본을 보고
`fetch_krx.py`의 `FUNDS_OBJ` 필드 매핑을 고치세요. 급할 때는 `data/manual/funds_manual.csv`
(date,deposit,credit_total,credit_kospi,credit_kosdaq,misu,bandae,bandae_ratio · 단위 백만원)에 직접 넣어도 됩니다.

## 6. 자주 쓰는 명령

```
python collector/run.py                 오늘(18시 전이면 전 거래일) 수집 + 계산
python collector/run.py --date 2026-10-08
python collector/run.py --rebuild       기준을 바꾼 뒤 전체 날짜 다시 계산
python collector/run.py --sample        가상 데이터로 화면 시험 (docs/sample)
```

투자 판단의 참고용이며, 수치는 각 데이터 제공처 기준으로 실제와 차이가 있을 수 있습니다.
