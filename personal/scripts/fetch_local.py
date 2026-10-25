"""복지로(한국사회보장정보원) 지자체 복지서비스 중 대구·경북 사업만 받아 data/local.json 으로 저장합니다.

인증키: 환경변수 BOKJIRO_KEY (공공데이터포털 일반 인증키)
응답 필드 이름이 버전마다 조금 달라(lifeArray / lifeNmArray 등) 둘 다 받아 둡니다.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

URL = "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "local.json")
KST = timezone(timedelta(hours=9))
SIDO = ["대구광역시", "경상북도"]


def get(key, page, rows, sido=None):
    params = {"serviceKey": key, "pageNo": page, "numOfRows": rows}
    if sido:
        params["ctpvNm"] = sido
    q = urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(URL + "?" + q, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            if e.code in (401, 403) or attempt == 3:
                sys.exit(f"HTTP {e.code}: {body}")
        except Exception as e:
            if attempt == 3:
                sys.exit(f"요청 실패: {e}")
        time.sleep(5)


def rows_of(raw):
    root = ET.fromstring(raw)
    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or ""
    if code and code not in ("0", "00"):
        sys.exit(f"API 오류 {code}: {root.findtext('.//resultMessage') or root.findtext('.//returnAuthMsg')}")
    total = int(root.findtext(".//totalCount") or 0)
    out = []
    for s in root.findall(".//servList"):
        out.append({c.tag: " ".join((c.text or "").split()) for c in s})
    return total, out


def fetch(key, sido=None):
    items, page, rows = [], 1, 500
    while True:
        total, batch = rows_of(get(key, page, rows, sido))
        items += batch
        print(f"지자체복지 {sido or '전체'}: {len(items)}/{total}", flush=True)
        if not batch or len(items) >= total:
            return items
        page += 1
        time.sleep(0.5)


def main():
    key = os.environ.get("BOKJIRO_KEY", "").strip()
    if not key:
        sys.exit("BOKJIRO_KEY가 없습니다.")
    if "%" in key:
        key = urllib.parse.unquote(key)

    got = []
    for sido in SIDO:
        got += fetch(key, sido)
    # 시도 조건이 적용되지 않은 경우를 대비해 한 번 더 걸러냄
    keep = [x for x in got if any((x.get("ctpvNm") or "").startswith(s[:2]) for s in SIDO)]
    if not keep and got:
        print("시도 필드를 찾지 못해 전체를 저장합니다. 필드:", sorted(got[0].keys()))
        keep = got
    seen, items = set(), []
    for x in keep:
        sid = x.get("servId") or x.get("servNm")
        if sid in seen:
            continue
        seen.add(sid)
        items.append(x)
    if not items:
        sys.exit("저장할 사업이 없습니다.")
    print("응답 필드:", sorted(items[0].keys()))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "count": len(items), "items": items},
                  f, ensure_ascii=False, separators=(",", ":"))
    by = {}
    for x in items:
        k = (x.get("ctpvNm") or "?")[:2]
        by[k] = by.get(k, 0) + 1
    print(f"저장 완료: {len(items)}건 {by}")


if __name__ == "__main__":
    main()
