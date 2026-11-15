"""개인·사업자 지원 중 가장 최근에 올라온 것만 골라 data/latest.json 으로 만든다.

화면(index.html)은 이 작은 파일 하나만 읽고, 내 조건으로 해당/애매/미해당을 판정한다.
- 사업자: 기업마당 공고 중 소상공인·개인사업자 관련(forSmall) 공고, 등록일(created) 순
- 개인: 보조금24(등록일 posted, 없으면 수정일), 복지로 중앙(최초 등록일), 복지로 지자체(수정일),
        온통청년(정책번호 앞 8자리 = 등록일)
마감이 지난 것은 뺀다. 이름이 같은 개인 지원은 한 번만 넣는다.
"""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PER_SIDE = 80  # 개인·사업자 각각 넉넉히 담아 두고 화면에서 합쳐 30개를 고른다


def load(path):
    try:
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    except Exception as exc:  # 파일 하나가 깨져도 나머지로 만든다
        print(f"skip {path}: {type(exc).__name__}")
        return {}


def ymd(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 8 and digits[:2] == "20":
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def base(name):
    return re.sub(r"[\s·ㆍ.()\[\]「」『』<>-]", "", str(name or ""))


def money(d):
    if not d:
        return {}
    out = {}
    for k in ("amtText", "loanText"):
        if d.get(k) and d.get(k.replace("Text", "") + "Sure", True) is not False:
            out[k] = d[k]
    for k in ("forms", "excl", "hasExclList", "inc", "age"):
        if d.get(k):
            out[k] = d[k]
    if d.get("target"):
        out["dtarget"] = str(d["target"])[:300]
    return out


def clip(text, n=400):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:n]


def main():
    today = (dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))).strftime("%Y-%m-%d")

    # ---------- 사업자 ----------
    notices = load("business/data/notices.json")
    bdet = load("business/data/details.json").get("items", {})
    biz = []
    for it in notices.get("items", []):
        if not it.get("forSmall") or not it.get("created"):
            continue
        if it.get("end") and it["end"] < today:
            continue
        regions = it.get("regions") or []
        if len(regions) >= 10:
            regions = []
        biz.append({
            "side": "biz", "src": "기업마당", "id": it["id"], "title": it.get("title", ""),
            "org": it.get("execOrg") or it.get("org") or "", "date": it["created"], "dateKind": "올라옴",
            "url": it.get("url", ""), "start": it.get("start"), "end": it.get("end"), "period": it.get("period", ""),
            "regions": regions, "target": it.get("target", ""), "summary": clip(it.get("summary")),
            "tags": (it.get("tags") or [])[:12], **money(bdet.get(it["id"])),
        })
    biz.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    biz = biz[:PER_SIDE]

    # ---------- 개인 ----------
    pdet = load("personal/data/details.json").get("items", {})
    manual = load("personal/data/manual.json")
    seen = {base(p.get("name")) for p in manual.get("programs", [])}  # 사이트에 직접 정리된 지원은 따로 있으므로 제외
    per = []

    def add(item):
        key = base(item["title"])
        if not key or key in seen or not item["date"]:
            return
        if item.get("end") and item["end"] < today:
            return
        if re.search(r"테스트|시연|test", item["title"], re.I):
            return
        seen.add(key)
        per.append(item)

    for it in load("personal/data/youth.json").get("items", []):
        end = ymd(it.get("bizPrdEndYmd"))
        add({
            "side": "per", "src": "온통청년", "id": "y:" + str(it.get("plcyNo")), "title": it.get("plcyNm", ""),
            "org": it.get("sprvsnInstCdNm") or it.get("operInstCdNm") or "", "date": ymd(str(it.get("plcyNo", ""))[:8]),
            "dateKind": "올라옴", "end": end or None, "reg": it.get("reg", "전국"), "sgg": it.get("sgg", ""),
            "url": it.get("aplyUrlAddr") or it.get("refUrlAddr1") or
                   f"https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/{it.get('plcyNo')}",
            "summary": clip(it.get("plcyExplnCn")), "content": clip(it.get("plcySprtCn"), 300),
            "y": {k: it.get(k) for k in ("sprtTrgtMinAge", "sprtTrgtMaxAge", "sprtTrgtAgeLmtYn", "earnCndSeCd",
                                         "earnMaxAmt", "addAplyQlfcCndCn") if it.get(k)},
            **money(pdet.get("y:" + str(it.get("plcyNo")))),
        })
    for it in load("personal/data/benefits.json").get("items", []):
        posted, modified = ymd(it.get("posted")), ymd(it.get("modified"))
        add({
            "side": "per", "src": "보조금24", "id": "g:" + str(it.get("id")), "title": it.get("name", ""),
            "org": it.get("org", ""), "date": posted or modified, "dateKind": "올라옴" if posted else "수정",
            "reg": it.get("reg", "전국"), "sgg": it.get("sgg", ""), "url": it.get("url", ""),
            "summary": clip(it.get("summary")), "content": clip(it.get("content"), 300),
            "target": clip(it.get("target"), 300), "deadline": clip(it.get("deadline"), 120), "cond": it.get("cond") or {},
            **money(pdet.get("g:" + str(it.get("id")))),
        })
    for it in load("personal/data/bokjiro.json").get("items", []):
        add({
            "side": "per", "src": "복지로", "id": "b:" + str(it.get("servId")), "title": it.get("servNm", ""),
            "org": " ".join(x for x in (it.get("jurMnofNm"), it.get("jurOrgNm")) if x), "date": ymd(it.get("svcfrstRegTs")),
            "dateKind": "올라옴", "reg": "전국", "sgg": "", "url": it.get("servDtlLink", ""), "summary": clip(it.get("servDgst")),
            "life": it.get("lifeArray", ""), "who": it.get("trgterIndvdlArray", ""),
            **money(pdet.get("b:" + str(it.get("servId")))),
        })
    for it in load("personal/data/local.json").get("items", []):
        ct = it.get("ctpvNm", "")
        reg = "대구" if ct.startswith("대구") else "경북" if ct.startswith("경") else ""
        if not reg:
            continue
        add({
            "side": "per", "src": "복지로 지자체", "id": "l:" + str(it.get("servId")), "title": it.get("servNm", ""),
            "org": " ".join(x for x in (ct, it.get("sggNm"), it.get("bizChrDeptNm")) if x), "date": ymd(it.get("lastModYmd")),
            "dateKind": "수정", "reg": reg, "sgg": it.get("sggNm", ""), "url": it.get("servDtlLink", ""),
            "summary": clip(it.get("servDgst")), "life": it.get("lifeNmArray", ""), "who": it.get("trgterIndvdlNmArray", ""),
            **money(pdet.get("l:" + str(it.get("servId")))),
        })
    per.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    per = per[:PER_SIDE]

    out = {
        "updated": (dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))).strftime("%Y-%m-%d %H:%M"),
        "sources": {
            "biz": notices.get("updatedAt", ""),
            "personal": load("personal/data/benefits.json").get("updated", ""),
        },
        "median": manual.get("median", {}),
        "items": sorted(biz + per, key=lambda x: (x["date"], x["id"]), reverse=True),
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "latest.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"latest.json: 사업자 {len(biz)}건 · 개인 {len(per)}건")


if __name__ == "__main__":
    main()
