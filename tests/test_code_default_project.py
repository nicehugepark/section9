"""사람이 치는 것은 install 과 code 둘뿐이다 (REQ-20260908-031-62x6).

주인 물음(2026-09-08 13:01): 「사용자는 실제로 설치할 때 s9-install, s9 code
이거 두개만 실행하지 않나? 이 상황에서 사용자가 추가되는 경우 기본 프로젝트에
붙는것맞지?」 — 그때는 아니었다.

`s9-install` 은 `s9 init` 을 부르지만 그 시점에는 등록된 사람이 없어
`ensure_default_project` 가 아무 일도 하지 않는다(REQ-20260908-027: 설치가
신원을 지어내면 안 된다). 그래서 첫 요청이 프로젝트 없이 남았다.

신원이 정해지는 순간이 프로젝트가 설 수 있는 첫 순간이다 — `s9 code` 의 첫
실행 등록 바로 뒤가 그 자리다. 이 파일은 그 이음을 잰다: 소스 글자가 아니라
**함수를 불러** 잰다.

실행: python3 tests/ code_default_project
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9.py")


def load(root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            "s9_cdp_%d" % abs(hash(root)),
            importlib.machinery.SourceFileLoader("s9_cdp_%d" % abs(hash(root)), S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class TheProjectStandsWhenTheIdentityDoes(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cdp-")
        self.m = load(self.root)
        self.m.cmd_init(type("A", (), {})())

    def test_install_alone_leaves_no_project(self):
        """정상 — 설치만으로는 안 선다. 설치가 신원을 지어내지 않기 때문이다."""
        self.assertEqual(self.m.ensure_default_project(), "")
        self.assertEqual(self.m.all_projects(), [])

    def test_the_identity_makes_it_stand(self):
        """실패 자리 — 사람이 등록되면 그 자리에서 선다(s9 code 의 첫 실행)."""
        self.m.do_user_add("hong", role="admin")
        self.assertEqual(self.m.ensure_default_project(), self.m.DEFAULT_PROJECT_SLUG)
        self.assertEqual(len(self.m.all_projects()), 1)

    def test_calling_it_twice_does_nothing(self):
        """경계 — 멱등. `s9 code` 는 매번 도는 자리라 두 번째부터는 조용해야 한다."""
        self.m.do_user_add("hong", role="admin")
        self.m.ensure_default_project()
        self.assertEqual(self.m.ensure_default_project(), "")
        self.assertEqual(len(self.m.all_projects()), 1)

    def test_the_first_request_lands_in_it(self):
        """정상 — 그 뒤 첫 요청이 미정 없이 붙는다(이 요청의 전부)."""
        self.m.do_user_add("hong", role="admin")
        self.m.ensure_default_project()
        args = type("A", (), {"project": None, "project_tag": None,
                              "doc_type": "request"})()
        got = self.m.resolve_project(args, "hong", "")
        proj = got[0] if isinstance(got, tuple) else got
        self.assertEqual(proj, self.m.DEFAULT_PROJECT_SLUG)


class TheGuideStandsWithTheProject(unittest.TestCase):
    """기본 프로젝트가 처음 설 때 사용법 안내 요청이 함께 선다 (REQ-20260908-028).

    주인 2026-09-08: 「기본 프로젝트에는 기본적으로 제공되는 open 상태의 요청이
    존재하는데 사실상 설명서들이 될 것이다 … 설치하자마자 바로 이해를 할 수 있을
    것 아닌가.」 설치한 사람이 처음 보는 보드에 읽을 것이 있어야 한다.
    글은 harness/common/onboarding/*.md 에서 온다 (REQ-20260914-011-62x6) — 여기서는
    가짜 파일 둘로 **함께 선다**는 것만 잰다; 심는 기계는 test_onboarding_seed 가 잰다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cdp-g-")
        self.m = load(self.root)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.m.ONBOARDING_DIR = os.path.join(self.root, "fake-onboarding")
        os.makedirs(self.m.ONBOARDING_DIR)
        for name, title in (("01-a.md", "첫 화면 읽기"), ("02-b.md", "요청 만들기")):
            with open(os.path.join(self.m.ONBOARDING_DIR, name), "w", encoding="utf-8") as f:
                f.write(f"---\ntitle: {title}\nsummary: {title}\ngoal: {title} 를 해 본다\n"
                        f"size: S\ntags: [onboarding]\n---\n## Original\n\n{title} 본문\n")

    def _guides(self):
        out = []
        for dp, _dn, fns in os.walk(os.path.join(self.root, "vault", "requests")):
            for fn in fns:
                if fn.endswith(".md"):
                    meta, body = self.m.read_doc(os.path.join(dp, fn))
                    if "onboarding" in (meta.get("tags") or []):
                        out.append((meta, body))
        return out

    def test_g1_guides_stand_open_in_the_default_project(self):
        slug = self.m.ensure_default_project()
        self.assertEqual(slug, self.m.DEFAULT_PROJECT_SLUG)
        guides = self._guides()
        self.assertEqual(len(guides), 2, "안내 요청이 서지 않았다")
        for meta, body in guides:
            self.assertEqual(meta.get("status"), "open", meta.get("title"))
            self.assertEqual(meta.get("project"), slug, meta.get("title"))
            self.assertTrue(meta.get("goal"), f"goal 이 없다: {meta.get('title')}")
            self.assertEqual(meta.get("user"), "hong")
            self.assertIn("## Original", body)

    def test_g2_calling_twice_does_not_double_the_guides(self):
        self.m.ensure_default_project()
        self.m.ensure_default_project()
        self.assertEqual(len(self._guides()), 2)

    def test_g3_an_existing_project_gets_no_guides(self):
        """옛 설치에 소급하지 않는다 — 프로젝트가 이미 있으면 안내도 서지 않는다."""
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")
        self.assertEqual(self.m.ensure_default_project(), "")
        self.assertEqual(self._guides(), [])


if __name__ == "__main__":
    unittest.main()
