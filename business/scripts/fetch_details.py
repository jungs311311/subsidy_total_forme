"""새 공고의 공고문(HWP·HWPX·PDF)을 내려받아 금액·금리·대상·제외 업종을 뽑아 data/details.json 에 쌓는다.

fetch_bizinfo.py 가 공고 목록을 받은 직후 부른다. 이미 읽은 공고(같은 공고문 주소)는 다시 받지 않는다.
공고문이 없거나 못 읽으면 API 소개글(bsnsSumryCn)로만 뽑는다.
"""
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
import time
import urllib.request
from pathlib import Path

import doc_text
import details

OUT = Path(__file__).resolve().parent.parent / "data" / "details.json"
KST = dt.timezone(dt.timedelta(hours=9))
MAX_NEW = 1500        # 한 번에 새로 받을 공고문 수 (나머지는 다음 날)
WORKERS = 6
VERSION = 6           # 뽑는 규칙을 크게 바꾸면 올려서 전부 다시 읽게 함


def pick_file(it):
    """공고문 파일 하나 고르기: 본문 출력 파일(printFlpthNm)이 있으면 그것, 없으면 첨부 중 '공고'가 들어간 것."""
    url, name = (it.get("printFlpthNm") or "").strip(), (it.get("printFileNm") or "").strip()
    if url.startswith("http"):
        return url.split("@")[0], name.split("@")[0]
    urls = [u for u in (it.get("flpthNm") or "").split("@") if u.startswith("http")]
    names = (it.get("fileNm") or "").split("@")
    pairs = list(zip(urls, names + [""] * len(urls)))
    pairs.sort(key=lambda p: (not re.search(r"공고", p[1]), bool(re.search(r"서식|양식|신청서|별첨|FAQ", p[1]))))
    return pairs[0] if pairs else ("", "")


def download(url, tries=2):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (bizzsubsidy)"})
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read(15 * 1024 * 1024)
        except Exception as e:
            if n == tries - 1:
                print(f"  받기 실패 {url[-40:]}: {type(e).__name__}")
            time.sleep(2)
    return b""


def summary_text(it):
    s = html.unescape(str(it.get("bsnsSumryCn") or ""))
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s)
    return re.sub(r"<[^>]+>", " ", s)


def one(it):
    try:
        return _one(it)
    except Exception as e:  # 공고 하나가 이상해도 나머지는 계속
        print(f"  분석 실패 {it.get('pblancId')}: {type(e).__name__}: {str(e)[:80]}")
        d = details.extract(summary_text(it), title=str(it.get("pblancNm") or ""), cash_cap=10**9, loan_cap=5 * 10**9)
        d.update(src="소개글", f="", v=0)
        return str(it.get("pblancId")), d


def _one(it):
    url, name = pick_file(it)
    doc = ""
    if url:
        data = download(url)
        if data:
            doc = doc_text.text_of(data, name)
    text = (summary_text(it) + "\n" + doc).strip()
    d = details.extract(text, title=str(it.get("pblancNm") or ""), cash_cap=10**9, loan_cap=5 * 10**9)
    d["src"] = "공고문" if len(doc) > 200 else "소개글"
    d["f"] = url
    d["v"] = VERSION
    return str(it.get("pblancId")), d


def run(raw_items, keep_ids):
    """raw_items: API 원본 목록, keep_ids: 사이트에 보여줄 공고 id 집합"""
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("items", {})
        except Exception:
            old = {}
    result, todo = {}, []
    for it in raw_items:
        pid = str(it.get("pblancId") or "")
        if pid not in keep_ids:
            continue
        url, _ = pick_file(it)
        prev = old.get(pid)
        if prev and prev.get("f") == url and prev.get("v") == VERSION:
            result[pid] = prev
        else:
            todo.append(it)
    print(f"공고문 분석: 이미 읽은 {len(result)}건, 새로 읽을 {len(todo)}건 (이번에 최대 {MAX_NEW}건)")
    t0 = time.time()
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for n, (pid, d) in enumerate(ex.map(one, todo[:MAX_NEW]), 1):
            result[pid] = d
            if n % 100 == 0:
                print(f"  {n}건 읽음 ({time.time() - t0:.0f}초)", flush=True)
    for it in todo[MAX_NEW:]:  # 못 읽은 건 소개글로라도
        pid = str(it.get("pblancId"))
        d = details.extract(summary_text(it), title=str(it.get("pblancNm") or ""), cash_cap=10**9, loan_cap=5 * 10**9)
        d.update(src="소개글", f="", v=0)
        result[pid] = d
    by_src = {}
    for d in result.values():
        by_src[d["src"]] = by_src.get(d["src"], 0) + 1
    found = sum(1 for d in result.values() if "amt" in d or "loan" in d)
    print(f"공고문 분석 끝: {len(result)}건 {by_src}, 금액 찾음 {found}건, {time.time() - t0:.0f}초")
    body = json.dumps({
        "updatedAt": dt.datetime.now(KST).isoformat(timespec="minutes"),
        "count": len(result), "withAmount": found,
        "items": result,
    }, ensure_ascii=False, separators=(",", ":"))
    tmp = OUT.with_suffix(".tmp")
    tmp.write_bytes(body.encode("utf-8", "replace"))  # 깨진 글자가 있어도 파일이 비지 않게
    tmp.replace(OUT)
