"""보관함에 갇힌 작업 — 남은 두 자리 (REQ-20260914-005-62x6).

REQ-20260914-003-62x6 이 `_sync_pull_cmd` 를 막았으나 같은 기제가 두 자리 더
열려 있었다.

1. `sync resolve` 의 `rebase --autostash @{upstream}` — rebase 는 성공하는데
   마지막 되돌리기(`stash apply`)만 실패하면 git 은 걷어 간 변경을 보관함에
   `autostash` 로 남기고 **returncode 0** 으로 끝낸다. 작업 트리는 HEAD 로
   돌아가 있고 알려 주는 것은 stderr 한 줄뿐이다.
2. `s9 doctor` — state/sync-stash-orphan.txt 는 되돌리기 검사가 선 뒤의 실패만
   받는다. 그 전에 이미 쌓인 autostash(2026-09-14 기준 다섯, 09-06~09-14)는
   여전히 어느 화면에도 뜨지 않았다.

고정하는 계약 셋.
1. resolve 의 rebase 뒤에 남은 autostash 는 작업 트리로 돌아오고 보관함에서 빠진다.
2. doctor 는 `git stash list` 의 autostash 를 세어 warn 으로 올리고 되돌리는
   명령을 함께 적는다.
3. 보관함이 비어 있으면 그대로 ok 다.

격리: S9_ROOT=mktemp + 진짜 git 저장소(원격도 진짜다).
실행: python3 tests/ sync_stash_left
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
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


class TheResolveKeepsTheWorkingTree(unittest.TestCase):
    """`sync resolve` 의 rebase 도 되돌리기에만 실패할 수 있다."""

    def setUp(self):
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="s9resolvestash-")
        self.up = os.path.join(self.tmp, "up")
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(self.up)
        _git(self.up, "init", "-q", "-b", "main")
        _git(self.up, "config", "user.name", "t")
        _git(self.up, "config", "user.email", "t@t")
        for name, body in (("code.py", "원래 줄\n"), ("doc.md", "문서\n")):
            with open(os.path.join(self.up, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        _git(self.up, "add", "-A")
        _git(self.up, "commit", "-qm", "init")
        _git(self.tmp, "clone", "-q", self.up, self.root)
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "config", "user.email", "t@t")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        with open(os.path.join(self.root, ".s9-sync"), "w", encoding="utf-8") as fh:
            fh.write("remote\n")
        self.code = os.path.join(self.root, "code.py")
        self.doc = os.path.join(self.root, "doc.md")
        os.environ["S9_ROOT"] = self.root
        spec = importlib.util.spec_from_loader(
            "s9_resolvestash", importlib.machinery.SourceFileLoader(
                "s9_resolvestash", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stash_list(self):
        return [l for l in (_git(self.root, "stash", "list").stdout or "").splitlines()
                if l.strip()]

    def _store_autostash(self, text):
        """git 이 되돌리기에 실패했을 때 남기는 그 모양을 만든다."""
        with open(self.code, "w", encoding="utf-8") as fh:
            fh.write(text)
        sha = (_git(self.root, "stash", "create").stdout or "").strip()
        self.assertTrue(sha, "보관함을 만들지 못했다")
        _git(self.root, "stash", "store", "-m", "autostash", "-q", sha)
        _git(self.root, "checkout", "-q", "--", "code.py")   # 작업 트리는 HEAD 로

    # --- 정상 -------------------------------------------------------------
    def test_a_stash_left_by_the_resolve_rebase_comes_back(self):
        # 원격이 앞서 있어야 resolve 의 rebase 가 실제로 돈다
        with open(os.path.join(self.up, "other.py"), "w", encoding="utf-8") as fh:
            fh.write("원격의 다른 파일\n")
        _git(self.up, "add", "-A")
        _git(self.up, "commit", "-qm", "원격")

        real = self.m._sync_git

        def spy(*argv, timeout=6):
            r = real(*argv, timeout=timeout)
            if argv[:2] == ("rebase", "--autostash"):
                # rebase 는 성공했는데 되돌리기만 실패한 그 자리
                self._store_autostash("내가 고치던 줄\n")
            return r

        with mock.patch.object(self.m, "_sync_git", spy), \
             mock.patch.object(self.m, "find_path", lambda d: self.doc), \
             mock.patch.object(self.m, "_serve_owner_alive", lambda: True), \
             mock.patch.object(self.m, "sync_run", lambda *a, **k: "local"):
            out = self.m.sync_resolve(["DOC-20260914-000-test"], "mine")

        self.assertTrue(out.get("ok"), out)
        with open(self.code, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "내가 고치던 줄\n",
                             "resolve 의 rebase 가 걷어 간 작업이 돌아오지 않았다 — "
                             "returncode 0 뒤의 조용한 유실이 이 사고의 본체다")
        self.assertEqual(self._stash_list(), [],
                         "되돌린 뒤에도 보관함에 남겼다 — 같은 것이 두 벌 쌓인다")


class TheDoctorSeesTheStrandedWork(unittest.TestCase):
    """보관함에 이미 쌓인 autostash 는 아무 화면에도 안 떴다 — doctor 가 센다."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9doctor_stash", importlib.machinery.SourceFileLoader(
                "s9doctor_stash", S9_DOCTOR))
        cls.d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.d)

    def _base(self, **kw):
        s = {"instance": True, "mode": "remote", "chosen": True,
             "origin": "git@x:y.git", "orphan": [], "autostash": 0}
        s.update(kw)
        return s

    # --- 실패 -------------------------------------------------------------
    def test_stranded_autostash_is_reported(self):
        v = self.d.sync_verdict(self._base(autostash=5))
        self.assertEqual(v["level"], "warn",
                         "보관함에 갇힌 작업 다섯을 ok 로 넘겼다")
        self.assertIn("autostash", v["line"])
        self.assertIn("stash apply", v["advice"])
        # orphan 파일이 함께 있으면 그 줄이 이긴다(critical) — 그때도 이미 쌓인
        # 건수가 함께 보여야 한다. 「1건」만 읽고 넘어가면 나머지는 또 안 보인다.
        v = self.d.sync_verdict(self._base(
            orphan=["2026-09-14T00:00:00+09:00 " + "a" * 40], autostash=7))
        self.assertEqual(v["level"], "critical")
        self.assertIn("7건", v["line"],
                      "orphan 줄 뒤에 이미 쌓인 autostash 가 가려졌다")

    # --- 경계 -------------------------------------------------------------
    def test_a_clean_repo_stays_ok(self):
        self.assertEqual(self.d.sync_verdict(self._base())["level"], "ok")


if __name__ == "__main__":
    unittest.main()
