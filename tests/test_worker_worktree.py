"""워커는 자기 작업 디렉터리에서 일하고 자기 가지에 커밋한다
(REQ-20260828-011-62x6 2·3단계).

1단계에서 `s9 worktree add/ls/rm` 을 세웠지만 아무도 쓰지 않았다 — 사람이 손으로
만들 때만 쓰이는 장치는 사고가 나는 자리(무인 워커·서브에이전트)에 없는 것과 같다.

이 저장소가 네 번 겪은 것: 같은 파일 하나(web/index.html)에 여러 주체가 붙어
**남의 미커밋 작업이 조용히 사라졌다.** 워크트리는 그것을 없애지 않는다 —
**보이는 충돌로 바꾼다.**

다만 그냥 갈면 vault·index·state 까지 갈려 진실이 두 벌이 된다. 그래서
**코드는 갈리고 데이터는 하나다**: 작업 디렉터리만 워크트리, `S9_ROOT` 는 언제나
본 저장소.

거두는 자리도 함께 만든다. 안 거두면 쌓이고, 오늘 실제로 그 잔재가 사고를 냈다 —
지워진 워크트리 경로를 가리키는 훅이 조용히 죽어 있었다 (REQ-20260828-014).
다만 **남길 것이 있으면 남긴다**: 미커밋 변경이나 안 합친 커밋이 있는 워크트리를
거두는 것은 이 기능이 막으려던 바로 그 소실이다.

격리: S9_ROOT=mktemp git repo. 실행: python3 tests/ worker_worktree
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _git(cwd, *a):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *a], cwd=cwd, env=env, capture_output=True,
                          text=True)


class WorkerWorktree(unittest.TestCase):
    def setUp(self):
        # git 훅 안에서 돌면 GIT_DIR·GIT_INDEX_FILE 이 환경에 실려 온다 —
        # 그러면 임시 저장소를 만지려던 git 명령이 **본 저장소**를 만진다.
        # 실제로 커밋 게이트에서 이 테스트가 그렇게 엇나갔다. 봉하고 시작한다.
        self._git_env = {k: v for k, v in os.environ.items()
                         if k.startswith("GIT_")}
        for k in self._git_env:
            os.environ.pop(k, None)
        self.root = tempfile.mkdtemp(prefix="s9wtw-")
        _git(self.root, "init", "-q", "-b", "main")
        # 합치기는 본 저장소에서 git 이 직접 돈다 — 신원이 없으면 merge 가
        # 거부된다. 임시 저장소에 신원을 박아 실환경과 같게 만든다.
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        with open(os.path.join(self.root, "a.txt"), "w") as f:
            f.write("one\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_wtw", importlib.machinery.SourceFileLoader("s9_wtw", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._git_env)
        for w in (self.m.worktree_list() or []):
            _git(self.root, "worktree", "remove", "--force", w["path"])
        shutil.rmtree(self.root, ignore_errors=True)

    # N1. 기본은 지금까지와 같다 — 켜지 않으면 아무것도 갈리지 않는다.
    def test_n1_off_by_default(self):
        cwd, env, name = self.m.worker_workspace("REQ-x", {}, self.root)
        self.assertEqual(cwd, self.root)
        self.assertEqual(env, {})
        self.assertEqual(name, "")
        self.assertEqual(self.m.worktree_list(), [])

    # N2. 켜면 자기 자리를 받되 **데이터는 본 저장소** 하나다.
    def test_n2_on_gives_own_dir_but_shared_data(self):
        cwd, env, name = self.m.worker_workspace(
            "REQ-20260828-011-62x6", {"worker_worktree": True}, self.root)
        self.assertTrue(name)
        self.assertNotEqual(cwd, self.root)
        self.assertTrue(os.path.isdir(cwd))
        self.assertEqual(env.get("S9_ROOT"), self.root,
                         "데이터까지 갈리면 진실이 두 벌이 된다")
        self.assertIn(cwd, [w["path"] for w in self.m.worktree_list()])

    # N3. 3단계 — 워커는 자기 가지에 커밋하고 리드가 합친다.
    def test_n3_merge_brings_branch_home(self):
        cwd, _env, name = self.m.worker_workspace(
            "REQ-y", {"worker_worktree": True}, self.root)
        with open(os.path.join(cwd, "b.txt"), "w") as f:
            f.write("worker\n")
        _git(cwd, "add", "-A")
        _git(cwd, "commit", "-qm", "워커의 일")
        ok, msg = self.m.worktree_merge(name)
        self.assertTrue(ok, msg)
        self.assertTrue(os.path.exists(os.path.join(self.root, "b.txt")),
                        "합쳤는데 본 저장소에 없다")
        self.assertEqual(self.m.worktree_list(), [], "합친 뒤 거두지 않았다")

    # B1. 미커밋 변경이 남은 워크트리는 거두지 않는다 — 그게 이 기능의 존재 이유다.
    def test_b1_sweep_keeps_dirty_worktree(self):
        cwd, _e, name = self.m.worker_workspace(
            "REQ-z", {"worker_worktree": True}, self.root)
        with open(os.path.join(cwd, "a.txt"), "w") as f:
            f.write("작업 중\n")
        self.m.worktree_owner_write(name, {"doc": "REQ-z", "pid": 999999,
                                           "created": time.time() - 86400})
        self.assertEqual(self.m.worktree_sweep(), [])
        self.assertTrue(os.path.isdir(cwd), "미커밋 작업을 지웠다")

    # B2. 안 합친 커밋이 남아 있어도 거두지 않는다.
    def test_b2_sweep_keeps_unmerged_commits(self):
        cwd, _e, name = self.m.worker_workspace(
            "REQ-u", {"worker_worktree": True}, self.root)
        with open(os.path.join(cwd, "c.txt"), "w") as f:
            f.write("x\n")
        _git(cwd, "add", "-A")
        _git(cwd, "commit", "-qm", "아직 안 합친 것")
        self.m.worktree_owner_write(name, {"doc": "REQ-u", "pid": 999999,
                                           "created": time.time() - 86400})
        self.assertEqual(self.m.worktree_sweep(), [])
        self.assertTrue(os.path.isdir(cwd))

    # B3. 주인이 떠나고 남길 것도 없으면 거둔다 — 안 거두면 쌓이고,
    #     그 잔재가 실제로 사고를 냈다 (REQ-20260828-014).
    def test_b3_sweep_reaps_finished_worktree(self):
        cwd, _e, name = self.m.worker_workspace(
            "REQ-v", {"worker_worktree": True}, self.root)
        self.m.worktree_owner_write(name, {"doc": "REQ-v", "pid": 999999,
                                           "created": time.time() - 86400})
        self.assertEqual(self.m.worktree_sweep(), [name])
        self.assertFalse(os.path.isdir(cwd))

    # B4. 주인이 살아 있으면 비어 있어도 손대지 않는다.
    def test_b4_sweep_leaves_live_worker_alone(self):
        cwd, _e, name = self.m.worker_workspace(
            "REQ-w", {"worker_worktree": True}, self.root)
        self.m.worktree_owner_write(name, {"doc": "REQ-w", "pid": os.getpid(),
                                           "created": time.time() - 86400})
        self.assertEqual(self.m.worktree_sweep(), [])
        self.assertTrue(os.path.isdir(cwd))


class WorktreeAutoCommit(unittest.TestCase):
    """B6·B7 — 워커가 커밋을 안 하고 끝나면 리드가 대신 박는다.

    실사고 2026-08-28 16:16~17:56. 무인 작업자가 REQ-20260828-025 를 **구현까지
    끝내고 문서에 완료 보고까지 적었는데**, 그 코드가 워크트리 안에만 있고
    커밋되지 않아 본 저장소에는 한 줄도 없었다. 화면에는 39분째 "진행 중" 으로
    떠 있었고 사용자가 "진짜 진행중인건가" 로 발견했다. 워크트리 네 개가 전부
    그 상태였다.

    그날 오전에 봉투(allowedTools)에 git add·commit 을 이미 넣어 뒀다. **손을
    쥐여 줬는데도 안 했다** — 커밋이 규율로 남아 있는 한 이 실패는 반복된다.
    그래서 장치로 바꾼다: 주인이 떠났는데 미커밋이 남아 있으면 거두기 전에
    그 가지에 박는다. 박은 뒤에는 "안 합친 커밋" 이 되어 sweep 이 손대지 않고,
    리드가 `s9 worktree ls` 에서 보고 합친다.
    """

    def setUp(self):
        self._git_env = {k: v for k, v in os.environ.items()
                         if k.startswith("GIT_")}
        for k in self._git_env:
            os.environ.pop(k, None)
        self.root = tempfile.mkdtemp(prefix="s9wtac-")
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        with open(os.path.join(self.root, "a.txt"), "w") as f:
            f.write("one\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_wtac", importlib.machinery.SourceFileLoader("s9_wtac", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._git_env)
        for w in (self.m.worktree_list() or []):
            _git(self.root, "worktree", "remove", "--force", w["path"])
        shutil.rmtree(self.root, ignore_errors=True)

    def _dead_owner_worktree(self, doc):
        cwd, _e, name = self.m.worker_workspace(
            doc, {"worker_worktree": True}, self.root)
        self.m.worktree_owner_write(name, {"doc": doc, "pid": 999999,
                                           "created": time.time() - 86400})
        return cwd, name

    def test_b6_unfinished_work_is_committed_not_lost(self):
        cwd, name = self._dead_owner_worktree("REQ-lost")
        with open(os.path.join(cwd, "worker.txt"), "w") as f:
            f.write("워커가 만든 것\n")

        self.assertEqual(self.m.worktree_sweep(), [],
                         "미커밋이 있는데 거뒀다")
        st = self.m.worktree_state(name)
        self.assertFalse(st["dirty"], "커밋하지 않았다 — 거두면 사라진다")
        self.assertEqual(st["ahead"], 1, "그 가지에 커밋이 안 남았다")
        self.assertTrue(os.path.isdir(cwd), "합칠 것이 있는데 자리를 거뒀다")
        msg = _git(self.root, "log", "-1", "--format=%s",
                   f"wt/{name}").stdout
        self.assertIn("REQ-lost", msg, "무엇의 작업인지 커밋이 말하지 않는다")

    def test_b7_live_owner_is_left_alone(self):
        cwd, _e, name = self.m.worker_workspace(
            "REQ-busy", {"worker_worktree": True}, self.root)
        self.m.worktree_owner_write(name, {"doc": "REQ-busy",
                                           "pid": os.getpid(),
                                           "created": time.time() - 86400})
        with open(os.path.join(cwd, "wip.txt"), "w") as f:
            f.write("아직 쓰는 중\n")
        self.m.worktree_sweep()
        self.assertTrue(self.m.worktree_state(name)["dirty"],
                        "일하는 중인 워커의 작업을 커밋해 버렸다")


class WorktreeEnvelope(unittest.TestCase):
    """B5 — 워크트리 워커는 자기 가지에 커밋할 수 있어야 한다.

    실사고 2026-08-28 15:07: 워크트리에서 돈 무인 작업자가 REQ-20260828-007 을
    고쳐 놓고 **커밋하지 못했다** — 봉투(allowedTools)에 git 이 없었다. 규율은
    "자기 가지에 커밋하라"인데 그럴 손이 없었던 것이다. 변경은 작업 트리에만
    남았고, 사용자 화면에는 아무것도 반영되지 않은 채 두 시간이 지났다.
    커밋할 수 없는 워크트리는 소실 장치다 — 거두는 순간 다 사라진다.

    다만 넓히지 않는다: 담고(add)·박고(commit)·보는(status·diff) 것까지다.
    push 도 checkout·reset 도 주지 않는다 — 앞엣것은 바깥으로 나가는 일이고
    뒤엣것은 남의 작업을 지우는 손이다.
    """

    def test_b5_worktree_worker_may_commit_its_branch(self):
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        self.assertIn("WORKTREE_GIT_TOOLS", src,
                      "워크트리 봉투가 따로 없다 — 워커가 커밋할 수 없다")
        m = re.search(r"WORKTREE_GIT_TOOLS = \[([^\]]*)\]", src)
        self.assertIsNotNone(m, "WORKTREE_GIT_TOOLS 를 읽을 수 없다")
        body = m.group(1)
        for allow in ("git add", "git commit", "git status", "git diff"):
            self.assertIn(allow, body, f"{allow} 가 봉투에 없다")
        for deny in ("git push", "git checkout", "git reset", "git stash"):
            self.assertNotIn(deny, body, f"{deny} 를 워커에게 준다")


if __name__ == "__main__":
    unittest.main()
