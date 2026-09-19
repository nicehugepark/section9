"""화면을 훑는 **한 벌의 눈** — 사람이 읽는 글자만 남긴다.

`test_screen_lexicon` 이 반려어를 쓸어내려고 지은 것인데, 말투를 재는
`test_screen_speech` 가 같은 자리를 읽어야 해서 여기로 옮겼다
(REQ-20260919-013-62x6). **검사가 둘로 늘 때 읽는 자리까지 복사하면 한 벌만
고쳐진다** — 그 시험이 제 안에서 세운 규율이고, 시험이 둘이 된 지금은 모듈
하나로만 지킬 수 있다.

읽는 자리는 넷이다.

  · `web/app/*.js` — 따옴표 안만. 주석은 걷는다(아래 `_strings` 참조).
  · `web/*.html` — 태그 밖의 글자와 사람이 읽는 속성.
  · `bin/s9` — **서버의 문장이 곧 팝업이다** (REQ-20260902-005). 스폰 거부
    사유·중단 결과는 서버가 지어 화면이 그대로 띄운다.
  · `bin/s9-guard` — 커밋 검사의 경고도 사람이 읽는 글이다
    (REQ-20260919-007-62x6). 화면이 아니라 터미널에 뜨지만, 읽고 다음 행동을
    정하는 것은 사람이다.

**`code_blind`** — 코드와 인용을 아예 안 보는 눈이다(기본값은 끔). 낱말을 재는
눈은 `<pre>`·`<code>` 안까지 보아야 한다(거기 선 반려어도 사람이 읽는 글자다).
말투를 재는 눈은 반대다: 그 안에 있는 것은 **기계가 찍은 출력을 그대로 옮긴
인용**이라(가이드 2.1 절의 첫 실행 출력이 그렇다) 말투를 고치면 가이드가
거짓말이 된다. 기본값을 그대로 둔 까닭은 하나다 — 이미 서 있는 검사의 잣대를
새 검사가 조용히 바꾸면, 바뀐 줄 모르는 채로 지나가는 자리가 생긴다.
"""
import ast
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "web")
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
S9_GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

# 낱말 하나가 두 표면에 살면 안 되는 것은 아니다 — 개발자만 보는 진단 출력은
# 이 검사 밖이다(진단은 코드 말이 오히려 정확하다). 파일 단위로 뺀다.
DIAG_FILES = {"boot.js", "graph.js", "diag.js"}

# `bin/s9` 안에서 **사람이 읽지 않는** 문자열. 파일 단위로 뺄 수 없어(한
# 파일에 서버 문장과 기계 글자가 함께 산다) 자리마다 근거를 적어 뺀다.
# 오탐 하나가 목록째 지워지게 만들기 때문에 넓힐 때 이 자리를 먼저 채운다.
S9_NOT_SCREEN = {
    "자동 ?재작업|무인|워커|스폰":
        "분류기의 정규식이다 — 옛 낱말로 적힌 지난 요청을 계속 맞혀야 하므로"
        " 폐기어가 **패턴 안에 살아 있어야** 한다 (bin/s9 topic 분류)",
}

# 화면에 나가지만 사람 눈에는 안 보이는 글 — 템플릿 안의 HTML 주석이다.
# 다음 개발자에게 하는 말이라 `//` 주석과 같은 갈래이고, 명령형이 제 말투다.
_HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
# 기계가 찍은 것을 그대로 옮긴 자리 — 가이드의 첫 실행 출력이 여기 산다.
_HTML_CODE = re.compile(r"<(pre|code|style)\b[\s\S]*?</\1>", re.I)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
# 템플릿 문자열 안의 `${…}` — 여기는 **코드**다. 그런데 그 안에 문장이 산다
# (`${quiet ? "…지났다. " : ""}`). 바깥 백틱이 통째로 한 덩어리로 잡히는 탓에
# 안쪽 따옴표는 따로 꺼내지지 않고, 문장 검사는 그것을 「인용」으로 보고 건너뛴다
# (실측 2026-09-19: 그렇게 빠져나간 문장이 여섯이었다). 그래서 코드는 버리고
# **그 안의 글자만** 줄로 꺼낸다.
_TPL_EXPR = re.compile(r"\$\{([^{}]*)\}")
_TPL_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'')


def _unwrap_exprs(text):
    def repl(m):
        lits = [a or b for a, b in _TPL_LITERAL.findall(m.group(1))]
        return "\n" + "\n".join(lits) + "\n"
    return _TPL_EXPR.sub(repl, text)


def _strings(src, code_blind=False):
    """주석을 걷고 **따옴표 안**만 남긴다 — 화면에 나가는 것은 그것뿐이다.

    블록/줄 주석을 먼저 지운다. 남은 코드에서 홑·겹따옴표와 백틱 문자열을
    모아 한 덩어리로 잇는다(어느 줄에 있었는지는 부르는 쪽에서 다시 찾는다).

    `code_blind` 면 따옴표 안에 든 HTML 주석까지 걷는다 — 템플릿 문자열 안의
    `<!-- … -->` 는 DOM 에는 들어가도 사람 눈에는 안 보이는 개발자의 말이다.
    태그도 함께 걷는다: 이 화면의 문장은 `…집힌다.</div>` 처럼 태그를 달고
    끝나서, 태그를 남겨 두면 문장의 **종결이 가려진다**(실측 2026-09-19: 그
    자리 여섯이 말투 검사를 그대로 빠져나갔다). `${…}` 안은 `_unwrap_exprs`
    가 글자만 남기고 코드를 버린다."""
    src = re.sub(r"/\*[\s\S]*?\*/", " ", src)
    src = re.sub(r"(?m)^\s*//.*$", " ", src)
    src = re.sub(r"(?m)\s//[^\"'`]*$", " ", src)
    out = []
    for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"'
                         r"|'((?:[^'\\\n]|\\.)*)'"
                         r"|`((?:[^`\\]|\\.)*)`", src):
        out.append(m.group(1) or m.group(2) or m.group(3) or "")
    text = "\n".join(out)
    if code_blind:
        text = _HTML_CODE.sub(" ", _HTML_COMMENT.sub(" ", text))
        text = _HTML_TAG.sub(" ", _unwrap_exprs(text))
    return text


def _html_text(src, code_blind=False):
    """HTML 은 태그 밖의 글자와 title·placeholder 같은 사람 읽는 속성만 본다."""
    src = re.sub(r"<!--[\s\S]*?-->", " ", src)
    src = re.sub(r"<script[\s\S]*?</script>", " ", src, flags=re.I)
    if code_blind:
        src = _HTML_CODE.sub(" ", src)
    keep = " ".join(re.findall(
        r'(?:title|placeholder|aria-label|alt|value)="([^"]*)"', src))
    return re.sub(r"<[^>]*>", " ", src) + "\n" + keep


def _py_strings(src, code_blind=False):
    """`bin/s9` 는 파이썬이라 **AST 로** 문자열만 뽑는다.

    정규식으로 따옴표를 세면 주석 안의 인용을 문자열로 오인한다 — 이 저장소의
    주석에는 반려어가 근거로 인용돼 있고, 그것을 걸면 다음 사람이 근거를
    지우게 된다. docstring 도 뺀다: 그것은 다음 개발자에게 하는 말이지
    사용자에게 하는 말이 아니다.

    **용어를 다루는 표 자신도 뺀다** (REQ-20260919-007-62x6): `BANNED_TERMS` 는
    반려된 말을 왼쪽에 적어 둬야 성립하는 자료라, 그것을 화면 문장으로 세면 표가
    제 검사에 걸린다. 종전에는 글자를 `"무인 " + "작업자"` 로 나눠 피했는데, 그
    수법은 읽기 어렵고 나눈 조각(「작업자」)이 다음 검사에 다시 걸린다 — 표를
    통째로 빼는 것이 자리에 맞는 답이다. 규칙은 **이름**이다: 대입문의 이름이
    `BANNED_` 로 시작하면 그 아래 글자는 화면 문장이 아니다."""
    tree = ast.parse(src)
    not_screen = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id.startswith("BANNED_")
                        for t in node.targets)):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    not_screen.add(id(sub))
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and body:
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                not_screen.add(id(first.value))
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in not_screen):
            text = node.value
            for skip in S9_NOT_SCREEN:
                if skip in text:
                    text = ""
                    break
            if text:
                out.append(text)
    text = "\n".join(out)
    if code_blind:
        text = _HTML_CODE.sub(" ", _HTML_COMMENT.sub(" ", text))
    return text


def surfaces(code_blind=False):
    """표시 이름 → 사람이 읽는 글자만. 읽는 자리는 이 파일 머리에 적었다."""
    out = {}
    for p in sorted(glob.glob(os.path.join(WEB, "app", "*.js"))):
        name = os.path.basename(p)
        if name in DIAG_FILES:
            continue
        with open(p, encoding="utf-8") as f:
            out["app/" + name] = _strings(f.read(), code_blind)
    for p in sorted(glob.glob(os.path.join(WEB, "*.html"))):
        with open(p, encoding="utf-8") as f:
            out[os.path.basename(p)] = _html_text(f.read(), code_blind)
    with open(S9_SRC, encoding="utf-8") as f:
        out["bin/s9"] = _py_strings(f.read(), code_blind)
    with open(S9_GUARD, encoding="utf-8") as f:
        out["bin/s9-guard"] = _py_strings(f.read(), code_blind)
    return out
