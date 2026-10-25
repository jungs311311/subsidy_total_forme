"""기업마당 공고로 사이트 지원 38개의 접수 상태를 매일 계산하고, 알릴 일이 생기면 report.md를 만든다.

- data/status.json : 지원별 지금 접수 중인 공고 (전국 / 지역)
- data/seen.json   : 이미 알린 공고 ID (같은 공고를 두 번 알리지 않음)
- report.md        : 새로 알릴 내용이 있을 때만 생김 → 워크플로가 GitHub 이슈로 올림
"""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAMS = ROOT / "data" / "programs.json"
SHEET = ROOT / "data" / "sheet.json"
STATUS = ROOT / "data" / "status.json"
SEEN = ROOT / "data" / "seen.json"
REPORT = ROOT / "report.md"
REPORT_TITLE = ROOT / "report_title.txt"
KST = dt.timezone(dt.timedelta(hours=9))
OWNER = "jungs311311"


def squash(text):
    return re.sub(r"\s+", "", text or "")


def is_local(row):
    """제목이 [지역]으로 시작하면 지역 공고."""
    return (row.get("title") or "").lstrip().startswith("[")


def brief(row):
    return {k: row.get(k) for k in ("id", "title", "url", "org", "start", "end", "period", "regions")}


def merge_sheet(progs):
    """구글 시트(data/sheet.json)의 '공고 찾기 단어'·'사이트 표시'와 새로 추가한 지원을 반영."""
    try:
        sheet = json.loads(SHEET.read_text(encoding="utf-8"))
        rows = sheet["programs"] + sheet.get("pre", [])
    except (OSError, ValueError, KeyError):
        return progs
    by = {p["name"]: dict(p) for p in progs}
    for s in rows:
        name = s["name"]
        if s.get("show") == "N":
            by.pop(name, None)
            continue
        p = by.setdefault(name, {"name": name, "kind": "notice" if s.get("match") else "law", "match": None})
        p["match"] = s.get("match") or None
    return list(by.values())


def run(rows, today):
    conf = json.loads(PROGRAMS.read_text(encoding="utf-8"))
    progs = merge_sheet(conf["programs"])
    nb = conf["newBusiness"]
    first_run = not SEEN.exists()
    seen = set(json.loads(SEEN.read_text(encoding="utf-8"))) if not first_run else set()

    status, matched_ids = {}, set()
    new_for_program = []  # (지원 이름, 공고)
    for p in progs:
        entry = {"kind": p["kind"], "national": [], "local": []}
        if p.get("match"):
            rx = re.compile(p["match"])
            for r in rows:
                if rx.search(squash(r["title"])):
                    matched_ids.add(r["id"])
                    (entry["local"] if is_local(r) else entry["national"]).append(brief(r))
                    if r["id"] not in seen and not is_local(r):
                        new_for_program.append((p["name"], r))
        for k in ("national", "local"):
            entry[k].sort(key=lambda x: (x["end"] or "9999-12-31"))
        status[p["name"]] = entry

    # 38개에 없는 새 사업 후보: 전국 공고 + 정해진 중앙부처 + 소상공인 관련 말
    new_business = []
    for r in rows:
        if r["id"] in matched_ids or r["id"] in seen or is_local(r):
            continue
        text = " ".join([r["title"], r.get("target") or ""])
        if any(o in (r.get("org") or "") for o in nb["orgs"]) and any(w in text for w in nb["words"]):
            new_business.append(r)

    STATUS.write_text(json.dumps({
        "updatedAt": dt.datetime.now(KST).isoformat(timespec="minutes"),
        "programs": status,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # 알린 공고 기록: 지원에 짝지어진 전국 공고 + 새 사업 후보
    report_ids = {r["id"] for _, r in new_for_program} | {r["id"] for r in new_business}
    SEEN.write_text(json.dumps(sorted(seen | report_ids), ensure_ascii=False, indent=0), encoding="utf-8")

    for f in (REPORT, REPORT_TITLE):
        if f.exists():
            f.unlink()
    if not (new_for_program or new_business):
        print("알릴 새 공고 없음")
        return
    REPORT.write_text(make_report(first_run, today, new_for_program, new_business, status), encoding="utf-8")
    head = "공고 알림 시작" if first_run else "새 공고 알림"
    n_prog = len({r["id"] for _, r in new_for_program})
    REPORT_TITLE.write_text(f"{head} {today.isoformat()}: 사이트 지원 새 공고 {n_prog}건 · 새 사업 후보 {len(new_business)}건", encoding="utf-8")
    print(f"알림: 지원 새 공고 {len(new_for_program)}건, 새 사업 후보 {len(new_business)}건")


def line(r):
    period = r.get("period") or "기간 미정"
    return f"- [{r['title']}]({r.get('url') or ''}) · {r.get('org') or ''} · {period}"


def make_report(first_run, today, new_for_program, new_business, status):
    out = []
    if first_run:
        out.append(f"@{OWNER} 공고 알림을 시작했어요. 지금 접수 중인 공고를 한 번 정리해 드려요. "
                   "앞으로는 새로 뜬 공고만 알려드려요.\n")
    else:
        out.append(f"@{OWNER} {today.isoformat()} 기업마당에 새 공고가 떴어요.\n")
    if new_for_program:
        out.append("## 사이트 지원에 새 공고\n")
        out.append("금액·조건·제외 업종이 작년과 달라졌을 수 있어요. 공고문을 확인하고 사이트 판정을 고쳐야 하는지 봐 주세요.\n")
        by, rows = {}, {}
        for name, r in new_for_program:  # 공고 하나에 지원 여러 개가 붙으면 한 줄로
            by.setdefault(r["id"], []).append(name)
            rows[r["id"]] = r
        for rid, names in by.items():
            out.append(line(rows[rid]) + f"\n  → 관련 지원: {', '.join(names)}")
        out.append("")
    if new_business:
        out.append("## 사이트에 없는 새 사업 후보\n")
        out.append("중앙부처가 낸 소상공인·개인사업자 대상 공고예요. 사이트에 넣을 만한지 봐 주세요.\n")
        out += [line(r) for r in new_business]
        out.append("")
    quiet = [n for n, e in status.items() if e["kind"] == "notice" and not e["national"]]
    if quiet:
        out.append("## 지금 전국 공고가 없는 지원\n")
        out.append(", ".join(quiet) + "\n")
    out.append("---\n사이트: https://jungs311311.github.io/bizzsubsidy · 이 알림은 매일 아침 자동으로 만들어져요.")
    return "\n".join(out)

