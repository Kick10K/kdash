"""수급 전략 백테스트

  python collector/backtest.py            → docs/backtest.html 에서 결과 확인

질문 두 가지에 답합니다.
  1) 어떤 수급 신호가 나온 날 사는 게 좋은가  (신호별 성과 비교)
  2) 사고 나서 언제 파는 게 좋은가           (보유일수별 누적 초과수익 곡선, 매도 규칙 비교)

원칙
  · 신호는 장 마감 후(18시) 확정되므로 '다음 거래일'에 산다고 가정 (시가 데이터가 있으면 시가, 없으면 종가)
  · 매일 신호 점수 상위 10종목을 같은 비중으로 산다고 가정
  · 왕복 거래비용 0.25% (수수료 + 거래세) 차감
  · 벤치마크 = 같은 날 조건을 만족하는 전체 종목의 평균 수익률 → '초과수익'은 신호의 순수한 효과
  · 기간을 앞/뒤 절반으로 나눠 두 구간에서 모두 통하는지 확인 (한 구간에서만 통하면 우연일 가능성이 큼)
  · 상장폐지·급락 종목도 그날 데이터에 있던 그대로 포함 (살아남은 종목만 보는 착시 없음)
"""
from __future__ import annotations

import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

TOPK = 10
COST = 0.25          # 왕복 비용 %
MAX_H = 20           # 최대 보유 거래일
MIN_CAP = 500        # 시가총액 하한 (억원)
MIN_TV = 1000        # 거래대금 하한 (백만원 = 10억)
INV3 = ["사모", "연기금", "투신"]


# ------------------------------------------------------------------ 데이터
def load_panel():
    files = sorted(C.RAW_DIR.glob("????-??-??.json.gz"))
    days = [json.loads(gzip.decompress(p.read_bytes()).decode("utf-8")) for p in files]
    dates = [d["date"] for d in days]

    def frame(fn):
        return pd.DataFrame({d["date"]: fn(d) for d in days}).T.reindex(dates)

    close = frame(lambda d: {t: v["c"] for t, v in d["stocks"].items()})
    opn = frame(lambda d: {t: v.get("o") for t, v in d["stocks"].items()}).astype(float)
    cap = frame(lambda d: {t: v["cap"] for t, v in d["stocks"].items()})
    tv = frame(lambda d: {t: v.get("tv", 0) for t, v in d["stocks"].items()})
    names = {t: v["n"] for d in days for t, v in d["stocks"].items()}
    keys = sorted({k for d in days for f in d["flows"].values() for k in f})
    flows = {}
    for k in keys:
        f = frame(lambda d, k=k: {t: v.get(k, 0.0) for t, v in d["flows"].items()})
        flows[k] = f.reindex(columns=close.columns).fillna(0.0)
    # 일부 날짜에만 있는 키(외국인·개인 등)는, 없는 날을 NaN 으로 표시
    for k in keys:
        has = pd.Series([any(k in f for f in d["flows"].values()) for d in days], index=dates)
        flows[k].loc[~has.values] = np.nan
    cap = cap.ffill()
    excl = [t for t in close.columns if any(w in str(names.get(t, "")) for w in C.EXCLUDE_NAME_WORDS)]
    univ = (cap >= MIN_CAP) & (tv >= MIN_TV) & close.notna()
    univ[excl] = False
    strength = {k: (f / cap) for k, f in flows.items()}  # %
    return dict(dates=dates, close=close, open=opn, cap=cap, names=names, flows=flows, S=strength, univ=univ)


# ------------------------------------------------------------------ 신호
def top_by(score: pd.DataFrame, cond: pd.DataFrame, univ: pd.DataFrame, k=TOPK):
    """날짜별로 cond & univ 를 만족하는 종목 중 score 상위 k 개"""
    sc = score.where(cond & univ)
    picks = {}
    for d, row in sc.iterrows():
        row = row.dropna()
        row = row[row > 0]
        if len(row):
            picks[d] = list(row.sort_values(ascending=False).index[:k])
    return picks


def streak(df_pos: pd.DataFrame):
    out = np.zeros(df_pos.shape)
    arr = df_pos.values.astype(bool)
    for i in range(len(arr)):
        out[i] = np.where(arr[i], (out[i - 1] if i else 0) + 1, 0)
    return pd.DataFrame(out, index=df_pos.index, columns=df_pos.columns)


def build_signals(P):
    S, F, U = P["S"], P["flows"], P["univ"]
    sig = {}
    have = lambda k: k in S and S[k].notna().any().any()  # noqa: E731

    # 현재 대시보드 방식
    if all(have(k) for k in INV3):
        s3 = sum(S[k] for k in INV3)
        allpos = (F["사모"] > 0) & (F["연기금"] > 0) & (F["투신"] > 0)
        sig["3기관 합산강도 (모두 순매수)"] = top_by(s3, allpos, U)
        ranks = [S[k].where(U & (F[k] >= C.MIN_AMOUNT)).rank(axis=1, ascending=False) for k in INV3]
        inter = (ranks[0] <= 20) & (ranks[1] <= 20) & (ranks[2] <= 20)
        sig["3기관 동시 상위20 (현재 감지)"] = top_by(s3, inter, U)
        for k in INV3:
            sig[f"{k} 단독 강도"] = top_by(S[k], F[k] > 0, U)
    if have("기관"):
        sig["기관합계 강도"] = top_by(S["기관"], F["기관"] > 0, U)
        st = streak(F["기관"] > 0)
        sig["기관 3일+ 연속 순매수"] = top_by(S["기관"].rolling(5, min_periods=1).sum(), st >= 3, U)
    if have("외국인"):
        fo = S["외국인"]
        sig["외국인 강도"] = top_by(fo, F["외국인"] > 0, U)
        st = streak(F["외국인"] > 0)
        sig["외국인 3일+ 연속 순매수"] = top_by(fo.rolling(5, min_periods=1).sum(), st >= 3, U)
        if have("기관"):
            both = (F["외국인"] > 0) & (F["기관"] > 0)
            sig["외국인+기관 동반 순매수"] = top_by(fo + S["기관"], both, U)
            stb = streak(both)
            sig["외국인+기관 동반 3일+ 연속"] = top_by((fo + S["기관"]).rolling(5, min_periods=1).sum(), stb >= 3, U)
            sm = fo + S["기관"]
            sig["외국인+기관 5일 누적 강도"] = top_by(sm.rolling(5).sum(), sm.rolling(5).sum() > 0, U)
            c20 = sm.rolling(20).sum().shift(3)
            c3 = sm.rolling(3).sum()
            sig["수급 전환 (20일 매도 → 최근 3일 매수)"] = top_by(c3, (c20 < 0) & (c3 > 0), U)
    if have("개인"):
        sig["개인 순매도 강도 (역발상)"] = top_by(-S["개인"], F["개인"] < 0, U)
    # 비교용: 수급 없이 가격 모멘텀만
    r5 = P["close"].pct_change(5) * 100
    sig["[비교] 5일 상승률 상위 (수급 미사용)"] = top_by(r5, r5 > 0, U)
    return sig


# ------------------------------------------------------------------ 성과
def fwd_paths(P, use_open):
    """d 일 신호 → d+1 매수 → d+1+h 종가 매도, h=0..MAX_H 의 수익률(%)  (h=0 은 시가 매수 후 당일 종가)"""
    close = P["close"]
    entry = P["open"].shift(-1) if use_open else close.shift(-1)
    paths = {}
    for h in range(0, MAX_H + 1):
        exitp = close.shift(-(1 + h))
        paths[h] = (exitp / entry - 1) * 100
    return paths


def bench(paths, U):
    return {h: p.where(U).mean(axis=1) for h, p in paths.items()}


def evaluate(picks, paths, bm, dates, H=range(1, MAX_H + 1)):
    """날짜별로 그날 산 종목 평균 → 날짜 평균. 초과 = 종목 - 벤치마크"""
    curve, n = {}, 0
    half = dates[len(dates) // 2]
    per_h = {}
    for h in H:
        rows = []
        for d, tks in picks.items():
            v = paths[h].loc[d, tks].dropna()
            b = bm[h].get(d)
            if len(v) and b is not None and not np.isnan(b):
                rows.append((d, v.mean() - COST, v.mean() - COST - b, (v > COST).mean()))
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=["d", "ret", "ex", "win"]).set_index("d")
        # 보유기간이 겹치면 t값이 부풀려지므로 h일 간격으로 겹치지 않게 뽑아 계산
        nov = df["ex"].iloc[::max(h, 1)]
        t = nov.mean() / (nov.std(ddof=1) / math.sqrt(len(nov))) if len(nov) > 2 and nov.std() > 0 else 0
        per_h[h] = {"n_days": len(df), "ret": df["ret"].mean(), "ex": df["ex"].mean(), "win": df["win"].mean() * 100,
                    "t": t, "ex_h1": df.loc[df.index < half, "ex"].mean(), "ex_h2": df.loc[df.index >= half, "ex"].mean(),
                    "series": df}
        curve[h] = df["ex"].mean()
        n = max(n, len(df))
    return per_h, curve


def exit_rules(picks, P, use_open, flow_key):
    """보유일 고정 외의 매도 규칙 비교 (최대 20일)"""
    close, U = P["close"], P["univ"]
    entry_px = (P["open"] if use_open else close).shift(-1)
    dates = P["dates"]
    idx = {d: i for i, d in enumerate(dates)}
    F = P["flows"].get(flow_key)
    out = {"손절 -7% / 익절 +15%": [], "수급 이탈 (2일 연속 순매도) 시 매도": [], "20일선 이탈 시 매도": []}
    ma20 = close.rolling(20, min_periods=10).mean()
    for d, tks in picks.items():
        i = idx[d]
        if i + 2 >= len(dates):
            continue
        for tk in tks:
            e = entry_px.at[d, tk]
            if not e or np.isnan(e):
                continue
            last = min(i + 1 + MAX_H, len(dates) - 1)
            seg = close.iloc[i + 1: last + 1][tk]
            # 1) 손절/익절
            r = (seg / e - 1) * 100
            hit = r[(r <= -7) | (r >= 15)]
            out["손절 -7% / 익절 +15%"].append((r.loc[hit.index[0]] if len(hit) else r.iloc[-1], len(r.loc[:hit.index[0]]) if len(hit) else len(r)))
            # 2) 수급 이탈
            if F is not None:
                fseg = F.iloc[i + 1: last + 1][tk]
                neg = (fseg < 0).astype(int)
                two = (neg + neg.shift(1).fillna(0)) >= 2
                j = two[two].index
                ex_d = j[0] if len(j) else seg.index[-1]
                out["수급 이탈 (2일 연속 순매도) 시 매도"].append((r.loc[ex_d], len(r.loc[:ex_d])))
            # 3) 20일선 이탈
            below = seg < ma20.iloc[i + 1: last + 1][tk]
            j = below[below].index
            ex_d = j[0] if len(j) else seg.index[-1]
            out["20일선 이탈 시 매도"].append((r.loc[ex_d], len(r.loc[:ex_d])))
    res = {}
    for k, v in out.items():
        if v:
            a = np.array(v, dtype=float)
            res[k] = {"n": len(a), "ret": float(a[:, 0].mean() - COST), "win": float((a[:, 0] > COST).mean() * 100),
                      "hold": float(a[:, 1].mean())}
    return res


def weekday_effect(series: pd.DataFrame):
    if series is None or series.empty:
        return {}
    wd = pd.to_datetime(series.index).weekday
    names = "월화수목금"
    g = series.groupby(wd)["ex"].agg(["mean", "count"])
    # 신호일 다음날이 매수일 → 매수 요일 = 신호 요일 + 1 (대략)
    return {names[i]: {"ex": float(r["mean"]), "n": int(r["count"])} for i, r in g.iterrows() if i < 5}


def r2(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def main():
    P = load_panel()
    dates = P["dates"]
    use_open = P["open"].notna().mean(axis=1).gt(0.8).mean() > 0.8
    print(f"기간 {dates[0]} ~ {dates[-1]} ({len(dates)}거래일) · 매수가: {'다음날 시가' if use_open else '다음날 종가'}")
    print("수급 항목:", ", ".join(k for k in P["flows"] if P["flows"][k].notna().any().any()))
    paths = fwd_paths(P, use_open)
    bm = bench(paths, P["univ"])
    sig = build_signals(P)

    results = []
    for name, picks in sig.items():
        per_h, curve = evaluate(picks, paths, bm, dates)
        if not per_h:
            continue
        best_h = max(per_h, key=lambda h: per_h[h]["ex"])
        b = per_h[best_h]
        h5 = per_h.get(5, b)
        results.append({"name": name, "days": len(picks), "best_h": best_h,
                        "best": {k: r2(v) for k, v in b.items() if k != "series"},
                        "h5": {k: r2(v) for k, v in h5.items() if k != "series"},
                        "curve": [r2(curve.get(h)) for h in range(1, MAX_H + 1)],
                        "_series": b["series"], "_picks": picks})
        print(f"  {name:32s} 최적 {best_h:2d}일 초과 {b['ex']:+.2f}%  t={b['t']:.1f}  앞/뒤 {b['ex_h1']:+.2f}/{b['ex_h2']:+.2f}")

    # 신뢰도 등급: 표본·t값·앞뒤 구간 일관성
    for r in results:
        b = r["best"]
        consistent = (b["ex_h1"] or 0) > 0 and (b["ex_h2"] or 0) > 0
        if b["n_days"] >= 120 and (b["t"] or 0) >= 2.0 and consistent:
            r["grade"] = "유력"
        elif b["n_days"] >= 60 and (b["t"] or 0) >= 1.5 and consistent:
            r["grade"] = "가능성"
        elif (b["ex"] or 0) > 0:
            r["grade"] = "근거 부족"
        else:
            r["grade"] = "효과 없음"
    results.sort(key=lambda r: (-{"유력": 3, "가능성": 2, "근거 부족": 1, "효과 없음": 0}[r["grade"]], -(r["best"]["ex"] or 0)))

    # 상위 신호: 매수 시점 지연, 매도 규칙, 요일
    detail = []
    for r in results[:4]:
        key = "외국인" if "외국인" in r["name"] else ("기관" if "기관" in r["name"] else
                                                     next((k for k in INV3 if k in r["name"]), "기관"))
        delays = {}
        for lag in (0, 1, 2):
            shifted = {}
            for d, tks in r["_picks"].items():
                i = dates.index(d)
                if i + lag < len(dates):
                    shifted[dates[i + lag]] = tks
            per_h, _ = evaluate(shifted, paths, bm, dates, H=[r["best_h"]])
            if per_h:
                delays[["신호 다음날", "하루 늦게", "이틀 늦게"][lag]] = r2(per_h[r["best_h"]]["ex"])
        detail.append({"name": r["name"], "best_h": r["best_h"], "delays": delays,
                       "exits": {k: {kk: r2(vv) for kk, vv in v.items()} for k, v in exit_rules(r["_picks"], P, use_open, key).items()},
                       "fixed": {"ret": r["best"]["ret"], "win": r["best"]["win"], "hold": r["best_h"]},
                       "weekday": {k: {"ex": r2(v["ex"]), "n": v["n"]} for k, v in weekday_effect(r["_series"]).items()},
                       "recent": [{"d": d, "names": [P["names"].get(t, t) for t in tks[:5]]}
                                  for d, tks in sorted(r["_picks"].items())[-5:]]})
    for r in results:
        r.pop("_series"), r.pop("_picks")

    out = {"from": dates[0], "to": dates[-1], "n_days": len(dates), "entry": "다음날 시가" if use_open else "다음날 종가",
           "flows": [k for k in P["flows"] if P["flows"][k].notna().any().any()],
           "topk": TOPK, "cost": COST, "min_cap": MIN_CAP, "min_tv": MIN_TV, "results": results, "detail": detail,
           "generated": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M")}
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUT_DIR / "backtest.js").write_text("window.KD_BT=" + json.dumps(out, ensure_ascii=False) + ";", encoding="utf-8")
    print("저장:", C.OUT_DIR / "backtest.js", "→ docs/backtest.html 에서 확인")


if __name__ == "__main__":
    main()
