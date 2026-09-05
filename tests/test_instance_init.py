"""s9 instance init 테스트 (REQ-20260824-053, 플로우 DOC-20260824-003).

업스트림-인스턴스 구조: 인스턴스는 데이터를 track하고, 업스트림 merge로
하네스를 업그레이드한다. 네트워크 없이 로컬 bare 리포를 origin으로 검증.

실행: python3 tests/test_instance_init.py
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PHOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


def sh(*argv, cwd=None, env=None, inp=None):
    return subprocess.run(list(argv), cwd=cwd, env=env, input=inp,
                          capture_output=True, text=True, timeout=60)


class DetachedBase(unittest.TestCase):
    """I7. 베이스가 detached HEAD 여도 인스턴스는 main 가지로 서고 push 된다.

    원격 CI(tests/remote_run.py)는 베이스를 `checkout -f <sha>` 로 놓고 돈다 —
    그 클론에는 가지가 없어 `push -u origin main` 이 「src refspec main does not
    match any」로 섰다(jade 실측 2026-09-06). 인스턴스의 가지는 베이스가 어디에
    서 있든 main 이다.
    """
    def test_detached_base_still_pushes_main(self):
        base = tempfile.mkdtemp(prefix="s9inst-detached-")
        root = os.path.join(base, "base")
        sh("git", "clone", "-q", os.path.join(HERE, ".."), root)
        sh("git", "checkout", "-q", "--detach", cwd=root)
        self.assertEqual(sh("git", "branch", "--show-current", cwd=root).stdout.strip(), "")
        origin = os.path.join(base, "work.git")
        sh("git", "init", "-q", "--bare", origin)
        target = os.path.join(base, "org-work")
        env = {**os.environ, "S9_ROOT": root}
        for k in ("S9_SESSION", "S9_AUTO_RESUME"):
            env.pop(k, None)
        r = sh(os.path.join(root, "bin", "s9"), "instance", "init", origin, "--dir", target, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("⑤ push 완료", r.stdout)
        self.assertEqual(sh("git", "branch", "--show-current", cwd=target).stdout.strip(), "main")
        self.assertIn("main", sh("git", "--git-dir", origin, "branch").stdout)


class TestInstanceInit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9inst-")
        cls.origin = os.path.join(cls.base, "work.git")   # 사설 리포(로컬 bare)
        sh("git", "init", "-q", "--bare", cls.origin)
        cls.target = os.path.join(cls.base, "org-work")
        cls.env = {**os.environ}
        cls.env.pop("S9_ROOT", None)
        cls.env.pop("S9_SESSION", None)
        # 무인 워커 세션 상속분 격리 — 훅이 auto-resume 턴으로 오인해
        # REQ 생성을 건너뛴다 (i4/i5가 단독 실행에서만 깨지던 원인)
        cls.env.pop("S9_AUTO_RESUME", None)
        r = sh(S9, "instance", "init", cls.origin, "--dir", cls.target,
               env=cls.env)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.out = r.stdout

    # I1. 기본: 클론·리모트·gitignore 전환·초기 커밋·푸시
    def test_test_instance_init(self):
        """TestInstanceInit 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("i1_layout"):
                r = sh("git", "remote", "-v", cwd=self.target)
                self.assertIn("upstream", r.stdout)
                self.assertIn(f"origin\t{self.origin}", r.stdout)
                gi = open(os.path.join(self.target, ".gitignore")).read()
                self.assertNotIn("vault/", gi)          # 데이터 track
                # 세션 바인딩도 이 머신 것 — 담당은 문서 lease 가 나른다 (REQ-20260902-026)
                self.assertNotIn("!state/sessions", gi)
                self.assertIn("state/*", gi)            # chat inbox 등은 로컬
                log = sh("git", "log", "--oneline", cwd=self.target).stdout
                self.assertIn("instance init", log)
                self.assertIn("⑤ push 완료", self.out)
                # 코드도 함께 들어 있다 (사용자는 이 리포만 알면 된다)
                self.assertTrue(os.path.exists(
                    os.path.join(self.target, "bin", "s9")))
                self.assertTrue(os.path.exists(
                    os.path.join(self.target, "web", "index.html")))

            # I2. 데이터 track: 인스턴스에서 만든 REQ 문서가 git에 추적된다.
            # REQ-20260824-048 이후 문서 이벤트가 즉시 commit→push 되므로
            # 스테이징 예정(add -An)이 아니라 추적 여부(ls-files)로 검증한다.
        with self.subTest("i2_data_tracked"):
                env = {**self.env, "S9_ROOT": self.target}
                r = sh(S9, "new", "request", "--title", "인스턴스 요청",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       "--user", "alice", "--body", "b", env=env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                st = sh("git", "add", "-An", cwd=self.target).stdout
                ls = sh("git", "ls-files", cwd=self.target).stdout
                self.assertIn("vault/requests", st + ls)
                self.assertNotIn("\nindex/", "\n" + st + "\n" + ls)  # 파생물은 여전히 제외

            # I3. 푸시 불가(원격 미존재) → 단계별 가이드 출력, 비정상 종료 아님
        with self.subTest("i3_push_fail_guide"):
                tgt = os.path.join(self.base, "no-remote")
                r = sh(S9, "instance", "init",
                       os.path.join(self.base, "없는리포.git"), "--dir", tgt,
                       env=self.env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("push 실패", r.stdout)
                self.assertIn("github.com/new", r.stdout)
                self.assertIn("git push -u origin main", r.stdout)

            # I4. 훅 cwd 감지: S9_ROOT 없이 cwd=인스턴스 → REQ가 인스턴스 vault에 생성
        with self.subTest("i4_hook_cwd_detection"):
                payload = {"session_id": "instsess-full", "cwd": self.target,
                           "prompt": "인스턴스에서 대시보드 스킨을 추가해줘"}
                r = sh(PHOOK, env=self.env, inp=json.dumps(payload))
                self.assertEqual(r.returncode, 0, r.stderr)
                ls = sh(S9, "ls", env={**self.env, "S9_ROOT": self.target}).stdout
                self.assertIn("스킨", ls)

            # I5. 회귀: cwd가 s9 루트가 아니면 명시 S9_ROOT 유지(감지 미발동)
        with self.subTest("i5_no_detection_outside_root"):
                sandbox = tempfile.mkdtemp(prefix="s9plain-")
                env = {**self.env, "S9_ROOT": sandbox}
                sh(S9, "init", env=env)
                payload = {"session_id": "plainsess-x", "cwd": "/tmp",
                           "prompt": "샌드박스 대시보드에 새 시계 위젯을 추가해줘"}
                r = sh(PHOOK, env=env, inp=json.dumps(payload))
                self.assertEqual(r.returncode, 0, r.stderr)
                ls = sh(S9, "ls", env=env).stdout
                self.assertIn("샌드박스", ls)

            # I6. 업그레이드: 업스트림 커밋 → 인스턴스 fetch+merge 로 수령
        with self.subTest("i6_upgrade_merge"):
            up = os.path.join(self.base, "upstream-copy")
            sh("git", "clone", "-q", os.path.join(HERE, ".."), up)
            marker = os.path.join(up, "docs", "upgrade-marker.md")
            with open(marker, "w") as f:
                f.write("업그레이드 확인용\n")
            sh("git", "add", "docs/upgrade-marker.md", cwd=up)
            sh("git", "-c", "user.name=t", "-c", "user.email=t@t",
               "commit", "-q", "-m", "harness upgrade", cwd=up)
            sh("git", "remote", "set-url", "upstream", up, cwd=self.target)
            r = sh("git", "fetch", "-q", "upstream", cwd=self.target)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = sh("git", "-c", "user.name=t", "-c", "user.email=t@t",
                   "merge", "--no-edit", "upstream/main", cwd=self.target)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(
                os.path.join(self.target, "docs", "upgrade-marker.md")))

if __name__ == "__main__":
    unittest.main(verbosity=2)
