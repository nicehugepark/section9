"""가이드의 「저장소」 절 — 화면과 같은 말을 하는가 (REQ-20260902-012-62x6).

REQ-20260901-023 이 Settings 에 「저장소」 판(pull·push)을 세웠는데 사용자
가이드 두 벌(`web/guide.html` · `docs/guide.md`)에는 그 판이 없었다. 문서는
코드와 함께 늙는다 — 그래서 이 시험의 계약은 "그 절이 있는가"가 아니라
**"그 절이 서버의 판정과 같은 말을 하는가"** 다.

  ① 단추가 잠기는 사유는 **서버 한 곳**(`git_can`)에만 산다. 그 함수가 둘 다
     잠그는 조건을 **일곱** 넘게 갖게 되면 이 시험이 먼저 깨진다 — 가이드가
     여섯 개만 적은 채 조용히 낡는 것을 막는 자리다.
  ② 일곱 사유 각각의 핵심 조각이 **서버가 실제로 짓는 문장 안에 있고**, 동시에
     가이드 두 벌 안에도 있다. `GIT_SAY` 를 고치면 서버 쪽 대조가 먼저 깨지므로,
     화면 문구와 가이드가 갈릴 수 없다.
  ③ 한쪽만 잠기는 자리 셋(pull 의 고치던 파일·pull 할 것 없음, push 할 것 없음)도
     같은 방식으로 잰다.
  ④ `docs/guide.md` 는 `web/guide.html` 의 파생물이다 — 원본만 고치고
     `bin/s9-guide-md` 재실행을 잊으면 두 벌이 갈린다. 재생성 결과와 **글자까지**
     같은지 본다.
  ⑤ 낱말 규율 (REQ-20260902-002): `pull`·`push`·`commit`·`git` 은 원어로 서고,
     음차(「푸시」·「커밋」)와 옮김(「받기」·「올리기」·「동기화」)은 0건이다.
     반대로 「저장소」·「갈래」·「고치던 파일」·「도는 일」은 우리 말로 남는다 —
     무차별 원어도 같은 결함이다.

픽셀은 단위 시험이 못 본다. 실제 렌더는 사람의 캡처 확인 몫이다.

실행: python3 tests/ guide_repo
"""
import ast
import importlib.machinery
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
S9 = os.path.join(ROOT, "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
GEN = os.path.join(ROOT, "bin", "s9-guide-md")
HTML = os.path.join(ROOT, "web", "guide.html")
MD = os.path.join(ROOT, "docs", "guide.md")

# 절의 경계 — 두 벌에서 「저장소」 절만 떼어 본다. 낱말 규율은 이 절 안에서만
# 잰다(가이드의 다른 장은 제 사정이 있고, 이 REQ 가 손댄 자리가 아니다).
HTML_FROM, HTML_TO = '<h3 id="s-repo"', '<h3 id="s-project"'
MD_FROM, MD_TO = "### Settings › 저장소", "### 프로젝트 정보 패널"


def _load_s9():
    """bin/s9 를 모듈로 읽는다 — 사유 문장을 **서버가 짓는 그대로** 받기 위해."""
    tmp = tempfile.mkdtemp(prefix="s9guide-")
    keys = ("S9_ROOT", "S9_MACHINE", "S9_USER")
    prev = {k: os.environ.get(k) for k in keys}
    os.environ.update({"S9_ROOT": tmp, "S9_MACHINE": "testbox",
                       "S9_USER": "tester"})
    try:
        spec = importlib.util.spec_from_loader(
            "s9_mod_guide",
            importlib.machinery.SourceFileLoader("s9_mod_guide", S9))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


S9MOD = _load_s9()


def _base_state(**over):
    """열린 상태 — 여기서 한 칸씩 뒤집어 사유 하나씩을 만든다."""
    st = {"repo": True, "branch": "main", "upstream": "origin/main",
          "remote": "origin", "ahead": 1, "behind": 0, "dirty": [],
          "dirty_n": 0, "jobs": 0, "admin": True,
          "remote_ok": True, "remote_error": ""}
    st.update(over)
    return st


# 둘 다 잠그는 일곱 — (이름, 상태를 뒤집는 값, 대리 시점, 가이드에 서야 할 조각).
# 조각은 **서버 문장 안에도** 있어야 한다(setUp 이 그것부터 잰다).
BOTH = [
    ("저장소가 아님", {"repo": False}, "",
     "이 자리는 git 저장소가 아닙니다"),
    ("짝지은 갈래 없음", {"upstream": ""}, "",
     "GitHub 의 어느 갈래와도 짝지어 두지 않았습니다"),
    ("남의 시점", {}, "someone",
     "시점으로 보는 중입니다"),
    ("admin 아님", {"admin": False}, "",
     "저장소를 바꾸는 일은 admin 만 합니다"),
    ("갈래 갈림", {"ahead": 3, "behind": 2}, "",
     "여기와 GitHub 에 각각 새 commit 이 있습니다"),
    ("도는 일", {"jobs": 2}, "",
     "지금 도는 일"),
    ("GitHub 에 못 물음", {"remote_ok": False,
                           "remote_error": "GitHub 에 묻지 못했습니다 — x"}, "",
     "GitHub 에 묻지 못했습니다"),
]

# 한쪽만 잠기는 셋 — (이름, 상태, 잠기는 쪽, 열려 있어야 하는 쪽, 조각)
ONE_SIDED = [
    ("고치던 파일", {"ahead": 1, "behind": 0, "dirty_n": 12},
     "pull", "push", "고치던 파일이"),
    ("pull 할 것 없음", {"ahead": 1, "behind": 0}, "pull", "push",
     "pull 할 것이 없습니다"),
    ("push 할 것 없음", {"ahead": 0, "behind": 1}, "push", "pull",
     "push 할 것이 없습니다"),
]

FORBIDDEN = ["푸시", "커밋", "리베이스", "머지", "클론", "리모트", "워크트리",
             "리포지토리", "리포지터리", "동기화", "브랜치"]
# 「주고받기」는 판의 덩이 이름이라 그 안의 '받기' 는 사유가 아니다.
FORBIDDEN_RE = [r"(?<!주고)받기", r"올리기"]
NATIVE = ["저장소", "갈래", "고치던 파일", "도는 일"]
VERBATIM = ["pull", "push", "commit", "git", "origin/main", "GitHub"]


def _section(text, start, end):
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


class TestGuideRepoSection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(HTML, encoding="utf-8").read()
        cls.md = io.open(MD, encoding="utf-8").read()
        cls.h_sec = _section(cls.html, HTML_FROM, HTML_TO)
        cls.m_sec = _section(cls.md, MD_FROM, MD_TO)

    # ── ① 사유의 개수가 코드에 몇 개인가 ──────────────────────────────
    def test_test_guide_repo_section(self):
        """TestGuideRepoSection 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("both_gate_has_exactly_seven"):
                tree = ast.parse(io.open(S9_SRC, encoding="utf-8").read())
                fn = next(n for n in ast.walk(tree)
                          if isinstance(n, ast.FunctionDef) and n.name == "git_can")
                both = next(n.value for n in fn.body
                            if isinstance(n, ast.Assign)
                            and getattr(n.targets[0], "id", "") == "both")
                self.assertIsInstance(both, ast.List)
                self.assertEqual(len(both.elts), 7,
                                 "둘 다 잠그는 사유가 7개가 아니다 — 가이드의 "
                                 "「단추가 잠기는 이유」도 함께 고쳐야 한다")

            # ── ② 일곱이 서버 문장과 가이드 두 벌에 함께 서 있는가 ────────────
        with self.subTest("seven_reasons_match_server_and_both_guides"):
            for name, over, proxy, frag in BOTH:
                with self.subTest(name):
                    can = S9MOD.git_can(_base_state(**over), proxy_for=proxy)
                    self.assertFalse(can["pull"]["ok"], "%s: pull 이 열려 있다" % name)
                    self.assertFalse(can["push"]["ok"], "%s: push 가 열려 있다" % name)
                    self.assertIn(frag, can["pull"]["why"],
                                  "%s: 서버 문장이 바뀌었다 — 가이드도 함께" % name)
                    self.assertIn(frag, can["push"]["why"])
                    self.assertIn(frag, self.h_sec, "%s: guide.html 에 없다" % name)
                    self.assertIn(frag, self.m_sec, "%s: guide.md 에 없다" % name)
        with self.subTest("one_sided_reasons_match_server_and_both_guides"):
            for name, over, locked, open_side, frag in ONE_SIDED:
                with self.subTest(name):
                    can = S9MOD.git_can(_base_state(**over))
                    self.assertFalse(can[locked]["ok"],
                                     "%s: %s 가 열려 있다" % (name, locked))
                    self.assertTrue(can[open_side]["ok"],
                                    "%s: %s 까지 잠겼다" % (name, open_side))
                    self.assertIn(frag, can[locked]["why"])
                    self.assertIn(frag, self.h_sec, "%s: guide.html 에 없다" % name)
                    self.assertIn(frag, self.m_sec, "%s: guide.md 에 없다" % name)
        with self.subTest("network_timeout_number_is_the_code_number"):
                n = S9MOD.GIT_NET_TIMEOUT
                for label, sec in (("guide.html", self.h_sec), ("guide.md", self.m_sec)):
                    self.assertIn("%d초" % n, sec,
                                  "%s: 대기 시간이 코드(%d초)와 다르다" % (label, n))

            # ── ③ 낱말 규율 ────────────────────────────────────────────────────
        with self.subTest("word_discipline"):
                for label, sec in (("guide.html", self.h_sec), ("guide.md", self.m_sec)):
                    for bad in FORBIDDEN:
                        self.assertNotIn(bad, sec,
                                         "%s: 「%s」 — 원어로 세울 낱말이다" % (label, bad))
                    for pat in FORBIDDEN_RE:
                        self.assertIsNone(re.search(pat, sec),
                                          "%s: /%s/ — 원어로 세울 낱말이다" % (label, pat))
                    for word in VERBATIM:
                        self.assertIn(word, sec, "%s: `%s` 가 없다" % (label, word))
                    for word in NATIVE:
                        self.assertIn(word, sec,
                                      "%s: 「%s」 는 우리 말로 남는다 — 무차별 원어도 "
                                      "결함이다" % (label, word))

            # ── ④ 두 벌이 갈리지 않는가 ────────────────────────────────────────
        with self.subTest("md_is_regenerated_from_html"):
            with tempfile.TemporaryDirectory(prefix="s9guidemd-") as tmp:
                out = os.path.join(tmp, "guide.md")
                r = subprocess.run([sys.executable, GEN, "--src", HTML,
                                    "--out", out],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                fresh = io.open(out, encoding="utf-8").read()
            self.assertEqual(self.md, fresh,
                             "docs/guide.md 가 web/guide.html 과 갈렸다 — "
                             "`bin/s9-guide-md` 를 다시 돌려라")
        with self.subTest("tables_stay_tables"):
            n_html = self.html.count("<table")
            heads = [ln for ln in self.md.splitlines()
                     if ln.startswith("|") and set(ln) <= set("| -")]
            self.assertEqual(len(heads), n_html,
                             "html 의 표 %d 개 중 md 에서 표로 선 것은 %d 개다"
                             % (n_html, len(heads)))
            self.assertIn("| 점 | 의미 | 해석 |", self.md,
                          "3장 「실시간 신호 읽기」 표가 다시 뭉갰다")
        with self.subTest("toc_has_the_section"):
            self.assertIn('href="#s-repo"', self.html,
                          "좌측 목차에서 「저장소」 절로 갈 수 없다")

if __name__ == "__main__":
    unittest.main()
