"""온통청년 청년정책 API에서 전국 + 대구·경북 청년정책을 받아 data/youth.json 으로 저장합니다.

인증키: 환경변수 YOUTH_KEY
요청: https://www.youthcenter.go.kr/go/ythip/getPlcy?apiKeyNm=...&pageNum=1&pageSize=100&rtnType=json
지역: zipCd(법정 시군구 코드, 쉼표 구분) — 대구 27xxx, 경북 47xxx. 시도가 10곳 이상이면 전국 정책으로 봅니다.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "youth.json")
KST = timezone(timedelta(hours=9))

SGG = {
    "27110": "중구", "27140": "동구", "27170": "서구", "27200": "남구", "27230": "북구", "27260": "수성구",
    "27290": "달서구", "27710": "달성군", "27720": "군위군",
    "47111": "포항시", "47113": "포항시", "47130": "경주시", "47150": "김천시", "47170": "안동시", "47190": "구미시",
    "47210": "영주시", "47230": "영천시", "47250": "상주시", "47280": "문경시", "47290": "경산시", "47720": "군위군",
    "47730": "의성군", "47750": "청송군", "47760": "영양군", "47770": "영덕군", "47820": "청도군", "47830": "고령군",
    "47840": "성주군", "47850": "칠곡군", "47900": "예천군", "47920": "봉화군", "47930": "울진군", "47940": "울릉군",
}
KEEP = ["plcyNo", "plcyNm", "plcyKywdNm", "plcyExplnCn", "lclsfNm", "mclsfNm", "plcySprtCn", "sprvsnInstCdNm",
        "operInstCdNm", "aplyYmd", "plcyAplyMthdCn", "aplyUrlAddr", "refUrlAddr1", "sprtTrgtMinAge", "sprtTrgtMaxAge",
        "sprtTrgtAgeLmtYn", "earnCndSeCd", "earnMinAmt", "earnMaxAmt", "earnEtcCn", "addAplyQlfcCndCn", "inqCnt",
        "bizPrdBgngYmd", "bizPrdEndYmd", "bizPrdEtcCn"]


def clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def get(key, page, size):
    q = urllib.parse.urlencode({"apiKeyNm": key, "pageNum": page, "pageSize": size, "rtnType": "json"})
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL + "?" + q, headers={"User-Agent": "Mozilla/5.0 personalsubsidy"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            if e.code in (401, 403) or attempt == 3:
                sys.exit(f"HTTP {e.code}: {body}")
        except Exception as e:
            if attempt == 3:
                sys.exit(f"요청 실패: {e}")
        time.sleep(5)


from fetch_api import DG_SGG, GB_SGG, OTHER


def region_by_org(org):
    """주관·운영기관 이름으로 지역 판단. 모르면 None."""
    org = org or ""
    if org.startswith("대구"):
        return "대구", next((v for k, v in DG_SGG.items() if k in org), "")
    if org.startswith("경상북도") or org.startswith("경북"):
        return "경북", next((v for k, v in GB_SGG.items() if k in org), "")
    for k, v in DG_SGG.items():
        if k in org:
            return "대구", v
    for k, v in GB_SGG.items():
        if k in org:
            return "경북", v
    if any(x in org for x in OTHER):
        return "다른지역", ""
    return None


def region(zips, orgs=()):
    for org in orgs:
        r = region_by_org(org)
        if r == ("다른지역", ""):
            return None, None
        if r:
            return r
    codes = [z.strip() for z in str(zips or "").split(",") if z.strip()]
    sido = {c[:2] for c in codes}
    if not codes or len(sido) >= 10:
        return "전국", ""
    if sido == {"27"}:
        names = {SGG.get(c, "") for c in codes}
        return "대구", (names.pop() if len(names) == 1 else "")
    if sido == {"47"}:
        names = {SGG.get(c, "") for c in codes}
        return "경북", (names.pop() if len(names) == 1 else "")
    if "27" in sido:
        return "대구", ""
    if "47" in sido:
        return "경북", ""
    return None, None


def main():
    key = os.environ.get("YOUTH_KEY", "").strip()
    if not key:
        sys.exit("YOUTH_KEY가 없습니다.")
    rows, page, size = [], 1, 100
    while True:
        j = get(key, page, size)
        code = str(j.get("resultCode", ""))
        if code and code != "200":
            sys.exit(f"API 오류 {code}: {j.get('resultMessage')}")
        res = j.get("result") or {}
        batch = res.get("youthPolicyList") or []
        pg = res.get("pagging") or {}
        total = int(pg.get("totCount") or pg.get("totalCount") or 0)
        if page == 1:
            print("응답 필드:", sorted(batch[0].keys()) if batch else "(없음)", flush=True)
        rows += batch
        print(f"온통청년: {len(rows)}/{total}", flush=True)
        if not batch or (total and len(rows) >= total):
            break
        page += 1
        time.sleep(0.4)

    items = []
    for p in rows:
        reg, sgg = region(p.get("zipCd"), (p.get("sprvsnInstCdNm"), p.get("operInstCdNm")))
        if not reg or p.get("lclsfNm") == "참여권리":
            continue
        it = {k: clip(p.get(k), 800) for k in KEEP if p.get(k) not in (None, "")}
        it["reg"], it["sgg"] = reg, sgg
        items.append(it)
    if not items:
        sys.exit("저장할 정책이 없습니다. 응답 형식을 확인하세요.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "count": len(items), "items": items},
                  f, ensure_ascii=False, separators=(",", ":"))
    by = {}
    for it in items:
        by[it["reg"]] = by.get(it["reg"], 0) + 1
    print(f"저장 완료: {len(items)}건 {by} (전체 {len(rows)}건 중)")


if __name__ == "__main__":
    main()
