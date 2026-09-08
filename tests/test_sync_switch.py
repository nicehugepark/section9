"""Settings 「저장소」 판의 문서 동기화 스위치 (REQ-20260908-068).

주인 물음 2026-09-08 21:00: 「깃헙 동기화 설정은 세팅스에서 기본값을 수정할 수
있지?」 — 없었다. 값은 저장소 하나의 것(`.s9-sync`)이라 계정 판이 아니라 「저장소」
판에 서고, 판정(바꿀 수 있나·remote 를 고를 수 있나)은 서버 한 곳이 한다.
화면은 `git_state()["sync_cfg"]` 를 그대로 그리고, 바꾸기는 `s9 sync --on/--off`
와 같은 sync_set_mode 한 경로를 지난다.

실행: python3 tests/ sync_switch
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class SyncSwitch(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC")}
        self.tmp = tempfile.mkdtemp(prefix="s9syncsw-")
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "vault"))
        git(self.root, "init", "-q", "-b", "main")
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_SYNC", None)
        name = "s9syncsw_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.user_role = lambda n: "admin" if n == "boss" else "member"

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def marker(self, mode="local"):
        self.m.sync_set_mode(mode, chosen=False)

    def origin(self):
        bare = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", bare)
        git(self.root, "remote", "add", "origin", bare)

    # -- 얼굴 셋 --------------------------------------------------------
    def test_w1_no_marker_means_no_sync_and_no_hand(self):
        st = self.m.sync_panel_state(actor="boss")
        self.assertFalse(st["marker"])
        self.assertEqual(st["mode"], "")
        self.assertFalse(st["can"]["ok"])
        self.assertIn("instance init", st["can"]["why"])

    def test_w2_admin_with_origin_may_choose_both(self):
        self.marker("local")
        self.origin()
        st = self.m.sync_panel_state(actor="boss")
        self.assertEqual((st["mode"], st["origin"], st["can"]["ok"]),
                         ("local", True, True))
        self.assertEqual(st["remote_why"], "")

    def test_w3_no_origin_keeps_remote_out_of_reach(self):
        self.marker("local")
        st = self.m.sync_panel_state(actor="boss")
        self.assertTrue(st["can"]["ok"])
        self.assertFalse(st["origin"])
        self.assertIn("origin", st["remote_why"])
        res = self.m.sync_mode_do("remote", actor="boss")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], st["remote_why"])
        self.assertEqual(self.m.sync_mode(), "local", "막았는데 값이 바뀌었다")

    def test_w4_not_admin_reads_but_does_not_change(self):
        self.marker("remote")
        self.origin()
        st = self.m.sync_panel_state(actor="alice")
        self.assertEqual(st["mode"], "remote", "값은 누구에게나 보인다")
        self.assertFalse(st["can"]["ok"])
        self.assertIn("admin", st["can"]["why"])
        res = self.m.sync_mode_do("local", actor="alice")
        self.assertFalse(res["ok"])
        self.assertEqual(self.m.sync_mode(), "remote")

    # -- 바꾸기 ---------------------------------------------------------
    def test_w5_change_goes_through_the_one_path_and_is_chosen(self):
        self.marker("remote")          # 설치가 둔 값 — 아직 고르지 않음
        self.origin()
        self.assertFalse(self.m.sync_mode_chosen())
        res = self.m.sync_mode_do("local", actor="boss")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.m.sync_mode(), "local")
        self.assertTrue(self.m.sync_mode_chosen(), "화면에서 고른 값은 사람의 결정이다")
        self.assertEqual(res["state"]["mode"], "local")
        self.assertTrue(res["said"])
        back = self.m.sync_mode_do("remote", actor="boss")
        self.assertTrue(back["ok"], back)
        self.assertEqual(self.m.sync_mode(), "remote")

    def test_w6_proxy_never_changes_the_repository(self):
        self.marker("local")
        self.origin()
        res = self.m.sync_mode_do("remote", actor="boss", proxy_for="alice")
        self.assertFalse(res["ok"])
        self.assertEqual(self.m.sync_mode(), "local")

    def test_w7_the_repo_panel_carries_it(self):
        self.marker("local")
        st = self.m.git_state(actor="boss")
        self.assertIn("sync_cfg", st)
        self.assertEqual(st["sync_cfg"]["mode"], "local")


if __name__ == "__main__":
    unittest.main(verbosity=2)
