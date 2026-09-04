"""백그라운드로 잡힌 세션을 뺏으려다 워커가 즉사하는가 (REQ-20260826-035-62x6).

실사고 2026-08-26 REQ-20260826-021. 워커가 담당 세션에 `--resume` 으로 붙으려
했고, 세 번 다 CLI 가 거부했다:

    Error: Session dc4f4d76-… is currently running as a background agent (bg).

그 세션은 백그라운드 에이전트로 돌고 있었다 — inbox tail 도 attach pid 도 없고
transcript 도 조용해서 `chat_live` 는 "죽었다"로 읽었지만, 프로세스는 멀쩡히
살아 있었다. 워커는 스폰되자마자 그 한 줄만 남기고 죽었고, 실패도 쿨다운·캡을
똑같이 태우므로 재시도가 점점 뜸해져 카드가 24분간 붉은 네모로 굳었다.
사용자가 "왜 작업이 안 되냐"로 발견했다.

고침은 생존 판정을 하나 더 두는 것이다 — **활동이 아니라 프로세스**로 본다.
그 id 가 살아 있으면 resume 을 포기하고 새 세션으로 띄운다. 컨텍스트는 REQ
문서가 주므로 잃는 것은 없고, 멈추지 않는 것을 얻는다.

격리: S9_ROOT=mktemp, subprocess.Popen 모킹(실스폰 방지).
실행: python3 tests/ bg_session_resume
"""
import importlib.machinery
import importlib.util
import os
import subprocess as real_subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
FULLSID = "bbbb7777-1111-2222-3333-444444444444"


class BgSessionResume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9bgsid-")
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_AUTO_RESUME_DISABLE"):
            os.environ.pop(k, None)
        spec = importlib.util.spec_from_loader(
            "s9bgmod", importlib.machinery.SourceFileLoader("s9bgmod", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.env = {**os.environ}

        def cli(sess, *argv):
            env = dict(cls.env)
            if sess:
                env["S9_SESSION"] = sess
            r = real_subprocess.run([S9, *argv], capture_output=True, text=True,
                                    env=env, timeout=15)
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
        cls.transcript = os.path.join(cls.tmp, FULLSID + ".jsonl")
        with open(cls.transcript, "w") as f:
            f.write("{}\n")
        cli("bbbb7777", "bind", "transcript_path", cls.transcript)
        cli("bbbb7777", "bind", "cwd", cls.tmp)
        # 담당 세션은 '조용하다' — 이게 옛 판정이 resume 을 고른 조건이다.
        old = time.time() - 600
        os.utime(cls.transcript, (old, old))

    def _req(self, title):
        doc = self.cli("bbbb7777", "new", "request", "--title", title,
                       "--summary", "t", "--goal", "t", "--size", "S",
                       "--user", "alice", "--body", "x").split()[0]
        meta = {"user": "alice", "machine": "testbox", "session": "bbbb7777"}
        return doc, meta

    def _spawn(self, doc, meta, cmdlines):
        """워커 스폰을 한 번 돌리고 실제 argv 를 돌려준다."""
        calls = []

        def fake_popen(argv, **kw):
            calls.append(argv)
            return mock.Mock()
        with mock.patch("subprocess.Popen", side_effect=fake_popen), \
             mock.patch.object(self.mod, "_proc_cmdlines",
                               return_value=cmdlines):
            ok = self.mod._spawn_worker(doc, meta, "prompt", "test",
                                        allow_resume=True)
        self.assertTrue(ok, "스폰 자체가 막혔다 — 테스트 전제가 깨졌다")
        return calls[0]

    def test_bg_session_resume(self):
        """BgSessionResume 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("dead_session_still_resumes"):
            doc, meta = self._req("resume-case")
            argv = self._spawn(doc, meta, ["/usr/bin/python3 something-else"])
            self.assertIn("--resume", argv, argv)
            self.assertIn(FULLSID, argv, argv)
        with self.subTest("bg_locked_session_spawns_fresh"):
            doc, meta = self._req("bg-locked-case")
            argv = self._spawn(doc, meta, [
                f"claude --session-id {FULLSID} --model claude-opus-5[1m]"])
            self.assertNotIn("--resume", argv, argv)
            self.assertNotIn(FULLSID, " ".join(map(str, argv)), argv)
        with self.subTest("no_resume_is_recorded"):
            with open(os.path.join(self.tmp, "state", "auto_resume",
                                   "spawn.log")) as f:
                log = f.read()
            self.assertIn("NO-RESUME", log, log)
            self.assertIn("프로세스 생존", log, log)
        with self.subTest("proc_alive_matches_full_id_only"):
            self.assertFalse(self.mod._session_proc_alive("", ["claude x"]))
            self.assertFalse(self.mod._session_proc_alive(FULLSID, []))
            self.assertTrue(self.mod._session_proc_alive(
                FULLSID, [f"claude --session-id {FULLSID}"]))

if __name__ == "__main__":
    unittest.main()
