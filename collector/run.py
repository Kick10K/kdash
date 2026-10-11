"""수집 + 계산 실행기

  python collector/run.py                 # 오늘(최근 거래일) 수집 후 계산
  python collector/run.py --date 2026-10-08
  python collector/run.py --backfill 60   # 과거 60거래일 일괄 수집(최초 1회 권장)
  python collector/run.py --rebuild       # 저장된 원천 데이터로 모든 날짜 JSON 재계산
  python collector/run.py --sample        # 가상 데이터로 대시보드 시험
  python collector/run.py --debug-funds   # 증시자금 원본 응답 확인
  python collector/run.py --funds-only    # 증시자금만 다시 받고 재계산
"""
import argparse
import datetime as dt
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import config as C  # noqa: E402
from analyze import build_many, raw_dates, write_output  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))


def today_kst():
    return dt.datetime.now(KST).date()


def collect(date: str, force=False) -> bool:
    from fetch_krx import fetch_day
    from fetch_krx import RAW_VERSION
    p = C.RAW_DIR / f"{date}.json.gz"
    if p.exists() and not force:
        try:
            if json.loads(gzip.decompress(p.read_bytes())).get("v", 1) >= RAW_VERSION:
                return True
            print(f"[수집] {date} (형식 갱신으로 다시 받음)")
        except Exception:
            pass
    else:
        print(f"[수집] {date}")
    day = None
    for attempt in range(3):
        try:
            day = fetch_day(date)
            break
        except Exception as e:
            print(f"  오류 ({attempt + 1}/3): {e}")
            import time
            time.sleep(10)
    else:
        print("  건너뜀 - 나중에 같은 명령을 다시 실행하면 이어서 받습니다")
        return p.exists()
    if not day:
        print("  휴장일 또는 데이터 없음")
        return False
    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(day, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    print(f"  종목 {len(day['stocks'])} · 수급 {len(day['flows'])}")
    return True


def update_funds(end: str, days_back=400, debug=False):
    from fetch_krx import fetch_funds
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=days_back)).isoformat()
    try:
        new = fetch_funds(start, end, debug=debug)
    except Exception as e:
        print("[증시자금] 수집 실패:", e)
        return
    if new.empty:
        print("[증시자금] 응답 없음")
        return
    old = pd.read_csv(C.FUNDS_CSV, dtype={"date": str}).set_index("date") if C.FUNDS_CSV.exists() else None
    df = new if old is None else new.combine_first(old)
    df.sort_index().to_csv(C.FUNDS_CSV)
    print(f"[증시자금] {len(df)}일 저장 (최근 {df.index.max()})")


def business_days_back(end: dt.date, n: int):
    d, out = end, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--backfill", type=int, default=0)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--debug-funds", action="store_true")
    ap.add_argument("--force", action="store_true", help="이미 받은 날짜도 다시 수집")
    ap.add_argument("--funds-only", action="store_true", help="증시자금만 다시 받고 전체 재계산 (KRX 로그인 불필요)")
    ap.add_argument("--no-notify", action="store_true", help="텔레그램 알림 끄기")
    a = ap.parse_args()

    if a.debug_funds:
        update_funds(today_kst().isoformat(), 10, debug=True)
        return

    if a.sample:
        from sample_data import make_sample
        make_sample()
        dates = raw_dates()[-45:]
    elif a.rebuild or a.funds_only:
        if a.funds_only:
            update_funds(today_kst().isoformat())
        dates = raw_dates()
    else:
        end = dt.date.fromisoformat(a.date) if a.date else today_kst()
        if not a.date and dt.datetime.now(KST).hour < 18:
            end -= dt.timedelta(days=1)  # KRX 당일 확정 수급은 18시 이후
        # 기본: 최근 5영업일 중 빠진 날짜를 채움 (PC가 꺼져 있던 날도 자동 복구)
        targets = business_days_back(end, max(a.backfill, 5))
        got = [d for d in targets if collect(d, a.force)]
        update_funds(end.isoformat())
        dates = got

    stored = set(raw_dates())
    if len(dates) > 150 and not a.rebuild:
        print(f"[계산] 오래된 날짜는 건너뛰고 최근 150거래일만 화면용으로 계산합니다 (백테스트에는 전부 사용)")
        dates = sorted(dates)[-150:]
    todo = [d for d in sorted(dates) if d in stored]
    if todo:
        import time
        t0 = time.time()
        for d, data in build_many(todo):
            write_output(d, data)
            print(f"[계산] {d} 완료")
        print(f"[계산] {len(todo)}일 · {time.time() - t0:.0f}초")

    if not (a.sample or a.rebuild or a.funds_only or a.no_notify):
        try:
            from notify import notify_latest
            notify_latest()
        except Exception as e:
            print("[텔레그램] 오류:", e)


if __name__ == "__main__":
    import tee
    tee.start()
    main()
