"""가상(샘플) 데이터 생성기 — 실제 데이터 없이 대시보드를 시험할 때 사용.
결과는 data/sample_raw → docs/sample 에 따로 저장되어 실제 데이터와 섞이지 않습니다.
※ 종목명은 화면 확인용이며 수치는 모두 무작위로 만든 가짜입니다.
"""
import csv
import gzip
import datetime as dt
import json
import random

import numpy as np
import pandas as pd

import config as C

SAMPLE_RAW = C.ROOT / "data" / "sample_raw"

UNIVERSE = {
    "2차전지": ["알멕", "삼아알미늄", "한중엔시에스", "엘앤에프", "에코프로머티", "포스코퓨처엠", "천보", "대주전자재료", "솔루스첨단소재"],
    "반도체후공정": ["인텍플러스", "한양디지텍", "엑시콘", "디아이", "리노공업", "ISC", "티에스이", "하나마이크론"],
    "반도체전공정": ["한솔테크닉스", "원익IPS", "주성엔지니어링", "테스", "유진테크", "피에스케이", "이오테크닉스", "케이씨텍"],
    "기판": ["이수페타시스", "대덕전자", "코리아써키트", "심텍", "티엘비", "해성디에스"],
    "유리기판": ["와이씨켐", "필옵틱스", "제이앤티씨", "켐트로닉스", "중앙첨단소재", "HB테크놀러지", "기가비스", "에프엔에스테크", "태성", "삼성전기", "SKC"],
    "MLCC": ["삼화콘덴서", "아모텍", "코스모신소재", "대주전자", "삼성전기"],
    "광통신 부품·장비": ["RF머트리얼즈", "빛과전자", "오이솔루션", "우리로", "에치에프알", "라이콤"],
    "보안": ["SGA솔루션즈", "지니언스", "드림시큐리티", "한컴위드", "라온시큐어"],
    "화장품": ["한국화장품제조", "코스맥스", "실리콘투", "아이패밀리에스씨", "브이티", "토니모리"],
    "의료AI": ["루닛", "뷰노", "딥노이드", "제이엘케이", "코어라인소프트"],
    "전선": ["LS", "대한전선", "가온전선", "일진전기", "LS에코에너지"],
    "우주": ["쎄트렉아이", "AP위성", "인텔리안테크", "한화에어로", "켄코아"],
    "원전": ["두산에너빌리티", "한전기술", "비에이치아이", "우진", "보성파워텍"],
    "방산": ["LIG디펜스", "현대로템", "풍산", "한화시스템", "빅텍"],
    "로봇": ["레인보우로보틱스", "유진로봇", "로보티즈", "두산로보틱스", "엔젤로보틱스"],
    "바이오": ["알테오젠", "리가켐바이오", "에이비엘바이오", "펩트론", "오름테라퓨틱"],
    "조선": ["HD한국조선", "한화오션", "삼성중공업", "HD현대미포"],
    "건설": ["현대건설", "GS건설", "DL이앤씨", "대우건설"],
    "엔터": ["하이브", "JYP", "SM", "에스엠C&C", "디어유"],
    "철강": ["현대제철", "세아제강지주", "동국제강", "포스코홀딩스"],
    "음식료": ["농심", "오리온", "삼양식품", "CJ제일제당"],
    "게임": ["NC", "크래프톤", "넷마블", "펄어비스"],
}
KNOWN_CODES = {"알멕": "354320", "삼아알미늄": "006110", "한중엔시에스": "107640", "인텍플러스": "064290",
               "한양디지텍": "078350", "엑시콘": "092870", "디아이": "003160", "리노공업": "058470",
               "한솔테크닉스": "004710", "RF머트리얼즈": "327260"}
TREND = {"2차전지": .45, "반도체후공정": .5, "반도체전공정": .35, "기판": .55, "유리기판": .4, "MLCC": .3,
         "광통신 부품·장비": .45, "보안": .35, "의료AI": .3, "화장품": -.15, "엔터": -.1, "음식료": -.1,
         "철강": -.05, "게임": -.12}


def make_sample(n_days=95, seed=7):
    rng = np.random.default_rng(seed)
    random.seed(seed)
    C.RAW_DIR = SAMPLE_RAW
    C.FUNDS_CSV = SAMPLE_RAW / "funds.csv"
    C.MANUAL_FUNDS_CSV = SAMPLE_RAW / "none.csv"
    C.SECTORS_AUTO = SAMPLE_RAW / "sectors_auto.csv"
    C.OUT_DIR = C.ROOT / "docs" / "sample"
    SAMPLE_RAW.mkdir(parents=True, exist_ok=True)
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in list(SAMPLE_RAW.glob("*.json*")) + list(C.OUT_DIR.glob("*.js")):
        p.unlink()

    # 종목 구성
    stocks, sec_rows, code_i = {}, [], 100000
    for sec, names in UNIVERSE.items():
        for nm in names:
            if nm not in {s["n"] for s in stocks.values()}:
                code = KNOWN_CODES.get(nm)
                if not code:
                    code_i += 137
                    code = f"9{code_i % 100000:05d}"
                stocks[code] = {"n": nm, "m": random.choice(["KS", "KQ", "KQ"]),
                                "cap": float(rng.lognormal(9.0, 0.9)), "sec": sec}
            code = next(c for c, s in stocks.items() if s["n"] == nm)
            sec_rows.append({"ticker": code, "name": nm, "sector": sec, "theme": sec})
    for i in range(260):  # 기타 종목
        code_i += 211
        stocks[f"8{code_i % 100000:05d}"] = {"n": f"샘플종목{i + 1:03d}", "m": random.choice(["KS", "KQ"]),
                                              "cap": float(rng.lognormal(8.6, 1.0)), "sec": None}
    with open(C.SECTORS_AUTO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "sector", "theme"])
        w.writeheader()
        w.writerows(sec_rows)

    end = dt.date(2026, 10, 8)
    dates = pd.bdate_range(end=end, periods=n_days).strftime("%Y-%m-%d").tolist()
    codes = list(stocks)
    px = {c: 10000.0 * rng.uniform(.3, 5) for c in codes}
    # 매집 종목(3기관 누적 매수) 몇 개를 심어둔다
    accum = {c: (random.randint(0, n_days - 10), random.randint(8, 30)) for c in random.sample(codes, 40)}
    for k in KNOWN_CODES.values():
        accum[k] = (random.randint(n_days - 35, n_days - 3), random.randint(10, 30))
    persist = {c: {k: 0.0 for k in C.INVESTORS} for c in codes}
    kospi, kosdaq = 6200.0, 830.0
    for di, d in enumerate(dates):
        mk_k = rng.normal(0.0004, .012)
        mk_q = rng.normal(0.001, .011)
        if di == len(dates) - 1:
            mk_k, mk_q = -.0262, -.0069
        kospi *= 1 + mk_k
        kosdaq *= 1 + mk_q
        sec_shock = {s: rng.normal(TREND.get(s, 0) / 100, .018) for s in UNIVERSE}
        day = {"date": d, "stocks": {}, "flows": {}, "index": {}, "fx": None}
        tv = {"KS": 0.0, "KQ": 0.0}
        for c in codes:
            s = stocks[c]
            mret = mk_k if s["m"] == "KS" else mk_q
            a = accum.get(c)
            active = a and a[0] <= di < a[0] + a[1]
            r = mret * .8 + (sec_shock[s["sec"]] if s["sec"] else 0) + rng.normal(0, .022) + (.006 if active else 0)
            r = float(np.clip(r, -.29, .29))
            px[c] *= 1 + r
            s["cap"] *= 1 + r
            cap = s["cap"]
            tvv = cap * 100 * rng.uniform(.002, .02)  # 백만원
            tv[s["m"]] += tvv
            fl = {}
            for k in C.INVESTORS:
                persist[c][k] = .55 * persist[c][k] + rng.normal(0, 1)
                base = persist[c][k] * cap * 100 * .0007
                if active:
                    base += cap * 100 * rng.uniform(.0008, .005)
                if abs(base) > 5:
                    fl[k] = round(base, 1)
            inst = sum(fl.values()) + rng.normal(0, cap * 100 * .001)
            fl["기관"] = round(inst, 1)
            day["flows"][c] = fl
            day["stocks"][c] = {"n": s["n"], "m": s["m"], "c": round(px[c], 0), "r": round(r * 100, 2),
                                "cap": round(cap, 1), "tv": round(tvv, 1)}
        scale = {"KS": 24.4e4 / max(tv["KS"] / 100, 1), "KQ": 8.0e4 / max(tv["KQ"] / 100, 1)}
        noise = rng.uniform(.75, 1.3)
        day["index"] = {"KOSPI": {"c": round(kospi, 2), "r": round(mk_k * 100, 2), "tv": round(tv["KS"] / 100 * scale["KS"] * noise, 0)},
                        "KOSDAQ": {"c": round(kosdaq, 2), "r": round(mk_q * 100, 2), "tv": round(tv["KQ"] / 100 * scale["KQ"] * noise, 0)}}
        day["fx"] = {"c": round(1370 + rng.normal(0, 8), 2), "d": d, "r": round(rng.normal(0, .4), 2)}
        (SAMPLE_RAW / f"{d}.json.gz").write_bytes(gzip.compress(json.dumps(day, ensure_ascii=False).encode("utf-8")))

    # 증시자금 (백만원)
    fd = pd.bdate_range(end=end - dt.timedelta(days=1), periods=215)
    n = len(fd)
    t = np.linspace(0, 1, n)
    dep = (80 + 55 * np.sin(t * 3.1) ** 2 + rng.normal(0, 3, n).cumsum() * .3) * 1e6
    cr_k = (17 + 12 * np.sin(t * 2.6) ** 1 + rng.normal(0, .3, n).cumsum() * .1) * 1e6
    cr_q = (10.5 - 4 * t ** 2 + rng.normal(0, .1, n).cumsum() * .1) * 1e6
    misu = rng.uniform(6e5, 1.1e6, n)
    ratio = np.clip(rng.normal(1.6, .5, n), .5, 5)
    pd.DataFrame({"date": fd.strftime("%Y-%m-%d"), "deposit": dep.round(), "credit_total": (cr_k + cr_q).round(),
                  "credit_kospi": cr_k.round(), "credit_kosdaq": cr_q.round(), "misu": misu.round(),
                  "bandae": (misu * ratio / 100).round(), "bandae_ratio": ratio.round(2)}).to_csv(C.FUNDS_CSV, index=False)
    print(f"[샘플] {len(dates)}거래일 · 종목 {len(codes)}개 생성")
