"""실제 데이터 수집 (KRX via pykrx, 금융투자협회 FreeSIS, 환율).

필요 환경변수: KRX_ID, KRX_PW  (data.krx.co.kr 무료 회원 계정)
  - pykrx 최신 버전은 KRX 로그인이 필요한 데이터에 이 두 값을 사용합니다.
"""
from __future__ import annotations

import datetime as dt
import json
import time

import pandas as pd
import requests

from config import INVESTORS, INST_TOTAL

MARKETS = (("KOSPI", "KS"), ("KOSDAQ", "KQ"))
RAW_VERSION = 1   # 이 숫자를 올리면 예전에 받은 날짜를 다시 받습니다
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}


def _ymd(d: str) -> str:
    return d.replace("-", "")


def _sleep():
    time.sleep(0.6)  # KRX 서버 차단 방지


def fetch_day(date: str) -> dict | None:
    """date='YYYY-MM-DD'. 휴장일이면 None."""
    from pykrx import stock

    d = _ymd(date)
    frames = []
    for mkt, tag in MARKETS:
        o = stock.get_market_ohlcv(d, market=mkt)
        _sleep()
        if o is None or o.empty:
            continue
        if "시가총액" not in o.columns:  # 구버전 pykrx 는 시총을 따로 받아야 함
            c = stock.get_market_cap(d, market=mkt)
            _sleep()
            o = o.join(c[["시가총액"]], how="left")
        if "등락률" not in o.columns:
            o["등락률"] = 0.0
        o["m"] = tag
        frames.append(o)
    if not frames:
        return None
    px = pd.concat(frames)
    if px["거래대금"].sum() == 0:
        return None  # 휴장일

    px = px[~px.index.duplicated()]
    names = {}
    for t in px.index:
        try:
            names[t] = stock.get_market_ticker_name(t)
        except Exception:
            names[t] = t
    stocks = {}
    for t, r in px.iterrows():
        if not r["시가총액"] or pd.isna(r["시가총액"]) or r["종가"] <= 0:
            continue
        stocks[t] = {
            "n": names[t] if isinstance(names[t], str) else t,
            "m": r["m"],
            "c": float(r["종가"]),
            "o": float(r["시가"]) if "시가" in r and r["시가"] else None,
            "r": round(float(r["등락률"]), 2),
            "cap": round(float(r["시가총액"]) / 1e8, 1),   # 억원
            "tv": round(float(r["거래대금"]) / 1e6, 1),     # 백만원
        }

    flows: dict[str, dict] = {}
    for inv in INVESTORS + [INST_TOTAL]:
        key = "기관" if inv == INST_TOTAL else inv
        for mkt, _ in MARKETS:
            df = stock.get_market_net_purchases_of_equities(d, d, mkt, inv)
            _sleep()
            if df is None or df.empty:
                print(f"  [수급] {inv}/{mkt} 응답 없음")
                continue
            col = "순매수거래대금" if "순매수거래대금" in df.columns else \
                next((c for c in df.columns if "순매수" in c and "대금" in c), None)
            if col is None:
                print(f"  [수급] {inv}/{mkt} 열 이름을 찾지 못함: {list(df.columns)}")
                continue
            for t, r in df.iterrows():
                v = round(float(r[col]) / 1e6, 1)  # 백만원
                if v:
                    flows.setdefault(t, {})[key] = v

    index = {}
    start = (dt.date.fromisoformat(date) - dt.timedelta(days=14)).strftime("%Y%m%d")
    for code, name in (("1001", "KOSPI"), ("2001", "KOSDAQ")):
        ix = stock.get_index_ohlcv(start, d, code)
        _sleep()
        ix = ix[ix.index <= pd.Timestamp(date)]
        if ix.empty:
            continue
        last = ix.iloc[-1]
        prev = ix.iloc[-2]["종가"] if len(ix) > 1 else last["종가"]
        index[name] = {
            "c": round(float(last["종가"]), 2),
            "r": round((float(last["종가"]) / float(prev) - 1) * 100, 2),
        }
    for tag, name in (("KS", "KOSPI"), ("KQ", "KOSDAQ")):
        if name in index:
            index[name]["tv"] = round(float(px.loc[px["m"] == tag, "거래대금"].sum()) / 1e8, 0)  # 억원

    return {"v": RAW_VERSION, "date": date, "stocks": stocks, "flows": flows, "index": index, "fx": fetch_fx(date)}


def fetch_fx(date: str):
    """원/달러 종가. FinanceDataReader 가 없으면 None."""
    try:
        import FinanceDataReader as fdr
        start = (dt.date.fromisoformat(date) - dt.timedelta(days=10)).isoformat()
        df = fdr.DataReader("USD/KRW", start, date)
        if df.empty:
            return None
        return {"c": round(float(df["Close"].iloc[-1]), 2),
                "d": df.index[-1].strftime("%Y-%m-%d"),
                "r": round((df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100, 2) if len(df) > 1 else 0}
    except Exception as e:  # noqa
        print("  [환율] 수집 실패:", e)
        return None


# ---------------- 금융투자협회 FreeSIS 증시자금 ----------------
# 응답 필드명(tmpV*)은 사이트 개편 시 바뀔 수 있어 여기서만 관리합니다.
# 수집이 틀어지면  python collector/run.py --debug-funds  로 원본 응답을 확인 후 이 매핑을 고치세요.
FREESIS_URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
FUNDS_OBJ = {
    # 증시자금추이: 날짜, 투자자예탁금, 장내파생예수금, RP, 위탁매매미수금, 반대매매금액, 미수금대비반대매매비중
    "STATSCU0100000060BO": {"tmpV1": "date", "tmpV2": "deposit", "tmpV5": "misu",
                            "tmpV6": "bandae", "tmpV7": "bandae_ratio"},
    # 신용공여 잔고추이: 날짜, 신용공여합계, 신용거래융자 전체/유가/코스닥 ...
    "STATSCU0100000070BO": {"tmpV1": "date", "tmpV2": "credit_total",
                            "tmpV3": "credit_kospi", "tmpV4": "credit_kosdaq"},
}


def _freesis(obj: str, start: str, end: str, debug=False) -> list[dict]:
    body = {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D",
                         "tmpV45": _ymd(start), "tmpV46": _ymd(end), "OBJ_NM": obj}}
    r = requests.post(FREESIS_URL, json=body, headers={**UA, "Content-Type": "application/json"}, timeout=20)
    r.raise_for_status()
    js = r.json()
    rows = js.get("ds1") or js.get("DS1") or []
    # 원본을 남겨 형식이 바뀌었을 때 바로 확인
    from config import ROOT
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / f"funds_raw_{obj}.json").write_text(
        json.dumps({"keys": list(js.keys()), "rows": rows[:5]}, ensure_ascii=False, indent=1), encoding="utf-8")
    if debug:
        print(obj, json.dumps(rows[:3], ensure_ascii=False, indent=1))
    return [{str(k).lower(): v for k, v in row.items()} for row in rows]


def _to_date(v):
    s = "".join(ch for ch in str(v) if ch.isdigit())[:8]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else None


def fetch_funds(start: str, end: str, debug=False) -> pd.DataFrame:
    """단위: 백만원 (비중은 %). index=date(YYYY-MM-DD)"""
    out = None
    for obj, mp in FUNDS_OBJ.items():
        rows = _freesis(obj, start, end, debug)
        df = pd.DataFrame(rows)
        if df.empty:
            print(f"[증시자금] {obj} 응답 행 없음")
            continue
        mp = {k.lower(): v for k, v in mp.items()}
        if "tmpv1" not in df.columns:
            print(f"[증시자금] {obj} 날짜 항목을 찾지 못함. 받은 항목: {list(df.columns)[:12]}")
            continue
        df = df[[k for k in mp if k in df.columns]].rename(columns=mp)
        df["date"] = df["date"].map(_to_date)
        df = df.dropna(subset=["date"])
        for c in df.columns:
            if c != "date":
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
        df = df.groupby("date").last()
        out = df if out is None else out.join(df, how="outer")
    if out is None:
        return pd.DataFrame()
    # 단위 보정: 예탁금이 '억원'으로 오면(약 100만 단위) 백만원으로 환산
    if "deposit" in out and out["deposit"].dropna().size and out["deposit"].dropna().median() < 5e6:
        print("[증시자금] 억원 단위로 판단 → 백만원으로 환산")
        for c in ("deposit", "credit_total", "credit_kospi", "credit_kosdaq", "misu", "bandae"):
            if c in out:
                out[c] = out[c] * 100
    return out
