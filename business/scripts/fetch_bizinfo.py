"""기업마당 지원사업 공고를 받아 소상공인·개인사업자용으로 걸러 data/notices.json 에 저장한다.

실행: BIZINFO_KEY=인증키 python scripts/fetch_bizinfo.py
테스트: python scripts/fetch_bizinfo.py --from-file 응답.json
외부 패키지 없이 파이썬 기본 기능만 쓴다.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
OUT = Path(__file__).resolve().parent.parent / "data" / "notices.json"
KST = dt.timezone(dt.timedelta(hours=9))

REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
           "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
# 공고명·대상·해시태그에 이 말이 있으면 개인사업자·소상공인도 볼 만한 공고로 본다
KEEP = ("소상공인", "자영업", "개인사업자", "전통시장", "상인", "상점가", "골목",
        "중소기업", "소기업", "예비창업", "창업기업", "1인", "프랜차이즈", "가맹")
# 이것만 대상이면 뺀다
ONLY_BIG = ("중견기업", "대기업")


def call_api(key, tries=3):
    """기업마당 서버가 느리거나 끊기면 30초 쉬고 다시 시도한다."""
    query = urllib.parse.urlencode({"crtfcKey": key, "dataType": "json", "searchCnt": "0"})
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": "Mozilla/5.0 (bizzsubsidy)"})
    for n in range(1, tries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as e:  # 시간 초과, 접속 끊김, 깨진 응답
            print(f"{n}번째 시도 실패: {type(e).__name__}: {e}")
            if n == tries:
                raise
            time.sleep(30)


def items_of(data):
    arr = data.get("jsonArray", data) if isinstance(data, dict) else data
    if isinstance(arr, dict):
        arr = arr.get("item", [])
    if isinstance(arr, dict):
        arr = [arr]
    return arr if isinstance(arr, list) else []


def clean(text, limit=None):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def dates_in(text):
    found = []
    for y, m, d in re.findall(r"(20\d{2})[.\-/ ]?(\d{1,2})[.\-/ ]?(\d{1,2})", text or ""):
        try:
            found.append(dt.date(int(y), int(m), int(d)))
        except ValueError:
            pass
    return found


ORG_REGION = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}


def hashtags_of(item):
    raw = item.get("hashTags") or item.get("hashtags") or ""
    if isinstance(raw, list):
        raw = ",".join(map(str, raw))
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def regions_of(item, tags):
    """지역 공고면 그 시·도, 전국 공고면 빈 목록."""
    found = set()
    title = str(item.get("pblancNm") or item.get("title") or "")
    for bracket in re.findall(r"\[([^\]]+)\]", title[:20]):  # [경북], [충남] 같은 머리말
        found.update(r for r in REGIONS if r in bracket)
    org = str(item.get("jrsdInsttNm") or item.get("author") or "")
    found.update(v for k, v in ORG_REGION.items() if k in org)  # 소관기관이 시·도
    tag_regions = {r for r in REGIONS if any(r in t for t in tags)}
    if len(tag_regions) < 10:  # 17개 시·도가 다 붙은 태그는 지역 정보로 보지 않음
        found.update(tag_regions)
    return [r for r in REGIONS if r in found]


def convert(item, today):
    title = clean(item.get("pblancNm") or item.get("title"))
    target = clean(item.get("trgetNm"))
    tags = hashtags_of(item)
    period = clean(item.get("reqstBeginEndDe") or item.get("reqstDt"))
    ds = dates_in(period)
    start = ds[0] if len(ds) >= 2 else None
    end = ds[-1] if ds else None

    if end and end < today:
        return None  # 이미 마감
    text = " ".join([title, target, " ".join(tags)])
    # 사이트 '새 공고' 칸에 보여줄 소상공인·개인사업자용인지 (지원 짝짓기에는 전부 씀)
    keep = any(k in text for k in KEEP) and not (
        target and any(k in target for k in ONLY_BIG) and not any(k in target for k in KEEP))

    regions = regions_of(item, tags)
    if regions and len(regions) <= 3 and not title.lstrip().startswith("["):
        title = f"[{'·'.join(regions)}] {title}"  # 지역 공고인데 제목에 [지역]이 없으면 붙임

    url = item.get("pblancUrl") or item.get("link") or ""
    if url.startswith("/"):
        url = "https://www.bizinfo.go.kr" + url
    return {
        "id": str(item.get("pblancId") or item.get("seq") or url),
        "title": title,
        "url": url,
        "applyUrl": clean(item.get("rceptEngnHmpgUrl")),
        "org": clean(item.get("jrsdInsttNm") or item.get("author")),
        "execOrg": clean(item.get("excInsttNm")),
        "target": target,
        "field": clean(item.get("pldirSportRealmLclasCodeNm") or item.get("lcategory")),
        "summary": clean(item.get("bsnsSumryCn") or item.get("description"), 220),
        "period": period,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "regions": regions,
        "tags": [t for t in tags if t not in REGIONS][:12],
        "created": clean(item.get("creatPnttm") or item.get("pubDate"))[:10],
        "forSmall": any(k in text for k in ("소상공인", "자영업", "개인사업자", "전통시장", "상인")),
        "_keep": keep,
    }


def main():
    if "--from-file" in sys.argv:
        data = json.loads(Path(sys.argv[sys.argv.index("--from-file") + 1]).read_text(encoding="utf-8"))
    else:
        key = os.environ.get("BIZINFO_KEY", "").strip()
        if not key:
            print("BIZINFO_KEY(기업마당 인증키)가 아직 등록되지 않아 건너뜁니다.")
            return 0
        data = call_api(key)

    raw = items_of(data)
    if not raw:
        print("받은 공고가 0건입니다. 인증키나 응답 형식을 확인하세요:", str(data)[:300])
        return 1

    today = dt.datetime.now(KST).date()
    seen, items, broken = set(), [], 0
    for it in raw:
        try:
            row = convert(it, today)
        except Exception as e:  # 공고 하나가 이상해도 나머지는 저장
            broken += 1
            print("건너뛴 공고:", str(it.get("pblancId") if isinstance(it, dict) else it)[:60], e)
            continue
        if row and row["id"] not in seen:
            seen.add(row["id"])
            items.append(row)
    # 38개 지원 접수 상태 계산 + 새 공고·새 사업 알림 (전체 접수 중 공고로)
    import watch_programs
    watch_programs.run(items, today)
    # 사이트 '새 공고' 칸에는 소상공인·개인사업자용만, 마감이 가까운 순, 상시 접수는 뒤로
    items = [{k: v for k, v in r.items() if k != "_keep"} for r in items if r["_keep"]]
    items.sort(key=lambda x: (x["end"] or "9999-12-31", x["title"]))
    # 공고문 내려받아 금액·금리·대상·제외 업종 뽑기 (실패해도 공고 목록 저장은 계속)
    if "--no-details" not in sys.argv:
        try:
            import fetch_details
            fetch_details.run(raw, {r["id"] for r in items})
        except Exception as e:
            print("공고문 분석 건너뜀:", type(e).__name__, e)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updatedAt": dt.datetime.now(KST).isoformat(timespec="minutes"),
        "source": "기업마당(bizinfo.go.kr) 지원사업정보 API",
        "fetched": len(raw),
        "count": len(items),
        "items": items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"받은 공고 {len(raw)}건 중 소상공인·개인사업자용 {len(items)}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
