"""보조금24(행정안전부 공공서비스 혜택 정보) 데이터를 받아 data/benefits.json으로 정리합니다.

- 개인·가구 대상만 남깁니다 (소상공인·법인 전용 제외).
- 전국(중앙부처·공공기관) + 대구광역시 + 경상북도 사업만 남깁니다.
- 지원조건 코드(JA....)를 서비스별로 붙여서 페이지가 자동 판정할 수 있게 합니다.

인증키는 환경변수 GOV24_KEY 에서 읽습니다 (GitHub Secrets).
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://api.odcloud.kr/api/gov24/v3/"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "benefits.json")
KST = timezone(timedelta(hours=9))


def fetch_all(key, part):
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({"page": page, "perPage": 1000, "returnType": "JSON", "serviceKey": key})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(BASE + part + "?" + q, timeout=90) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")[:300]
                if e.code in (401, 403) or attempt == 3:
                    sys.exit(f"[{part}] HTTP {e.code}: {body}")
                time.sleep(5)
            except Exception as e:  # 네트워크 오류 재시도
                if attempt == 3:
                    sys.exit(f"[{part}] {e}")
                time.sleep(5)
        batch = data.get("data") or []
        rows += batch
        total = data.get("totalCount", 0)
        print(f"{part}: {len(rows)}/{total}", flush=True)
        if len(rows) >= total or not batch:
            return rows
        page += 1
        time.sleep(0.3)


DG_SGG = {"수성": "수성구", "달서": "달서구", "달성": "달성군", "군위": "군위군"}
GB_SGG = {k: v for k, v in (
    ("포항", "포항시"), ("경주", "경주시"), ("김천", "김천시"), ("안동", "안동시"), ("구미", "구미시"), ("영주", "영주시"),
    ("영천", "영천시"), ("상주", "상주시"), ("문경", "문경시"), ("경산", "경산시"), ("의성", "의성군"), ("청송", "청송군"),
    ("영양", "영양군"), ("영덕", "영덕군"), ("청도", "청도군"), ("고령", "고령군"), ("성주", "성주군"), ("칠곡", "칠곡군"),
    ("예천", "예천군"), ("봉화", "봉화군"), ("울진", "울진군"), ("울릉", "울릉군"))}
OTHER = ("서울", "부산", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충청", "충북", "충남", "전라", "전북", "전남",
         "경상남도", "경남", "제주", "수원", "성남", "고양", "용인", "부천", "안산", "안양", "화성", "평택", "의정부", "시흥", "파주",
         "김포", "광명", "하남", "춘천", "원주", "강릉", "청주", "충주", "천안", "아산", "공주", "전주", "군산", "익산", "목포", "여수",
         "순천", "창원", "김해", "진주", "양산", "거제", "통영", "서귀포")


def region_of(svc):
    """(지역, 시군구) 반환. 전국 사업이면 ("전국",""), 대구·경북이 아닌 지역 사업이면 (None, None)."""
    org = (svc.get("소관기관명") or "").strip()
    typ = (svc.get("소관기관유형") or "").strip()
    name = (svc.get("서비스명") or "").strip()
    if org.startswith("대구"):
        rest = org.replace("대구광역시", "").replace("교육청", "").strip()
        return "대구", rest
    if org.startswith("경상북도") or org.startswith("경북"):
        rest = org.replace("경상북도", "").replace("교육청", "").strip()
        return "경북", rest
    # 산하 재단·공사 등: 기관명에 지역 이름이 들어 있는 경우
    for k, v in DG_SGG.items():
        if k in org:
            return "대구", v
    for k, v in GB_SGG.items():
        if k in org:
            return "경북", v
    if any(x in org for x in OTHER):
        return None, None
    if any(x in typ for x in ("지방자치단체", "교육청", "시도", "시군구", "지방")):
        return None, None
    return "전국", ""


def is_personal(svc):
    who = svc.get("사용자구분") or ""
    return ("개인" in who) or ("가구" in who) or who == ""


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


COND_KEYS = ["JA0101", "JA0102", "JA0201", "JA0202", "JA0203", "JA0204", "JA0205",
             "JA0301", "JA0302", "JA0303", "JA0313", "JA0314", "JA0315", "JA0316", "JA0317", "JA0318",
             "JA0319", "JA0320", "JA0322", "JA0326", "JA0327", "JA0328", "JA0329", "JA0330",
             "JA0401", "JA0402", "JA0403", "JA0404", "JA0410", "JA0411", "JA0412", "JA0413", "JA0414"]


def compact_cond(c):
    out = {}
    for k in ("JA0110", "JA0111"):
        v = c.get(k)
        if v not in (None, "", 0) or (k == "JA0110" and v == 0):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
    on = [k for k in COND_KEYS if str(c.get(k) or "").upper() == "Y"]
    if on:
        out["on"] = on
    return out


def main():
    key = os.environ.get("GOV24_KEY", "").strip()
    if not key:
        sys.exit("GOV24_KEY가 없습니다. GitHub Settings → Secrets → Actions 에 GOV24_KEY 를 넣어 주세요.")
    if "%" in key:
        key = urllib.parse.unquote(key)

    services = fetch_all(key, "serviceList")
    conds = {c.get("서비스ID"): c for c in fetch_all(key, "supportConditions")}

    items = []
    for s in services:
        if not is_personal(s):
            continue
        reg, sgg = region_of(s)
        if not reg:
            continue
        sid = s.get("서비스ID")
        items.append({
            "id": sid,
            "name": clip(s.get("서비스명"), 80),
            "reg": reg,
            "sgg": sgg,
            "org": clip(s.get("소관기관명"), 40),
            "orgType": s.get("소관기관유형") or "",
            "kind": s.get("지원유형") or "",
            "field": s.get("서비스분야") or "",
            "summary": clip(s.get("서비스목적요약"), 400),
            "target": clip(s.get("지원대상"), 700),
            "criteria": clip(s.get("선정기준"), 700),
            "content": clip(s.get("지원내용"), 800),
            "how": clip(s.get("신청방법"), 300),
            "deadline": clip(s.get("신청기한"), 120),
            "recv": clip(s.get("접수기관"), 60),
            "tel": clip(s.get("전화문의"), 60),
            "url": s.get("상세조회URL") or "",
            "views": s.get("조회수") or 0,
            "cond": compact_cond(conds.get(sid, {})),
        })

    items.sort(key=lambda x: -int(x["views"] or 0))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "count": len(items), "items": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    by = {}
    for it in items:
        by[it["reg"]] = by.get(it["reg"], 0) + 1
    print(f"저장 완료: {len(items)}건 {by} (전체 {len(services)}건 중)")
    types = {}
    for sv in services:
        t = sv.get("소관기관유형") or "(없음)"
        types[t] = types.get(t, 0) + 1
    print("소관기관유형:", types)


if __name__ == "__main__":
    main()
