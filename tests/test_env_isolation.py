"""파일 사이의 환경 격리 — 앞이 두고 간 것이 뒤를 흔들지 않는다 (REQ-20260904-002).

`os.environ` 은 프로세스 전체의 것인데 순차 실행은 297개 파일을 한 프로세스에서
돈다. 실측(2026-09-04): `S9_USER` 하나를 두고 간 파일 셋이 각각 test_jobfile 의
귀속 시험을 넘어뜨렸고, 전체 실행마다 붉은 파일의 **조합이 달라졌다**.

여기서 재는 것은 러너의 되돌림이 **클래스 경계에서만** 도는가다 — 시험마다
되돌리면 `setUpClass` 로 세운 값이 첫 시험 뒤에 사라져 멀쩡한 파일이 깨진다.

실행: python3 tests/ env_isolation
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def runner():
    """러너를 모듈로 집는다 — `python3 tests/` 가 아니라 그 안의 함수를 잰다."""
    loader = importlib.machinery.SourceFileLoader(
        "s9runner_t", os.path.join(HERE, "__main__.py"))
    spec = importlib.util.spec_from_loader("s9runner_t", loader)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = runner()


class Restore(unittest.TestCase):
    """되돌림 자체 — 무엇을 되살리고 무엇을 두는가."""

    def setUp(self):
        self._saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_b1_a_deleted_key_comes_back(self):
        os.environ["S9_ZZ_TEST"] = "base"
        base = R.env_baseline()
        del os.environ["S9_ZZ_TEST"]
        R.env_restore(base)
        self.assertEqual(os.environ.get("S9_ZZ_TEST"), "base")

    def test_a_leaked_key_goes_away(self):
        base = R.env_baseline()
        os.environ["S9_ZZ_LEAK"] = "alice"
        R.env_restore(base)
        self.assertIsNone(os.environ.get("S9_ZZ_LEAK"))

    def test_a_changed_key_goes_back(self):
        os.environ["S9_ZZ_TEST"] = "base"
        base = R.env_baseline()
        os.environ["S9_ZZ_TEST"] = "moved"
        R.env_restore(base)
        self.assertEqual(os.environ["S9_ZZ_TEST"], "base")

    def test_b2_foreign_keys_are_untouched(self):
        """S9_ 밖은 우리 것이 아니다 — PATH 를 되돌리면 그 프로세스가 죽는다."""
        base = R.env_baseline()
        os.environ["ZZ_NOT_OURS"] = "keep"
        R.env_restore(base)
        self.assertEqual(os.environ.get("ZZ_NOT_OURS"), "keep")


class ClassBoundary(unittest.TestCase):
    """경계 판정 — 클래스가 바뀔 때**만** 되돌린다."""

    class _Res:
        """unittest 이 경계에서 만지는 최소한의 것만 흉내 낸다."""
        _previousTestClass = None
        _moduleSetUpFailed = False

    def suite_with(self, baseline):
        s = R.EnvIsolatingSuite()
        s.baseline = baseline
        return s

    def test_n1_a_new_class_gets_the_baseline_back(self):
        """앞 클래스가 두고 간 S9_USER 를 뒤 클래스가 물려받지 않는다."""
        saved = os.environ.get("S9_USER")
        try:
            os.environ.pop("S9_USER", None)
            base = R.env_baseline()
            os.environ["S9_USER"] = "alice"          # 앞 클래스가 두고 갔다
            res = self._Res()
            res._previousTestClass = Restore         # 다른 클래스였다
            s = self.suite_with(base)
            s._handleClassSetUp(self, res)           # 경계를 넘는다
            self.assertIsNone(os.environ.get("S9_USER"),
                              "앞이 두고 간 값이 뒤로 넘어왔다")
        finally:
            if saved is None:
                os.environ.pop("S9_USER", None)
            else:
                os.environ["S9_USER"] = saved

    def test_n2_same_class_keeps_what_setupclass_set(self):
        """같은 클래스가 이어지면 되돌리지 않는다 — 안 그러면 setUpClass 가 헛돈다."""
        saved = os.environ.get("S9_ZZ_CLS")
        try:
            os.environ.pop("S9_ZZ_CLS", None)
            base = R.env_baseline()
            os.environ["S9_ZZ_CLS"] = "set-by-setupclass"
            res = self._Res()
            res._previousTestClass = self.__class__   # 같은 클래스가 이어진다
            s = self.suite_with(base)
            s._handleClassSetUp(self, res)
            self.assertEqual(os.environ.get("S9_ZZ_CLS"), "set-by-setupclass",
                             "같은 클래스 안에서 setUpClass 의 값이 지워졌다")
        finally:
            if saved is None:
                os.environ.pop("S9_ZZ_CLS", None)
            else:
                os.environ["S9_ZZ_CLS"] = saved

    def test_b3_no_baseline_means_no_restore(self):
        """기준선이 없으면(안쪽 실행 등) 아무것도 하지 않는다."""
        os.environ["S9_ZZ_NOBASE"] = "x"
        try:
            s = R.EnvIsolatingSuite()
            res = self._Res()
            res._previousTestClass = Restore
            s._handleClassSetUp(self, res)
            self.assertEqual(os.environ.get("S9_ZZ_NOBASE"), "x")
        finally:
            os.environ.pop("S9_ZZ_NOBASE", None)


class TheSuiteIsWired(unittest.TestCase):
    """discover() 가 실제로 이 스위트를 돌려주는가 — 안 그러면 위 계약이 죽은 글자다."""

    def test_discover_returns_the_isolating_suite(self):
        suite, _empty = R.discover(["test_env_isolation.py"])
        self.assertIsInstance(suite, R.EnvIsolatingSuite)


if __name__ == "__main__":
    unittest.main(verbosity=2)
