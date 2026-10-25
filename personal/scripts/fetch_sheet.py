"""구글 시트 "개인 보조금 기준표"를 읽어 data/manual.json 으로 저장합니다.

- 시트는 "링크가 있는 모든 사용자: 뷰어"로 공유되어 있어야 합니다 (로그인 없이 CSV로 받음).
- 값이 이상하면 그 칸만 버리고, 시트 전체가 이상하면 저장하지 않고 이전 manual.json 을 그대로 둡니다.
- 기준값은 scripts/manual_defaults.json 의 기본값과 비교해 1/3 ~ 3배 범위를 벗어나면 버립니다 (오타 방지).
"""
import csv, io, json, os, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

SHEET_ID = os.environ.get("SHEET_ID", "1yABrnJB03pDRq7KqRVuE9ezVPMXJpT2eCJcVN-Xh3fc")
GID = {"지원목록": 1, "기준값": 2, "중위소득": 3, "새 지원": 4, "설정": 6}
HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "data", "manual.json")
DEF = json.load(open(os.path.join(HERE, "manual_defaults.json"), encoding="utf-8"))
KST = timezone(timedelta(hours=9))
warn = []


def tab(name):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID[name]}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 personalsubsidy"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if "text/csv" not in (r.headers.get("Content-Type") or ""):
            raise RuntimeError("CSV가 아닌 응답 (시트가 '링크가 있는 모든 사용자 보기'로 공유되어 있는지 확인)")
        rows = list(csv.reader(io.StringIO(r.read().decode("utf-8"))))
    return [[c.strip() for c in row] for row in rows[1:] if any(c.strip() for c in row)]


def date(s, where):
    s = (s or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            pass
    warn.append(f"{where}: 날짜 형식 이상 '{s}' → 무시")
    return ""


def number(s):
    s = (s or "").replace(",", "").replace(" ", "")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def cell(row, i):
    return row[i] if i < len(row) else ""


def main():
    try:
        lst, prm, med, new, cfg = (tab(n) for n in ("지원목록", "기준값", "중위소득", "새 지원", "설정"))
    except Exception as e:
        print(f"시트를 읽지 못했습니다: {e}\n이전 data/manual.json 을 그대로 둡니다.")
        return

    names = set(DEF["names"])
    programs = []
    for r in lst:
        n = cell(r, 0)
        if n not in names:
            warn.append(f"지원목록: 사이트에 없는 이름 '{n}' → 무시 (새 지원은 '새 지원' 탭에)")
            continue
        it = {"name": n}
        for key, i in (("org", 3), ("amount", 4), ("apply", 5), ("status", 6), ("period", 10), ("asset", 11)):
            v = cell(r, i)
            if v and not (key == "amount" and v.startswith("(자동")):
                it[key] = v[:400]
        if cell(r, 7).upper() in ("O", "Y", "○", "상시"):
            it["always"] = 1
        for key, i in (("start", 8), ("end", 9)):
            v = date(cell(r, i), f"지원목록 {n}")
            if v:
                it[key] = v
        programs.append(it)
    if len(programs) < len(names) * 0.8:
        sys.exit(f"지원목록이 {len(programs)}개뿐입니다 (정상 {len(names)}개). 시트가 망가졌을 수 있어 저장하지 않습니다.")

    params = {}
    for r in prm:
        k = f"{cell(r, 0)}.{cell(r, 1)}"
        v = number(cell(r, 2))
        d = DEF["params"].get(k)
        if d is None:
            warn.append(f"기준값: 모르는 항목 '{k}' → 무시")
        elif v is None or v < 0:
            warn.append(f"기준값: '{k}' 값이 숫자가 아님 '{cell(r, 2)}' → 기본값 {d}")
        elif d and not (d / 3 <= v <= d * 3):
            warn.append(f"기준값: '{k}' 값 {v} 가 기본값 {d}와 너무 다름 (오타?) → 기본값 유지")
        else:
            params[k] = v

    median = {}
    for r in med:
        y = number(cell(r, 0))
        vals = [number(cell(r, i)) for i in range(1, 7)]
        if not isinstance(y, int) or not (2020 <= y <= 2100):
            continue
        if all(isinstance(v, (int, float)) and v > 1_000_000 for v in vals) and vals == sorted(vals):
            median[str(y)] = vals
        else:
            warn.append(f"중위소득 {y}년: 1~6인 값이 비었거나 이상함 → 무시")

    added = []
    for r in new:
        n = cell(r, 0)
        if not n:
            continue
        reg = cell(r, 1)
        if reg not in ("전국", "대구", "경북"):
            warn.append(f"새 지원 '{n}': 지역은 전국/대구/경북 중 하나 → 무시")
            continue
        if n in names:
            warn.append(f"새 지원 '{n}': 이미 지원목록에 있는 이름 → 무시")
            continue
        it = {"name": n[:80], "reg": reg, "sgg": cell(r, 2), "type": cell(r, 3), "org": cell(r, 4), "amount": cell(r, 5)[:400],
              "apply": cell(r, 6)[:300], "conds": cell(r, 9)[:400], "period": cell(r, 13)[:300], "asset": cell(r, 14)[:400]}
        for key, i in (("minAge", 7), ("maxAge", 8)):
            v = number(cell(r, i))
            if isinstance(v, int) and 0 <= v <= 120:
                it[key] = v
        if cell(r, 10).upper() in ("O", "Y", "○", "상시"):
            it["always"] = 1
        for key, i in (("start", 11), ("end", 12)):
            v = date(cell(r, i), f"새 지원 {n}")
            if v:
                it[key] = v
        added.append({k: v for k, v in it.items() if v not in ("", None)})

    checked = ""
    for r in cfg:
        if cell(r, 0) == "마지막 확인일":
            checked = date(cell(r, 1), "설정")

    out = {"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "checked": checked, "params": params,
           "median": median, "programs": programs, "added": added, "warnings": warn}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print(f"저장 완료: 지원 {len(programs)}개, 기준값 {len(params)}개, 중위소득 {list(median)}, 새 지원 {len(added)}개, 확인일 {checked}")
    for w in warn:
        print("주의:", w)


if __name__ == "__main__":
    main()
