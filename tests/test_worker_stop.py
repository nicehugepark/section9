"""리드가 무인 작업자를 세울 수 있는가 (REQ-20260829-021).

사용자: "kill 584610 이걸 니가 하기 위한 권한을 가져가서 직접 해."

그 자리에서 드러난 것은 권한이 아니라 **수단의 부재**였다. `s9 workers` 는
목록만 낸다 — 세우는 명령이 없다. 그래서 리드가 문서를 집은 뒤에도 이미 뜬
작업자를 정리할 길이 s9 안에 없고, 남는 것은 생짜 `kill <pid>` 뿐이다. 그
자리가 게이트에 막히는 것은 당연하다(에이전트가 아무 프로세스나 죽이는 권한을
갖는 것은 위험하다). 결과는 아무도 아무것도 못 하는 상태다.

그래서 여는 것은 "아무 프로세스나 죽이는 권한"이 아니라 **좁은 문 하나**다.

- pid 는 **호출자가 주지 않는다.** 스폰 마커(`state/auto_resume/<문서id>.json`)
  에 적힌 것만 쓴다. 그래야 이 명령으로는 s9 가 띄운 작업자 말고 아무것도 죽일
  수 없다.
- **그 문서를 집은 세션만** 세울 수 있다. 남의 작업을 지나가다 끄는 일이
  생기면 안 된다.
- 이유가 필수다. 이유 없는 중단은 나중에 아무도 판정할 수 없다
  (`relates --why` 와 같은 규칙, REQ-20260827-030).
- 세운 사실이 문서에 남는다. 로그만 남기고 문서에 안 적으면 다음 사람은
  작업자가 왜 사라졌는지 모른다.

실행: python3 tests/ worker_stop
"""
import importlib.machinery
import importlib.util
import inspect
import json
import os
import re
import shutil
import signal
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

DOC = "REQ-20260829-999-62x6"
PID = 424242


def _load():
    spec = importlib.util.spec_from_loader(
        "s9wstop", importlib.machinery.SourceFileLoader("s9wstop", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheDoor(unittest.TestCase):
    """좁은 문 — 마커에 적힌 작업자만, 집은 세션만."""

    def setUp(self):
        self.m = _load()
        self.tmp = tempfile.mkdtemp(prefix="s9wstop-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.m._auto_dir = lambda: self.tmp
        self.fn = getattr(self.m, "worker_stop", None)
        if not self.fn:
            self.skipTest("worker_stop() 미구현 — 아래 시험이 계약이다")

    def marker(self, doc=DOC, pid=PID):
        with open(os.path.join(self.tmp, doc + ".json"), "w") as f:
            json.dump({"pid": pid, "last": 0}, f)

    def test_the_caller_cannot_hand_in_a_pid(self):
        """pid 를 인자로 받으면 이 명령은 '아무거나 죽이는 명령'이 된다."""
        names = set(inspect.signature(self.fn).parameters)
        self.assertNotIn("pid", names,
                         "호출자가 pid 를 준다 — 마커에 적힌 것만 써야 한다")
        self.assertIn("why", names, "이유가 필수 인자가 아니다")

    def test_a_reason_is_required(self):
        """이유 없는 중단은 나중에 아무도 판정할 수 없다."""
        self.marker()
        r = self.fn(DOC, session="01c62d83", why="  ",
                    claims=lambda d, s: True, kill=lambda *a: None,
                    alive=lambda p: False, note=lambda *a, **k: None)
        self.assertFalse(r.get("ok"))
        self.assertIn("이유", r.get("reason", ""))

    def test_only_the_claiming_session_may_stop_it(self):
        """지나가다 남의 작업을 끄는 일이 생기면 안 된다."""
        self.marker()
        sent = []
        r = self.fn(DOC, session="deadbeef", why="중복이다",
                    claims=lambda d, s: False,
                    kill=lambda p, s: sent.append((p, s)),
                    alive=lambda p: False, note=lambda *a, **k: None)
        self.assertFalse(r.get("ok"))
        self.assertEqual(sent, [], "집지도 않은 세션이 작업자를 죽였다")

    def test_no_worker_is_not_an_error(self):
        """멱등이어야 두 번 쳐도 안전하다 — 이미 끝난 것을 오류로 만들지 않는다."""
        r = self.fn(DOC, session="01c62d83", why="중복이다",
                    claims=lambda d, s: True, kill=lambda *a: None,
                    alive=lambda p: False, note=lambda *a, **k: None)
        self.assertTrue(r.get("ok"))
        self.assertFalse(r.get("stopped"))

    def test_term_first_then_kill(self):
        """먼저 물러나기를 청하고, 안 물러나면 그때 확실히 회수한다."""
        self.marker()
        sent = []
        r = self.fn(DOC, session="01c62d83", why="리드가 직접 한다",
                    claims=lambda d, s: True,
                    kill=lambda p, s: sent.append((p, s)),
                    alive=lambda p: True,          # 끝내 안 죽는 척
                    wait=lambda _s: None, note=lambda *a, **k: None)
        self.assertTrue(r.get("ok"))
        self.assertEqual([s for _, s in sent],
                         [signal.SIGTERM, signal.SIGKILL],
                         f"신호 순서가 틀렸다: {sent}")
        self.assertTrue(all(p == PID for p, _ in sent),
                        "마커에 적힌 pid 가 아닌 것을 죽였다")

    def test_a_polite_exit_needs_no_second_signal(self):
        self.marker()
        sent = []
        alive = [True]

        def _alive(_p):
            v = alive[0]
            alive[0] = False       # SIGTERM 뒤에 물러난다
            return v
        self.fn(DOC, session="01c62d83", why="리드가 직접 한다",
                claims=lambda d, s: True,
                kill=lambda p, s: sent.append((p, s)),
                alive=_alive, wait=lambda _s: None, note=lambda *a, **k: None)
        self.assertEqual([s for _, s in sent], [signal.SIGTERM],
                         "물러난 프로세스에 SIGKILL 을 더 보냈다")

    def test_the_stop_is_written_into_the_document(self):
        """로그만 남기면 다음 사람은 작업자가 왜 사라졌는지 모른다."""
        self.marker()
        notes = []
        self.fn(DOC, session="01c62d83", why="리드가 이미 붙어 있다",
                claims=lambda d, s: True, kill=lambda *a: None,
                alive=lambda p: False, wait=lambda _s: None,
                note=lambda doc, text, **k: notes.append((doc, text)))
        self.assertTrue(notes, "문서에 아무것도 안 남겼다")
        self.assertEqual(notes[0][0], DOC)
        self.assertIn("리드가 이미 붙어 있다", notes[0][1],
                      "이유가 기록에 안 실렸다")

    def test_the_marker_is_cleared(self):
        """세운 뒤에도 마커가 남으면 목록이 유령을 계속 보여 준다."""
        self.marker()
        self.fn(DOC, session="01c62d83", why="중복이다",
                claims=lambda d, s: True, kill=lambda *a: None,
                alive=lambda p: False, wait=lambda _s: None,
                note=lambda *a, **k: None)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, DOC + ".json")))


class TheCommand(unittest.TestCase):
    """명령이 있어야 사람이 쓴다 — 함수만 있으면 아무도 못 부른다."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(S9, encoding="utf-8").read()

    def test_the_command(self):
        """명령이 있어야 사람이 쓴다 — 함수만 있으면 아무도 못 부른다."""
        with self.subTest("workers_takes_stop"):
            # 실패 메시지에 원본을 싣지 않는다 — 65,000줄이 화면을 덮으면 정작
            # 무엇이 없는지가 안 읽힌다.
            self.assertTrue(re.search(r'wk\.add_argument\("--stop"', self.src),
                            "`s9 workers --stop <문서id>` 가 파서에 없다")
        with self.subTest("workers_takes_why"):
            self.assertTrue(re.search(r'wk\.add_argument\("--why"', self.src),
                            "이유를 받는 자리가 없다")
        with self.subTest("the_command_goes_through_the_one_function"):
            i = self.src.find("def cmd_workers(")
            self.assertGreater(i, 0)
            self.assertIn("worker_stop", self.src[i:i + 1400],
                          "명령이 자기 손으로 죽인다 — 판정이 두 벌이 된다")
        with self.subTest("nothing_else_grew_a_kill"):
            i = self.src.find("def worker_stop(")
            self.assertGreater(i, 0, "worker_stop() 이 없다")
            # 다음 최상위 함수까지가 이 함수다. 글자 수로 잘라 두면 주석 몇 줄에
            # 창이 밀려 **제품은 멀쩡한데 시험만 빨개진다** (REQ-20260830-002 에서
            # 실제로 그랬다).
            j = self.src.find("\ndef ", i + 1)
            blk = self.src[i:j if j > 0 else len(self.src)]
            self.assertIn("SIGTERM", blk)     # 먼저 물러나기를 청하고
            # 회수 신호는 `sig_kill()` 로 부른다 — 윈도우에 SIGKILL 이 없어
            # 이름을 그대로 쓰면 그 판에서 AttributeError 로 죽는다
            # (REQ-20260903-005). 계약은 「회수한다」이지 「그 글자를 쓴다」가
            # 아니므로, 그 뜻을 부르는 자리를 본다.
            self.assertIn("sig_kill()", blk)  # 안 물러나면 그때 회수한다

if __name__ == "__main__":
    unittest.main()
