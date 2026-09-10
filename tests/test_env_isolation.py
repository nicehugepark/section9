"""파일 사이의 환경 격리 — 앞이 두고 간 것이 뒤를 흔들지 않는다 (REQ-20260904-002).

`os.environ` 은 프로세스 전체의 것인데 순차 실행은 297개 파일을 한 프로세스에서
돈다. 실측(2026-09-04): `S9_USER` 하나를 두고 간 파일 셋이 각각 test_jobfile 의
귀속 시험을 넘어뜨렸고, 전체 실행마다 실패한 파일의 **조합이 달라졌다**.

여기서 재는 것은 러너의 되돌림이 **클래스 경계에서만** 도는가다 — 시험마다
되돌리면 `setUpClass` 로 세운 값이 첫 시험 뒤에 사라져 멀쩡한 파일이 깨진다.

실행: python3 tests/ env_isolation
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid

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


class CallerEnvelopeIsScrubbed(unittest.TestCase):
    """부른 쪽의 s9 봉투는 시험에 물려주지 않는다 (REQ-20260910-004).

    무인 재작업 워커가 `S9_USER=<담당자>`·`S9_JOB_REQ=<REQ>`·`S9_AUTO_RESUME=1`
    을 실어 띄우면, 임시 뿌리에 제 사용자·제 요청을 세우는 시험들이 그 뿌리에
    없는 이름을 현재 사용자로 받고(`ensure_default_project` → ''), 새 요청이
    전부 origin=derived 로 선다. 실측 2026-09-10: 워커 안에서만 19파일 56건이
    졌고 같은 tree 를 사람이 돌리면 통과했다. 걷은 값은 사라지지 않는다 —
    알림은 그 앞에 뜬 사본을, 잡 파일은 `start(req=…)` 를 쓴다."""

    def setUp(self):
        self._saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_i1_the_whole_worker_envelope_is_taken_out(self):
        env = {"S9_USER": "nicehugepark", "S9_JOB_REQ": "REQ-20260910-004",
               "S9_AUTO_RESUME": "1", "PATH": "/x"}
        taken = R.scrub_caller_envelope(env)
        self.assertEqual(taken, {"S9_USER": "nicehugepark",
                                 "S9_JOB_REQ": "REQ-20260910-004",
                                 "S9_AUTO_RESUME": "1"})
        self.assertEqual(env, {"PATH": "/x"})

    def test_i2_the_session_stays(self):
        """세션은 사람의 실행에도 있다 — 걷으면 잡 카드가 세션 귀속을 잃는다."""
        env = {"S9_USER": "u", "S9_SESSION": "abcd1234"}
        R.scrub_caller_envelope(env)
        self.assertEqual(env, {"S9_SESSION": "abcd1234"})

    def test_i3_nothing_to_take_is_not_an_error(self):
        env = {"PATH": "/x"}
        self.assertEqual(R.scrub_caller_envelope(env), {})
        self.assertEqual(env, {"PATH": "/x"})

    def test_i4_the_default_target_is_the_process_environment(self):
        os.environ["S9_USER"] = "zz-worker-owner"
        os.environ.pop("S9_JOB_REQ", None)
        os.environ.pop("S9_AUTO_RESUME", None)
        self.assertEqual(R.scrub_caller_envelope(), {"S9_USER": "zz-worker-owner"})
        self.assertIsNone(os.environ.get("S9_USER"))

    def test_i5_the_runner_scrubs_after_taking_the_notify_copy(self):
        """순서가 뒤집히면 알림이 담당자 이름을 잃는다 — 소스에서 잰다."""
        with open(os.path.join(HERE, "__main__.py"), encoding="utf-8") as f:
            src = f.read()
        take = src.index("async_notify.take_env()")
        scrub = src.index("scrub_caller_envelope()")
        self.assertLess(take, scrub, "봉투를 알림 사본보다 먼저 걷었다")

    def test_i6_the_job_declaration_survives_as_a_value(self):
        """걷은 S9_JOB_REQ 가 잡 파일에 값으로 닿는다 — 카드의 귀속이 끊기지 않는다."""
        import jobfile
        root = tempfile.mkdtemp(prefix="s9envjob-")
        try:
            os.environ.pop("S9_TESTS_NESTED", None)
            os.environ.pop("S9_JOB_REQ", None)     # 환경에는 없다(걷힌 뒤)
            _bump, clear = jobfile.start(1, root=root, req="REQ-20260910-004")
            with open(os.path.join(root, "state", "jobs",
                                   "tests-%d.json" % os.getpid()),
                      encoding="utf-8") as f:
                self.assertEqual(json.load(f)["req"], "REQ-20260910-004")
            clear()
        finally:
            shutil.rmtree(root, ignore_errors=True)


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


class PerModuleBaseline(unittest.TestCase):
    """모듈마다 기준선 (REQ-20260908-062) — 먼저 import 된 모듈이 남의 뿌리를 보지 않는다.

    서른 남짓한 파일이 모듈 최상위에서 `os.environ["S9_ROOT"]` 로 제 임시 뿌리를
    세운다. 기준선이 프로세스에 하나면 그 값은 마지막으로 import 된 모듈의 것이라,
    앞 모듈의 클래스는 경계를 넘을 때마다 남의 뿌리로 되돌려졌다 —
    test_async_result_notify 가 전체 실행에서만 지던 까닭(REQ-20260908-060).
    """

    SRC = """import os, unittest
MY_ROOT = {root!r}
os.environ["S9_ROOT"] = MY_ROOT
{extra}

class T(unittest.TestCase):
    def test_sees_own_root(self):
        self.assertEqual(os.environ.get("S9_ROOT"), MY_ROOT)

    def test_session_is_what_this_module_left(self):
        self.assertEqual(os.environ.get("S9_SESSION"), {session!r})
"""
    LEAK = "zz-leak-from-a"

    def setUp(self):
        self._saved = dict(os.environ)
        self._mods = set(sys.modules)
        self._path = list(sys.path)
        self.dir = tempfile.mkdtemp(prefix="s9envmod-")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)
        for k in [k for k in sys.modules if k not in self._mods]:
            del sys.modules[k]
        sys.path[:] = self._path
        shutil.rmtree(self.dir, ignore_errors=True)

    def two_modules(self):
        """a 는 뿌리와 S9_SESSION 을 남기고, b 는 뿌리만 세운다. 이름순으로
        a 가 먼저 import 된다 — 기준선이 하나면 a 가 b 의 뿌리를 본다."""
        tag = uuid.uuid4().hex[:8]
        names = []
        outside = os.environ.get("S9_SESSION")      # b 가 볼 값 = discovery 전의 것
        for who, extra, session in (
                ("a", f'os.environ["S9_SESSION"] = {self.LEAK!r}', self.LEAK),
                ("b", "", outside)):
            name = f"test_zz_pm_{tag}_{who}"
            with open(os.path.join(self.dir, name + ".py"), "w",
                      encoding="utf-8") as f:
                f.write(self.SRC.format(root=f"/root-of-{who}-{tag}",
                                        extra=extra, session=session))
            names.append(name)
        return names

    def run_suite(self, suite):
        res = unittest.TestResult()
        suite.run(res)
        return res

    def test_m2_each_class_sees_its_own_modules_root(self):
        names = self.two_modules()
        suite, empty = R.discover(["test_zz_pm_*.py"], start=self.dir)
        self.assertEqual(empty, [])
        self.assertEqual(suite.countTestCases(), 4)
        self.assertEqual(set(suite.per_module), set(names),
                         "모듈마다 기준선이 찍히지 않았다 — import 자리의 감싸기가 안 걸렸다")
        res = self.run_suite(suite)
        self.assertTrue(res.wasSuccessful(),
                        [f for _, f in res.failures + res.errors])

    def test_m3_one_baseline_for_all_makes_the_first_module_fail(self):
        """고치기 전 동작을 그대로 흉내 낸다 — 기준선이 하나면 a 가 b 의 뿌리를 본다.
        이 시험이 지면 M2 는 아무것도 가려내지 못하는 시험이다."""
        self.two_modules()
        suite, _ = R.discover(["test_zz_pm_*.py"], start=self.dir)
        suite.per_module = None
        suite.baseline = R.env_baseline()      # discovery 뒤의 값 = 마지막 모듈의 것
        res = self.run_suite(suite)
        self.assertFalse(res.wasSuccessful(), "기준선이 하나인데도 통과했다")
        self.assertTrue(any("test_sees_own_root" in t.id() and t.id().endswith("_a.T.test_sees_own_root")
                            for t, _ in res.failures),
                        [t.id() for t, _ in res.failures])

    def test_m4_a_module_does_not_inherit_what_the_one_before_left(self):
        """a 가 남긴 S9_SESSION 을 b 는 보지 않는다 — 모듈마다 discovery 전 환경에서
        import 하므로 홀로 돌 때와 같은 환경이다."""
        names = self.two_modules()
        suite, _ = R.discover(["test_zz_pm_*.py"], start=self.dir)
        self.assertNotEqual(suite.per_module[names[1]].get("S9_SESSION"), self.LEAK)
        self.assertEqual(suite.per_module[names[0]].get("S9_SESSION"), self.LEAK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
