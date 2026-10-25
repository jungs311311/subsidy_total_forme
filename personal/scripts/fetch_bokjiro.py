"""복지로(한국사회보장정보원) 중앙부처 복지서비스 목록을 받아 data/bokjiro.json 으로 저장합니다.

생애주기(lifeArray)·대상특성(trgterIndvdlArray)·관심주제(intrsThemaArray)가 함께 오므로
페이지에서 나이·가구 상황으로 판정할 수 있습니다.

인증키: 환경변수 BOKJIRO_KEY (공공데이터포털 일반 인증키, 보통 보조금24와 같은 키)
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

URL = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "bokjiro.json")
KST = timezone(timedelta(hours=9))
FIELDS = ["servId", "servNm", "jurMnofNm", "jurOrgNm", "servDgst", "servDtlLink", "lifeArray",
          "intrsThemaArray", "trgterIndvdlArray", "sprtCycNm", "srvPvsnNm", "rprsCtadr", "onapPsbltYn", "inqNum"]


def get(key, page, rows):
    q = urllib.parse.urlencode({"serviceKey": key, "callTp": "L", "pageNo": page, "numOfRows": rows, "srchKeyCode": "003"})
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
                sys.exit(str(e))
        time.sleep(5)


def text(el, tag):
    x = el.find(tag)
    return " ".join((x.text or "").split()) if x is not None and x.text else ""


def main():
    key = os.environ.get("BOKJIRO_KEY", "").strip()
    if not key:
        sys.exit("BOKJIRO_KEY가 없습니다.")
    if "%" in key:
        key = urllib.parse.unquote(key)

    items, page, rows = [], 1, 500
    while True:
        root = ET.fromstring(get(key, page, rows))
        code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or ""
        msg = root.findtext(".//resultMessage") or root.findtext(".//returnAuthMsg") or ""
        if code and code not in ("0", "00"):
            sys.exit(f"API 오류 {code}: {msg}")
        total = int(root.findtext(".//totalCount") or 0)
        batch = root.findall(".//servList")
        for s in batch:
            items.append({f: text(s, f) for f in FIELDS})
        print(f"복지로 목록: {len(items)}/{total}", flush=True)
        if not batch or len(items) >= total:
            break
        page += 1
        time.sleep(0.5)

    if not items:
        sys.exit("받은 데이터가 없습니다. 응답 형식을 확인하세요.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "count": len(items), "items": items},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"저장 완료: {len(items)}건")


if __name__ == "__main__":
    main()
