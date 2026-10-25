"""공고문 파일(HWP, HWPX, PDF)에서 글자만 뽑는다.

- HWPX: 압축 파일 안의 Contents/section*.xml 글자
- HWP(5.0): olefile로 BodyText 구역을 열고 문단 글자 기록(태그 67)만 읽음
- PDF: pypdf (스캔본처럼 글자가 없는 PDF는 빈 문자열)
읽지 못하면 빈 문자열을 돌려준다. 어떤 파일 하나 때문에 전체가 멈추지 않게 한다.
"""
import io
import re
import struct
import zipfile
import zlib

MAX_CHARS = 60000  # 공고문 앞부분이면 충분 (서식·별첨은 뒤에 붙는 경우가 많음)


def _hwpx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = sorted((n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)),
                       key=lambda n: int(re.findall(r"\d+", n)[-1]))
        out = []
        for n in names:
            xml = z.read(n).decode("utf-8", "ignore")
            xml = re.sub(r"</hp:p>|<hp:lineBreak[^>]*/>|</hp:tc>", "\n", xml)
            xml = re.sub(r"<[^>]+>", "", xml)
            out.append(xml)
            if sum(map(len, out)) > MAX_CHARS:
                break
    import html
    return html.unescape("\n".join(out))


# 8칸(16바이트)을 차지하는 확장·인라인 제어 문자
_HWP_WIDE = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}


def _hwp_para(buf):
    out, i, n = [], 0, len(buf) // 2
    units = struct.unpack(f"<{n}H", buf[:n * 2])
    while i < n:
        c = units[i]
        if c in _HWP_WIDE:
            i += 8
            continue
        if c in (10, 13):
            out.append("\n")
        elif c == 9:
            out.append(" ")
        elif c >= 32 and not 0xD800 <= c <= 0xDFFF:  # 짝 없는 서로게이트는 저장할 때 오류를 내므로 뺌
            out.append(chr(c))
        i += 1
    return "".join(out)


def _hwp(data):
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        header = ole.openstream("FileHeader").read()
        flags = struct.unpack("<I", header[36:40])[0]
        compressed, encrypted = flags & 1, flags & 2
        if encrypted:
            return ""
        sections = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
                          key=lambda e: int(re.findall(r"\d+", e[1])[0]))
        out = []
        for sec in sections:
            raw = ole.openstream(sec).read()
            if compressed:
                raw = zlib.decompress(raw, -15)
            p = 0
            while p + 4 <= len(raw):
                h = struct.unpack("<I", raw[p:p + 4])[0]
                p += 4
                tag, size = h & 0x3FF, (h >> 20) & 0xFFF
                if size == 0xFFF:
                    size = struct.unpack("<I", raw[p:p + 4])[0]
                    p += 4
                if tag == 67:  # HWPTAG_PARA_TEXT
                    out.append(_hwp_para(raw[p:p + size]))
                p += size
            if sum(map(len, out)) > MAX_CHARS:
                break
        return "\n".join(out)
    finally:
        ole.close()


def _pdf(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    out = []
    for page in r.pages[:15]:
        out.append(page.extract_text() or "")
        if sum(map(len, out)) > MAX_CHARS:
            break
    return "\n".join(out)


def text_of(data, name=""):
    """파일 내용(bytes)과 파일 이름으로 글자를 뽑는다. 이름이 없어도 내용으로 형식을 짐작한다."""
    name = (name or "").lower()
    try:
        if data[:4] == b"PK\x03\x04" or name.endswith(".hwpx"):
            t = _hwpx(data)
        elif data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or name.endswith(".hwp"):
            t = _hwp(data)
        elif data[:5] == b"%PDF-" or name.endswith(".pdf"):
            t = _pdf(data)
        else:
            return ""
    except Exception as e:  # 깨진 파일, 지원 안 하는 형식
        print(f"  읽기 실패 {name[:40]}: {type(e).__name__}: {str(e)[:80]}")
        return ""
    t = re.sub(r"[ \t 　]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t[:MAX_CHARS].strip()


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        t = text_of(open(f, "rb").read(), f)
        print(f"== {f} ({len(t)}자)\n{t[:600]}\n")
