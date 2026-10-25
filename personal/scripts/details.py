"""공고문 글에서 지원 금액·금리·지원 비율·선정 규모·지원 형태·지원 대상·제외 업종을 패턴으로 뽑는다.

AI 없이 정해진 규칙(정규식)만 쓴다. 못 찾은 칸은 비워 둔다.
개인 지원금 사이트(personalsubsidy)도 같은 파일을 복사해 쓴다.
"""
import re

UNIT = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "십만": 10**5, "만": 10**4, "천": 10**3}
NUM = r"\d[\d,]*(?:\.\d+)?"
# '1억 5천만원', '2,000만 원', '500만원', '3,000,000원', '7천만원' 같은 금액
AMT_RE = re.compile(
    rf"((?:{NUM}\s*(?:조|억|천만|백만|십만|만|천)\s*)+(?:{NUM}\s*)?원|{NUM}\s*원)(?!\s*당)")


def to_won(s):
    s = s.replace(" ", "").rstrip("원")
    total, rest = 0, s
    for num, unit in re.findall(rf"({NUM})(조|억|천만|백만|십만|만|천)", s):
        total += float(num.replace(",", "")) * UNIT[unit]
    tail = re.sub(rf"{NUM}(조|억|천만|백만|십만|만|천)", "", rest)
    if re.fullmatch(NUM, tail or ""):
        total += float(tail.replace(",", ""))
    return int(total)


def won_text(w):
    if w >= 10**8:
        eok, man = divmod(w, 10**8)
        return f"{eok:,}억" + (f" {man // 10**4:,}만원" if man >= 10**4 else "원")
    if w >= 10**4:
        return f"{w // 10**4:,}만원"
    return f"{w:,}원"


SUPPORT = re.compile(r"최대|한도|이내|까지|지원|단가|장학금|적립|위로금|축하금|양육|업체당|개사당|개소당|점포당|1인당|가구당|1개사|보조|지급|융자|보증|대출|수당|급여|장려금|바우처|감면|환급")
CRITERIA = re.compile(r"매출|자산|부채|소득|과세표준|재산|보증금|시가|공시가|건강보험료|월급|임금|연봉|주택|가격|매매|분양가|전세금|평가액|보험가입금액|총급여|종합소득|원금|납입|저축액|합산액|수출액|수출실적|투자유치|투자\s*금액|거래금액|누적")
BUDGET = re.compile(r"(^|[\s(,:])총\s*$|예산|사업비|규모|총\s*사업비|총\s*예산|사업\s*예산|예산\s*규모|총\s*\d|총액|기금\s*규모|사업\s*규모|재원")
LOAN = re.compile(r"융자|대출|대부|보증|이차보전|이자\s*지원|대환|특례보증|자금")
FORMS = [
    ("대출·보증", re.compile(r"융자|대출|특례보증|신용보증|보증서|대환|이차보전|이자\s*(지원|보전)")),
    ("현금", re.compile(r"지원금|보조금|장려금|수당|급여|현금|지급|환급")),
    ("바우처·감면", re.compile(r"바우처|이용권|감면|할인|쿠폰|포인트|카드\s*지원")),
    ("컨설팅·교육", re.compile(r"컨설팅|교육|멘토링|상담|코칭|진단")),
    ("판로·홍보", re.compile(r"판로|입점|기획전|홍보|마케팅|박람회|라이브커머스")),
    ("시설·장비", re.compile(r"시설\s*개선|인테리어|간판|장비|설치|환경\s*개선|리모델링")),
]
EXCL_WORDS = ["약국", "보건업", "의료업", "병원", "의원", "유흥", "사행", "도박", "부동산", "금융", "보험",
              "법무", "세무", "회계", "변호사", "담배", "주점", "숙박", "음식점", "도매", "소매", "제조"]


def _clean(s, n):
    s = re.sub(r"\s+", " ", s).strip(" -·•○◦□■▶☞※:")
    return s if len(s) <= n else s[:n].rstrip() + "…"


def amounts(text, loose=False, cap=5 * 10**10):
    """지원 금액 후보들: (1년 기준 원, 근거 문장, 대출 여부, 적힌 금액, '월'이면 매월 지급)"""
    out = []
    for m in AMT_RE.finditer(text):
        w = to_won(m.group(1))
        if w < 10**4 or w > 5 * 10**10:  # 1만원 미만, 500억 초과는 지원 단가가 아님
            continue
        before = text[max(0, m.start() - 45):m.start()]
        after = text[m.end():m.end() + 12]
        near_b = before[-22:]
        if CRITERIA.search(near_b) or re.match(r"\s*(이하|미만|이상|초과)", after) and (
                CRITERIA.search(before) or not re.search(r"최대|한도|지원|이내", near_b)):
            continue  # 매출 30억 이하, 재산 3억 이하, 투자유치 30억 초과 같은 자격 기준
        if BUDGET.search(near_b) and not re.search(r"업체당|개사당|1인당|가구당|당\s*최대|개소당", before[-15:] + after[:3]):
            continue  # 총 사업비, 예산
        if not loose and not SUPPORT.search(before + after):
            continue
        line_s = text.rfind("\n", 0, m.start()) + 1
        line_e = text.find("\n", m.end())
        line = text[line_s:line_e if line_e > 0 else m.end() + 60]
        near = text[max(line_s, m.start() - 30):m.end() + 25]  # 같은 줄 안에서만 대출 여부 판단
        per = "월" if re.search(r"(?<!개)(매월|월)\s*(최대|최고)?\s*$", before[-8:]) else ""  # "12개월 최대"는 월 지급 아님
        if not per and re.search(r"매달|매월|월마다", before[-40:]) and not re.search(r"\d\s*개월", before[-15:]):
            per = "월"
        if not per and re.search(r"(1일|일당|하루)\s*(최대)?\s*$", before[-8:]):
            per = "1일"
        strong = bool(re.search(r"최대|한도|이내|업체당|기업당|개사당|업소당|점포당|1인당|인당|가구당|호당|과제당|까지|최고", before[-20:] + after[:8]))
        if loose and not strong:  # '지원내용' 칸: 월 지급이거나 바로 옆에 지급·지원 같은 말이 있으면 확실한 금액
            strong = bool(per) or bool(re.search(r"지원|지급|보조|적립|수당|장학금", before[-12:] + after[:10]))
        yearly = w * 12 if per == "월" else w
        out.append((yearly, _clean(line, 90), bool(LOAN.search(near) or LOAN.search(line[:50])), w, per, strong))
    return out


def extract(text, main="", cash_cap=None, title="", loan_cap=None):
    """공고문 글 → 세부 정보 dict (못 찾은 칸은 넣지 않음).
    main: '지원내용'처럼 금액이 나오면 곧 지원 금액인 글 (지원·최대 같은 말이 없어도 금액으로 봄)"""
    text = ((main + "\n") if main else "") + (text or "")
    d = {}
    am = (amounts(main, loose=True) if main else []) + amounts(text[len(main):] if main else text)
    if title and re.search(r"융자|육성자금|경영안정자금|특례보증|정책자금|대출|보증", title) and not re.search(r"보조|지원금|무상|바우처", title):
        am = [(a[0], a[1], a[2] or not re.search(r"보조금|지원금|무상|현금", a[1]), a[3], a[4], a[5]) for a in am]  # 대출 공고의 금액은 대출 한도로 봄
    cash = [a for a in am if not a[2] and (not cash_cap or a[3] <= cash_cap)]
    loan = [a for a in am if a[2] and (not loan_cap or a[3] <= loan_cap)]
    # '최대·한도·업체당' 같은 말이 붙은 금액이 있으면 그것만 봄 (표 속 총액·예산 배분을 피함)
    cash = [a for a in cash if a[5]] or cash
    loan = [a for a in loan if a[5]] or loan
    if cash:
        w, why, _, raw, per, _s = max(cash)
        d["amt"], d["amtText"], d["amtWhy"] = w, (f"{per} {won_text(raw)}" if per else won_text(raw)), why
        d["amtSure"] = bool(_s)  # '업체당·1인당·최대·한도'가 붙은 금액이면 화면에 숫자로 보여줌
    if loan:
        w, why, _, raw, per, _s = max(loan)
        d["loan"], d["loanText"], d["loanWhy"] = raw, won_text(raw), why
        d["loanSure"] = bool(_s)

    rates = []
    for m in re.finditer(r"(연\s*)?(\d{1,2}(?:\.\d{1,2})?)\s*%\s*(p|포인트)?", text):
        ctx = text[max(0, m.start() - 25):m.end() + 8]
        if re.search(r"금리|이자|이차보전|보전|이율|대출", ctx) and not re.search(r"우대|가산|인하|감면", ctx[:30]):
            rates.append((float(m.group(2)), bool(re.search(r"이차\s*보전|이자\s*(지원|보전|감면)|보전", ctx)), _clean(ctx, 60)))
    if rates:
        sub = [r for r in rates if r[1]]
        fix = [r for r in rates if not r[1]]
        if sub:
            r = max(sub)
            d["rateSub"], d["rateWhy"] = r[0], r[2]   # 이차보전·이자 지원 %p
        elif fix:
            r = min(fix)
            d["rate"], d["rateWhy"] = r[0], r[2]      # 대출 금리

    m = re.search(r"(\d{2,3})\s*%\s*(이내|까지)?\s*(지원|보조|국비)|자부담\s*(\d{1,2})\s*%", text)
    if m:
        d["ratio"] = int(m.group(1)) if m.group(1) else 100 - int(m.group(4))
        if not 10 <= d["ratio"] <= 100:
            d.pop("ratio")

    m = re.search(r"(\d[\d,]*)\s*(개사|개소|개\s?업체|개\s?점포|명|곳|가구|팀)\s*(내외|이내|정도)?\s*(선정|모집|지원)", text)
    if m:
        n = int(m.group(1).replace(",", ""))
        if 0 < n < 1000000:
            d["count"], d["countText"] = n, f"{n:,}{m.group(2).replace(' ', '')}"

    forms = [name for name, rx in FORMS if len(rx.findall(text)) >= 1]
    if forms:
        score = {name: len(rx.findall(text)) for name, rx in FORMS}
        d["forms"] = sorted(forms, key=lambda f: -score[f])[:3]

    m = re.search(r"(지원\s*대상|신청\s*대상|신청\s*자격|참여\s*대상|모집\s*대상|지원\s*자격|사업\s*대상)\s*[:：]?[ \t]*([^\n]*)\n?([^\n]*)", text)
    if m:
        t = m.group(2).strip()
        if len(t) < 8:
            t = (t + " " + m.group(3)).strip()
        t = re.split(r"\s\d\.\s|\s[가-하]\.\s|\s[②③④⑤]", t)[0]
        if len(t) >= 6:
            d["target"] = _clean(t, 140)

    m = re.search(r"(기준\s*)?중위소득\s*(\d{2,3})\s*%\s*(이하|미만|이내)", text)
    if m:
        d["inc"] = int(m.group(2))
    m = re.search(r"만\s*(\d{1,2})\s*세\s*(?:이상|부터)?\s*[~∼\-–]\s*(?:만\s*)?(\d{1,2})\s*세", text)
    if m and int(m.group(1)) < int(m.group(2)):
        d["age"] = [int(m.group(1)), int(m.group(2))]

    excl = set()
    for m in re.finditer(r"제외|불가|지원\s*불가|신청\s*불가|해당\s*없음", text):
        ctx = text[max(0, m.start() - 160):m.end() + 160]
        if re.search(r"업종|업체|사업자|사업장", ctx):
            excl.update(w for w in EXCL_WORDS if w in ctx)
    if re.search(r"47811", text):
        excl.add("약국")
    if excl:
        d["excl"] = sorted(excl)
    d["hasExclList"] = bool(re.search(r"(지원|신청)?\s*제외\s*(업종|대상)", text))
    return d


if __name__ == "__main__":
    import json, sys
    print(json.dumps(extract(open(sys.argv[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))
