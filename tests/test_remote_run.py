"""전체 스위트를 원격에서 (REQ-20260905-012) — 값은 안 보고, 큰 것은 안 보낸다.

실행: python3 tests/ remote_run
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import remote_run  # noqa: E402


class RemoteRun(unittest.TestCase):
    def test_k1_key_comes_from_argv_then_env_then_file(self):
        """K1. `--remote KEY` > S9_TEST_REMOTE > state/test-remote — 없으면 None."""
        old_file, old_env = remote_run.REMOTE_KEY_FILE, os.environ.pop("S9_TEST_REMOTE", None)
        d = tempfile.mkdtemp(prefix="s9rr-")
        remote_run.REMOTE_KEY_FILE = os.path.join(d, "test-remote")
        try:
            self.assertEqual(remote_run.remote_key(["--remote", "relay1"]), "relay1")
            self.assertIsNone(remote_run.remote_key([]))
            os.environ["S9_TEST_REMOTE"] = "opal"
            self.assertEqual(remote_run.remote_key([]), "opal")
            self.assertEqual(remote_run.remote_key(["--remote", "relay1"]), "relay1")
            os.environ.pop("S9_TEST_REMOTE", None)
            remote_run.remember("ruby")
            self.assertEqual(remote_run.remote_key([]), "ruby")
        finally:
            remote_run.REMOTE_KEY_FILE = old_file
            if old_env is not None:
                os.environ["S9_TEST_REMOTE"] = old_env

    def test_k5_document_dirt_does_not_count_as_uncommitted(self):
        """K5. vault/·state/ 의 미커밋은 지문 밖 — 세지 않는다; bin/ 의 미커밋은 센다.

        commit 훅이 REQ 문서에 commit 노트를 붙이므로 commit 직후의 나무는 늘 vault/
        하나가 더럽다. 그것을 세면 통과 기록은 영영 안 남는다(실측 2026-09-06).
        """
        import subprocess
        d = tempfile.mkdtemp(prefix="s9rr-tree-")
        def git(*a):
            return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, check=True)
        git("init", "-q", "-b", "main")
        for p in ("vault/r.md", "state/x.json", "bin/tool"):
            os.makedirs(os.path.join(d, os.path.dirname(p)), exist_ok=True)
            open(os.path.join(d, p), "w").write("a\n")
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
        sha, dirty = remote_run.head_state(repo=d)
        self.assertEqual((len(sha), dirty), (40, 0))
        open(os.path.join(d, "vault/r.md"), "a").write("commit 노트\n")
        open(os.path.join(d, "state/x.json"), "a").write("1\n")
        self.assertEqual(remote_run.head_state(repo=d)[1], 0, "문서·상태의 때는 세지 않는다")
        open(os.path.join(d, "bin/tool"), "a").write("b\n")
        self.assertEqual(remote_run.head_state(repo=d)[1], 1, "코드의 때는 센다")

    def test_k2_the_remote_runs_the_commit_it_was_handed(self):
        """K2. 원격 한 줄: bundle 받기 → refs/ci/<sha7> fetch → 그 커밋 → index → 시험.

        REQ-20260907-049 로 커밋이 GitHub 을 거치지 않고 ssh 통로의 bundle 로 직접
        건너간다 — 그때 `repo` 인자가 사라졌는데 이 시험이 옛 서명을 부르고 있었다.
        """
        sha = "0123456789abcdef0123456789abcdef01234567"
        line = remote_run.remote_script(sha, "~/section9-ci/x",
                                        16, ["test_a.py"], user="nicehugepark")
        for part in ("cat > ", "refs/ci/0123456", "-q -f " + sha,
                     "index rebuild", "user attach 'nicehugepark'", "--jobs 16", "'test_a.py'"):
            self.assertIn(part, line)
        # 커밋은 남을 거쳐 오지 않는다 — 원격의 키는 다른 저장소의 것이라
        # GitHub 이 「없는 저장소」로 답했다 (REQ-20260907-049).
        self.assertNotIn("github", line.lower(), "커밋이 GitHub 을 거친다")
        self.assertNotIn("git clone", line, "남의 저장소에서 받아 온다")
        self.assertNotIn("S9_USER=", line, "정체를 환경변수로 강제하면 제 사용자를 만드는 시험이 실패한다")
        # 원격은 파일 목록을 명시로 받아 「전체」가 아니다 — 실패 파일 표식(RED_MARK)을
        # 찍게 하는 손잡이가 한 줄에 있어야 이 머신이 무엇이 실패했는지 안다
        # (실측 2026-09-06 ee223fa: 표식이 없어 「실패 파일을 못 읽었다」, REQ-20260906-060).
        self.assertIn("S9_TEST_WORKER=1 python3 tests/", line)
        self.assertNotIn("tar", line,
                         "나무를 통째로 보낸다 — 건네는 것은 커밋 꾸러미(bundle) 하나다")

    def test_k4_full_means_no_pattern_and_jobs_is_not_a_pattern(self):
        """K4. 전체 = 패턴 없음. `--jobs 16` 의 16 과 `--remote relay1` 의 relay1 은 패턴이 아니다."""
        f = remote_run.is_full_invocation
        self.assertTrue(f([]))
        self.assertTrue(f(["--jobs", "16"]))
        self.assertTrue(f(["--jobs", "16", "--no-reuse", "--remote", "relay1"]))
        self.assertFalse(f(["--jobs", "16", "jobs_shard"]))
        self.assertFalse(f(["--smoke", "--jobs", "4"]))
        self.assertFalse(f(["--changed"]))

    def test_k3_the_secret_is_only_ever_substituted(self):
        """K3. 원격 명령은 `s9 secret run` 의 치환({{secret:KEY}})으로만 선다 — 값을 읽는 코드가 없다."""
        src = open(remote_run.__file__, encoding="utf-8").read()
        self.assertIn("{{secret:%s}}", src)
        self.assertNotIn('"secret", "get"', src)
        self.assertEqual(remote_run._sh_quote("a'b"), "'a'\"'\"'b'")


if __name__ == "__main__":
    unittest.main()
