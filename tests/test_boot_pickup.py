"""기동한 세션이 멈춘 일을 이어받는다 (REQ-20260828-015-62x6).

사용자: "그런데 왜 알아서 시작을 안하지? inprogress 요청들. 세션 시작하면 뻔하잖아"

재부팅 뒤 in-progress 4건이 4시간 넘게 그대로 있었다. `s9 stalled` 은 "258분째
진전 없음"으로 정확히 알고 있었고, 대시보드도 회색 점으로 정직했다. 없던 것은
**아는 능력**이 아니라 **집으라는 지시**와 **무엇을 집을지 고르는 한 줄**이다.

기동 프롬프트(CODE_BOOTSTRAP)는 그때까지 정반대를 말하고 있었다 — "그 밖의
작업은 시작하지 마라". 그 문장은 세션을 깨우는 턴을 싸게 유지하려고 붙인
안전선이었는데, 재부팅처럼 **아무도 안 남은 자리**에서는 그 안전선이 곧 정지였다.

고르는 기준은 대기열 순서(work_order)다. 오래 멈춘 순으로 집으면 우선순위가
낮아 뒤로 밀어 둔 것이 늘 먼저 온다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ boot_pickup
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
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NextPickup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9next-")
        cls.claude = os.path.join(cls.root, "cc")
        os.makedirs(os.path.join(cls.claude, "proj"), exist_ok=True)
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                   "S9_CLAUDE_PROJECTS": cls.claude, "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)
        cls.cli(None, "init")
        cls.cli(None, "user", "add", "alice")

        def mk(sess, title, prio=None):
            rid = cls.cli(sess, "new", "request", "--title", title,
                          "--summary", "s", "--size", "S", "--user", "alice",
                          "--body", "x").split()[0]
            if prio is not None:
                cls.cli(sess, "set", rid, "--priority", str(prio))
            cls.cli(sess, "status", rid, "in-progress", "--note", "착수")
            return rid

        # LOW/HIGH: 아무도 안 붙어 있는 미완 — HIGH 가 먼저 집혀야 한다.
        # HIGH 를 **나중에** 만든다: 우선순위가 아니라 대기 시간으로 고르면
        # LOW 가 앞서게 되어 이 테스트가 그 실수를 잡는다.
        cls.LOW = mk("aaaa1111", "뒤로 밀어 둔 것", 30)
        cls.HIGH = mk("bbbb2222", "먼저 할 것", 80)
        # BUSY: 살아 있는 세션이 실제로 붙어 있는 것 — 뺏지 않는다.
        cls.BUSY = mk("cccc3333", "남이 하는 중", 90)

        streams = os.path.join(cls.root, "streams")
        os.makedirs(streams, exist_ok=True)
        old = time.time() - 7200
        for sid, age in (("aaaa1111", old), ("bbbb2222", old),
                         ("cccc3333", time.time())):
            p = os.path.join(streams, sid + ".jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"role": "assistant", "text": "x"}) + "\n")
            os.utime(p, (age, age))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, sess, *args):
        env = dict(cls.env)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *args], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL)
        assert r.returncode == 0, f"{args}: {r.stderr}"
        return r.stdout.strip()

    def _next(self, *extra):
        out = self.cli(None, "next", "--json", *extra)
        return json.loads(out)

    def test_n1_picks_highest_priority_unheld(self):
        self.assertEqual(self._next()["id"], self.HIGH,
                         "대기열 순서가 아니라 다른 기준으로 고른다")

    def test_n2_leaves_held_work_alone(self):
        """살아 있는 세션이 붙어 있는 건은 후보가 아니다 — 우선순위가 제일
        높아도 뺏으면 두 주체가 같은 문서를 동시에 고친다."""
        self.assertNotEqual(self._next()["id"], self.BUSY,
                            "살아 있는 세션이 붙어 있는 것을 집는다")
        # 살아 있는 세션(dddd4444)이 HIGH 를 클레임하면 다음 차례는 LOW 다.
        p = os.path.join(self.root, "streams", "dddd4444.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"role": "assistant", "text": "x"}) + "\n")
        self.cli("dddd4444", "claim", self.HIGH)
        self.assertEqual(self._next()["id"], self.LOW,
                         "이미 집힌 것을 또 집는다")

    def test_b1_nothing_to_pick_is_not_an_error(self):
        r = subprocess.run([S9, "next", "--json"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL,
                           env={**self.env, "S9_USER": "nobody"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(json.loads(r.stdout)["id"])

    def test_b2_human_output_says_how_to_take_it(self):
        out = self.cli(None, "next")
        self.assertIn(self.HIGH, out)
        self.assertIn(f"s9 last {self.HIGH} --add", out,
                      "이어받는 방법이 출력에 없다")


class BootstrapAsksForPickup(unittest.TestCase):
    """B3 — 기동 프롬프트가 인계를 지시한다."""

    def test_b3_bootstrap_tells_session_to_pick_up(self):
        m = _load("s9_bootpick", S9)
        self.assertIn("s9 next", m.CODE_BOOTSTRAP)
        self.assertNotIn("그 밖의 작업은 시작하지 마라", m.CODE_BOOTSTRAP)
        self.assertIn("수신함", m.CODE_BOOTSTRAP, "arm 지시는 그대로 남아야 한다")


if __name__ == "__main__":
    unittest.main()
