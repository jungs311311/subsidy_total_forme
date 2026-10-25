"""구글 시트 '사업체 보조금 조건표'를 읽어 data/sheet.json으로 저장한다.

- 시트는 '링크가 있는 모든 사용자 - 뷰어'로 공유돼 있어야 함 (로그인 없이 CSV로 읽음)
- 읽기에 실패하거나 내용이 이상하면 기존 data/sheet.json을 그대로 둔다 (사이트는 마지막으로 읽은 값 또는 기본값으로 계속 동작)
"""
import csv
import datetime as dt
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

SHEET_ID = "13crp7Mxc9zroQjgtSpVjeMvLAGd87dPfCFFQY2ZevDY"
TABS = {"programs": 0, "k": 1, "ind": 2, "pre": 5}  # 탭 gid: 지원 목록, 기준값, 업종 규모 기준, 창업 전 지원
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sheet.json"
KST = dt.timezone(dt.timedelta(hours=9))

# 지원 목록 탭: 머리글에 이 말이 들어 있는 칸을 찾는다 (칸 순서가 바뀌어도 됨)
PROGRAM_COLS = {
    "name": "지원명", "org": "기관", "cat": "분류", "tag": "꼬리표", "size": "대상 규모",
    "amt": "지원 금액", "when": "신청 시기", "about": "설명", "url": "신청 링크",
    "extra": "추가 확인 조건", "match": "공고 찾기 단어", "show": "사이트 표시",
    "checked": "마지막 확인일", "basis": "확인 근거",
}
SIZES = {"소상공인": "ss", "소기업 이하": "small", "중소기업": "sme", "제한 없음": "any", "중진공 기준": "kosmes"}
CATS = {"받는 돈", "줄이는 돈", "빌리는 돈", "재기", "성장", "우대", "배우기"}

# 창업 전 지원 탭
PRE_COLS = {
    "name": "지원명", "org": "기관", "cat": "분류", "tag": "꼬리표", "amt": "지원 금액", "when": "신청 시기",
    "about": "설명", "url": "신청 링크", "ageMin": "나이 최소", "ageMax": "나이 최대", "fields": "맞는 분야",
    "noFields": "안 되는 분야", "must": "꼭 필요한 조건", "extra": "추가 확인 조건", "match": "공고 찾기 단어",
    "show": "사이트 표시", "checked": "마지막 확인일", "basis": "확인 근거",
}
FIELDS = {"기술", "음식", "생활", "농업", "사회", "전체"}
MUSTS = {"여성", "장애인", "폐업경험", "팀"}


class SheetError(Exception):
    pass


def fetch_csv(gid):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as res:
                text = res.read().decode("utf-8-sig")
            if text.lstrip().startswith("<"):
                raise SheetError("시트가 공개돼 있지 않아요 (로그인 화면이 돌아옴). 공유 → '링크가 있는 모든 사용자'로 바꿔 주세요.")
            return list(csv.reader(io.StringIO(text)))
        except SheetError:
            raise
        except Exception as e:  # 네트워크 오류는 다시 시도
            last = e
            time.sleep(10)
    raise SheetError(f"시트를 못 읽었어요: {last}")


def num(text):
    t = re.sub(r"[,\s%원명점억만]", "", str(text or ""))
    if not t:
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def cell(row, i):
    return str(row[i]).strip() if i is not None and i < len(row) else ""


def parse_programs(rows):
    head = rows[0]
    idx = {}
    for key, word in PROGRAM_COLS.items():
        idx[key] = next((i for i, h in enumerate(head) if word in h), None)
    for need in ("name", "amt", "about"):
        if idx[need] is None:
            raise SheetError(f"지원 목록 탭에 '{PROGRAM_COLS[need]}' 칸이 없어요")
    out, warn, names = [], [], set()
    for n, row in enumerate(rows[1:], start=2):
        r = {k: cell(row, i) for k, i in idx.items()}
        if not r["name"]:
            continue
        if r["name"] in names:
            warn.append(f"{n}행 '{r['name']}' 이름이 겹쳐서 뺐어요")
            continue
        names.add(r["name"])
        if r["size"] and r["size"] not in SIZES:
            warn.append(f"{n}행 대상 규모 '{r['size']}'를 몰라서 비웠어요")
            r["size"] = ""
        r["size"] = SIZES.get(r["size"], "")
        if r["cat"] and r["cat"] not in CATS:
            warn.append(f"{n}행 분류 '{r['cat']}'를 몰라서 비웠어요")
            r["cat"] = ""
        if r["match"]:
            try:
                re.compile(r["match"])
            except re.error:
                warn.append(f"{n}행 공고 찾기 단어 '{r['match']}'가 잘못돼서 비웠어요")
                r["match"] = ""
        r["show"] = "N" if r["show"].upper() == "N" else "Y"
        if r["url"] and not r["url"].startswith("http"):
            r["url"] = "https://" + r["url"]
        out.append(r)
    return out, warn


def parse_pre(rows):
    head = rows[0]
    idx = {k: next((i for i, h in enumerate(head) if w in h), None) for k, w in PRE_COLS.items()}
    for need in ("name", "amt", "about"):
        if idx[need] is None:
            raise SheetError(f"창업 전 지원 탭에 '{PRE_COLS[need]}' 칸이 없어요")
    out, warn, names = [], [], set()
    for n, row in enumerate(rows[1:], start=2):
        r = {k: cell(row, i) for k, i in idx.items()}
        if not r["name"] or r["name"] in names:
            continue
        names.add(r["name"])
        for k in ("ageMin", "ageMax"):
            r[k] = num(r[k]) if r[k] else None
        for k in ("fields", "noFields"):
            vals = [v.strip() for v in re.split(r"[,·/]", r[k]) if v.strip()]
            bad = [v for v in vals if v not in FIELDS]
            if bad:
                warn.append(f"창업 전 {n}행 분야 '{', '.join(bad)}'를 몰라서 뺐어요")
            r[k] = [v for v in vals if v in FIELDS]
        if r["must"] and r["must"] not in MUSTS:
            warn.append(f"창업 전 {n}행 꼭 필요한 조건 '{r['must']}'를 몰라서 비웠어요")
            r["must"] = ""
        if r["cat"] and r["cat"] not in CATS:
            r["cat"] = ""
        if r["match"]:
            try:
                re.compile(r["match"])
            except re.error:
                warn.append(f"창업 전 {n}행 공고 찾기 단어가 잘못돼서 비웠어요")
                r["match"] = ""
        r["show"] = "N" if r["show"].upper() == "N" else "Y"
        if r["url"] and not r["url"].startswith("http"):
            r["url"] = "https://" + r["url"]
        out.append(r)
    return out, warn


def parse_k(rows):
    out, warn = {}, []
    for n, row in enumerate(rows[1:], start=2):
        code = cell(row, 0)
        if not code:
            continue
        v = num(cell(row, 2))
        if v is None:
            warn.append(f"기준값 {n}행 '{code}' 값이 숫자가 아니라서 뺐어요")
            continue
        out[code] = v
    return out, warn


def parse_ind(rows):
    out, warn = [], []
    for n, row in enumerate(rows[1:], start=2):
        code = cell(row, 0)
        if not code:
            continue
        vals = [num(cell(row, i)) for i in (2, 3, 4)]
        if any(v is None or v <= 0 for v in vals):
            warn.append(f"업종 규모 기준 {n}행 '{code}' 숫자가 비었거나 잘못돼서 뺐어요")
            continue
        out.append({"k": code, "n": cell(row, 1), "small": vals[0], "mid": vals[1], "ss": vals[2], "note": cell(row, 5)})
    return out, warn


def main():
    try:
        programs, w1 = parse_programs(fetch_csv(TABS["programs"]))
        k, w2 = parse_k(fetch_csv(TABS["k"]))
        ind, w3 = parse_ind(fetch_csv(TABS["ind"]))
    except SheetError as e:
        print(f"⚠ {e} → 기존 sheet.json을 그대로 씀")
        return 0
    if len(programs) < 10 or len(k) < 5 or len(ind) < 5:
        print(f"⚠ 시트 내용이 너무 적어요 (지원 {len(programs)}, 기준값 {len(k)}, 업종 {len(ind)}) → 기존 sheet.json을 그대로 씀")
        return 0
    warnings = w1 + w2 + w3
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    try:  # 창업 전 탭은 못 읽어도 나머지는 반영
        pre, w4 = parse_pre(fetch_csv(TABS["pre"]))
        warnings += w4
    except SheetError as e:
        print(f"⚠ 창업 전 지원 탭: {e} → 지난 값 그대로")
        pre = old.get("pre", [])
    data = {
        "updatedAt": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "programs": programs, "k": k, "ind": ind, "pre": pre, "warnings": warnings,
    }
    same = all(old.get(x) == data[x] for x in ("programs", "k", "ind", "pre", "warnings"))
    if same:
        print("시트 내용 바뀐 것 없음")
        return 0
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"시트 반영: 지원 {len(programs)}개, 창업 전 {len(pre)}개, 기준값 {len(k)}개, 업종 {len(ind)}개")
    for w in warnings:
        print("  ⚠", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
