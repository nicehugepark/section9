"""화면 조각을 브라우저가 받는 **한 장**으로 이어 붙인다 (REQ-20260829-027).

`web/index.html` 은 이제 껍데기다: `<link href="css/…">` 와 `<script src="app/…">`
로 조각을 부른다. 시험이 조각을 하나씩 열면 계약이 파일 배치를 따라 흩어지고,
"이 규칙은 어느 조각에 있나"가 시험의 관심사가 된다 — 그건 화면의 계약이 아니다.
계약이 보는 것은 늘 하나였다: **브라우저가 실제로 받는 그 한 장.**

그래서 이 도우미가 그 한 장을 되돌려 준다. 조각을 옮기거나 이름을 바꿔도
시험은 바뀌지 않는다. 도우미는 하나뿐이다 — 두 벌이 되면 이어 붙이는 규칙이
갈라지고, 그때부터 시험은 서로 다른 화면을 본다.

    from webasset import index_path
    INDEX = index_path()          # open(INDEX) 이 그대로 통한다
"""
import atexit
import os
import re
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
SHELL = os.path.join(WEB, "index.html")

LINK_RE = re.compile(r'^<link rel="stylesheet" href="css/([\w.-]+)">\s*$')
SRC_RE = re.compile(r'^<script src="app/([\w.-]+)"></script>\s*$')

_cache = {}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parts():
    """(css 파일명들, app 파일명들) — index.html 이 부르는 순서 그대로."""
    css, app = [], []
    for line in _read(SHELL).splitlines(True):
        m = LINK_RE.match(line)
        if m:
            css.append(m.group(1))
            continue
        m = SRC_RE.match(line)
        if m:
            app.append(m.group(1))
    return css, app


def source():
    """조각을 제자리에 되꽂은 index.html 전문.

    `<link>` 묶음은 `<style>…</style>` 한 덩어리로, `<script src>` 묶음은
    `<script>…</script>` 한 덩어리로 돌려놓는다 — 가르기 전의 모양 그대로다.
    """
    if "src" in _cache:
        return _cache["src"]
    out, css_open, js_open = [], False, False
    for line in _read(SHELL).splitlines(True):
        m = LINK_RE.match(line)
        if m:
            if not css_open:
                out.append("<style>\n")
                css_open = True
            out.append(_read(os.path.join(WEB, "css", m.group(1))))
            continue
        if css_open:
            out.append("</style>\n")
            css_open = False
        m = SRC_RE.match(line)
        if m:
            if not js_open:
                out.append("<script>\n")
                js_open = True
            out.append(_read(os.path.join(WEB, "app", m.group(1))))
            continue
        if js_open:
            out.append("</script>\n")
            js_open = False
        out.append(line)
    _cache["src"] = "".join(out)
    return _cache["src"]


def index_path():
    """`source()` 를 담은 파일 경로 — `open(INDEX)` 을 쓰는 시험이 그대로 쓴다.

    프로세스당 한 번만 만든다. 파일로 내놓는 이유는 하나다: 이 저장소의 화면
    계약 시험 아흔 몇 개가 이미 `open(INDEX)` 으로 쓰여 있고, 그 아흔 몇 개의
    읽는 방식을 바꾸는 것은 이 작업의 일이 아니다 (계약은 그대로 두고 **읽는
    자리만** 옮긴다).
    """
    if "path" not in _cache:
        fd, path = tempfile.mkstemp(prefix="s9-webasset-", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(source())
        _cache["path"] = path
        # 끝날 때 스스로 지운다 (REQ-20260829-003 의 규율). 러너로 돌리면
        # 실행 전용 임시 루트가 통째로 지워지므로 이 줄이 없어도 남지 않지만,
        # 시험 파일 하나만 직접 돌릴 때는 이 줄만이 /tmp 를 지킨다.
        atexit.register(_drop, path)
    return _cache["path"]


def _drop(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def part(name):
    """조각 **하나**의 원문을 준다 (`part("app/graph.js")`).

    가른 뒤 새로 생긴 함정 하나를 막는 검사다: `source()` 는 조각 서른 몇 개를
    이어 붙이므로, 거기서 `function draw(` 를 정규식으로 찾으면 **먼저 오는
    조각의 같은 이름**이 잡힌다. 실제로 REQ-20260829-038 이 진단 조각(`oops.js`,
    맨 앞)에 자기 `draw()` 를 두자 그래프 시험이 그것을 집었다 — 제품은 멀쩡한데
    시험만 빨개지는, 읽기 어려운 실패다.

    어느 조각에 있는지가 계약의 일부인 것을 물을 때는 이것을 써라. 이어 붙인
    한 장을 봐야 하는 계약(순서·캐스케이드·전체 존재)은 `source()` 그대로다.
    """
    return _read(os.path.join(WEB, *name.split("/")))
