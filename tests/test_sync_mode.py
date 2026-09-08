"""바깥과 오갈지는 사람이 고른다 (REQ-20260828-019-62x6).

사용자: "상태가 전이될 때마다 깃 커밋과 깃헙 풀, 푸시가 자동으로 될텐데, 개인
로컬용으로만 사용할 수 있게 pull, push를 하지 않게 기본적으로는 off 했으면 한다.
설치 시 혼자 사용이면 off, 여럿이서 사용이면 on으로 할 수 있게 질문 유도 후 반영."

그리고 이어서: **"로컬 커밋은 기본인데... 끌 일이 없잖아."** 그 말이 맞다 —
끌 일이 없는 것에는 스위치를 달지 않는다. 스위치는 설명할 것을 하나 늘리고,
아무도 안 끄는 스위치는 그 값을 못 갚는다.

그래서 셋(commit·pull·push)을 한 덩이로 켜던 것을 나누되 스위치는 하나만 둔다:

    로컬 커밋   언제나       스위치 없음 — 문서는 커밋돼야 남는다
    pull·push   기본 끔      instance init 이 묻고, s9 sync 로 나중에도 바꾼다

파일도 새로 만들지 않는다. `.s9-sync` 하나의 **내용이 모드**다 — 두 파일이면
조합이 넷이 되고 그중 둘은 뜻이 없다.

격리: S9_ROOT=mktemp + bare 원격. 실행: python3 tests/ sync_mode
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class SyncMode(unittest.TestCase):
    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items()
                      if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self._sync = os.environ.pop("S9_SYNC", None)
        self.tmp = tempfile.mkdtemp(prefix="s9sync-")
        self.bare = os.path.join(self.tmp, "origin.git")
        _git(self.tmp, "init", "-q", "--bare", self.bare)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "vault"))
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        _git(self.root, "remote", "add", "origin", self.bare)
        with open(os.path.join(self.root, "vault", "seed.md"), "w") as f:
            f.write("seed\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        _git(self.root, "push", "-q", "-u", "origin", "main")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_sync", importlib.machinery.SourceFileLoader("s9_sync", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_SYNC", None)
        if self._sync is not None:
            os.environ["S9_SYNC"] = self._sync
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mark(self, text):
        with open(os.path.join(self.root, ".s9-sync"), "w",
                  encoding="utf-8") as f:
            f.write(text)

    def _new_doc(self, name):
        with open(os.path.join(self.root, "vault", name), "w") as f:
            f.write("x\n")

    def _remote_count(self):
        r = _git(self.bare, "rev-list", "--count", "main")
        return int((r.stdout or "0").strip() or 0)

    def _local_count(self):
        r = _git(self.root, "rev-list", "--count", "main")
        return int((r.stdout or "0").strip() or 0)

    # N1. 혼자 쓰는 자리 — 커밋은 되고 바깥으로는 안 나간다.
    def test_n1_local_commits_but_never_pushes(self):
        self._mark("local")
        self.assertEqual(self.m.sync_mode(), "local")
        self._new_doc("a.md")
        before = self._remote_count()
        self.assertEqual(self.m.sync_run("test"), "local")
        self.assertEqual(self._local_count(), 2, "로컬 커밋이 안 됐다")
        self.assertEqual(self._remote_count(), before,
                         "혼자 쓰기인데 바깥으로 나갔다")

    # N2. 여럿이 쓰는 자리 — 바깥까지 간다.
    def test_n2_remote_pushes(self):
        self._mark("remote")
        self.assertEqual(self.m.sync_mode(), "remote")
        self._new_doc("b.md")
        self.assertEqual(self.m.sync_run("test"), "ok")
        self.assertEqual(self._remote_count(), 2, "바깥으로 안 갔다")

    # B1. 옛 마커("on — …")를 쓰던 인스턴스가 조용히 끊기면 안 된다.
    def test_b1_legacy_marker_reads_as_remote(self):
        self._mark("on — 문서 이벤트마다 commit→pull→push\n")
        self.assertEqual(self.m.sync_mode(), "remote",
                         "이미 여럿이 쓰던 인스턴스가 조용히 끊긴다")

    # B2. 마커가 없으면 아무 git 쓰기도 없다 — 코드 리포를 클론한 사람.
    def test_b2_no_marker_no_writes(self):
        self.assertEqual(self.m.sync_mode(), "")
        self.assertFalse(self.m.sync_enabled())

    # B3. 끄는 손잡이는 그대로 살아 있다.
    def test_b3_env_kill_switch(self):
        self._mark("remote")
        os.environ["S9_SYNC"] = "off"
        self.assertEqual(self.m.sync_mode(), "")
        self.assertFalse(self.m.sync_enabled())

    # B4. 나중에도 바꾼다 — "파일을 지우세요" 를 외우게 하지 않는다.
    def test_b4_toggle_writes_mode(self):
        self._mark("local")
        self.m.sync_set_mode("remote")
        self.assertEqual(self.m.sync_mode(), "remote")
        self.m.sync_set_mode("local")
        self.assertEqual(self.m.sync_mode(), "local")


class InstanceInitDoesNotAsk(unittest.TestCase):
    """B5 → D1·D2·D5 (REQ-20260908-065) — 설치는 묻지 않는다, origin 이 정한다.

    처음에는 「혼자/여럿」을 묻고 답이 없으면 local 이었다(위 원문). 주인이
    2026-09-08 뒤집었다: 「켜져 있는 게 기본이고 끄는 게 옵션이어야 하는 거
    아니야」. origin 이 있으면 remote, 없으면 local, 끄는 길은 `s9 sync --off`."""

    def _mod(self):
        spec = importlib.util.spec_from_loader(
            "s9_ask", importlib.machinery.SourceFileLoader("s9_ask", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_d1_an_origin_means_remote_without_asking(self):
        m = self._mod()
        self.assertEqual(m.default_sync_mode(has_origin=True), "remote",
                         "origin 을 줬는데 바깥과 오가지 않는다 — 켜진 것이 기본이다")

    def test_d2_no_origin_means_local(self):
        m = self._mod()
        self.assertEqual(m.default_sync_mode(has_origin=False), "local",
                         "내보낼 곳이 없는데 remote 다")

    def test_d5_the_asking_name_is_gone(self):
        """물음이 없는데 「묻는다」는 이름이 남으면 다음 사람이 물음을 되살린다."""
        self.assertFalse(hasattr(self._mod(), "ask_sync_mode"))


if __name__ == "__main__":
    unittest.main()
