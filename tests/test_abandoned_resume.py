"""맡던 손이 사라진 in-progress 는 이어받아진다 (REQ-20260903-015-62x6).

사용자 지적: "012가 이미 죽었는데 왜 진행 중인것처럼 표시되나? 이건 도대체 무슨
상황이야. 버그잖아."

**본질.** 진행 보장(`rework_watch_tick`)이 집는 것은 `rework_candidate` 를 통과한
것뿐이었고, 그 함수는 마지막 전이가 반려(review→in-progress)이거나 대시보드 드래그
착수일 때만 참이다. 그래서 `open→in-progress` 로 시작한 요청의 작업자가 죽으면
**후보 자체가 되지 않았다** — 아무도 이어받지 않고, 문서는 영영 in-progress 로
남는다. 2026-09-03 실측: 001·005·008·012 넷이 그 상태였고 화면은 넷 다 「진행 중」
이라고 적고 있었다. 죽음을 알아채는 자리는 있는데(stalled·s9 next) 자리를 다시
채우는 자리가 없었다.

**좁혀 둔 것이 안전장치도 아니었다.** 겹쳐 뜨는 것을 막는 문은 `rework_claimed()`
이고(프로세스 생존·위임·세션 바인딩), 그 문은 후보를 넓혀도 그대로 선다.

격리: 임시 S9_ROOT + Popen 모킹(실스폰 방지).
실행: python3 tests/ abandoned_resume
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess as real_subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
FULLSID = "abab1212-cccc-dddd-eeee-ffffffffffff"


class AbandonedResume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9aband-")
        os.environ["S9_ROOT"] = cls.tmp          # 모듈 import 전에 고정
        os.environ["S9_MACHINE"] = "testbox"
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_AUTO_RESUME_DISABLE"):
            os.environ.pop(k, None)
        spec = importlib.util.spec_from_loader(
            "s9aband", importlib.machinery.SourceFileLoader("s9aband", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.env = {**os.environ}

        def cli(sess, *argv):
            env = dict(cls.env)
            if sess:
                env["S9_SESSION"] = sess
            r = real_subprocess.run([S9, *argv], capture_output=True, text=True,
                                    env=env, timeout=20)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r.stdout
        cls.cli = staticmethod(cli)

        cli(None, "init")
        cli(None, "user", "add", "alice")
        cli(None, "user", "config", "alice", "auto_resume", "on")
        cli(None, "user", "config", "alice", "auto_resume_cooldown_sec", "0")
        cli(None, "user", "config", "alice", "auto_resume_global_per_hour", "50")
        cli(None, "user", "config", "alice", "auto_resume_global_per_day", "100")
        # 담당 세션 — 이 파일의 mtime 이 곧 「살아 있음」의 증거다.
        cls.transcript = os.path.join(cls.tmp, FULLSID + ".jsonl")
        with open(cls.transcript, "w") as f:
            f.write("{}\n")
        cli("abab1212", "bind", "transcript_path", cls.transcript)
        cli("abab1212", "bind", "cwd", cls.tmp)

    def started(self, title):
        """CLI 착수(open→in-progress) — 반려도 드래그도 아닌 그 길."""
        doc = self.cli("abab1212", "new", "request", "--title", title,
                       "--summary", "t", "--goal", "t", "--size", "S",
                       "--user", "alice", "--body", "x").split()[0]
        self.cli("abab1212", "status", doc, "in-progress", "--note", "착수")
        return doc

    def kill_the_hand(self):
        """맡던 세션이 사라진 상태로 만든다 — 프로세스도 활동도 없다."""
        old = time.time() - 7200
        os.utime(self.transcript, (old, old))

    def tick(self, **kw):
        calls = []

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return mock.Mock()
        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            spawned = self.mod.rework_watch_tick(**kw)
        return spawned, calls

    # ------------------------------------------------------------------
    def test_abandoned_in_progress_is_taken_over(self):
        doc = self.started("버려진 자리")
        with self.subTest("a1_quiet_window_holds"):
            # 방금 손이 닿았다 — 살아 있는 세션이 집을 기회를 뺏지 않는다.
            spawned, _ = self.tick()
            self.assertNotIn(doc, spawned, spawned)
        self.kill_the_hand()
        with self.subTest("a2_after_the_grace_it_is_resumed"):
            spawned, calls = self.tick(grace=0)
            self.assertIn(doc, spawned, (spawned, calls))
            argv = [a for a in calls if doc in " ".join(map(str, a))]
            self.assertTrue(argv, calls)
            prompt = [s for s in argv[0] if isinstance(s, str) and doc in s][0]
            # 이어받기지 새 출발이 아니다 — 프롬프트가 그렇게 말해야 한다.
            self.assertIn("이어서 끝내는 일", prompt)
            self.assertIn("작업자가 사라졌다", prompt)
            # 반려 봉투를 씌우지 않는다 — 반려 사유가 없는 자리다.
            self.assertNotIn("반려 사유다", prompt)
            self.assertIn(f"last {doc}", prompt, "클레임 지시가 빠졌다")

    def test_a_live_claim_still_blocks_the_spawn(self):
        """겹침을 막는 문은 그대로 선다 — 넓힌 것은 후보뿐이다."""
        doc = self.started("살아 있는 손")
        self.kill_the_hand()
        os.utime(self.transcript, None)      # 세션이 되살아났다
        self.cli("abab1212", "last", doc, "--add")
        spawned, _ = self.tick(grace=0)
        self.assertNotIn(doc, spawned, spawned)

    def test_only_in_progress(self):
        """done·review·blocked 는 대상이 아니다."""
        for st, note in (("review", "확인 포인트: 눌러 보세요"),
                         ("blocked", "외부 대기")):
            doc = self.started(f"상태-{st}")
            if st == "review":
                self.cli("abab1212", "note", doc, "- [x] S1. 됨",
                         "--label", "tdd")
            self.cli("abab1212", "status", doc, st, "--note", note)
            self.kill_the_hand()
            spawned, _ = self.tick(grace=0)
            self.assertNotIn(doc, spawned, (st, spawned))

    def test_the_grace_is_measured_from_the_last_touch(self):
        """기준은 전이 시각이 아니라 마지막 손길이다.

        전이로 재면 아침에 착수해 지금도 일하는 문서가 유예를 이미 넘긴 것으로
        보인다 — 일하는 파일 위에 두 번째 손이 얹힌다."""
        doc = self.started("오래전 착수, 방금 손댐")
        self.kill_the_hand()
        # 전이는 한참 전이지만 방금 노트를 붙였다 = 누군가 일하고 있다.
        self.cli("abab1212", "note", doc, "진행 중", "--label", "response")
        spawned, _ = self.tick(grace=600)
        self.assertNotIn(doc, spawned, spawned)

    def test_rework_path_keeps_its_own_grace(self):
        """반려의 30초는 그대로다 — 넓힌 갈래가 좁은 갈래를 덮지 않는다."""
        m = self.mod
        self.assertEqual(m.abandon_grace({"user": "alice"}), m.ABANDON_GRACE)
        self.assertEqual(m.rework_grace({"user": "alice"}), 30)
        self.assertGreater(m.ABANDON_GRACE, m.rework_grace({"user": "alice"}),
                           "이어받기가 반려보다 빨리 뜨면 겹친다")

    def test_the_watcher_does_not_eat_the_human_wake_budget(self):
        """사람이 누르는 「이어가기」 한도를 워처가 먹으면 안 된다.

        `reason == "wake"` 갈래는 사람 몫(auto_resume_wake_per_day)을 쓰고,
        사람이 세워 둔 요청(stop_mark)까지 되살린다 — 둘 다 워처의 것이 아니다
        (tests/test_wake.py W4 가 붙잡은 사고)."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        import re
        tick = re.search(r"\ndef rework_watch_tick\(.*?\n\ndef ", src, re.S)
        self.assertIsNotNone(tick)
        body = tick.group(0)
        self.assertIn('kind="resume"', body,
                      "워처의 이어받기가 사람 몫(wake) 예산을 쓴다")
        self.assertNotIn('"wake"', body)

    def test_the_worker_is_told_there_is_no_later(self):
        """뒤로 미루면 그 일이 사라진다 (REQ-20260903-017-62x6).

        무인 워커는 `claude -p` 로 돈다 — 턴을 닫는 순간 프로세스가 사라지고
        백그라운드로 돌려 둔 명령도 함께 죽는다. 실사고 2026-09-03 21:40:28:
        012 의 워커가 전체 스위트를 백그라운드로 띄우고 "끝나면 보고하겠다" 로
        턴을 닫았다. 오류도 예외도 없이 사라졌고, 스위트도 함께 사라졌다.

        봉투는 **모든 스폰 경로가 지나는 한 곳**에 있어야 한다 — 프롬프트마다
        옮겨 적으면 언젠가 한 곳이 빠진다. 그래서 갈래 둘을 함께 두드린다."""
        doc = self.started("나중은 없다")
        self.kill_the_hand()
        _, calls = self.tick(grace=0)
        argv = [a for a in calls if doc in " ".join(map(str, a))]
        self.assertTrue(argv, calls)
        prompt = [s for s in argv[0] if isinstance(s, str) and doc in s][0]
        self.assertIn("나중이 없다", prompt)
        self.assertIn("앞에서 기다려라", prompt)
        self.assertIn("blocked", prompt, "자리를 넘기는 길을 안 알려 준다")

    def test_the_spawn_log_says_why(self):
        """조용히 뜨면 다음 사람이 왜 떴는지 못 찾는다."""
        doc = self.started("기록 남기기")
        self.kill_the_hand()
        self.tick(grace=0)
        with open(os.path.join(self.tmp, "state", "auto_resume",
                               "spawn.log")) as f:
            log = f.read()
        self.assertIn(doc, log, log)


if __name__ == "__main__":
    unittest.main()
