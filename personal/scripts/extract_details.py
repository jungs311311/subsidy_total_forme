"""받아 온 지원금 데이터의 글(지원내용·대상·선정기준)에서 금액·소득 기준·나이를 뽑아 data/details.json 에 저장한다.

- 보조금24(benefits.json): 지원내용(content)·지원대상(target)·선정기준(criteria) 글을 바로 분석
- 온통청년(youth.json): 지원내용(plcySprtCn)·설명 글을 분석
- 복지로 중앙·지자체(bokjiro.json, local.json): 목록에는 한 줄 소개뿐이라, 상세 API로
  지원대상·선정기준·지원내용 글을 받아 분석 (이미 받은 건 다시 받지 않음)
AI 없이 패턴(정규식)만 쓴다. 매일 GitHub 자동 실행에서 데이터 받기 다음에 돈다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import details  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "details.json")
KST = timezone(timedelta(hours=9))
VERSION = 1
MAX_DETAIL_CALLS = 900  # 공공데이터포털 개발계정 하루 1,000건 제한 안쪽으로
DETAIL = {
    "b": ("https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfaredetailedV001",
          {"callTp": "D"}, {"target": "tgtrDtlCn", "criteria": "slctCritCn", "content": "alwServCn"}),
    "l": ("https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfaredetailed",
          {}, {"target": "sprtTrgtCn", "criteria": "slctCritCn", "content": "alwServCn"}),
}


def load(name):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except Exception:
        return []


def squash(s, n=500):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def keep(d):
    """사이트에 필요한 칸만 남겨 파일 크기를 줄임"""
    k = ("amt", "amtText", "amtWhy", "amtSure", "loan", "loanText", "loanSure", "rate", "rateSub", "inc", "age", "forms", "count", "countText")
    return {x: d[x] for x in k if x in d}


LOG = {"calls": 0, "ok": {"b": 0, "l": 0}, "empty": {"b": 0, "l": 0}, "errors": []}


def note(msg):
    print(msg)
    if len(LOG["errors"]) < 8:
        LOG["errors"].append(msg[:200])


def get_detail(kind, key, sid):
    url, extra, fields = DETAIL[kind]
    q = urllib.parse.urlencode({"serviceKey": key, "servId": sid, **extra})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url + "?" + q, timeout=60) as r:
                root = ET.fromstring(r.read())
            code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or ""
            if code and code not in ("0", "00"):
                note(f"{kind} 상세 API 오류 {sid}: {code} {root.findtext('.//resultMessage') or root.findtext('.//returnAuthMsg')}")
                return None if code in ("22", "30", "31", "32") else {}
            got = {k: squash(root.findtext(f".//{tag}") or "", 900) for k, tag in fields.items()}
            if not any(got.values()):
                LOG["empty"][kind] += 1
                if LOG["empty"][kind] <= 2:
                    note(f"{kind} 상세 응답에 내용 없음 {sid}: {ET.tostring(root, encoding='unicode')[:150]}")
            else:
                LOG["ok"][kind] += 1
            return got
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(15)  # 초당 호출 제한: 잠깐 쉬고 다시
                continue
            if e.code in (401, 403, 429):
                note(f"{kind} 상세 API 거절 HTTP {e.code} {sid} — 오늘은 여기까지")
                return None
        except Exception as e:
            if attempt == 2:
                note(f"{kind} 상세 받기 실패 {sid}: {type(e).__name__}: {str(e)[:80]}")
                return {}
        time.sleep(3)
    return {}


def main():
    old = {}
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f).get("items", {})
    except Exception:
        pass
    out = {}

    for it in load("benefits.json"):
        text = "\n".join([it.get("target", ""), it.get("criteria", ""), it.get("summary", "")])
        d = keep(details.extract(text, main=it.get("content", ""), cash_cap=10**8, loan_cap=10**9))
        if d:
            out["g:" + str(it.get("id"))] = d

    for it in load("youth.json"):
        text = "\n".join(str(it.get(k) or "") for k in ("plcyExplnCn", "addAplyQlfcCndCn", "earnEtcCn"))
        d = keep(details.extract(text, main=str(it.get("plcySprtCn") or ""), cash_cap=10**8, loan_cap=10**9))
        if d:
            out["y:" + str(it.get("plcyNo"))] = d

    key = os.environ.get("BOKJIRO_KEY", "").strip()
    if "%" in key:
        key = urllib.parse.unquote(key)
    calls, stopped = 0, set()
    for kind, fname in (("b", "bokjiro.json"), ("l", "local.json")):
        for it in load(fname):
            sid = str(it.get("servId") or "")
            if not sid:
                continue
            k = f"{kind}:{sid}"
            prev = old.get(k)
            if prev and prev.get("v") == VERSION and prev.get("mod") == it.get("lastModYmd", ""):
                if prev.get("content") or prev.get("target"):  # 저장해 둔 상세 글로 새 규칙을 다시 적용
                    d = keep(details.extract("\n".join([prev.get("target", ""), prev.get("criteria", "")]),
                                             main=prev.get("content", ""), cash_cap=10**8, loan_cap=10**9))
                    d.update({x: prev[x] for x in ("v", "mod", "target", "criteria", "content") if x in prev})
                    out[k] = d
                else:
                    out[k] = prev
                continue
            txt = None
            if key and kind not in stopped and calls < MAX_DETAIL_CALLS:
                txt = get_detail(kind, key, sid)
                calls += 1
                if txt is None:
                    stopped.add(kind)
                time.sleep(0.3)
            if not txt:
                if prev:
                    out[k] = prev  # 못 받으면 예전 것 유지
                else:
                    d = keep(details.extract(it.get("servDgst", ""), cash_cap=10**8, loan_cap=10**9))
                    if d:
                        out[k] = d
                continue
            d = keep(details.extract("\n".join([txt.get("target", ""), txt.get("criteria", "")]), main=txt.get("content", ""), cash_cap=10**8, loan_cap=10**9))
            d.update(v=VERSION, mod=it.get("lastModYmd", ""),
                     target=squash(txt.get("target"), 400), criteria=squash(txt.get("criteria"), 400),
                     content=squash(txt.get("content"), 400))
            out[k] = {x: y for x, y in d.items() if y not in ("", None)}

    found = sum(1 for d in out.values() if "amt" in d or "loan" in d)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "count": len(out), "withAmount": found,
                   "log": {**LOG, "calls": calls}, "items": out}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"세부 정보 {len(out)}건 저장 (금액 찾음 {found}건, 복지로 상세 API {calls}번 호출)")


if __name__ == "__main__":
    main()
