"""백그라운드 작업자가 어느 계정으로 뜨고, 한도에 막히면 무엇을 말하는가
(REQ-20260911-014).

실사고 2026-09-11: REQ-20260911-013 이 4시간 10분 멈춰 있었다. 워처는 제 할 일을
했다 — 16:14 에 집어 작업자를 띄웠고 그 뒤로도 여섯 번 띄웠다. 여섯 번 다 뜨자마자
죽었고 `state/auto_resume/<id>.log` 에 남은 것은 같은 줄 여섯 개였다:
「You've hit your weekly limit · resets Sep 13, 8pm」.

까닭 둘이 겹쳤다.
 ① 작업자는 서버 프로세스의 환경을 그대로 물려받는다(`env = dict(os.environ)`).
    서버는 보통 `CLAUDE_CONFIG_DIR` 없이 떠 있으므로 작업자는 **언제나 기본
    계정**이었다 — 사람이 토큰을 아끼려고 다른 계정으로 옮겨 두어도 그렇다.
 ② 즉사한 워커를 가르는 표(`_spawn_fail_kind`, REQ-20260903-018)에 **계정의
    한도**가 없었다. 그 줄은 `other` 로 떨어졌고 `other` 는 그 경로를 안 타므로,
    사유가 어디에도 안 서고 30초마다 같은 죽음이 되풀이됐다.

고치는 자리는 있는 기계 안이다 — 새 감시를 만들지 않는다.

실행: python3 tests/ worker_account
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
LIMIT_LINE = "You've hit your weekly limit · resets Sep 13, 8pm (Asia/Seoul)"


def _load(name):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TheWorkerWearsTheChosenAccount(unittest.TestCase):
    """① 사람이 고른 계정이 작업자에게 간다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9wacct-")
        cls.home = os.path.join(cls.tmp, "home")
        os.makedirs(cls.home, exist_ok=True)
        cls._prev = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_MACHINE", "S9_USER",
                               "S9_SESSION", "S9_REWORK_WATCH", "HOME",
                               "CLAUDE_CONFIG_DIR")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        os.environ["S9_REWORK_WATCH"] = "off"
        os.environ["HOME"] = cls.home
        os.environ.pop("S9_SESSION", None)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       timeout=20, stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "add", "tester"], capture_output=True,
                       text=True, timeout=20, stdin=subprocess.DEVNULL)
        cls.s9 = _load("s9_mod_wacct")

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # W1 — 고른 계정이 작업자가 받을 환경에 실린다
    def test_w1_the_chosen_account_reaches_the_worker_env(self):
        prof = os.path.join(self.home, ".claude-profiles", "claude04")
        os.makedirs(prof, exist_ok=True)
        self.s9._record_account_choice("tester", "claude04")
        env = {"PATH": "/usr/bin"}       # 서버가 물려주는 그 환경 — 계정 없음
        got = self.s9.code_account_apply(env, "tester")
        self.assertEqual(got["account"], "claude04")
        self.assertEqual(env.get("CLAUDE_CONFIG_DIR"), os.path.abspath(prof))

    # W2 — 스폰이 그 자리를 실제로 지난다 (환경만 고치면 소용없다)
    def test_w2_the_spawn_applies_it(self):
        with open(os.path.join(ROOT, "bin", "s9.py"), encoding="utf-8") as f:
            src = f.read()
        seg = src[src.index('env["S9_AUTO_RESUME"] = "1"'):][:1200]
        self.assertIn("code_account_apply(env", seg,
                      "작업자 스폰이 계정을 걸지 않는다 — 서버 환경을 그대로 "
                      "물려받으면 언제나 기본 계정으로 뜬다")
        self.assertRegex(src, r"_auto_mark_pid\(doc_id, wp, reason,\s*acct=",
                         "어느 계정으로 띄웠는지 마커에 안 남으면, 한도로 "
                         "죽었을 때 어느 계정을 바꿔야 하는지 말할 수 없다")


class TheAccountLimitIsItsOwnKind(unittest.TestCase):
    """② 한도로 죽은 워커는 사유를 말하고 선다 — 되풀이하지 않는다."""

    def setUp(self):
        self.m = _load("s9_mod_wlimit")
        self.tmp = tempfile.mkdtemp(prefix="s9wlimit-")
        os.makedirs(os.path.join(self.tmp, "auto"), exist_ok=True)
        self.m._auto_dir = lambda: os.path.join(self.tmp, "auto")
        self.calls = []
        self.m.do_transition = lambda *a, **k: self.calls.append((a, k))
        self.m._auto_log = lambda *a, **k: None
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _mark(self, **kw):
        p = {"pid": 999999, "spawn_at": time.time(), "count": 1,
             "last": time.time(), "reason": "rework"}
        p.update(kw)
        with open(os.path.join(self.tmp, "auto", "REQ-X.json"), "w",
                  encoding="utf-8") as f:
            json.dump(p, f)

    def _log(self, text):
        with open(os.path.join(self.tmp, "auto", "REQ-X.log"), "w",
                  encoding="utf-8") as f:
            f.write(text + "\n")

    # L1 — 그 줄이 제 갈래를 얻는다 (종전에는 other 로 떨어져 아무 일도 안 났다)
    def test_l1_the_weekly_limit_is_named(self):
        self.assertEqual("limit", self.m._spawn_fail_kind(LIMIT_LINE))
        self.assertEqual("limit", self.m._spawn_fail_kind(
            "Claude usage limit reached"))

    # L2 — 과부하·인증과 섞이지 않는다
    def test_l2_it_is_not_overload_nor_fatal(self):
        self.assertEqual("overload", self.m._spawn_fail_kind(
            "API Error 529 Overloaded"))
        self.assertEqual("fatal", self.m._spawn_fail_kind("Invalid API key"))
        self.assertEqual("other", self.m._spawn_fail_kind(
            "Traceback (most recent call last)"))

    # L3 — 한도는 물러나는 갈래가 아니라 세우는 갈래다
    def test_l3_a_limit_blocks_instead_of_retrying(self):
        self.m.pid_alive = lambda pid: False
        self._mark(acct="claude01")
        self._log(LIMIT_LINE)
        out = self.m._spawn_retry_tick("REQ-X", cfg={})
        self.assertEqual("blocked", out,
                         "30초 뒤에 다시 걸어도 같은 답이다 — 되풀이하면 "
                         "화면에는 「멈춤」만 남는다")
        self.assertTrue(self.calls, "문서를 세우지 않았다")
        (args, kw) = self.calls[0]
        self.assertEqual("blocked", args[1])
        note = kw.get("note") or ""
        self.assertIn("claude01", note,
                      "어느 계정이 막혔는지 말해야 사람이 고칠 수 있다")
        self.assertIn("한도", note)

    # L4 — 계정을 모르면 지어내지 않는다
    def test_l4_without_the_account_it_stays_neutral(self):
        self.m.pid_alive = lambda pid: False
        self._mark()                      # acct 칸이 없는 옛 마커
        self._log(LIMIT_LINE)
        self.m._spawn_retry_tick("REQ-X", cfg={})
        note = (self.calls[0][1].get("note") or "")
        self.assertIn("기본 계정", note)


if __name__ == "__main__":
    unittest.main()
