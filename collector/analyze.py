"""원천 데이터(data/raw) → 날짜별 대시보드 JSON(docs/data) 계산.

매수강도(%) = 순매수(백만원) / 시가총액(억원)   (= 순매수 / 시가총액 × 100)
3기관 합산강도 = 사모 + 연기금 + 투신 매수강도
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict

import numpy as np
import pandas as pd

import config as C

INV = C.INVESTORS
INV_KEYS = INV + ["기관"]


# ------------------------------------------------------------------ 로딩
def raw_dates() -> list[str]:
    return sorted(p.name[:10] for p in C.RAW_DIR.glob("????-??-??.json.gz"))


def load_days(upto: str, n: int) -> list[dict]:
    ds = [d for d in raw_dates() if d <= upto][-n:]
    return [json.loads(gzip.decompress((C.RAW_DIR / f"{d}.json.gz").read_bytes()).decode("utf-8")) for d in ds]


class Panel:
    """여러 날짜를 종목×날짜 표로 정리"""

    def __init__(self, days: list[dict]):
        self.dates = [d["date"] for d in days]
        self.close = pd.DataFrame({d["date"]: {t: v["c"] for t, v in d["stocks"].items()} for d in days}).T
        self.ret = pd.DataFrame({d["date"]: {t: v["r"] for t, v in d["stocks"].items()} for d in days}).T
        self.cap = pd.DataFrame({d["date"]: {t: v["cap"] for t, v in d["stocks"].items()} for d in days}).T
        self.close = self.close.reindex(self.dates)
        self.ret = self.ret.reindex(self.dates).fillna(0).clip(-30, 30)
        self.cap = self.cap.reindex(self.dates).ffill()
        last = days[-1]["stocks"]
        self.name = {t: v["n"] for d in days for t, v in d["stocks"].items()}
        self.market = {t: v["m"] for d in days for t, v in d["stocks"].items()}
        self.cap_last = pd.Series({t: v["cap"] for t, v in last.items()})
        self.flow = {}
        for k in INV_KEYS:
            f = pd.DataFrame({d["date"]: {t: v.get(k, 0.0) for t, v in d["flows"].items()} for d in days}).T
            self.flow[k] = f.reindex(index=self.dates, columns=self.close.columns).fillna(0.0)
        # 스팩(SPAC)은 순위·추적에서 제외 (시총이 작아 강도가 왜곡됨)
        excl = [t for t in self.close.columns if any(w in str(self.name.get(t, "")) for w in C.EXCLUDE_NAME_WORDS)]
        for k in INV_KEYS:
            self.flow[k][excl] = 0.0
        self.strength = {k: (self.flow[k] / self.cap).replace([np.inf, -np.inf], np.nan).fillna(0.0) for k in INV_KEYS}
        self.sum3_flow = sum(self.flow[k] for k in INV)
        self.sum3_str = sum(self.strength[k] for k in INV)
        self.index = {m: pd.Series({d["date"]: d["index"].get(m, {}).get("c") for d in days}, dtype=float)
                      for m in ("KOSPI", "KOSDAQ")}
        self.index_tv = {m: pd.Series({d["date"]: d["index"].get(m, {}).get("tv") for d in days}, dtype=float)
                         for m in ("KOSPI", "KOSDAQ")}
        self.fx = {d["date"]: d.get("fx") for d in days}


def r2(x, n=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


# ------------------------------------------------------------------ 섹터 매핑
def load_sector_map(names: dict) -> tuple[dict, dict, dict]:
    """returns (primary: ticker->sector, members: sector->[tickers], tag: ticker->tag)"""
    members = defaultdict(set)
    primary, tag = {}, {}
    if C.SECTORS_AUTO.exists():
        with open(C.SECTORS_AUTO, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                t = r["ticker"].zfill(6)
                members[r["sector"]].add(t)
                primary.setdefault(t, r["sector"])
    if C.SECTORS_MANUAL.exists():
        with open(C.SECTORS_MANUAL, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                t = r["ticker"].strip().zfill(6)
                s = r["sector"].strip()
                for mem in members.values():
                    mem.discard(t)
                members[s].add(t)
                primary[t] = s
                tag[t] = (r.get("tag") or "직접").strip()
    return primary, {s: sorted(v) for s, v in members.items()}, tag


# ------------------------------------------------------------------ 수급 상위
def top_lists(P: Panel, t: str):
    res = {"buy": {}, "sell": {}}
    sets = {}
    for k in INV:
        f, s = P.flow[k].loc[t], P.strength[k].loc[t]
        b = s[(f >= C.MIN_AMOUNT)].sort_values(ascending=False).head(C.TOP_N)
        sl = (-s[(f <= -C.MIN_AMOUNT)]).sort_values(ascending=False).head(C.TOP_N)
        sets[k] = list(b.index[: C.DETECT_TOP_N])
        res["buy"][k] = [(tk, f[tk], s[tk]) for tk in b.index]
        res["sell"][k] = [(tk, -f[tk], -s[tk]) for tk in sl.index]
    return res, sets


def stock_row(P, t, tk, amt, st):
    return {"t": tk, "n": P.name.get(tk, tk), "amt": r2(amt, 0), "cap": r2(P.cap_last.get(tk), 0),
            "s": r2(st), "m": P.market.get(tk)}


# ------------------------------------------------------------------ 매집 추적
def detections(P: Panel, d: str, top_sets_cache: dict) -> set:
    if d not in top_sets_cache:
        top_sets_cache[d] = top_lists(P, d)[1]
    sets = top_sets_cache[d]
    inter = set(sets[INV[0]]).intersection(*[set(sets[k]) for k in INV[1:]])
    allpos = (P.flow[INV[0]].loc[d] > 0)
    for k in INV[1:]:
        allpos &= P.flow[k].loc[d] > 0
    strong = allpos & (P.sum3_str.loc[d] >= C.DETECT_SUM_STRENGTH) & (P.sum3_flow.loc[d] >= C.MIN_AMOUNT * 3)
    return inter | set(strong[strong].index)


def run_tracking(P: Panel, t: str):
    return run_tracking_all(P, [t], {})[t]


def run_tracking_all(P: Panel, targets, cache: dict):
    """처음부터 하루씩 한 번만 진행하며, targets 날짜마다 추적 목록 스냅샷을 만든다"""
    active: dict[str, dict] = {}
    ended = []
    events = []  # (최초 감지일, 종목) - 성과 검증용
    idx = {d: i for i, d in enumerate(P.dates)}
    targets = set(targets)
    last_t = max(targets, key=lambda d: idx[d])
    snaps = {}
    for i, d in enumerate(P.dates[: idx[last_t] + 1]):
        # 종료 조건
        for tk in list(active):
            a = active[tk]
            px = P.close.at[d, tk] if tk in P.close.columns else np.nan
            chg = (px / a["start_close"] - 1) * 100 if a["start_close"] else 0
            if i - idx[a["last"]] > C.TRACK_EXPIRE_DAYS:
                ended.append({**a, "end": d, "why": "기간만료"}); del active[tk]
            elif not np.isnan(chg) and chg <= C.TRACK_STOP_LOSS:
                ended.append({**a, "end": d, "why": "이탈"}); del active[tk]
        for tk in detections(P, d, cache):
            st, fl = P.sum3_str.at[d, tk], P.sum3_flow.at[d, tk]
            if tk in active:
                a = active[tk]
                if a["last"] != d:
                    a["count"] += 1
                    a["last"] = d
                    a["s_sum"] += st
                    a["f_sum"] += fl
            else:
                active[tk] = {"t": tk, "start": d, "last": d, "count": 1, "s_sum": st, "f_sum": fl,
                              "start_close": P.close.at[d, tk]}
                events.append((d, tk))
        if d in targets:
            snaps[d] = (_tracking_rows(P, d, active, idx), list(ended), list(events))
    return snaps


def _tracking_rows(P: Panel, t: str, active: dict, idx: dict):
    upto = idx[t]
    rows = []
    for tk, a in active.items():
        i0, il = idx[a["start"]], idx[a["last"]]
        after = P.dates[il + 1: upto + 1]
        post = {k: float(P.flow[k].loc[after, tk].sum()) if after else 0.0 for k in INV}
        post_sum = sum(post.values())
        cap = P.cap.at[t, tk] if tk in P.cap.columns else np.nan
        post_str = post_sum / cap if cap and not np.isnan(cap) else 0
        last3 = P.dates[max(0, upto - 2): upto + 1]
        recent3 = float(P.sum3_flow.loc[last3, tk].sum())
        before3 = [d for d in after if d not in last3]
        prev_sum = float(P.sum3_flow.loc[before3, tk].sum()) if before3 else 0.0
        px = P.close.at[t, tk]
        chg = (px / a["start_close"] - 1) * 100 if a["start_close"] else 0
        elapsed = upto - i0 + 1
        if elapsed <= C.NEW_DAYS:
            status, note = "신규", f"첫 감지 후 {elapsed}일"
        elif chg >= C.CONFIRM_GAIN and post_sum >= 0:
            status, note = "상승확인", f"신호 대비 {chg:+.1f}%"
        elif chg <= C.WARN_LOSS:
            status, note = "이탈주의", f"신호 대비 {chg:+.1f}%"
        elif upto - il <= 2:
            status, note = "매집진행", f"최근 감지 {a['last'][5:]} · 누적 {a['count']}회"
        elif recent3 > 0 and prev_sum < 0:
            status, note = "재점화 후보", "수급 개선 · 가격 전환 미확인" if chg < 3 else "수급 개선 · 가격 동반"
        else:
            status = "추적연장"
            note = ("재점화 후보 · " if recent3 > 0 else "") + f"최근3일 {recent3:+,.0f}백만원"
        series = P.dates[i0: upto + 1]
        base = a["start_close"]
        rows.append({
            "t": tk, "n": P.name.get(tk, tk), "start": a["start"], "last": a["last"],
            "elapsed": elapsed, "count": a["count"], "status": status, "note": note,
            "s_sum": r2(a["s_sum"]), "f_sum": r2(a["f_sum"], 0), "chg": r2(chg, 1),
            "post": {k: r2(v, 0) for k, v in post.items()}, "post_sum": r2(post_sum, 0), "post_s": r2(post_str),
            "px": [r2(P.close.at[d, tk] / base * 100, 1) for d in series],
            "cf": [r2(v, 0) for v in P.sum3_flow.loc[series, tk].cumsum()],
            "dates": series,
        })
    rows.sort(key=lambda r: -(r["s_sum"] or 0))
    return rows


# ------------------------------------------------------------------ 섹터
def _cum(series: pd.Series, n: int) -> float:
    s = series.iloc[-n:]
    return float((1 + s / 100).prod() - 1) * 100


def diagnose(r3, r5, r20, breadth, breadth_prev, above_ma):
    if r20 > 0 and r5 > 0 and r3 > 0 and breadth >= 60:
        return "강한지속(주도)", "상승지속"
    if r20 > 0 and r5 > 0 and (r3 < 0 or breadth_prev - breadth >= 20):
        return "혼조", "상승피로"
    if r20 > 0 and r5 <= 0 and above_ma and breadth >= 40:
        return "혼조", "건강한 눌림"
    if r20 > 0 and not above_ma and breadth < 35:
        return "지속약세", "하락전환 위험"
    if r20 <= 0 and r5 <= 0 and r3 <= 0 and breadth < 30:
        return "완전악화형(주의)", "하락지속"
    if r20 <= 0 and r5 > 0:
        return "개선시도", "반등시도"
    if r20 <= 0:
        return "지속약세", "횡보/재정비"
    return "혼조", "횡보/재정비"


def lead_tag(x):
    return "주도" if x >= C.LEAD_EXCESS else ("약세" if x <= -C.LEAD_EXCESS else "동행")


def sector_analysis(P: Panel, t: str, members_all: dict, top_sets_by_day: dict):
    upto = P.dates.index(t)
    dates = P.dates[: upto + 1]
    mret = {m: P.index[m].loc[dates].pct_change().fillna(0) * 100 for m in ("KOSPI", "KOSDAQ")}
    out = []
    series = {}
    for sec, mem in members_all.items():
        mem = [m for m in mem if m in P.cap_last.index and not np.isnan(P.close.at[t, m])]
        if len(mem) < 2:
            continue
        mem = sorted(mem, key=lambda m: -P.cap_last[m])[: C.SECTOR_MAX_MEMBERS]
        mk = "KOSPI" if sum(P.market.get(m) == "KS" for m in mem) * 2 >= len(mem) else "KOSDAQ"
        sret = P.ret.loc[dates, mem].mean(axis=1)
        sidx = (1 + sret / 100).cumprod() * 100
        rr = {n: _cum(sret, n) for n in (1, 3, 5, 20)}
        mm = {n: _cum(mret[mk], n) for n in (1, 3, 5, 20)}
        ex = {n: rr[n] - mm[n] for n in rr}
        cl = P.close.loc[dates, mem]
        ma20 = cl.rolling(20, min_periods=5).mean()
        above = (cl > ma20)
        breadth = float(above.iloc[-1].mean() * 100)
        breadth_prev = float(above.iloc[-6].mean() * 100) if len(above) > 6 else breadth
        sma = sidx.rolling(20, min_periods=5).mean()
        above_ma = bool(sidx.iloc[-1] > sma.iloc[-1])
        at_high = bool(sidx.iloc[-1] >= sidx.iloc[-20:].max() - 1e-9)
        pat, badge = diagnose(rr[3], rr[5], rr[20], breadth, breadth_prev, above_ma)
        rpat, _ = diagnose(ex[3], ex[5], ex[20], breadth, breadth_prev, above_ma)
        leader = mem[0]
        ldiff = _cum(P.ret.loc[dates, leader], 5) - rr[5]
        ltag = "리더 피로" if ldiff <= -2 else ("리더 주도" if ldiff >= 2 else "중립")
        crossed = bool((sidx.iloc[-4:-1] <= sma.iloc[-4:-1]).any() and above_ma)
        if at_high and breadth >= 70:
            pivot = "가격·확산 확인"
        elif crossed and breadth - breadth_prev >= 15:
            pivot = "바닥 전환 시도"
        else:
            pivot = None
        win = 20
        s_ = sidx.iloc[-win:]
        m_ = (1 + mret[mk].iloc[-win:] / 100).cumprod()
        series[sec] = {"lead": [P.name.get(m) for m in mem[:3]], "d": list(s_.index), "s": [r2(v / s_.iloc[0] * 100, 2) for v in s_],
                       "m": [r2(v / m_.iloc[0] * 100, 2) for v in m_], "mk": mk}
        out.append({
            "sector": sec, "n": len(mem), "mk": mk,
            "r": {str(k): r2(v) for k, v in rr.items()}, "ex": {str(k): r2(v) for k, v in ex.items()},
            "tag": {str(k): lead_tag(v) for k, v in ex.items()},
            "breadth": r2(breadth, 0), "pattern": pat, "badge": badge, "rpattern": rpat,
            "leader": ltag, "leader_name": P.name.get(leader), "pivot": pivot,
            "members": [{"t": m, "n": P.name.get(m), "r5": r2(_cum(P.ret.loc[dates, m], 5))} for m in mem],
        })
    if not out:
        return [], {}, {}
    df = pd.DataFrame([{"s": o["sector"], "e20": o["ex"]["20"], "e5": o["ex"]["5"], "e3": o["ex"]["3"],
                        "b": o["breadth"]} for o in out]).set_index("s")
    score = (df["e20"].rank(pct=True) * .35 + df["e5"].rank(pct=True) * .30 +
             df["e3"].rank(pct=True) * .15 + df["b"].rank(pct=True) * .20)
    for o in out:
        o["score"] = r2(score[o["sector"]] * 100, 1)
    out.sort(key=lambda o: -o["score"])
    for i, o in enumerate(out, 1):
        o["rank"] = i
    bubble = {str(w): sector_bubble(P, dates, members_all, top_sets_by_day, w, out) for w in C.BUBBLE_WINDOWS}
    return out, series, bubble


def sector_bubble(P, dates, members_all, top_sets_by_day, w, sec_rows):
    w = min(w, len(dates))
    win = dates[-w:]
    half = w // 2
    breadth = {o["sector"]: o["breadth"] for o in sec_rows}
    pts = []
    union = {d: set().union(*[set(v) for v in top_sets_by_day[d].values()]) for d in win}
    s3 = P.sum3_str.loc[win]
    f3 = P.sum3_flow.loc[win].sum()
    finv = {k: P.flow[k].loc[win].sum() for k in INV}
    for sec, mem in members_all.items():
        mem = set(mem)
        if sec not in breadth:
            continue
        app, strengths = [], []
        stock_app = {}  # 종목별 출현일
        for d in win:
            listed = union[d] & mem
            if listed:
                app.append(d)
                strengths.append(max(float(s3.at[d, m]) for m in listed))
                for m in listed:
                    stock_app.setdefault(m, []).append(d)
        a = sum(1 for d in app if d in win[:half])
        b = len(app) - a
        if a >= half * .5 and b >= half * .5:
            cls = "강한 지속"
        elif a == 0 and b > 0:
            cls = "신규 진입"
        elif a > 0 and b == 0:
            cls = "이탈"
        elif b > a:
            cls = "개선형"
        else:
            cls = "위험/약세"
        if not app:
            continue
        t = win[-1]
        stocks = []
        for m, ds in stock_app.items():
            c0 = P.close.at[win[0], m] if m in P.close.columns else np.nan
            c1 = P.close.at[t, m]
            stocks.append({
                "t": m, "n": P.name.get(m, m), "app": len(ds), "last": ds[-1],
                "s_avg": r2(np.mean([s3.at[d, m] for d in ds])),
                "flow": r2(float(f3[m]), 0),
                "inv": {k: r2(float(finv[k][m]), 0) for k in INV},
                "ret": r2((c1 / c0 - 1) * 100, 1) if c0 and not np.isnan(c0) else None,
                "r1": r2(P.ret.at[t, m]), "r5": r2(_cum(P.ret.loc[:t, m], 5)),
                "cap": r2(P.cap_last.get(m), 0)})
        stocks.sort(key=lambda s: (-s["app"], -(s["flow"] or 0)))
        pts.append({"sector": sec, "x": len(app), "y": r2(np.mean(strengths)), "size": breadth[sec], "cls": cls,
                    "stocks": stocks})
    return {"from": win[0], "to": win[-1], "points": pts}



# ------------------------------------------------------------------ 감지 성과 검증
def detection_backtest(P: Panel, t: str, events):
    """최초 감지일 종가에 샀다면 N거래일 뒤 수익률. 기준일까지의 데이터만 사용(미래 정보 없음).
    추적 종료(이탈)된 종목도 모두 포함하므로 '살아남은 종목만 보는' 착시가 없습니다."""
    upto = P.dates.index(t)
    idx = {d: i for i, d in enumerate(P.dates)}
    out = {"n_events": len(events), "first": P.dates[0], "h": {}, "recent": []}
    for h in C.BT_HORIZONS:
        rets, exs = [], []
        for d, tk in events:
            i = idx[d]
            if i + h > upto:
                continue
            p0, p1 = P.close.at[d, tk], P.close.iloc[i + h][tk]
            if not p0 or np.isnan(p0) or np.isnan(p1):
                continue
            r = (p1 / p0 - 1) * 100
            mk = "KOSPI" if P.market.get(tk) == "KS" else "KOSDAQ"
            m0, m1 = P.index[mk].iloc[i], P.index[mk].iloc[i + h]
            rets.append(r)
            exs.append(r - (m1 / m0 - 1) * 100 if m0 else r)
        if rets:
            a = np.array(rets)
            out["h"][str(h)] = {"n": len(a), "avg": r2(a.mean()), "med": r2(np.median(a)),
                                "win": r2((a > 0).mean() * 100, 0), "ex": r2(np.mean(exs)),
                                "ex_win": r2((np.array(exs) > 0).mean() * 100, 0),
                                "best": r2(a.max()), "worst": r2(a.min())}
    for d, tk in sorted(events, reverse=True)[:60]:
        i = idx[d]
        row = {"d": d, "t": tk, "n": P.name.get(tk, tk)}
        for h in C.BT_HORIZONS:
            if i + h <= upto:
                p0, p1 = P.close.at[d, tk], P.close.iloc[i + h][tk]
                row[str(h)] = r2((p1 / p0 - 1) * 100, 1) if p0 and not np.isnan(p1) else None
        row["now"] = r2((P.close.at[t, tk] / P.close.at[d, tk] - 1) * 100, 1)
        out["recent"].append(row)
    return out

# ------------------------------------------------------------------ 연속수급
def streaks(P: Panel, t: str):
    upto = P.dates.index(t)
    f = P.flow["기관"].iloc[: upto + 1]
    pos = (f > 0)
    cnt = pd.Series(0, index=f.columns)
    for i in range(len(pos) - 1, -1, -1):
        row = pos.iloc[i]
        alive = cnt == (len(pos) - 1 - i)
        cnt = cnt + (row & alive).astype(int)
    rows = []
    for tk, n in cnt[cnt >= C.STREAK_EARLY[0]].items():
        amt = float(f[tk].iloc[-n:].sum())
        cap = P.cap_last.get(tk, np.nan)
        if not cap or np.isnan(cap):
            continue
        rows.append({"t": tk, "n": P.name.get(tk, tk), "days": int(n), "amt": r2(amt, 0), "cap": r2(cap, 0),
                     "s": r2(amt / cap), "m": P.market.get(tk)})
    early = sorted([r for r in rows if C.STREAK_EARLY[0] <= r["days"] <= C.STREAK_EARLY[1]], key=lambda r: -r["s"])[: C.STREAK_TOP_N]
    conf = sorted([r for r in rows if r["days"] >= C.STREAK_CONFIRM], key=lambda r: -r["s"])[: C.STREAK_TOP_N]
    return {"early": early, "confirm": conf}


# ------------------------------------------------------------------ 시장/자금
def market_block(P: Panel, t: str):
    upto = P.dates.index(t)
    dates = P.dates[: upto + 1]
    idx = {}
    for m in ("KOSPI", "KOSDAQ"):
        s = P.index[m].loc[dates]

        def ch(n):
            return r2((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100) if len(s) > n and s.iloc[-1 - n] else None
        idx[m] = {"c": r2(s.iloc[-1]), "r1": ch(1), "r3": ch(3), "r5": ch(5), "r20": ch(20)}
    tvd = dates[-C.MARKET_CHART_DAYS:]
    ks, kq = P.index_tv["KOSPI"].loc[tvd], P.index_tv["KOSDAQ"].loc[tvd]
    tot = ks.fillna(0) + kq.fillna(0)
    ma5 = tot.rolling(5, min_periods=1).mean()
    comb = (P.index["KOSPI"].loc[tvd] / P.index["KOSPI"].loc[tvd].iloc[0] +
            P.index["KOSDAQ"].loc[tvd] / P.index["KOSDAQ"].loc[tvd].iloc[0]) / 2 * 100
    tv = {"d": list(tvd), "total": [r2(v / 1e4) for v in tot], "kospi": [r2(v / 1e4) for v in ks],
          "kosdaq": [r2(v / 1e4) for v in kq], "ma5": [r2(v / 1e4) for v in ma5], "idx": [r2(v) for v in comb]}
    prev_tot = float(tot.iloc[-2]) if len(tot) > 1 else np.nan
    fx = P.fx.get(t)
    if not fx:  # 가장 최근 값
        for d in reversed(dates):
            if P.fx.get(d):
                fx = P.fx[d]
                break
    return {"index": idx, "fx": fx,
            "tv_today": {"total": r2(tot.iloc[-1] / 1e4), "kospi": r2(ks.iloc[-1] / 1e4), "kosdaq": r2(kq.iloc[-1] / 1e4),
                         "chg": r2((tot.iloc[-1] / prev_tot - 1) * 100) if prev_tot else None},
            "tv": tv}


def load_funds() -> pd.DataFrame:
    frames = []
    for p in (C.FUNDS_CSV, C.MANUAL_FUNDS_CSV):
        if p.exists():
            frames.append(pd.read_csv(p, dtype={"date": str}).set_index("date"))
    if not frames:
        return pd.DataFrame()
    df = frames[0]
    for f in frames[1:]:
        df = f.combine_first(df)
    return df.sort_index()


def funds_block(t: str):
    df = load_funds()
    if df.empty:
        return None
    df = df[df.index < t] if (df.index < t).any() else df[df.index <= t]  # 협회 자료는 D-1 기준
    if df.empty:
        return None
    df = df.tail(C.FUNDS_CHART_DAYS)
    last = df.iloc[-1]

    def chg(col, n):
        s = df[col].dropna()
        return r2((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100) if len(s) > n and s.iloc[-1 - n] else None

    cards = {}
    for col in ("deposit", "credit_total", "credit_kospi", "credit_kosdaq", "misu", "bandae"):
        if col in df:
            cards[col] = {"v": r2(last.get(col), 0), "d1": chg(col, 1), "w1": chg(col, 5), "m1": chg(col, 20)}
    ratio = r2(last.get("bandae_ratio"))
    # 위험도 점수
    pts, why = 0, []
    if ratio is not None:
        if ratio >= 3:
            pts += 2; why.append(f"반대매매 비중 {ratio}% (3% 이상)")
        elif ratio >= 2.5:
            pts += 1; why.append(f"반대매매 비중 {ratio}% (2.5% 이상)")
    if cards.get("bandae", {}).get("d1") and cards["bandae"]["d1"] >= 50:
        pts += 1; why.append("반대매매 전일 대비 +50% 이상")
    if cards.get("misu", {}).get("w1") and cards["misu"]["w1"] >= 30:
        pts += 1; why.append("미수금 1주 +30% 이상")
    if cards.get("credit_total", {}).get("m1") and cards["credit_total"]["m1"] >= 10:
        pts += 1; why.append("신용잔고 1개월 +10% 이상(과열)")
    if cards.get("deposit", {}).get("w1") and cards["deposit"]["w1"] <= -10:
        pts += 1; why.append("예탁금 1주 -10% 이하(이탈)")
    level = "위험" if pts >= 3 else ("주의" if pts >= 2 else "안정")
    series = {"d": list(df.index)}
    for col in ("deposit", "credit_total", "credit_kospi", "credit_kosdaq"):
        if col in df:
            series[col] = [r2(v / 1e6) for v in df[col]]  # 조원
    return {"date": df.index[-1], "cards": cards, "ratio": ratio, "risk": {"level": level, "points": pts, "why": why},
            "series": series}


# ------------------------------------------------------------------ 메인
def build(t: str) -> dict:
    return next(iter(build_many([t])))[1]


def build_many(targets):
    """여러 날짜를 한 번에 계산: 원천 파일은 한 번만 읽고, 추적은 한 번만 진행 (날짜별 결과를 차례로 내보냄)"""
    targets = sorted(targets)
    all_dates = raw_dates()
    first = all_dates.index(targets[0]) if targets[0] in all_dates else 0
    use = [d for d in all_dates[max(0, first - C.ANALYSIS_LOOKBACK + 1):] if d <= targets[-1]]
    days = [json.loads(gzip.decompress((C.RAW_DIR / f"{d}.json.gz").read_bytes()).decode("utf-8")) for d in use]
    P = Panel(days)
    targets = [t for t in targets if t in P.dates]
    primary, members_all, tag = load_sector_map(P.name)
    top_cache = {}
    snaps = run_tracking_all(P, targets, top_cache)
    for t in targets:
        P.cap_last = P.cap.loc[t].dropna()
        yield t, _build_one(P, t, primary, members_all, tag, top_cache, snaps[t])


def _build_one(P, t, primary, members_all, tag, top_cache, snap):
    upto = P.dates.index(t)
    tops, _ = top_lists(P, t)
    for d in P.dates[max(0, upto - max(C.BUBBLE_WINDOWS) + 1): upto + 1]:
        if d not in top_cache:
            top_cache[d] = top_lists(P, d)[1]
    top_sets_by_day = top_cache
    tracking, ended, events = snap
    backtest = detection_backtest(P, t, events)
    tracked = {r["t"] for r in tracking}

    def sec(tk):
        return primary.get(tk)

    lists = {"buy": {}, "sell": {}}
    sets_side = {side: {k: {x[0] for x in tops[side][k]} for k in INV} for side in ("buy", "sell")}
    for side in ("buy", "sell"):
        for k in INV:
            rows = []
            for tk, amt, st in tops[side][k]:
                r = stock_row(P, t, tk, amt, st)
                r["star"] = tk in tracked
                r["sec"] = sec(tk)
                r["multi"] = sum(tk in sets_side[side][x] for x in INV)
                rows.append(r)
            lists[side][k] = rows

    # 3기관 동시수급
    rank = {k: {x[0]: i + 1 for i, x in enumerate(tops["buy"][k])} for k in INV}
    common = set.intersection(*[{tk for tk, rk in rank[k].items() if rk <= C.DETECT_TOP_N} for k in INV])
    sim = []
    for tk in common:
        sim.append({"t": tk, "n": P.name.get(tk), "sec": sec(tk), "tag": tag.get(tk),
                    "inv": {k: {"rank": rank[k][tk], "s": r2(P.strength[k].at[t, tk]), "amt": r2(P.flow[k].at[t, tk], 0)}
                            for k in INV},
                    "s": r2(P.sum3_str.at[t, tk]), "amt": r2(P.sum3_flow.at[t, tk], 0)})
    sim.sort(key=lambda r: -r["s"])

    for r in tracking:
        r["sec"] = sec(r["t"])
        r["tag"] = tag.get(r["t"])

    sectors, sec_series, bubble = sector_analysis(P, t, members_all, top_sets_by_day)

    return {
        "date": t,
        "generated": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M"),
        "market": market_block(P, t),
        "funds": funds_block(t),
        "simul": sim,
        "lists": lists,
        "streaks": streaks(P, t),
        "tracking": tracking,
        "backtest": backtest,
        "sectors": sectors,
        "sector_series": sec_series,
        "bubble": bubble,
        "sector_names": sorted(members_all.keys()),
        "n_days_stored": len(raw_dates()),
    }


def write_output(t: str, data: dict):
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # file:// 로 열어도 동작하도록 JS 로 감싼 형태로 저장
    (C.OUT_DIR / f"{t}.js").write_text(f"window.KD=window.KD||{{}};window.KD['{t}']={js};", encoding="utf-8")
    dates = sorted(p.stem for p in C.OUT_DIR.glob("????-??-??.js"))
    cfg = {"detect_str": C.DETECT_SUM_STRENGTH, "detect_top": C.DETECT_TOP_N, "expire": C.TRACK_EXPIRE_DAYS,
           "stop": C.TRACK_STOP_LOSS, "new_days": C.NEW_DAYS, "confirm": C.CONFIRM_GAIN, "warn": C.WARN_LOSS,
           "top_n": C.TOP_N, "streak_top": C.STREAK_TOP_N}
    (C.OUT_DIR / "dates.js").write_text(f"window.KD_DATES={json.dumps(dates)};window.KD_CFG={json.dumps(cfg)};",
                                        encoding="utf-8")
