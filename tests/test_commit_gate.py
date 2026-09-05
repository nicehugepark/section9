"""커밋이 남의 작업을 삼키는 것을 막는가 (REQ-20260826-021-62x6).

2026-08-26 21:42. 리드가 `git add web/index.html` 로 커밋하면서 같은 파일을
고치던 무인 워커의 진행 중 편집을 함께 담았다. 나쁜 것은 충돌이 아니라 **조용한
성공**이다 — 두 변경 모두 문법적으로 멀쩡해 커밋도 되고 서버도 떴다. 그런데
합쳐진 상태는 버튼이 한 이름을 내고 핸들러가 다른 이름을 읽는 반쪽이라, 원래
고치려던 결함이 그대로 남았다. **같은 커밋에 들어 있던 테스트조차 통과하지
못했다 — 돌리기만 했으면 잡혔다.**

그래서 커밋 훅(s9-guard)에 게이트 둘을 둔다.
  ① 무인 워커가 도는데 '방금 만져진' 파일을 담으려 하면 막는다. `git add <경로>`
     는 "내 변경"이 아니라 "그 파일의 지금 상태"를 담기 때문이다.
  ② 커밋에 테스트 파일이 있으면 그것만이라도 돌린다. 전체 스위트는 2분이라 매
     커밋에 물리면 규율이 먼저 죽는다 — 담긴 것으로 좁힌다.

둘 다 사람의 기억이 아니라 훅이 강제한다. 규율만으로 될 일이었으면 오늘 넷이
나지 않았다.

그리고 그 게이트가 **실제로 걸려 있는지**를 이 시험이 판정한다(G7·G11). 여기에
같은 종류의 조용한 성공이 하나 더 있었다 — 자리를 `<ROOT>/.git/hooks` 로
지어냈던 탓에, `.git` 이 파일인 워크트리에서는 늘 '저장소 아님'으로 읽혀 훅이
사라져도 초록이 났다. 무인 워커가 커밋하는 자리가 바로 워크트리다
(REQ-20260829-001). 자리는 git 에게 묻고, 건너뛰는 경우는 '저장소가 아닐 때'
하나로 좁힌다.

실행: python3 tests/ commit_gate
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")

# 훅 아래에서 돌 때 물려받는 git 환경을 벗긴다 (REQ-20260829-005). `-C <경로>`
# 도 cwd 도 GIT_DIR 을 이기지 못하므로, 임시 저장소에 묻는 질문이 본 저장소로
# 새지 않게 하려면 호출 전에 벗겨야 한다.
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_INDEX_VERSION",
                "GIT_QUARANTINE_PATH")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _clean_git_env():
    e = dict(os.environ)
    for k in GIT_ENV_VARS:
        e.pop(k, None)
    return e


def _git(*argv, cwd):
    return subprocess.run(["git", "-C", cwd, *argv], env=_clean_git_env(),
                          capture_output=True, text=True, timeout=30)


def _is_repo(path):
    """저장소인가 — `.git` 이 디렉토리인지로 묻지 않는다.

    워크트리의 `.git` 은 파일이라 그 질문은 늘 '아니오'를 낸다. 무인 워커가
    커밋하는 자리가 바로 워크트리이므로, 그 오판은 게이트 시험 전체를
    조용히 건너뛰게 만든다 (REQ-20260829-001)."""
    r = _git("rev-parse", "--is-inside-work-tree", cwd=path)
    return r.returncode == 0 and r.stdout.strip() == "true"


_DOCTOR_MOD = []


def _hooks_dir(cwd):
    """훅 자리를 묻는다 — 판정은 제품 코드(bin/s9-doctor)의 것을 그대로 쓴다.

    묻는 쪽이 두 벌이면 한쪽만 고쳐지고 다른 쪽은 조용히 옛 가정을 남긴다.
    물려받은 GIT_DIR 은 cwd 를 이기므로 벗기고 묻는다 (REQ-20260829-005)."""
    if not _DOCTOR_MOD:
        _DOCTOR_MOD.append(_load("s9doctor_gate", DOCTOR))
    with mock.patch.dict(os.environ, _clean_git_env(), clear=True):
        return _DOCTOR_MOD[0].git_hooks_dir(cwd)


def hook_state(root):
    """그 자리의 pre-commit 은 어떤 상태인가 — 셋을 또렷이 가른다.

    `no-repo` 만이 건너뛸 이유다. 예전 코드는 파일이 없다는 사실 하나로
    `no-repo` 와 `missing` 을 뭉갰고, 워크트리에서는 늘 앞의 것으로 읽혀
    훅이 사라져도 시험이 OK 를 냈다 (REQ-20260829-001)."""
    if not _is_repo(root):
        return "no-repo", ""
    hooks_dir = _hooks_dir(root)
    if not hooks_dir:
        return "no-repo", ""
    hook = os.path.join(hooks_dir, "pre-commit")
    if not os.path.exists(hook):
        return "missing", hook
    with open(hook, encoding="utf-8") as f:
        body = f.read()
    return ("ok" if "s9-guard" in body else "not-ours"), hook


class CommitGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load("s9guard", GUARD)

    def _fresh_file(self, name="web/index.html"):
        p = os.path.join(self.m.ROOT, name)
        return name if os.path.exists(p) else None

    def test_commit_gate(self):
        """CommitGate 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g1_worker_plus_fresh_file_blocks"):
            import time
            rel = "tests/test_commit_gate.py"          # 방금 쓴 이 파일
            os.utime(os.path.join(self.m.ROOT, rel), None)
            # 우회 환경변수를 **명시적으로 끈다**. 이 테스트가 그것에 오염된 적이
            # 있다 — 리드가 `S9_ALLOW_CONCURRENT=1` 로 커밋하자 훅이 그 환경을
            # 물려받은 채 테스트를 돌렸고, 게이트가 통과하는 바람에 "막힌다"는
            # 이 계약이 무너졌다. 주변 환경에 기대는 테스트는 조용히 거짓이 된다.
            with mock.patch.dict(os.environ, {}, clear=False), \
                 mock.patch.object(self.m, "live_workers",
                                   return_value=["- REQ-x (무인 작업자 pid 1, 1분째)"]):
                os.environ.pop(self.m.OVERRIDE, None)
                with self.assertRaises(SystemExit) as cm:
                    self.m.concurrent_gate([rel])
            self.assertEqual(cm.exception.code, 1)
        with self.subTest("g2_no_worker_no_block"):
            rel = "tests/test_commit_gate.py"
            with mock.patch.object(self.m, "live_workers", return_value=[]):
                self.m.concurrent_gate([rel])          # 예외 없이 통과
        with self.subTest("g9_window_matches_how_agents_work"):
            self.assertGreaterEqual(
                self.m.FRESH_SEC, 300,
                "창이 좁아 에이전트가 생각하는 동안의 커밋을 놓친다")
        with self.subTest("g10_message_says_when_it_changed"):
            with open(os.path.join(self.m.ROOT, "bin", "s9-guard"),
                      encoding="utf-8") as f:
                hook = f.read()
            self.assertIn("바뀜)", hook, "언제 바뀌었는지 말하지 않는다")
            self.assertNotIn("방금 바뀐 파일을 담으려", hook,
                             "머리말이 아직 '방금'이라 목록과 어긋난다")
        with self.subTest("g3_stale_file_is_not_in_flight"):
            rel = "tests/test_commit_gate.py"
            p = os.path.join(self.m.ROOT, rel)
            import time
            old = time.time() - (self.m.FRESH_SEC + 120)
            os.utime(p, (old, old))
            try:
                with mock.patch.dict(os.environ, {}, clear=False), \
                     mock.patch.object(self.m, "live_workers",
                                       return_value=["- REQ-x (pid 1)"]):
                    os.environ.pop(self.m.OVERRIDE, None)
                    self.m.concurrent_gate([rel])
            finally:
                os.utime(p, None)
        with self.subTest("g4_override_passes"):
            rel = "tests/test_commit_gate.py"
            os.utime(os.path.join(self.m.ROOT, rel), None)
            with mock.patch.dict(os.environ, {self.m.OVERRIDE: "1"}), \
                 mock.patch.object(self.m, "live_workers",
                                   return_value=["- REQ-x (pid 1)"]):
                self.m.concurrent_gate([rel])
        with self.subTest("g5_failing_staged_test_blocks"):
            def fake_run(argv, **kw):
                return subprocess.CompletedProcess(argv, 1, "FAILED (failures=1)", "")
            with mock.patch.object(subprocess, "run", side_effect=fake_run):
                with self.assertRaises(SystemExit) as cm:
                    self.m.staged_tests_gate(["tests/test_anything.py"])
            self.assertEqual(cm.exception.code, 1)
        with self.subTest("g6_docs_only_commit_runs_nothing"):
            called = []
            with mock.patch.object(subprocess, "run",
                                   side_effect=lambda *a, **k: called.append(a)):
                self.m.staged_tests_gate(["docs/x.md", "vault/requests/y.md"])
            self.assertEqual(called, [])
        with self.subTest("g6b_code_commit_runs_the_smoke_tier"):
            seen = {}

            def fake(argv, *a, **k):
                seen["argv"] = argv

                class R:
                    returncode = 0
                return R()
            with mock.patch.object(subprocess, "run", side_effect=fake):
                self.m.staged_tests_gate(["bin/s9", "docs/x.md"])
            self.assertIn("--smoke", seen.get("argv", ()),
                          "코드 커밋인데 스모크가 게이트로 안 돈다")
            self.assertIn("--jobs", seen["argv"], "게이트가 직렬로 돌면 무게 반론이 되살아난다")
        with self.subTest("g8_subagents_count_too"):
            with open(os.path.join(self.m.ROOT, "bin", "s9.py"), encoding="utf-8") as f:
                src = f.read()
            self.assertIn("def live_agents(", src, "서브에이전트 판정이 없다")
            self.assertIn("agents = live_agents()", src,
                          "`s9 workers` 가 서브에이전트를 내지 않는다")
            with open(os.path.join(self.m.ROOT, "bin", "s9-guard"),
                      encoding="utf-8") as f:
                hook = f.read()
            self.assertIn('"workers"', hook, "훅이 s9 에게 묻지 않는다")
            self.assertNotIn("무인 워커가 도는 중에", hook,
                             "메시지가 아직 워커만 말한다")
        with self.subTest("g7_hook_is_actually_installed"):
            state, hook = hook_state(self.m.ROOT)
            if state == "no-repo":
                self.skipTest("git 저장소가 아니다")
            self.assertEqual(state, "ok",
                             f"pre-commit 이 s9-guard 를 부르지 않는다({state}): "
                             f"{hook} — bin/s9-install 로 설치하라")

class HooksDirIsAskedOfGit(unittest.TestCase):
    """G11. 훅 자리는 경로를 지어내지 말고 git 에게 묻는다.

    실제 워크트리 하나를 만들어 확인한다 — 이 리포의 상태에 기대면, 본
    체크아웃에서 돌 때 우연히 통과하고 정작 문제가 나는 자리(워크트리)는
    검사되지 않는다.
    """

    @classmethod
    def setUpClass(cls):
        if not shutil.which("git"):
            raise unittest.SkipTest("git 없음")
        cls.base = tempfile.mkdtemp(prefix="s9hookdir-")
        cls.repo = os.path.join(cls.base, "repo")
        os.makedirs(cls.repo)
        _git("init", "-q", "-b", "main", cwd=cls.repo)
        _git("config", "user.email", "t@t", cwd=cls.repo)
        _git("config", "user.name", "t", cwd=cls.repo)
        open(os.path.join(cls.repo, "a.txt"), "w").close()
        _git("add", "a.txt", cwd=cls.repo)
        _git("commit", "-qm", "init", "--no-verify", cwd=cls.repo)
        cls.wt = os.path.join(cls.base, "wt")
        r = _git("worktree", "add", "-q", "-b", "wt1", cls.wt, cwd=cls.repo)
        if r.returncode != 0:
            raise unittest.SkipTest(f"워크트리를 못 만들었다: {r.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_hooks_dir_is_asked_of_git(self):
        """G11. 훅 자리는 경로를 지어내지 말고 git 에게 묻는다."""
        with self.subTest("worktree_dot_git_is_a_file"):
            self.assertTrue(os.path.isfile(os.path.join(self.wt, ".git")),
                            "워크트리의 .git 이 파일이 아니다 — 전제가 바뀌었다")
            self.assertFalse(os.path.isdir(os.path.join(self.wt, ".git", "hooks")),
                             "손으로 이은 <워크트리>/.git/hooks 가 있다")
        with self.subTest("worktree_resolves_to_common_hooks_dir"):
            got = _hooks_dir(self.wt)
            want = os.path.join(self.repo, ".git", "hooks")
            self.assertEqual(os.path.realpath(got), os.path.realpath(want))
        with self.subTest("main_checkout_resolves_too"):
            self.assertEqual(os.path.realpath(_hooks_dir(self.repo)),
                             os.path.realpath(
                                 os.path.join(self.repo, ".git", "hooks")))
        with self.subTest("non_repo_is_empty"):
            plain = os.path.join(self.base, "plain")
            os.makedirs(plain, exist_ok=True)
            self.assertEqual(_hooks_dir(plain), "")
            self.assertEqual(hook_state(plain)[0], "no-repo")
        with self.subTest("worktree_without_hook_fails_not_skips"):
            self.assertEqual(hook_state(self.wt)[0], "missing")
        with self.subTest("installed_hook_reads_ok"):
            hooks = os.path.join(self.repo, ".git", "hooks")
            os.makedirs(hooks, exist_ok=True)
            path = os.path.join(hooks, "pre-commit")
            with open(path, "w", encoding="utf-8") as f:
                f.write('#!/bin/sh\nexec "$MAIN/bin/s9-guard" "$@"\n')
            self.addCleanup(os.remove, path)
            # 워크트리에서 물어도 공용 자리의 그 훅이 보여야 한다
            self.assertEqual(hook_state(self.wt)[0], "ok")

if __name__ == "__main__":
    unittest.main()
