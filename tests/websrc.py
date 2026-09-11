r"""web 원문 계약 시험의 공용 도우미 (REQ-20260830-029).

같은 검사 '방법'이 시험 파일마다 복붙돼 있었다 — `_fn`(원문에서 JS 함수
본문 떼기) 16파일, 헥스 하드코딩 금지 한 줄 18곳. 방법이 흩어지면 규칙이
진화할 때(예: 8자리 알파 헥스) 한 곳만 고쳐지고 나머지는 옛 규칙으로
남는다. 그래서 **방법만** 여기에 모은다.

규칙: 이 모듈은 방법이다 — **무엇을 검사할지(계약)는 각 시험 파일에
남는다.** 여기에 assert 대상 목록·계약 문구를 쌓지 마라.

주의: `\n\}` 로 끝을 잡으므로 **최상위(들여쓰기 0) 함수**만 뗀다. 중첩
함수·메서드를 떼는 시험(`\n  \}` 변형)은 제 정규식을 그대로 가진다 —
그 변형까지 삼키면 매칭 범위가 달라져 시험이 조용히 다른 원문을 보게 된다.
"""
import glob
import re
import shutil


def find_node():
    """실행으로 재는 web 시험이 쓸 node — 없으면 None (REQ-20260911-003).

    `shutil.which` 만으로는 못 찾는 환경이 흔하다(이 저장소의 WSL 은 node 가
    .vscode-server 아래에만 있다). 그 자리를 시험 파일마다 다시 적으면
    한 파일만 고쳐지고 나머지는 조용히 건너뛴다 — 건너뛴 시험은 통과로
    보인다. 이 모듈의 규칙 그대로 **방법만** 여기 둔다.
    """
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None

# 최상위 function <name>(...){ ... }  (async 포함) — 16개 시험 파일이 쓰던
# 바로 그 정규식. 바꾸면 16개 시험이 보는 원문 범위가 한꺼번에 바뀐다.
FN_RE = r"(?:async )?function %s\([^)]*\)\{[\s\S]*?\n\}"

# 색 하드코딩 금지 (s9-design: 색은 토큰으로) — 3~6자리 헥스.
HEX_RE = r"#[0-9a-fA-F]{3,6}\b"


def fn(tc, src, name):
    """web 원문 src 에서 최상위 JS 함수 name 의 본문을 떼어 돌려준다."""
    m = re.search(FN_RE % name, src)
    tc.assertIsNotNone(m, "%s() 를 찾지 못했다" % name)
    return m.group(0)


def no_hex(tc, css, msg="색 하드코딩 금지"):
    """CSS/JS 조각에 헥스 색이 박혀 있지 않은지 — 색은 var(--토큰)으로."""
    tc.assertNotRegex(css, HEX_RE, msg)

def _css_blank_outside_comment(text):
    """주석 **밖**의 첫 빈 줄 위치 (없으면 len(text))."""
    i, n = 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if text.startswith("\n\n", i):
            return i
        i += 1
    return n


def css_section(tc, src, head):
    r"""머리 주석 head 가 여는 CSS 구역 — 주석 **밖**의 첫 빈 줄까지.

    실사고 2026-09-01 (REQ-20260901-021): 아홉 시험 파일이 구역의 끝을
    `\n\n`(첫 빈 줄)으로 잡고 있었다. 뜻은 맞다 — 이 저장소의 CSS 는 구역
    사이를 빈 줄로 띄운다. 틀린 것은 **어디서 세느냐**다: 주석 안에서도 셌다.
    그런데 이 저장소의 주석은 길고, 문단을 빈 줄로 나눈다 — 주석 한가운데
    빈 줄이 하나 생기는 순간 **그 아래 규칙 전부가 시험 밖으로 조용히
    빠진다.** 판정 대화상자 구역이 실제로 그랬고(`.dlgatt` 아래로 통째로),
    REQ-20260901-019 에서 주석을 문단으로 나눴다가 `.dlgbox 규칙을 찾지
    못했다`로 두 건이 엉뚱하게 깨져서야 드러났다. 시끄럽게 깨진 것이
    다행이었다 — 반대쪽, 구역이 조용히 줄어 그대로 통과하는 쪽이 이 자름의
    진짜 위험이다.

    그래서 세는 자리만 고친다: **주석 안의 빈 줄은 글의 호흡이지 구역의
    경계가 아니다.** 구역을 여는 규칙(빈 줄로 띄운다)은 그대로 둔다 —
    「다음 구역 머리까지」로 넓히는 길도 있었지만, 이 저장소의 CSS 가 구역
    머리를 늘 줄표로 긋는 것은 아니어서(docs.css 의 첨부 구역) 그 자는
    남의 구역까지 삼킨다.

    head 는 머리 주석을 여는 정규식(예: r"/\* -+ 판정 대화상자")이다.
    """
    m = re.search(head + r"[\s\S]*?\*/", src)
    tc.assertIsNotNone(m, "구역 머리(%s)를 찾지 못했다" % head)
    rest = src[m.end():]
    return rest[:_css_blank_outside_comment(rest)]
