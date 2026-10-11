"""텔레그램 알림.

준비 (1회):
  1) 텔레그램에서 @BotFather 검색 → /newbot → 봇 이름 정하면 '토큰'을 줍니다.
  2) 만든 봇과 대화방을 열고 아무 말이나 한 번 보냅니다 (예: 안녕).
  3) python collector/notify.py --find-chat   → 내 chat_id 가 출력됩니다.
  4) run_daily.bat (또는 GitHub Secrets) 에 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 를 넣습니다.
  5) python collector/notify.py --test        → 시험 메시지

이후 run.py 가 매일 계산을 마치면 가장 최근 날짜 기준으로 자동 발송합니다.
알림 내용: 3기관 동시수급 · 신규 매집 감지 · 재점화 후보 · 시장 위험도(주의 이상)
"""
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

API = "https://api.telegram.org/bot{token}/{method}"


def _token():
    return os.environ.get("TELEGRAM_TOKEN", "").strip()


def _chat():
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def enabled():
    return bool(_token() and _chat())


def send(text: str) -> bool:
    if not enabled():
        return False
    r = requests.post(API.format(token=_token(), method="sendMessage"),
                      json={"chat_id": _chat(), "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=15)
    if not r.ok:
        print("[텔레그램] 전송 실패:", r.status_code, r.text[:200])
    return r.ok


def load(date: str) -> dict:
    s = (C.OUT_DIR / f"{date}.js").read_text(encoding="utf-8")
    return json.loads(s[s.index("=", s.index("]")) + 1:-1])


def fmt(v, d=2):
    return "–" if v is None else f"{v:,.{d}f}"


def build_message(D: dict) -> str | None:
    lines = [f"<b>기관 수급 레이더 · {D['date']}</b>"]
    ix = D["market"]["index"]
    lines.append(f"코스피 {fmt(ix['KOSPI']['c'])} ({ix['KOSPI']['r1']:+.2f}%) · 코스닥 {fmt(ix['KOSDAQ']['c'])} ({ix['KOSDAQ']['r1']:+.2f}%)")
    F = D.get("funds")
    if F and F["risk"]["level"] != "안정":
        lines.append(f"⚠️ 시장 위험도 <b>{F['risk']['level']}</b>: " + ", ".join(F["risk"]["why"]))

    sim = D.get("simul", [])
    if sim:
        lines.append("\n<b>■ 3기관 동시수급</b>")
        for r in sim[:10]:
            rk = "/".join(str(r["inv"][k]["rank"]) for k in C.INVESTORS)
            lines.append(f"· {r['n']} {r['s']:.2f}% ({fmt(r['amt'], 0)}백만) 순위 {rk}" + (f" [{r['sec']}]" if r.get("sec") else ""))

    trk = D.get("tracking", [])
    new = [r for r in trk if r["start"] == D["date"]]
    if new:
        lines.append("\n<b>■ 신규 매집 감지</b>")
        for r in new[:10]:
            lines.append(f"· {r['n']} 합산강도 {r['s_sum']:.2f}%" + (f" [{r['sec']}]" if r.get("sec") else ""))
    again = [r for r in trk if r["last"] == D["date"] and r["start"] != D["date"]]
    if again:
        lines.append("\n<b>■ 재감지 (매집 반복)</b>")
        for r in again[:10]:
            lines.append(f"· {r['n']} {r['count']}회째 · 첫 감지 대비 {r['chg']:+.1f}%")
    re_ = [r for r in trk if r["status"] == "재점화 후보"]
    if re_:
        lines.append("\n<b>■ 재점화 후보</b>")
        for r in re_[:8]:
            lines.append(f"· {r['n']} · {r['note']}")

    if len(lines) <= 2:
        lines.append("오늘은 감지된 종목이 없습니다.")
    lines.append("\n참고용 정보이며 투자 판단의 책임은 본인에게 있습니다.")
    return "\n".join(lines)


def notify_latest():
    if not enabled():
        return
    dates = sorted(p.stem for p in C.OUT_DIR.glob("????-??-??.js"))
    if not dates:
        return
    D = load(dates[-1])
    msg = build_message(D)
    if msg and send(msg):
        print(f"[텔레그램] {dates[-1]} 알림 전송")


def find_chat():
    tok = _token()
    if not tok:
        print("먼저 TELEGRAM_TOKEN 을 설정하세요 (set TELEGRAM_TOKEN=...)")
        return
    r = requests.get(API.format(token=tok, method="getUpdates"), timeout=15).json()
    chats = {}
    for u in r.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        c = m.get("chat") or {}
        if c:
            chats[c["id"]] = c.get("title") or c.get("first_name") or c.get("username")
    if not chats:
        print("받은 메시지가 없습니다. 텔레그램에서 봇에게 아무 말이나 보낸 뒤 다시 실행하세요.")
    for cid, name in chats.items():
        print(f"chat_id = {cid}   ({name})")


if __name__ == "__main__":
    if "--find-chat" in sys.argv:
        find_chat()
    elif "--test" in sys.argv:
        print("성공" if send("기관 수급 레이더 알림 시험 메시지입니다.") else "실패: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 를 확인하세요")
    else:
        notify_latest()
