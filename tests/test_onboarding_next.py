"""사용법 안내(onboarding) 요청은 세션이 집지 않는다 (REQ-20260914-011-62x6).

첫 실행이 general 에 안내 요청 일곱을 open 으로 심는다. 그 카드는 사람이 읽고
따라 하는 것인데, `s9 code` 가 넣는 기동 프롬프트는 첫 세션에 「`s9 next` 로
이어받을 것이 나오면 `s9 claim` 으로 집으라」고 시킨다 — `here_requests` 가
안내 카드를 후보로 내면 첫 세션이 「안내 1 — 이 보드 읽는 법」을 집어 작업하려
든다(옛 안내 3건도 같았다). 계약: tags 에 onboarding 이 있으면 `here_requests`
의 목록에 오르지 않고, 같은 조건의 보통 요청은 오른다.
실행: python3 tests/ onboarding_next
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class OnboardingIsNotPickedUp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9onbnext-")
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        cls.env.update({"S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                        "S9_USER": "tester"})
        cls.cli("init")
        cls.cli("user", "add", "tester")
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_onbnext", importlib.machinery.SourceFileLoader("s9_onbnext", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=cls.env, stdin=subprocess.DEVNULL, timeout=30)

    def new(self, title, tags=None):
        r = self.cli("new", "request", "--title", title, "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b", "--any-machine")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rid = r.stdout.split()[0]
        if tags:
            path = self.m.locate(rid)
            meta, body = self.m.read_doc(path)
            meta["tags"] = list(tags)
            self.m.write_doc(path, meta, body)
            self.m.rebuild_index(quiet=True)
        return rid

    def here(self):
        return {r["id"] for r in self.m.here_requests(platform="Linux",
                                                      machine="testbox", user="tester")}

    # 정상 — 보통 요청은 오른다 (회귀)
    def test_a_plain_open_request_is_here(self):
        rid = self.new("보통 요청")
        self.assertIn(rid, self.here())

    # 계약 — 안내 요청은 오르지 않는다
    def test_an_onboarding_request_is_not_here(self):
        rid = self.new("안내 1 — 이 보드 읽는 법", tags=["onboarding"])
        self.assertNotIn(rid, self.here(),
                         "안내 카드가 집을 후보에 올랐다 — 첫 세션이 그것을 집어 작업하려 든다")

    # 경계 — 다른 태그와 함께 있어도 onboarding 이면 빠진다
    def test_onboarding_among_other_tags_is_still_skipped(self):
        rid = self.new("안내 6 — GitHub 잇기", tags=["docs", "onboarding"])
        self.assertNotIn(rid, self.here())


if __name__ == "__main__":
    unittest.main()
