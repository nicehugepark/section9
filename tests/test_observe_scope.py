"""관찰 범위 부여 (REQ-20260902-030 · DOC-20260902-001 §2 축4).

viewer 의 읽기 범위는 프로젝트 멤버십(project role viewer)이 기본이고, 그 위에
admin 이 `observe = all | slug,…` 와 `observe_until = YYYY-MM-DD` 로 예외를
얹는다(만료 지나면 무효). 여럿이 쓰는 인스턴스(remote)에서는 미등록 뷰어 전부
열람(부트스트랩 편의)을 거부로 뒤집는다. 판정은 `doc_visible`·`stream_visible`
한 쌍, 부여는 `do_user_config_set` 한 문이다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ observe_scope
"""
import datetime
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(os.path.dirname(HERE), "bin", "s9")
MACHINE = "TESTMACH"


class ObserveScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9obs-")
        env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": MACHINE}
        for k in ("S9_SESSION", "S9_USER", "S9_SYNC"):
            env.pop(k, None)

        def cli(*argv, user=None):
            e = dict(env)
            if user:
                e["S9_USER"] = user
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=e, timeout=20, stdin=subprocess.DEVNULL)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r
        cli("init")
        cli("user", "add", "root", "--role", "admin")
        cli("user", "add", "m1")
        cli("user", "add", "vw")
        cli("user", "role", "vw", "viewer", user="root")
        cli("project", "add", "px", "--name", "PX", "--user", "root")
        cli("project", "add", "py", "--name", "PY", "--user", "root")
        cli("project", "add", "pz", "--name", "PZ", "--user", "root")
        cli("project", "member", "px", "add", "vw", "--role", "viewer",
            "--user", "root")
        cls.patch = mock.patch.dict(os.environ, {"S9_ROOT": cls.root,
                                                 "S9_MACHINE": MACHINE})
        cls.patch.start()
        for k in ("S9_SESSION", "S9_USER", "S9_SYNC"):
            os.environ.pop(k, None)
        spec = importlib.util.spec_from_loader(
            "s9_observe", importlib.machinery.SourceFileLoader("s9_observe", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        cls.px = {"type": "request", "project": "px", "user": "root"}
        cls.py = {"type": "request", "project": "py", "user": "root"}
        cls.pz = {"type": "request", "project": "pz", "user": "root"}
        cls.solo = {"type": "request", "project": "", "user": "m1"}
        cls.prj_py = {"type": "project", "slug": "py", "id": "PRJ-py"}

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        # 각 시험은 부여 없는 상태에서 시작한다
        self.m.do_user_config_set("vw", "observe", "", actor="root")
        self.m.do_user_config_set("vw", "observe_until", "", actor="root")

    def vis(self, row):
        return self.m.doc_visible(row, "vw")

    # O1. 기본 = 프로젝트 멤버십
    def test_o1_membership_default(self):
        self.assertTrue(self.vis(self.px))
        self.assertFalse(self.vis(self.py))
        self.assertFalse(self.vis(self.prj_py))
        self.assertFalse(self.vis(self.solo))

    # O2. observe=all
    def test_o2_observe_all(self):
        self.m.do_user_config_set("vw", "observe", "all", actor="root")
        for row in (self.px, self.py, self.pz, self.solo, self.prj_py):
            self.assertTrue(self.vis(row), row)

    # O3. observe=slug 목록
    def test_o3_observe_projects(self):
        self.m.do_user_config_set("vw", "observe", "py, pz", actor="root")
        self.assertTrue(self.vis(self.px))      # 멤버십은 그대로
        self.assertTrue(self.vis(self.py))
        self.assertTrue(self.vis(self.pz))
        self.assertTrue(self.vis(self.prj_py))  # 프로젝트 문서 자신도
        self.assertFalse(self.vis(self.solo))   # 목록 밖 무소속은 여전히 아님

    # O4. 만료 — 어제면 무효, 오늘·미래면 유효
    def test_o4_until_expiry(self):
        today = datetime.date.fromisoformat(self.m.today_date())
        self.m.do_user_config_set("vw", "observe", "all", actor="root")
        self.m.do_user_config_set("vw", "observe_until",
                                  (today - datetime.timedelta(days=1)).isoformat(),
                                  actor="root")
        self.assertFalse(self.vis(self.py))
        self.assertTrue(self.vis(self.px))      # 기본 멤버십으로 복귀
        for d in (today, today + datetime.timedelta(days=30)):
            self.m.do_user_config_set("vw", "observe_until", d.isoformat(),
                                      actor="root")
            self.assertTrue(self.vis(self.py), d)

    # O5. 부여 권한 — admin 만, 형식 검증
    def test_o5_grant_is_admin_only(self):
        for who in ("vw", "m1", "", "nobody"):
            with self.assertRaises(ValueError, msg=who):
                self.m.do_user_config_set("vw", "observe", "all", actor=who)
            with self.assertRaises(ValueError, msg=who):
                self.m.do_user_config_set("vw", "observe_until", "2099-01-01",
                                          actor=who)
        self.assertFalse(self.vis(self.py))
        with self.assertRaises(ValueError):
            self.m.do_user_config_set("vw", "observe_until", "2026/01/01",
                                      actor="root")
        # actor 표기 'root via dashboard' 도 admin 으로 읽힌다
        self.m.do_user_config_set("vw", "observe", "all", actor="root via dashboard")
        self.assertTrue(self.vis(self.py))
        # 회수도 admin 만
        with self.assertRaises(ValueError):
            self.m.do_user_config_set("vw", "observe", "", actor="vw")
        # pref_* 는 본인이 그대로 만진다 (회귀)
        self.m.do_user_config_set("vw", "pref_tone", "짧게", actor="vw")

    # O6. remote 인스턴스에서 미등록 뷰어는 거부
    def test_o6_remote_flips_unregistered_bootstrap(self):
        self.assertTrue(self.m.doc_visible(self.py, "nobody"))
        self.assertTrue(self.m.stream_visible("abcd1234", "nobody", rows=[]))
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        marker = os.path.join(self.root, ".s9-sync")
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write("remote — 여럿이 쓰는 자리\n")
            self.assertEqual(self.m.sync_mode(), "remote")
            self.assertFalse(self.m.doc_visible(self.py, "nobody"))
            self.assertFalse(self.m.doc_visible(self.py, ""))
            self.assertFalse(self.m.stream_visible("abcd1234", "nobody", rows=[]))
            # 등록 사용자의 판정은 remote 여도 그대로
            self.assertTrue(self.m.doc_visible(self.py, "root"))
            self.assertTrue(self.vis(self.px))
            self.assertFalse(self.vis(self.py))
            with open(marker, "w", encoding="utf-8") as f:
                f.write("local\n")
            self.assertTrue(self.m.doc_visible(self.py, "nobody"))
        finally:
            os.remove(marker)

    # O7. 회귀 — admin 전부, member 는 멤버십
    def test_o7_admin_and_member_unchanged(self):
        for row in (self.px, self.py, self.solo, self.prj_py):
            self.assertTrue(self.m.doc_visible(row, "root"), row)
        self.assertFalse(self.m.doc_visible(self.px, "m1"))
        self.assertTrue(self.m.doc_visible(self.solo, "m1"))


if __name__ == "__main__":
    unittest.main()
