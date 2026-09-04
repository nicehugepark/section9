"""문서 이벤트 git 동기화 테스트 (REQ-20260824-048, 반려 확정 방향).

이벤트(생성·전이·노트)마다 commit → pull --rebase → push 순차 수행.
활성 조건 = 리포 루트 .s9-sync 마커. 로컬 bare 리포를 origin으로 검증.

실행: python3 tests/test_s9_sync.py
"""
import os
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def sh(*argv, cwd=None, env=None, timeout=30):
    return subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def origin_log(bare):
    r = sh("git", "--git-dir", bare, "log", "--oneline", "main")
    return r.stdout.strip().splitlines() if r.returncode == 0 else []


class TestS9Sync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9sync-")
        cls.bare = os.path.join(cls.base, "origin.git")
        sh("git", "init", "-q", "--bare", "-b", "main", cls.bare)
        cls.root = os.path.join(cls.base, "ws")
        os.makedirs(cls.root)
        for c in (["git", "init", "-q", "-b", "main"],
                  ["git", "config", "user.name", "t"],
                  ["git", "config", "user.email", "t@t"],
                  ["git", "remote", "add", "origin", cls.bare]):
            sh(*c, cwd=cls.root)
        with open(os.path.join(cls.root, ".gitignore"), "w") as f:
            f.write("index/\nstate/*\n!state/sessions\n!state/sessions/**\n")
        with open(os.path.join(cls.root, ".s9-sync"), "w") as f:
            f.write("on\n")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_SYNC", None)
        sh(S9, "init", env=cls.env)
        sh("git", "add", "-A", cwd=cls.root)
        sh("git", "commit", "-q", "-m", "base", cwd=cls.root)
        sh("git", "push", "-q", "-u", "origin", "main", cwd=cls.root)

    @classmethod
    def tearDownClass(cls):
        # 실행마다 /tmp 에 리포 두 벌을 남기던 누수 (REQ-20260826-003 결함 D).
        # "쓰고 회수 안 함"은 테스트에서도 같은 값을 치른다.
        import shutil
        shutil.rmtree(cls.base, ignore_errors=True)

    def s9(self, *argv, env_extra=None):
        return sh(S9, *argv, env={**self.env, **(env_extra or {})})

    # Y7. 스테이징된 코드는 sync 커밋에 실리지 않는다 (결함 A)
    def test_test_s9_sync(self):
        """TestS9Sync 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("y7_staged_code_never_rides_along"):
                wip = os.path.join(self.root, "bin", "fake_code.py")
                os.makedirs(os.path.dirname(wip), exist_ok=True)
                with open(wip, "w") as f:
                    f.write("# WIP — 나가면 안 된다\n")
                sh("git", "add", "--", "bin/fake_code.py", cwd=self.root)
                try:
                    r = self.s9("new", "request", "--title", "범위 확인",
                                "--summary", "s", "--goal", "g", "--size", "S",
                                "--user", "tester", "--body", "b")
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    show = sh("git", "--git-dir", self.bare, "show", "--stat", "main")
                    self.assertIn("vault/requests", show.stdout)
                    self.assertNotIn("fake_code.py", show.stdout,
                                     "스테이징된 코드가 sync 커밋에 실려 나갔다")
                    # 그리고 그 코드는 여전히 스테이징 상태로 남아 있어야 한다 —
                    # sync 가 남의 작업 상태를 건드리지 않는다.
                    idx = sh("git", "diff", "--cached", "--name-only", cwd=self.root)
                    self.assertIn("bin/fake_code.py", idx.stdout)
                finally:
                    sh("git", "reset", "-q", "--", "bin/fake_code.py", cwd=self.root)
                    os.remove(wip)

            # Y9. 첨부 이전도 같은 사이클에 실린다 (결함 C)
        with self.subTest("y9_assets_ride_the_same_cycle"):
                src = os.path.join(self.root, "state", "shot.png")
                os.makedirs(os.path.dirname(src), exist_ok=True)
                with open(src, "wb") as f:
                    f.write(b"\x89PNG\r\n\x1a\n")
                rid = self.s9("new", "request", "--title", "첨부 동기화",
                              "--summary", "s", "--goal", "g", "--size", "S",
                              "--user", "tester",
                              "--body", f"확인용\n\n[Image: {src}]\n").stdout.split()[0]
                n0 = len(origin_log(self.bare))
                r = self.s9("assets", "ingest", rid)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("1개 이전", r.stdout)
                self.assertGreater(len(origin_log(self.bare)), n0,
                                   "첨부 이전이 동기화 사이클을 놓쳤다")
                show = sh("git", "--git-dir", self.bare, "show", "--stat", "main")
                self.assertIn("assets", show.stdout)

            # Y8. 보호경로를 stage 해도 문서 동기화는 멈추지 않는다 (결함 B)
        with self.subTest("y8_guarded_path_does_not_halt_sync"):
                hook = os.path.join(self.root, ".git", "hooks", "pre-commit")
                with open(hook, "w") as f:
                    f.write("#!/bin/sh\n"
                            "git diff --cached --name-only | grep -q '^bin/' && {\n"
                            "  echo 'guard: 보호경로'; exit 1; }\nexit 0\n")
                os.chmod(hook, 0o755)
                guarded = os.path.join(self.root, "bin", "guarded.py")
                os.makedirs(os.path.dirname(guarded), exist_ok=True)
                with open(guarded, "w") as f:
                    f.write("# 보호경로\n")
                sh("git", "add", "--", "bin/guarded.py", cwd=self.root)
                n0 = len(origin_log(self.bare))
                try:
                    r = self.s9("new", "request", "--title", "가드 확인",
                                "--summary", "s", "--goal", "g", "--size", "S",
                                "--user", "tester", "--body", "b")
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertGreater(len(origin_log(self.bare)), n0,
                                       "보호경로가 stage 됐다고 문서 동기화가 멈췄다")
                finally:
                    sh("git", "reset", "-q", "--", "bin/guarded.py", cwd=self.root)
                    os.remove(guarded)
                    os.remove(hook)

            # Y1. 생성 이벤트 → 커밋이 origin까지 push된다
        with self.subTest("y1_new_pushes"):
                n0 = len(origin_log(self.bare))
                r = self.s9("new", "request", "--title", "동기화 확인",
                            "--summary", "s", "--goal", "g", "--size", "S",
                            "--user", "tester", "--body", "b")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                logs = origin_log(self.bare)
                self.assertGreater(len(logs), n0, logs)
                self.assertIn("s9 sync: new", logs[0])
                show = sh("git", "--git-dir", self.bare, "show", "--stat", "main")
                self.assertIn("vault/requests", show.stdout)

            # Y2. 전이 이벤트 → 추가 커밋 push
        with self.subTest("y2_transition_pushes"):
                rid = self.s9("new", "request", "--title", "전이 동기화",
                              "--summary", "s", "--goal", "g", "--size", "S",
                              "--user", "tester", "--body", "b").stdout.split()[0]
                n0 = len(origin_log(self.bare))
                r = self.s9("status", rid, "in-progress", "--note", "착수")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                logs = origin_log(self.bare)
                self.assertGreater(len(logs), n0)
                self.assertIn("in-progress", logs[0])

            # Y3. 마커 없음 → git 동작 0 (051 제약: 클론만 한 사용자 안전)
        with self.subTest("y3_no_marker_no_git"):
                root2 = os.path.join(self.base, "plain")
                os.makedirs(root2)
                sh("git", "init", "-q", "-b", "main", cwd=root2)
                env2 = {**self.env, "S9_ROOT": root2}
                sh(S9, "init", env=env2)
                r = sh(S9, "new", "request", "--title", "마커 없음", "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "tester", "--body", "b",
                       env=env2)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                log = sh("git", "log", "--oneline", cwd=root2)
                self.assertEqual(log.stdout.strip(), "")   # 커밋 자체가 없다

            # Y4. 원격 불능 → 작업은 성공, 로컬 커밋 보존 + sync.log 기록 + 백오프
        with self.subTest("y4_offline_failsoft"):
                sh("git", "remote", "set-url", "origin",
                   os.path.join(self.base, "없는곳.git"), cwd=self.root)
                try:
                    t0 = time.time()
                    r = self.s9("new", "request", "--title", "오프라인 생성",
                                "--summary", "s", "--goal", "g", "--size", "S",
                                "--user", "tester", "--body", "b")
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertLess(time.time() - t0, 20)
                    local = sh("git", "log", "--oneline", "-1", cwd=self.root).stdout
                    self.assertIn("s9 sync", local)          # 로컬 커밋은 됐다
                    with open(os.path.join(self.root, "state", "sync.log")) as f:
                        log = f.read()
                    self.assertIn("⚠", log)
                    # 백오프: 직후 이벤트는 네트워크 생략(빠름) — skip 기록
                    t1 = time.time()
                    self.s9("note", list_last_id(self.root), "백오프 확인")
                    self.assertLess(time.time() - t1, 8)
                    with open(os.path.join(self.root, "state", "sync.log")) as f:
                        self.assertIn("skip(net-backoff)", f.read())
                finally:
                    sh("git", "remote", "set-url", "origin", self.bare, cwd=self.root)
                    fp = os.path.join(self.root, "state", ".sync-fail.ts")
                    if os.path.exists(fp):
                        os.remove(fp)

            # Y5. 협업: 다른 클론이 먼저 push → 내 이벤트가 pull --rebase 후 push
        with self.subTest("y5_pull_before_push"):
                other = os.path.join(self.base, "other")
                sh("git", "clone", "-q", self.bare, other)
                with open(os.path.join(other, "vault", "from-other.md"), "w") as f:
                    f.write("동료 변경\n")
                for c in (["git", "config", "user.name", "o"],
                          ["git", "config", "user.email", "o@o"],
                          ["git", "add", "-A"],
                          ["git", "commit", "-q", "-m", "other change"],
                          ["git", "push", "-q"]):
                    sh(*c, cwd=other)
                r = self.s9("new", "request", "--title", "리베이스 확인",
                            "--summary", "s", "--goal", "g", "--size", "S",
                            "--user", "tester", "--body", "b")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                logs = "\n".join(origin_log(self.bare))
                self.assertIn("other change", logs)
                self.assertIn("s9 sync: new", logs.splitlines()[0])
                # 동료 변경이 내 워킹트리에도 반영됨 (pull의 효과)
                self.assertTrue(os.path.exists(
                    os.path.join(self.root, "vault", "from-other.md")))

            # Y6. 킬스위치 S9_SYNC=off
        with self.subTest("y6_kill_switch"):
            n0 = len(origin_log(self.bare))
            r = self.s9("new", "request", "--title", "킬스위치", "--summary", "s",
                        "--goal", "g", "--size", "S", "--user", "tester",
                        "--body", "b", env_extra={"S9_SYNC": "off"})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(len(origin_log(self.bare)), n0)

def list_last_id(root):
    import glob
    files = sorted(glob.glob(os.path.join(root, "vault", "requests", "**",
                                          "REQ-*.md"), recursive=True),
                   key=os.path.getmtime)
    return os.path.basename(files[-1])[:-3]


if __name__ == "__main__":
    unittest.main(verbosity=2)
