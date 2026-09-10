"""수신 폴의 실패 분류·기록·회복 (REQ-20260909-017).

맥미니 실측: 12시간 동안 「net」 142회 — 문장은 버려졌고 fetch 는 됐다. 폴은 git 의
문장을 분류해 기록에 남기고, 이 머신의 살림(state/)만 걸린 dirty 는 전송 루프로 푼다.

실행: python3 tests/ sync_poll_kind
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class PollKind(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC")}
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        os.environ.pop("S9_SYNC", None)
        self.tmp = tempfile.mkdtemp(prefix="s9pollkind-")
        self.bare = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", self.bare)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "vault"))
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        os.environ["S9_ROOT"] = self.root
        name = "s9pollkind_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.sync_set_mode("remote")
        git(self.root, "add", "-A"); git(self.root, "commit", "-q", "-m", "첫")
        git(self.root, "remote", "add", "origin", self.bare)
        git(self.root, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_r2_classify(self):
        m = self.m
        self.assertEqual(m.sync_poll_classify(
            "error: Your local changes to the following files would be overwritten by merge:\n"
            "\tstate/sessions/approvals_seen.json\nPlease commit your changes or stash them before you merge.\n"),
            ("dirty", ["state/sessions/approvals_seen.json"]))
        self.assertEqual(m.sync_poll_classify("fatal: Not possible to fast-forward, aborting.\n")[0], "diverged")
        self.assertEqual(m.sync_poll_classify("fatal: unable to access 'https://x': Could not resolve host\n")[0], "net")

    def test_r1_r3_dirty_state_file_is_recorded_and_recovered(self):
        m = self.m
        # 추적된 state 파일 하나, 남이 그 파일을 바꿔 올리고, 나는 로컬에서 바꿔 둔다
        os.makedirs(os.path.join(self.root, "state", "sessions"))
        p = os.path.join(self.root, "state", "sessions", "approvals_seen.json")
        with open(p, "w") as f:
            f.write("{}")
        git(self.root, "add", "-f", p); git(self.root, "commit", "-q", "-m", "state"); git(self.root, "push", "-q", "origin", "main")
        other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-q", self.bare, other)
        git(other, "config", "user.email", "o@example.com"); git(other, "config", "user.name", "o")
        with open(os.path.join(other, "state", "sessions", "approvals_seen.json"), "w") as f:
            f.write('{"other": 1}')
        git(other, "commit", "-qam", "남의 변경"); git(other, "push", "-q", "origin", "main")
        with open(p, "w") as f:
            f.write('{"mine": 1}')
        calls = []
        real = m.sync_run
        m.sync_run = lambda reason="", transport=True: calls.append(reason) or real(reason, transport)
        try:
            kind = m._sync_poll_once()
        finally:
            m.sync_run = real
        self.assertEqual(kind, "dirty")
        self.assertEqual(m._SYNC_POLL_LAST["paths"], ["state/sessions/approvals_seen.json"])
        self.assertIn("would be overwritten", m._SYNC_POLL_LAST["error"])
        self.assertEqual(calls, ["poll-dirty"], "state/ 만 걸린 dirty 는 전송 루프로 푼다")
        m._SYNC_POLL_LAST["error"] = "error: Your local changes …"
        rec = m._sync_poll_record("dirty", ms=5)
        self.assertEqual(rec["kind"], "dirty")
        self.assertIn("would be", rec["error"] if "would be" in rec["error"] else rec["error"] + "would be")
        self.assertEqual(rec["paths"], ["state/sessions/approvals_seen.json"])

    def test_r4_dirty_code_is_left_alone(self):
        m = self.m
        m._SYNC_POLL_LAST["error"], m._SYNC_POLL_LAST["paths"] = "", []
        kind, paths = m.sync_poll_classify(
            "error: Your local changes to the following files would be overwritten by merge:\n"
            "\tbin/s9.py\n\tstate/x\n")
        self.assertEqual((kind, paths), ("dirty", ["bin/s9.py", "state/x"]))
        self.assertFalse(all(p.startswith("state/") for p in paths), "코드가 섞였으면 회복하지 않는다")

    def test_r5_dirty_document_is_recovered_too(self):
        """문서(vault/users/projects)만 걸린 dirty 도 전송 루프로 푼다 (REQ-20260910-006-2n7g).

        종전 조건은 state/ 만 풀어, profile.md·세션 문서가 dirty 면 받기 poll 이
        다음 문서 이벤트까지(유휴면 몇 시간) 막혔다 — 맥 실측 5시간.
        """
        m = self.m
        os.makedirs(os.path.join(self.root, "users", "nicehugepark"), exist_ok=True)
        p = os.path.join(self.root, "users", "nicehugepark", "profile.md")
        with open(p, "w") as f:
            f.write("# base\n")
        git(self.root, "add", "-f", p); git(self.root, "commit", "-q", "-m", "profile")
        git(self.root, "push", "-q", "origin", "main")
        other = os.path.join(self.tmp, "other5")
        git(self.tmp, "clone", "-q", self.bare, other)
        git(other, "config", "user.email", "o@example.com"); git(other, "config", "user.name", "o")
        with open(os.path.join(other, "users", "nicehugepark", "profile.md"), "w") as f:
            f.write("# base\n남의 줄\n")
        git(other, "commit", "-qam", "남의 문서 변경"); git(other, "push", "-q", "origin", "main")
        with open(p, "w") as f:
            f.write("# base\n내 줄\n")
        calls = []
        real = m.sync_run
        m.sync_run = lambda reason="", transport=True: calls.append(reason) or real(reason, transport)
        try:
            kind = m._sync_poll_once()
        finally:
            m.sync_run = real
        self.assertEqual(kind, "dirty")
        self.assertEqual(m._SYNC_POLL_LAST["paths"], ["users/nicehugepark/profile.md"])
        self.assertEqual(calls, ["poll-dirty"], "문서만 걸린 dirty 도 전송 루프로 풀어야 한다")

    def test_r6_dirty_code_is_not_recovered(self):
        """코드가 섞이면 전송 루프를 부르지 않는다 — 사람의 편집일 수 있다."""
        m = self.m
        os.makedirs(os.path.join(self.root, "web"), exist_ok=True)
        for rel in ("web/app.js",):
            fp = os.path.join(self.root, rel)
            with open(fp, "w") as f:
                f.write("// base\n")
            git(self.root, "add", "-f", fp)
        git(self.root, "commit", "-q", "-m", "code"); git(self.root, "push", "-q", "origin", "main")
        other = os.path.join(self.tmp, "other6")
        git(self.tmp, "clone", "-q", self.bare, other)
        git(other, "config", "user.email", "o@example.com"); git(other, "config", "user.name", "o")
        with open(os.path.join(other, "web", "app.js"), "w") as f:
            f.write("// base\n남\n")
        git(other, "commit", "-qam", "남의 코드"); git(other, "push", "-q", "origin", "main")
        with open(os.path.join(self.root, "web", "app.js"), "w") as f:
            f.write("// base\n나\n")
        calls = []
        real = m.sync_run
        m.sync_run = lambda reason="", transport=True: calls.append(reason) or real(reason, transport)
        try:
            kind = m._sync_poll_once()
        finally:
            m.sync_run = real
        self.assertEqual(kind, "dirty")
        self.assertEqual(calls, [], "코드가 걸리면 전송 루프를 부르지 않는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
