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


if __name__ == "__main__":
    unittest.main()
