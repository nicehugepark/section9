"""origin 이 있으면 문서는 밖으로 나간다 (REQ-20260908-050-62x6).

실제 사고 2026-09-08. 사용자가 `s9 instance init` 으로 section9-test 인스턴스를
만들고 다른 WSL 머신에서 클론해 설치한 뒤 말했다: **"요청 문서가 깃헙으로
동기화가 되지 않는다."**

문서는 만들어졌고 로컬 커밋도 됐다. 마커가 `local` 이었을 뿐이다. 그리고 그
마커는 **track 되는 파일**이라 클론에도 그대로 실려 갔다 — 새 머신에서는 아무도
묻지 않았고 물을 자리도 없었다. 첫 머신에서도 아무도 고른 적이 없다:
`s9 instance init` 이 파이프 안에서 돌아 물음이 막혔고(`ask_sync_mode` 는 그때
`local` 을 돌려준다) 그 값이 그대로 굳었다.

설계는 원래 **사실로 판정**하려 했다 — REQ-20260905-013: "두 번째 머신이 붙는
순간이 곧 「여럿·바깥과 오간다」의 판정이다." 두 곳이 어긋나 있었다.

1. `attach_turns_sync_on` 이 `os.path.exists(SYNC_MARKER)` 면 물러났다. 그런데
   `s9 instance init` 은 마커를 **항상** 만든다 — 이 판정은 인스턴스에서 한 번도
   실행된 적이 없다.
2. 판정의 재료가 「사용자 문서에 붙은 머신 수」 하나뿐이었다. 새 머신에서
   사용자를 새로 등록하면 붙은 머신은 영영 하나다.

재료를 하나 더 둔다 — **origin 이 있다.** 없으면 내보낼 곳이 없으니 local 이
맞고, 있으면 내보내라고 둔 것이다. 대신 **사람이 고른 값은 뒤집지 않는다** —
`s9 sync --off` 가 무력해지면 안 되므로, 설치가 기본으로 둔 값과 사람이 고른
값을 마커가 구별한다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ sync_mode_fact
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


class ModeFollowsTheFact(unittest.TestCase):
    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self._sync = os.environ.pop("S9_SYNC", None)
        self.tmp = tempfile.mkdtemp(prefix="s9syncfact-")
        self.bare = os.path.join(self.tmp, "origin.git")
        _git(self.tmp, "init", "-q", "--bare", self.bare)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "vault"))
        _git(self.root, "init", "-q", "-b", "main")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_syncfact", importlib.machinery.SourceFileLoader("s9_syncfact", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m._SYNC_RAISE_AT[0] = 0.0

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        if self._sync is not None:
            os.environ["S9_SYNC"] = self._sync
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _origin(self):
        _git(self.root, "remote", "add", "origin", self.bare)

    def _raise(self):
        self.m._SYNC_RAISE_AT[0] = 0.0
        return self.m.sync_autoraise()

    # 정상 — 사고 그 자리
    def test_the_default_local_rises_when_an_origin_exists(self):
        self.m.sync_set_mode("local", chosen=False)
        self._origin()
        self.assertEqual(self._raise(), "remote")
        self.assertEqual(self.m.sync_mode(), "remote",
                         "origin 이 있는데 문서가 밖으로 안 나간다 — 2026-09-08 그 자리")

    # 경계 — 내보낼 곳이 없으면 올리지 않는다
    def test_without_an_origin_it_stays_local(self):
        self.m.sync_set_mode("local", chosen=False)
        self.assertEqual(self._raise(), "")
        self.assertEqual(self.m.sync_mode(), "local")

    # 실패 — 사람이 고른 값은 사실이 뒤집지 않는다
    def test_a_chosen_local_is_never_raised(self):
        self.m.sync_set_mode("local")          # `s9 sync --off` 가 부르는 그 길
        self._origin()
        self.assertEqual(self._raise(), "")
        self.assertEqual(self.m.sync_mode(), "local",
                         "사람이 끈 것을 기계가 다시 켰다 — --off 가 무력해진다")

    # 경계 — 한 번 올라간 뒤에는 다시 손대지 않는다
    def test_it_does_not_thrash(self):
        self.m.sync_set_mode("local", chosen=False)
        self._origin()
        self._raise()
        self.assertEqual(self._raise(), "", "두 번째 틱에서도 또 올린다")

    def test_the_marker_says_who_chose(self):
        self.m.sync_set_mode("local", chosen=False)
        self.assertFalse(self.m.sync_mode_chosen())
        self.m.sync_set_mode("local")
        self.assertTrue(self.m.sync_mode_chosen())

    def test_an_absent_marker_counts_as_chosen(self):
        # 마커가 없으면 인스턴스가 아니다 — 아무 git 쓰기도 하지 않는다
        self.assertTrue(self.m.sync_mode_chosen())
        self._origin()
        self.assertEqual(self._raise(), "")
        self.assertEqual(self.m.sync_mode(), "")


class TheSecondMachineJudgment(unittest.TestCase):
    """`attach_turns_sync_on` 은 인스턴스에서 한 번도 실행된 적이 없었다."""

    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="s9syncatt-")
        self.bare = os.path.join(self.tmp, "origin.git")
        _git(self.tmp, "init", "-q", "--bare", self.bare)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "vault"))
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "remote", "add", "origin", self.bare)
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_syncatt", importlib.machinery.SourceFileLoader("s9_syncatt", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_marker_alone_no_longer_blocks_the_judgment(self):
        self.m.sync_set_mode("local", chosen=False)
        self.assertTrue(self.m.attach_turns_sync_on({"machines": ["a", "b"]}),
                        "마커가 있다는 이유로 두 번째 머신 판정을 건너뛴다 — "
                        "instance init 은 마커를 항상 만든다")

    def test_one_machine_is_not_two(self):
        self.m.sync_set_mode("local", chosen=False)
        self.assertFalse(self.m.attach_turns_sync_on({"machines": ["a"]}))

    def test_a_chosen_local_still_wins(self):
        self.m.sync_set_mode("local")
        self.assertFalse(self.m.attach_turns_sync_on({"machines": ["a", "b"]}),
                         "사람이 끈 것을 두 번째 머신이 다시 켠다")

    def test_already_remote_is_left_alone(self):
        self.m.sync_set_mode("remote")
        self.assertFalse(self.m.attach_turns_sync_on({"machines": ["a", "b"]}))


if __name__ == "__main__":
    unittest.main()
