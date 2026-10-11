"""네이버 증권 '테마' 목록에서 종목-섹터 매핑을 자동 생성합니다.

  python collector/build_sectors.py

결과: sectors/sectors_auto.csv  (ticker,name,sector,theme)
대시보드 섹터명과 네이버 테마 키워드의 대응은 sectors/sector_rules.csv 에서 편집합니다.
한 종목이 여러 섹터에 들어갈 수 있으며, sectors_manual.csv(직접 지정)가 항상 우선합니다.
월 1회 정도 다시 돌리면 충분합니다.

2026년 네이버 증권 개편 후의 JSON API(stock.naver.com/api/domestic/market/theme/...)를 사용합니다.
"""
import csv
import json
import time

import requests

from config import SECTOR_RULES, SECTORS_AUTO

BASE = "https://stock.naver.com/api/domestic/market"
API = BASE + "/theme"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Referer": "https://stock.naver.com/", "Accept": "application/json"}
DEBUG_DIR = SECTOR_RULES.parent


def get_json(url, params):
    r = requests.get(url, params=params, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def dict_list(js):
    """응답 안에서 가장 긴 'dict 리스트'를 찾아 반환 (항목 이름이 바뀌어도 동작하도록)"""
    best = []

    def walk(o):
        nonlocal best
        if isinstance(o, list):
            if o and all(isinstance(x, dict) for x in o) and len(o) > len(best):
                best = o
            for x in o:
                walk(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(js)
    return best


def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def list_themes(api=None, raw_name="naver_raw_themes.json"):
    API = api or BASE + "/theme"
    themes = {}

    def add(rows):
        n = 0
        for r in rows:
            no = pick(r, "no", "themeNo", "themeCode", "id", "code")
            name = pick(r, "name", "themeName", "title")
            if no is not None and name and str(no) not in themes:
                themes[str(no)] = str(name).strip()
                n += 1
        return n

    # 첫 페이지 (pageSize 는 100이 상한)
    js = get_json(f"{API}/list", {"startIdx": 0, "pageSize": 100, "sortType": "changeRate"})
    (DEBUG_DIR / raw_name).write_text(json.dumps(js, ensure_ascii=False, indent=1)[:4000], encoding="utf-8")
    add(dict_list(js))
    # 다음 페이지: startIdx 를 '건수'(100,200..) 방식으로, 안 되면 '페이지'(1,2..) 방식으로
    for mode in ("count", "page"):
        before = len(themes)
        for i in range(1, 30):
            start = i * 100 if mode == "count" else i + 1
            try:
                rows = dict_list(get_json(f"{API}/list", {"startIdx": start, "pageSize": 100, "sortType": "changeRate"}))
            except Exception as e:
                print(f"  테마 목록 {mode} 방식 {i}쪽: {e}")
                break
            if not rows or add(rows) == 0:
                break
            time.sleep(0.3)
        if len(themes) > before:
            break
    return themes


def theme_members(no, first=False, api=None):
    API = api or BASE + "/theme"
    out, seen = [], set()
    for page in range(0, 5):
        js = get_json(f"{API}/{no}/stocklist", {"marketType": "ALL", "orderType": "marketSum",
                                                "startIdx": page * 100, "pageSize": 100})
        if first and page == 0:
            (DEBUG_DIR / "naver_raw_members.json").write_text(json.dumps(js, ensure_ascii=False, indent=1)[:4000], encoding="utf-8")
        rows = dict_list(js)
        for r in rows:
            code = pick(r, "itemCode", "itemcode", "stockCode", "code", "reutersCode")
            name = pick(r, "stockName", "itemName", "itemname", "name")
            if code and str(code)[:6] not in seen:
                c = str(code)[:6]
                seen.add(c)
                out.append((c, str(name or c).strip()))
        if len(rows) < 100:
            break
        time.sleep(0.2)
    return out


def main():
    rules = []
    with open(SECTOR_RULES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rules.append((r["sector"], [k.strip() for k in r["naver_theme_keywords"].split("|") if k.strip()]))

    groups = []  # (api, no, 표시이름, 매칭용 이름)
    themes = list_themes()
    print(f"네이버 테마 {len(themes)}개")
    (DEBUG_DIR / "naver_themes.txt").write_text("\n".join(f"{k}\t{v}" for k, v in themes.items()), encoding="utf-8")
    groups += [(BASE + "/theme", no, n, n) for no, n in themes.items()]
    try:
        ups = list_themes(BASE + "/upjong", "naver_raw_upjong.json")
        print(f"네이버 업종 {len(ups)}개")
        (DEBUG_DIR / "naver_upjong.txt").write_text("\n".join(f"{k}\t{v}" for k, v in ups.items()), encoding="utf-8")
        groups += [(BASE + "/upjong", no, "업종:" + n, "업종:" + n) for no, n in ups.items()]
    except Exception as e:
        print("업종 목록 실패:", e)
    if not groups:
        print("테마를 받지 못했습니다. sectors/naver_raw_themes.json 을 확인하세요.")
        return

    def match(kw, name):
        # '=이름' 정확히 일치, '업종:이름' 업종 포함, 그 외 테마 이름 포함
        if kw.startswith("="):
            return name == kw[1:]
        if kw.startswith("업종:"):
            return name.startswith("업종:") and kw[3:].lower() in name[3:].lower()
        return not name.startswith("업종:") and kw.lower() in name.lower()

    rows, seen, first = [], set(), True
    for api, no, tname, key in groups:
        sectors = [s for s, kws in rules if any(match(k, key) for k in kws)]
        if not sectors:
            continue
        try:
            members = theme_members(no, first, api)
        except Exception as e:
            print(f"  {tname}: 실패 {e}")
            continue
        first = False
        time.sleep(0.3)
        for code, name in members:
            for s in sectors:
                if (code, s) in seen:
                    continue
                seen.add((code, s))
                rows.append({"ticker": code, "name": name, "sector": s, "theme": tname})
        print(f"  {tname} → {', '.join(sectors)} ({len(members)}종목)")

    with open(SECTORS_AUTO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "sector", "theme"])
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {SECTORS_AUTO} ({len(rows)}행)")
    unmatched = [s for s, _ in rules if s not in {r['sector'] for r in rows}]
    if unmatched:
        print("매칭된 테마가 없는 섹터:", ", ".join(unmatched))


if __name__ == "__main__":
    import tee
    tee.start("sectors_run.log")
    main()
