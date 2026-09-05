"""반려된 낱말은 그 파일이 아니라 **화면 전체**에서 걷힌다 (REQ-20260830-039-62x6).

이 게이트가 생긴 실사고는 둘이고, 둘 다 같은 뿌리다.

  ① 사용자가 REQ-20260829-024-62x6 라운드4에서 낱말 둘을 직접 반려했다 —
     "깨우기, 세우기 라는 용어가 너무 어색한데". `card.js` 는 「이어가기」·
     「중단하기」로 고쳤는데, **같은 낱말이 살아 있던 세 자리**(session.js 둘,
     input.js 하나, terminal.js 하나)는 손대지 않았다. 한 화면에 반려어와
     채택어가 나란히 섰고, 그 상태로 다음 반려까지 갔다.
  ② 「맡은 손」도 같은 모양이었다 — 조어 하나를 캡션 자리에 세우고, 같은 뜻의
     낱말이 툴팁·확인창에 따로 남았다.

뿌리는 **반려를 낱말 하나에 내린 판정으로 읽은 것**이다. 반려는 개념에 내린
판정이라, 걷어낼 자리는 그 낱말이 나온 파일이 아니라 사람이 보는 화면 전부다.
그래서 이 시험은 파일을 가리지 않고 `web/app/*.js` 와 `web/*.html` 의 **사용자
문자열 전체**를 훑는다.

주석은 보지 않는다. 주석에는 "사용자가 「깨우기」를 반려했다" 처럼 **반려어를
인용해야만 쓸 수 있는 근거**가 들어 있고, 그 근거를 지우면 다음 사람이 같은
낱말을 다시 짓는다. 개발자 표면(진단 출력)도 같은 이유로 밖에 둔다.

유지 판정 낱말(맡은 창·일손·손길·치운 것·바로 보임 …)은 이 목록에 **없다** —
근거와 함께 REQ-20260830-039-62x6 의 tech-writer 노트에 재론 금지로 남았고,
과잉 게이트는 그 판정을 뒤엎는 다음 사고가 된다.

실행: python3 tests/ screen_lexicon
"""
import ast
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "..", "web")
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

# 낱말 → 왜 반려됐고 무엇으로 바뀌었나. 메시지가 곧 다음 사람이 읽을 판정문이다.
BANNED = {
    "맡은 손": "가리킬 실체가 없는 조어 — 「담당」·「없음」으로",
    "세션 깨우기": "사용자가 직접 반려한 낱말(라운드4) — 「여기서 세션 시작」으로",
    "세워 두면": "반려어 「세우기」의 활용형 — 「중단해 두면」으로",
    "세워 둡니다": "반려어 「세우기」의 활용형 — 「중단해 둡니다」로",
    "붙은 일": "국어에 없는 연어 — 「맡은 요청」으로",
    "집기 해제": "같은 × 버튼이 세 은유로 갈렸다 — 「문서 지목 해제」로",
    "자리 지우기": "오류 제목에 내부 은유 — 「계정 지우기」로",
    "화면 조각": "조각 = JS 모듈, 사용자에게 지시 대상이 없다 — 「화면 기능」으로",
    "손잡이가 붙습니다": "사용자 창이 버튼을 손잡이라 부른다 — 「이 버튼이 다시 생깁니다」로",
    "저절로 이어지지 않게 하기": "3차 반려(REQ-20260901-005) — 부정형 데뷔 + "
        "무주어 자동사 + 「이어가기」 어간 충돌, 「자동 이어받기 끄기」로",
    # ── 「이 창 밖에서 도는 것」의 옛 이름들 (REQ-20260902-005) ──────────
    # **같은 물건의 이름을 두 번 거부당했다.** 한 번은 취향일 수 있으나 두 번은
    # 결함이다 — 2026-08-30 사용자가 깨우기 창을 캡처해 보내며 "일반 사용자는
    # 무슨 내용인지 이해를 할 수가 없다"고 한 그 문장에 「무인 작업자」가 서
    # 있었고(REQ-20260830-007), 그 뒤 개칭한 「무인 작업」이 또 걸렸다.
    # 채택어는 「백그라운드 작업」이다: 사람들이 휴대폰·윈도우 설정에서 이미
    # 배운 낱말이고, 「배경 작업」으로 옮기면 뜻을 잃으며, `git background`
    # 라는 명령이 없어 남의 도구 이름 조항(위 음차 목록) 밖이다.
    "무인 작업": "사람이 읽는 말이 아니다(두 번째 반려) — 「백그라운드 작업」으로",
    "무인 작업자": "위와 같은 물건의 더 낡은 이름 — 「백그라운드 작업」으로",
    "워커": "밖에서 그 글자를 다시 칠 일이 없는 원어의 음차다"
            " (`s9 workers` 는 세는 명령이지 그 일을 하려고 치는 글자가 아니다)"
            " — 「백그라운드 작업」으로",
    "백그라운드 에이전트": "「에이전트」는 이 화면에서 나눠 맡은 일손에 배정돼"
                     " 있다 — 한 낱말이 두 개념을 덮는다",
}

# ── 대시보드 화면에서만 재는 낱말 ────────────────────────────────────────
#
# **판정이 선 자리가 곧 게이트의 자리다.** 위 BANNED 는 개념에 내려온 판정이라
# 사람이 읽는 곳이면 어디서나 걸리는데, 아래는 사용자가 **대시보드를 보며**
# 내린 판정이다(REQ-20260902-002). `bin/s9` 를 함께 훑기 시작하며 이 구분이
# 필요해졌다: 터미널만 쓰는 명령들(`s9 worktree`·`s9 sync`·`s9 doctor`)의
# 출력 53자리가 여기 걸렸는데, 그 자리는 판정을 받은 적이 없다. 판정 없이
# 게이트를 넓히면 다음 사람이 오탐으로 읽고 목록째 지운다 — 이 저장소가 가장
# 두려워하는 그 결말이다. 그 53자리는 따로 요청으로 세웠다.
#
# 여기 실은 것은 **음차뿐**이다: 한국어에 다른 뜻이 없어 오탐이 0 이다.
# **넣지 않은 것과 그 까닭** — 「풀」(「한도가 풀립니다」) · 「가지」
# (「이어가지 않음」) · 「머지」(「머지않아」가 언제든 생긴다) ·
# 「올리기」·「받기」(정당한 자리가 여럿) · 「저장소」·「동기화」
# (빌려 온 명령 이름이 아니라 우리 말이다 — 무차별 원어도 결함이다).
BANNED_WEB = {
    "푸시": "git 이 지은 이름의 음차 — `push` 로 (REQ-20260902-002)",
    "커밋": "git 이 지은 이름의 음차 — `commit` 으로",
    "워크트리": "git 이 지은 이름의 음차 — `worktree` 로",
    "리베이스": "git 이 지은 이름의 음차 — `rebase` 로",
    "클론": "git 이 지은 이름의 음차 — `clone` 으로",
    "체크아웃": "git 이 지은 이름의 음차 — `checkout` 으로",
    "브랜치": "git 이 지은 이름의 음차 — `branch` 로",
    "리모트": "git 이 지은 이름의 음차 — `remote` 로",
}
# 낱말 하나가 두 표면에 살면 안 되는 것은 아니다 — 개발자만 보는 진단 출력은
# 이 게이트 밖이다(진단은 코드 말이 오히려 정확하다). 파일 단위로 뺀다.
DIAG_FILES = {"boot.js", "graph.js", "diag.js"}
# 대시보드가 아닌 표면. 여기 실린 이름은 BANNED_WEB 의 잣대를 받지 않는다.
NOT_THE_DASHBOARD = {"bin/s9"}

# ── 「자동 작업」 — **낱말이 아니라 자리가 걸렸다** (DOC-20260831-005) ────────
#
# 위 BANNED 와 모양이 다르다. 저 목록은 낱말째 내려온 판정이라 문자열이 있으면
# 곧 결함인데, 이 낱말은 **참인 자리와 거짓인 자리가 함께 있다**:
#
#   · 뜻 A (앞으로) — "사람이 안 시켜도 저절로 다시 맡는 것". 사용자가 실제로
#     끄고 켜는 그것이라 「자동」이 참이고 값을 한다.
#   · 뜻 B (지금)  — "지금 이 요청을 맡아 도는 것". 사용자가 **제 손으로 ▶ 를
#     눌러 띄운 것**까지 같은 이름을 받아 "내가 안 시킨 일이 돈다"로 읽혔다.
#     사용자 지적("요청하고, 멈췄고, 다시 시작했을 뿐인데 자동인가")이 선 자리.
#
# 그래서 낱말을 통째로 막으면 뜻 A 열둘까지 삼키고, 안 막으면 뜻 B 가 다시
# 자란다. 게이트를 **허용 목록**으로 뒤집는 이유가 그것이다: 뜻 A 로 판정된
# 문장만 이름을 대고 지나가고, 그 밖의 「자동 작업」은 새로 생기는 즉시 걸린다.
# 목록에 없는 문장을 지나가게 하려면 이 자리에 근거와 함께 적어야 한다 —
# 판정을 코드가 아니라 문서에 남기게 하는 것이 이 게이트의 값이다.
#
# 판정표 전문: REQ-20260831-024-62x6 tech-writer 노트(유지 12 · 옮김 20).
KEPT_AUTO = {
    # 비었다 (REQ-20260901-005). 마지막 넷(정책 서술 둘·개체 열거·우선순위 창)이
    # 「무인 작업」·「자동 이어받기」로 개편되며 뜻 A 자리도 「자동 작업」이라는
    # 이름을 더는 안 쓴다 — 정책의 이름은 「자동 이어받기」(명사구)다.
    # 뜻 A 로 참인 새 문장이 필요해지면 근거와 함께 여기 올려라: 목록이 빈
    # 것과 게이트가 없어진 것은 다르다.
    #
    # `bin/s9` 를 함께 훑기 시작하며 둘이 올랐다 (REQ-20260902-005). 둘 다
    # **워처 전용 경로**의 문장이라 화면에 안 뜬다: 사람이 ▶ 를 눌러 온 걸음
    # (`reason == "wake"`)은 이 판정 앞에서 되돌아 나가므로, 여기까지 오는 것은
    # 사람이 안 시킨 걸음뿐이다 — 그 자리에서 「자동」은 뜻 A 로 참이다.
    "오늘 쓸 수 있는 자동 작업 횟수":
        "워처가 스스로 띄우는 횟수의 하루 상한 (bin/s9 _auto_cap_block)",
    "이번 시간에 쓸 수 있는 자동 작업 횟수":
        "같은 상한의 시간당 판 — 위와 한 함수, 한 갈래",
}


def _strings(src):
    """주석을 걷고 **따옴표 안**만 남긴다 — 화면에 나가는 것은 그것뿐이다.

    블록/줄 주석을 먼저 지운다. 남은 코드에서 홑·겹따옴표와 백틱 문자열을
    모아 한 덩어리로 잇는다(어느 줄에 있었는지는 아래에서 다시 찾는다)."""
    src = re.sub(r"/\*[\s\S]*?\*/", " ", src)
    src = re.sub(r"(?m)^\s*//.*$", " ", src)
    src = re.sub(r"(?m)\s//[^\"'`]*$", " ", src)
    out = []
    for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"'
                         r"|'((?:[^'\\\n]|\\.)*)'"
                         r"|`((?:[^`\\]|\\.)*)`", src):
        out.append(m.group(1) or m.group(2) or m.group(3) or "")
    return "\n".join(out)


def _html_text(src):
    """HTML 은 태그 밖의 글자와 title·placeholder 같은 사람 읽는 속성만 본다."""
    src = re.sub(r"<!--[\s\S]*?-->", " ", src)
    src = re.sub(r"<script[\s\S]*?</script>", " ", src, flags=re.I)
    keep = " ".join(re.findall(
        r'(?:title|placeholder|aria-label|alt|value)="([^"]*)"', src))
    return re.sub(r"<[^>]*>", " ", src) + "\n" + keep


# `bin/s9` 안에서 **사람이 읽지 않는** 문자열. 파일 단위로 뺄 수 없어(한
# 파일에 서버 문장과 기계 글자가 함께 산다) 자리마다 근거를 적어 뺀다 —
# KEPT_AUTO 와 같은 방식이다. 오탐 하나가 목록째 지워지게 만들기 때문에
# 넓힐 때 이 자리를 먼저 채운다.
S9_NOT_SCREEN = {
    "자동 ?재작업|무인|워커|스폰":
        "분류기의 정규식이다 — 옛 낱말로 적힌 지난 요청을 계속 맞혀야 하므로"
        " 폐기어가 **패턴 안에 살아 있어야** 한다 (bin/s9 topic 분류)",
}


def _py_strings(src):
    """`bin/s9` 는 파이썬이라 **AST 로** 문자열만 뽑는다.

    정규식으로 따옴표를 세면 주석 안의 인용을 문자열로 오인한다 — 이 저장소의
    주석에는 반려어가 근거로 인용돼 있고(위 BANNED 주석이 그 예다), 그것을
    걸면 다음 사람이 근거를 지우게 된다. docstring 도 뺀다: 그것은 다음
    개발자에게 하는 말이지 사용자에게 하는 말이 아니다."""
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and body:
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docs.add(id(first.value))
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docs):
            text = node.value
            for skip in S9_NOT_SCREEN:
                if skip in text:
                    text = ""
                    break
            if text:
                out.append(text)
    return "\n".join(out)


def _surfaces():
    """표시 이름 → 사람이 읽는 글자만. **훑는 눈은 한 벌이다** — 게이트가
    둘로 늘 때 읽는 자리까지 복사하면 한 벌만 고쳐진다.

    `bin/s9` 도 화면이다 (REQ-20260902-005). 「서버의 문장이 곧 팝업이다」 —
    스폰 거부 사유·중단 결과는 서버가 지어 화면이 그대로 띄운다. 여기를 안
    훑던 동안 폐기어가 서버 문장으로 계속 샜다."""
    out = {}
    for p in sorted(glob.glob(os.path.join(WEB, "app", "*.js"))):
        name = os.path.basename(p)
        if name in DIAG_FILES:
            continue
        with open(p, encoding="utf-8") as f:
            out["app/" + name] = _strings(f.read())
    for p in sorted(glob.glob(os.path.join(WEB, "*.html"))):
        with open(p, encoding="utf-8") as f:
            out[os.path.basename(p)] = _html_text(f.read())
    with open(S9_SRC, encoding="utf-8") as f:
        out["bin/s9"] = _py_strings(f.read())
    return out


class ScreenLexicon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.surfaces = _surfaces()

    def test_the_sweep_actually_read_the_screen(self):
        """게이트가 빈 문자열을 훑고 초록이 되는 일이 없게 — 먼저 눈을 확인한다.

        문자열 추출이 조용히 실패하면 이 시험은 영원히 통과하고, 그때부터
        게이트는 없는 것과 같아진다(이 저장소가 파이프 종료코드에서 배운 것)."""
        self.assertGreaterEqual(len(self.surfaces), 20,
                                "훑은 화면 파일이 너무 적다 — 경로가 틀렸다")
        joined = "\n".join(self.surfaces.values())
        self.assertGreater(len(joined), 50000,
                           "사용자 문자열을 못 읽었다 — 추출기가 고장 났다")
        # 살아 있는 낱말 몇 개로 추출기가 진짜 화면을 봤는지 확인한다
        for anchor in ("이어가기", "중단하기", "선행 대기"):
            self.assertIn(anchor, joined, "화면에 있어야 할 「%s」를 못 찾았다" % anchor)

    def test_no_rejected_word_lives_on_any_screen(self):
        hits = []
        for word, why in BANNED.items():
            for name, text in self.surfaces.items():
                if word in text:
                    hits.append("%s: 「%s」 — %s" % (name, word, why))
        self.assertEqual([], hits,
                         "반려된 낱말이 화면에 남아 있다:\n  " + "\n  ".join(hits))

    def test_no_rejected_word_lives_on_the_dashboard(self):
        """대시보드에서 내려온 판정은 대시보드에서 잰다 — 잣대와 자리의 짝."""
        hits = []
        for word, why in BANNED_WEB.items():
            for name, text in self.surfaces.items():
                if name in NOT_THE_DASHBOARD:
                    continue
                if word in text:
                    hits.append("%s: 「%s」 — %s" % (name, word, why))
        self.assertEqual([], hits,
                         "반려된 낱말이 화면에 남아 있다:\n  " + "\n  ".join(hits))

    def test_the_kept_words_are_not_swept_away(self):
        """유지 판정 낱말까지 함께 지우면 그것이 다음 사고다.

        「맡은 창」은 실재하는 터미널 창을 가리키는 지시어이고, 「일손」은 사전
        낱말이며 늘 "나눠 맡은"을 달고 나온다 — 셋의 4역 합의로 유지가 확정됐다
        (REQ-20260830-039-62x6). 금지 목록이 이들을 삼키지 않았는지 못박는다."""
        for kept in ("맡은 창", "일손", "이어가기", "중단하기", "끝났는지 확인"):
            for word in list(BANNED) + list(BANNED_WEB):
                self.assertNotIn(kept, word,
                                 "유지 판정 낱말 「%s」가 금지 목록의 「%s」에 "
                                 "삼켜졌다" % (kept, word))

    def test_the_kept_words_still_stand_on_the_screen(self):
        """유지 판정 낱말이 **화면에 살아 있다** — 목록에서 빠진 것만으로는
        지워지지 않았다는 증거가 못 된다. 재론 금지의 근거는 화면이다."""
        joined = "\n".join(self.surfaces.values())
        for kept in ("맡은 창", "일손", "바로 보임", "끝나면 보임", "치운 것",
                     "이어가기", "중단하기", "끝났는지 확인"):
            self.assertIn(kept, joined,
                          "유지 판정 낱말 「%s」가 화면에서 사라졌다" % kept)

    def test_the_replacements_actually_stand(self):
        """걷어낸 자리에 채택어가 실제로 서 있다 — 지우기만 하고 안 채우면
        화면에서 문장이 통째로 사라진다."""
        joined = "\n".join(self.surfaces.values())
        # 원어로 **되돌린** 자리는 금지어로 못 지킨다 — 이번 사고는 음차가
        # 아니라 원어를 아예 지우고 순우리말로 갈아 끼운 것이었다
        # (「따로 떼어 놓고 일하기」·「저장소에 올리는 것」). 그런 옮김은
        # 금지어 목록으로는 영원히 안 잡히니, **채택어를 고정점으로** 박는다.
        for word in ("여기서 세션 시작", "담당하는 것이 없습니다", "맡은 요청",
                     "문서 지목 해제", "계정 지우기", "화면 기능",
                     "이 버튼이 다시 생깁니다", "선행 작업",
                     "worktree", "commit 하면", "push 하는 것도"):
            self.assertIn(word, joined,
                          "채택어 「%s」가 화면 어디에도 없다" % word)


class TheAutoNameOnlyStandsWhereItIsTrue(unittest.TestCase):
    """「자동 작업」은 **뜻 A 로 판정된 자리에만** 선다 (DOC-20260831-005).

    위 게이트가 낱말째 막는 것과 달리, 여기는 허용 목록으로 뒤집혀 있다 —
    까닭은 KEPT_AUTO 곁에 적었다. 화면을 읽는 자리는 `_surfaces()` 한 곳으로
    같이 쓴다: 훑는 눈이 두 벌이면 한 벌만 고쳐진다.
    """

    @classmethod
    def setUpClass(cls):
        cls.surfaces = _surfaces()

    def test_the_name_never_stands_for_what_is_running_now(self):
        """지금 도는 것을 「자동 작업」이라 부르는 자리가 0이다."""
        hits = []
        for name, text in self.surfaces.items():
            rest = text
            for ok in KEPT_AUTO:
                rest = rest.replace(ok, " ")
            if "자동 작업" in rest:
                for line in rest.splitlines():
                    if "자동 작업" in line:
                        hits.append("%s: %s" % (name, line.strip()[:80]))
        self.assertEqual(
            [], hits,
            "지금 도는 것을 「자동 작업」이라 부르는 자리가 남았다 — 지금 도는 "
            "것은 「백그라운드 작업」이고 「자동·저절로」는 미래·정책 서술에만 쓴다 "
            "(DOC-20260831-005). 뜻 A 로 참인 새 문장이라면 근거와 함께 "
            "KEPT_AUTO 에 올려라:\n  " + "\n  ".join(hits))

    def test_the_kept_twelve_are_still_standing(self):
        """유지 판정 자리가 **화면에 살아 있다** — 허용 목록에서 뺀 것만으로는
        지워지지 않았다는 증거가 못 된다(위 유지어 시험이 세운 그 규율)."""
        joined = "\n".join(self.surfaces.values())
        for kept in KEPT_AUTO:
            self.assertIn(kept.strip(), joined,
                          "유지 판정 문장 「%s」가 화면에서 사라졌다 — 걷어낼 "
                          "자리가 아니었다" % kept.strip())

    def test_the_new_words_actually_stand(self):
        """신설어가 실제로 서 있다 — 지우기만 하고 안 채우면 문장이 사라진다."""
        joined = "\n".join(self.surfaces.values())
        for word in ("백그라운드 작업", "이어받", "도는 일 ",
                     "자동 이어받기 끄기"):
            self.assertIn(word, joined,
                          "채택어 「%s」가 화면 어디에도 없다" % word.strip())

    def test_the_long_running_line_has_no_subject(self):
        """카드 사실 줄은 **무주어**다 — 「오래 걸림 · 18분째」.

        주체를 알아도 이 줄의 결정(「중단하고 다시 맡길까」)이 안 바뀌고,
        신원은 점과 툴팁의 몫이라고 이 화면이 이미 정해 뒀다(REQ-20260830-040).
        이름만 「무인 작업」으로 갈아 끼우고 자리를 그대로 두면 규범 위반이
        그대로 남는다 — 그래서 캡션 바로 뒤에 주체 낱말이 오는지 못박는다."""
        card = self.surfaces["app/card.js"]
        self.assertIn(">오래 걸림</span>", card, "「오래 걸림」 캡션이 사라졌다")
        for bad in (">오래 걸림</span>자동 작업", ">오래 걸림</span>무인 작업",
                    ">오래 걸림</span>백그라운드 작업"):
            self.assertNotIn(bad, card,
                             "사실 줄 본문이 주체를 다시 세웠다 (%s) — 신원은 "
                             "점과 툴팁의 몫이다" % bad)

    def test_the_stop_hold_button_speaks_policy_grammar(self):
        """정책 단추는 정책 문법(자동 OO 끄기)으로 선다 (REQ-20260901-005 3차).

        옛 이름 두 벌이 되살아나지 않는 것도 여기서 함께 잰다 — 1차는 개체
        오칭, 2차는 부정형 데뷔·무주어가 반려 사유였다."""
        card = self.surfaces["app/card.js"]
        self.assertIn("자동 이어받기 끄기", card)
        self.assertNotIn("자동 작업 중단해 두기", card,
                         "1차 반려 이름이 되살아났다 (DOC-20260831-005 로 개정)")

    def test_the_forecast_line_shares_the_buttons_gate(self):
        """예고 줄과 정책 단추는 **한 관문**이다 (REQ-20260901-005 designer 1안).

        holdForecastHTML 이 제 조건을 지으면 줄만 서고 단추가 없는(또는 그
        반대) 화면이 언젠가 생긴다 — 조건은 holdLockHTML 하나에서만 나온다."""
        with open(os.path.join(WEB, "app", "card.js"), encoding="utf-8") as f:
            raw = f.read()
        m = re.search(r"function holdForecastHTML\(r\)\{([\s\S]*?)\n\}", raw)
        self.assertTrue(m, "예고 줄 함수가 없다")
        body = m.group(1)
        self.assertIn("holdLockHTML(", body, "예고 줄이 단추의 관문을 안 쓴다")
        for own in ("stoppable", "heldState", "status"):
            self.assertNotIn(own, body,
                             "예고 줄이 제 조건을 지었다 — 관문이 둘이다: %s" % own)
        # 낭독기에도 같은 짝이 들린다 — 단추가 줄을 가리킨다.
        self.assertIn('aria-describedby="pol-fore"', raw,
                      "단추가 예고 줄을 가리키지 않는다")
        self.assertIn('id="pol-fore"', body, "예고 줄에 짝의 이름표가 없다")
        # 문서 화면이 실제로 그 줄을 세운다.
        with open(os.path.join(WEB, "app", "docs.js"), encoding="utf-8") as f:
            docs = f.read()
        self.assertIn("holdForecastHTML(stallDoc)", docs,
                      "문서 화면이 예고 줄을 안 부른다")

    def test_nobody_stops_things_here_except_people(self):
        """「누군가」(중단 주어)는 폐기 — 이 화면에서 중단하는 것은 사람뿐이다."""
        for name, text in self.surfaces.items():
            self.assertNotIn("누군가", text,
                             "%s 에 모르는 주어가 남았다 — 「사람이」로" % name)


if __name__ == "__main__":
    unittest.main()
