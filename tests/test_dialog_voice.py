"""팝업은 사용자의 말로, 한 결로 말한다 (REQ-20260830-007-62x6).

실사고 2026-08-30 10:43. 사용자가 깨우기 창을 캡처해 보냈다. 창은 이렇게 말했다:

    깨움  REQ-20260830-003
    REQ-20260830-003-62x6 를 깨웠다 — 무인 작업자가 본 저장소에서
    이어받는다. 진행은 카드의 점과 Stream 에서 보인다.

사용자: "일반 사용자는 무슨 내용인지 이해를 할 수가 없다. … 개발자, 엔지니어가
아닌 일반 사용자를 대상으로 다시 검토해."

한 문장에 병이 셋이었다.

  ① **내부 낱말** — `무인 작업자`·`본 저장소`·`카드의 점`·`깨움` 은 전부 이
     시스템이 자기를 부르는 말이지 사용자의 말이 아니다. 이 저장소는 같은
     지적을 이미 다섯 번 받았다(REQ-20260829-030): "깃을 모르는 사람에게 이
     사실은 읽을 것도 할 일도 아니다."
  ② **말결이 둘** — 화면의 나머지가 전부 존댓말인데 창 본문만 반말이었다.
     서버가 지은 문장을 화면이 그대로 옮기는 구조라(그것 자체는 옳다) 서버가
     반말로 쓰면 창만 반말이 된다.
  ③ **다음 행동이 없다** — 무슨 일이 일어났는지는 말하는데, 지금 무엇을 보면
     되는지가 내부 이름(`카드의 점`·`Stream`)으로만 적혀 있었다.

문구는 고치면 그만이지만 **다음에 또 새로 지어진다** — 창을 짓는 자리가 서버와
화면 둘로 나뉘어 있어서다. 그래서 계약으로 못박는다.

계약 넷:
  V1 팝업에 서는 문장에 내부 낱말이 없다 (금지 낱말 목록).
  V2 팝업의 말결은 하나다 — 반말 종결(…다/…해라)이 없다.
  V3 자리의 뜻을 말하는 문장은 서버와 화면이 **같은 말**이다
     (bin/s9 `WS_MEANS_KO` ↔ web/app/card.js `WS_MEANS`).
     두 런타임이 문자열 하나를 나눠 가질 수 없어 부득이 두 벌인데, 두 벌이면
     한 벌만 고쳐진다 — 그 자리를 이 시험이 지킨다.
  V4 깨우기·세우기 창의 눈썹은 **사람이 누른 그 낱말**이다.

실행: python3 tests/ dialog_voice
"""
import ast
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
S9 = os.path.join(ROOT, "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
APP = os.path.join(ROOT, "web", "app")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ---- 금지 낱말 ------------------------------------------------------------
# 시스템이 **자기를 부르는 이름**이다. 사람이 이 화면에서 하려는 일과는 아무
# 관계가 없다 — 읽어도 할 일이 늘지 않고, 못 읽으면 창이 통째로 벽이 된다.
BANNED = [
    "무인 작업", "무인 작업자", "무인 워커", "서브에이전트", "스폰", "카드의 점",
    "무인 이어받기",
]
# 서버가 지어 화면에 그대로 뜨는 문장에는 **깃 낱말도** 서지 않는다. 자리
# 이름은 `작업 자리` 창 하나에만 남는다 — 사용자가 "문서에 포함은 되어도
# 상관없다"고 한 그 자리다(REQ-20260829-030 4·5차 반려).
BANNED_SERVER = BANNED + ["본 저장소", "워크트리", "머신", "pid"]

# ---- 반말 종결 ------------------------------------------------------------
# `…한다`·`…없다`·`…았다` 는 잡고 `…습니다`·`…입니다` 는 지난다. 명령형
# 해라체(`눌러라`·`늘려라`)도 같이 잡는다 — 창이 사람에게 명령하는 자리는 없다.
_DECL = re.compile(r"[가-힣]+다(?=[\s.!?…—)\]\"'`>]|$)")
_IMPER = re.compile(r"[가-힣]*(?:어라|아라|여라|해라|워라|거라)(?=[\s.!?…—)\]\"'`>]|$)")
# 종결이 아닌 `다` — 존댓말 종결(`…습니다`)과 조사(`30초마다`·`이보다`).
_DECL_OK = ("니다", "마다", "보다")


def plain_hits(text):
    out = [w for w in _DECL.findall(text) if not w.endswith(_DECL_OK)]
    out += _IMPER.findall(text)
    return out


# ---- JS 문자열 뽑기 -------------------------------------------------------
def js_strings(src, lo=0, hi=None):
    """[lo, hi) 안의 문자열 리터럴 — 주석은 건너뛴다.

    정규식으로 긁으면 주석 속 문장이 함께 잡힌다. 이 저장소의 주석은 반려문을
    **그대로 인용**하고 있어서(그게 이 코드의 값이다) 주석까지 재면 계약이
    자기 근거 때문에 깨진다. 그래서 한 글자씩 걷는다."""
    hi = len(src) if hi is None else hi
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'`":
            j, buf = i + 1, []
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                buf.append(src[j])
                j += 1
            if lo <= i < hi:
                out.append("".join(buf))
            i = j + 1
            continue
        i += 1
    return out


def js_call_spans(src, name):
    """`name(` 부터 짝이 맞는 `)` 까지 — 문자열·주석 안의 괄호는 세지 않는다."""
    spans, start = [], 0
    while True:
        k = src.find(name + "(", start)
        if k < 0:
            return spans
        i, depth = k + len(name), 0
        n = len(src)
        while i < n:
            c = src[i]
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j + 1
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if c in "\"'`":
                j = i + 1
                while j < n:
                    if src[j] == "\\":
                        j += 2
                        continue
                    if src[j] == c:
                        break
                    j += 1
                i = j + 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    spans.append((k, i + 1))
                    break
            i += 1
        start = k + 1


def js_fn_span(src, name):
    """`function name(` 부터 짝이 맞는 `}` 까지."""
    k = src.find("function %s(" % name)
    if k < 0:
        return None
    i, depth, n, seen = k, 0, len(src), False
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'`":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                j += 1
            i = j + 1
            continue
        if c == "{":
            depth += 1
            seen = True
        elif c == "}":
            depth -= 1
            if seen and depth == 0:
                return (k, i + 1)
        i += 1
    return None


# 창 안에 서지만 창 밖에서 지어지는 문장들 — 상수 선언도 함께 잰다.
DLG_CONSTS = ["WS_MEANS", "WS_WHY", "WS_FIX_COMMIT", "WS_FIX_SWEEP",
              "DLG_ATTACH_HINT"]
# 창의 **껍데기**가 스스로 짓는 글 — 바닥 힌트·기본 버튼 이름·빈 목록 문구.
DLG_SHELLS = ["s9dlg", "s9choose"]


def web_dialog_strings():
    """화면이 팝업에 세우는 문장 전부 — (파일, 문장)."""
    out = []
    for fn in sorted(os.listdir(APP)):
        if not fn.endswith(".js"):
            continue
        src = read(os.path.join(APP, fn))
        for a, b in js_call_spans(src, "s9dlg"):
            for s in js_strings(src, a, b):
                out.append((fn, s))
        for name in DLG_SHELLS:
            sp = js_fn_span(src, name)
            if sp:
                for s in js_strings(src, *sp):
                    out.append((fn, s))
        for name in DLG_CONSTS:
            m = re.search(r"const %s = " % name, src)
            if not m:
                continue
            end = src.find(";\n", m.end())
            for s in js_strings(src, m.end(), end if end > 0 else len(src)):
                out.append((fn, s))
    return out


# ---- 서버 문장 뽑기 -------------------------------------------------------
# 화면이 그대로 옮겨 적는 자리들 (`ok`·`message` 둘만 읽는다는 계약 때문에
# 문장을 짓는 곳은 전부 서버다).
SERVER_FNS = ["wake_request", "_wake_refusal", "stop_request",
              "stop_all_workers", "worker_stop", "_spawn_worker",
              "_auto_cap_block", "stall_verdict"]


def _texts(node):
    """문자열로 굳어질 조각만 — 로그·경로 같은 곁 문자열은 따라가지 않는다."""
    out = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.append(node.value)
    elif isinstance(node, ast.JoinedStr):
        out.append("".join(v.value for v in node.values
                           if isinstance(v, ast.Constant)
                           and isinstance(v.value, str)))
    elif isinstance(node, ast.BinOp):
        out += _texts(node.left) + _texts(node.right)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            out += _texts(e)
    elif isinstance(node, ast.BoolOp):
        for e in node.values:
            out += _texts(e)
    return [s for s in out if s.strip()]


def _fn_node(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    return None


def server_dialog_strings(tree):
    """사람에게 나가는 문장만 — `message`·`why`·`block()`·`out()` 의 자리."""
    out = []
    for name in SERVER_FNS:
        fn = _fn_node(tree, name)
        assert fn is not None, f"{name} 을 못 찾았다 — 이름이 바뀌었나"
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value in ("message",
                                                                   "why"):
                        out += [(name, s) for s in _texts(v)]
            elif isinstance(node, ast.Call):
                f = getattr(node.func, "id", None) \
                    or getattr(node.func, "attr", None)
                if f == "block" and len(node.args) >= 2:
                    out += [(name, s) for s in _texts(node.args[1])]
                elif f == "out" and len(node.args) >= 3:
                    out += [(name, s) for s in _texts(node.args[2])]
                elif f == "dict":
                    for kw in node.keywords:
                        if kw.arg == "why":
                            out += [(name, s) for s in _texts(kw.value)]
            elif isinstance(node, ast.Return) and node.value is not None:
                out += [(name, s) for s in _texts(node.value)]
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id in ("msg", "wait"):
                        out += [(name, s) for s in _texts(node.value)]
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name) \
                        and node.target.id == "msg":
                    out += [(name, s) for s in _texts(node.value)]
    return out


class DialogVoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s9src = read(S9_SRC)
        cls.tree = ast.parse(cls.s9src)
        cls.card = read(os.path.join(APP, "card.js"))
        cls.web = web_dialog_strings()
        cls.server = server_dialog_strings(cls.tree)

    # ---- V1. 내부 낱말이 창에 서지 않는다 --------------------------------
    def test_v1_no_house_words_on_screen(self):
        self.assertGreater(len(self.web), 40, "창 문장을 못 읽었다")
        for where, s in self.web:
            for w in BANNED:
                self.assertNotIn(w, s, f"{where}: 창이 내부 낱말 {w!r} 로 "
                                       f"말한다 — {s!r}")

    def test_v1b_no_house_words_in_the_server_sentence(self):
        self.assertGreater(len(self.server), 20, "서버 문장을 못 읽었다")
        for where, s in self.server:
            for w in BANNED_SERVER:
                self.assertNotIn(w, s, f"{where}: 창에 그대로 뜨는 문장이 "
                                       f"{w!r} 로 말한다 — {s!r}")

    # ---- V2. 말결이 하나다 -----------------------------------------------
    def test_v2_one_voice_on_screen(self):
        bad = [(w, s, plain_hits(s)) for w, s in self.web if plain_hits(s)]
        self.assertEqual(bad, [], "창 문구에 반말이 섞였다")

    def test_v2b_one_voice_in_the_server_sentence(self):
        bad = [(w, s, plain_hits(s)) for w, s in self.server if plain_hits(s)]
        self.assertEqual(bad, [], "서버가 지은 창 문장에 반말이 섞였다")

    # ---- V3. 자리의 뜻은 서버와 화면이 같은 말이다 -----------------------
    def test_v3_the_two_runtimes_say_the_same_thing(self):
        srv = None
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "WS_MEANS_KO"
                    for t in n.targets):
                srv = ast.literal_eval(n.value)
        self.assertIsNotNone(srv, "bin/s9 에 WS_MEANS_KO 가 없다")
        m = re.search(r"const WS_MEANS = \{(.*?)\};", self.card, re.S)
        self.assertIsNotNone(m, "card.js 에 WS_MEANS 가 없다")
        body = m.group(1)
        web = {k: re.search(r'%s:\s*"([^"]*)"' % k, body).group(1)
               for k in ("main", "worktree")}
        self.assertEqual(srv, web,
                         "자리의 뜻을 서버와 화면이 다르게 말한다 — 두 벌이면 "
                         "한 벌만 고쳐진다")

    # ---- V3b. 진단 답본은 서버 실문장이다 (REQ-20260830-048/-049) --------
    def test_v3b_the_diag_fixture_speaks_the_server_sentence(self):
        """`?dlg=wakespawn…` 의 고정 답본으로 창을 캡처·검증하는데, 그 문안이
        서버와 어긋나면 진단으로 고친 창이 사람이 보는 창이 아니게 된다 —
        실제로 어긋나 있었다(designer 실측). V3 과 같은 병의 다른 자리다.

        049 로 답이 **두 칸**이 됐다: `message`(한 절, 결과 그 자체)와
        `note`(예외 사실 한 줄, 워크트리 갈래에만). 두 칸을 다 비춰야 진단이
        사람이 보는 창과 같다 — main 갈래는 `note` 가 없어 아예 창이 서지
        않는 것까지가 답본의 몫이다."""
        def module_const(name):
            for n in ast.walk(self.tree):
                if isinstance(n, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == name
                        for t in n.targets):
                    return ast.literal_eval(n.value)
            return None
        title = module_const("WAKE_SPAWNED_KO")
        means = module_const("WS_MEANS_KO")
        self.assertIsNotNone(title, "bin/s9 에 WAKE_SPAWNED_KO 가 없다")
        # 제목은 **한 절**이다 — 급이 다른 두 말이 한 슬롯에 겹치지 않는다.
        self.assertNotIn("{means}", title,
                         "성공 제목이 아직 갈래 문장을 품고 있다 — 두 칸으로 "
                         "갈라야 창의 강조가 하나가 된다 (REQ-20260830-049)")
        note = means["worktree"] + "."
        for s in (title, note):
            self.assertEqual(plain_hits(s), [],
                             "깨우기 성공 문장에 반말이 섞였다: %r" % s)
        flat = re.sub(r"\s+", " ", read(os.path.join(APP, "diag.js")))
        self.assertIn('message: "%s", note: "%s"}' % (title, note), flat,
                      "워크트리 갈래 답본이 서버 실문장(두 칸)과 다르다 — "
                      "캡처가 사람이 보는 창을 비추지 못한다")
        self.assertIn('message: "%s"}' % title, flat,
                      "main 갈래 답본이 서버 실문장과 다르다")

    # ---- V4. 눈썹은 사람이 누른 그 낱말이다 ------------------------------
    def test_v4_the_eyebrow_repeats_the_button(self):
        """`깨움`·`세움` 은 동사를 명사로 굳힌 시스템의 말이다. 사람이 누른 것은
        「깨우기」·「세우기」이고, 답이 다른 낱말로 돌아오면 같은 것인지 한 박자
        맞춰 봐야 한다."""
        # 굳은 명사꼴이 창머리에 남아 있지 않다
        for dead in ('cap: d.ok ? "깨움"', 'cap: d.ok ? "세움"'):
            self.assertNotIn(dead, self.card,
                             f"창머리가 아직 굳은 명사꼴이다: {dead}")
        # 낱말 자체는 REQ-20260829-024 라운드4 반려로 바뀌었다("깨우기, 세우기
        # 라는 용어가 너무 어색한데"). 그러면서 계약이 한 겹 세졌다: 낱말이
        # 버튼과 창머리 두 곳에 **글자로** 있으면 개명 한 번에 둘이 갈린다
        # (실제로 갈렸다). 이제 둘은 같은 상수를 읽는다 — 그것을 여기서 지킨다.
        for live in ('cap: d.ok ? WAKE_LABEL : "이어가지 않음"',
                     'cap: d.ok ? STOP_LABEL : "중단하지 않음"'):
            self.assertIn(live, self.card,
                          f"창머리가 사람이 누른 낱말과 다르다: {live}")
        for pair in ('const WAKE_LABEL = "이어가기"',
                     'const STOP_LABEL = "중단하기"'):
            self.assertIn(pair, self.card,
                          f"손잡이의 낱말이 한 곳에 있지 않다: {pair}")


if __name__ == "__main__":
    unittest.main()
