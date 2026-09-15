"""코드 파일에서 충돌한 sync 를 푸는 길 (REQ-20260915-009-2n7g).

실제 사고 2026-09-15 17:13~18:55(1시간 40분): 맥이 `tests/test_s9_code_args.py`
의 옛 문구 대조를 고쳤고, 같은 무렵 다른 컴퓨터가 **같은 줄을 같은 값으로**
고쳤다(주석만 달랐다). 그 뒤 pull 은 240초마다 같은 자리에서 충돌하고 물러났다.
못 받은 커밋이 112건까지 쌓이는 동안 화면이 말한 것은 「충돌 — s9 sync resolve
필요」 한 줄뿐이었고, 그 resolve 는 **문서 id 만** 받아 코드 파일에는 댈 것이
없었다(「확정할 문서 id 가 없다」). 결국 사람이 손으로 git rebase 를 걸었다.

이 시험이 지키는 계약:
  ① 충돌이 서면 `_sync_abort_rebase()` 가 그것을 지우기 **전에** 적는다 —
     충돌한 경로 · 되감던 내 commit · 그 경로를 마지막으로 만진 origin 쪽
     commit · 두 본의 차이.
  ② `s9 sync --status` 의 다음 행동 줄과 대시보드 칩의 글이 「충돌」 한 낱말 대신 그 파일과 양쪽
     commit 을 짚고, 코드 파일이면 `--paths` 를 준다.
  ③ 다음 pull 이 성공하면 그 기록은 지워진다 — 지나간 충돌을 계속 짚으면 거짓이다.
  ④ `sync_resolve(..., paths=[...])` 가 코드 파일을 한쪽으로 확정하고 rebase 를 잇는다.
  ⑤ 지목하지 않은 것이 함께 충돌하면 abort 하고, 코드 파일은 **경로 그대로**
     돌려준다 — 그대로 `--paths` 에 넣을 수 있어야 한다.
  ⑥ 저장소 밖 경로·추적되지 않는 경로는 거부한다.

실행: python3 tests/ sync_conflict_paths
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


class ConflictOnACodeFile(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC")}
        self._genv = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
        for k in self._genv:
            os.environ.pop(k, None)
        os.environ.pop("S9_SYNC", None)
        self.tmp = tempfile.mkdtemp(prefix="s9conf-")
        self.bare = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", self.bare)
        self.root = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.root, "tests"))
        os.makedirs(os.path.join(self.root, "vault"))
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        os.environ["S9_ROOT"] = self.root
        name = "s9conf_" + os.path.basename(self.tmp)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.sync_set_mode("remote")
        self.code = "tests/test_thing.py"
        self._write(self.code, "assert 1\n옛 줄\nassert 2\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "첫")
        git(self.root, "remote", "add", "origin", self.bare)
        git(self.root, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.update(self._genv)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ 도구
    def _write(self, rel, body):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)

    def _read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def _both_fix_the_same_line(self):
        """그날 일어난 일 그대로 — 두 컴퓨터가 같은 줄을 각자 고친다."""
        other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-q", self.bare, other)
        git(other, "config", "user.email", "o@example.com")
        git(other, "config", "user.name", "o")
        with open(os.path.join(other, self.code), "w", encoding="utf-8") as f:
            f.write("assert 1\n새 줄  # 남의 주석\nassert 2\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "남이 고친 그 줄")
        git(other, "push", "-q", "origin", "main")
        self._write(self.code, "assert 1\n새 줄  # 내 주석\nassert 2\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "내가 고친 그 줄")

    def _pull_and_fail(self):
        """폴이 하는 그대로 — 당기다 충돌하면 적고 되돌린다."""
        r = self.m._sync_pull_cmd(timeout=20)
        self.assertNotEqual(r.returncode, 0, "충돌이 나야 하는 자리인데 pull 이 통과했다")
        self.assertEqual(self.m._sync_fail_kind(r.stderr), "conflict")
        rec = self.m._sync_conflict_record()
        self.m._sync_abort_rebase()
        return rec

    # ------------------------------------------------------------ 시험
    def test_conflict_is_written_down_before_the_abort(self):
        """① 되돌리기가 지우기 전에 적는다 — 파일·양쪽 commit·두 본의 차이."""
        self._both_fix_the_same_line()
        rec = self._pull_and_fail()
        self.assertEqual(rec.get("paths"), [self.code])
        self.assertEqual(rec["mine"]["subject"], "내가 고친 그 줄")
        f = rec["files"][0]
        self.assertEqual(f["path"], self.code)
        self.assertEqual(f["theirs"]["subject"], "남이 고친 그 줄")
        self.assertIn("내 주석", f["diff"])
        self.assertIn("남의 주석", f["diff"])
        # 적어 둔 것은 되돌린 뒤에도 읽힌다 — 그것이 이 기록의 전부다.
        self.assertEqual(self.m.sync_conflict_last().get("paths"), [self.code])

    def test_status_hint_names_the_file_and_both_commits(self):
        """② 「충돌」 한 낱말로는 무엇을 해야 할지 알 수 없다."""
        self._both_fix_the_same_line()
        self._pull_and_fail()
        hint = self.m.sync_status_hint({"kind": "conflict"})
        self.assertIn(self.code, hint)
        self.assertIn("남이 고친 그 줄", hint)
        self.assertIn("내가 고친 그 줄", hint)
        self.assertIn("--paths", hint, "코드 파일인데 문서 id 로 풀라고 말한다")

    def test_dashboard_chip_names_the_file(self):
        """② 칩을 눌러도 파일 이름 하나 안 나오던 자리 — 걸린 자리를 싣는다."""
        self._both_fix_the_same_line()
        self._pull_and_fail()
        txt = self.m.sync_alert_text({"kind": "conflict", "count": 7,
                                      "stage": "pull"}, pending=112)
        self.assertIn(self.code, txt)
        self.assertIn("112개", txt)
        # 충돌이 아닌 사유에는 붙지 않는다 — 없는 자리를 짚으면 거짓이다.
        self.assertNotIn(self.code, self.m.sync_alert_text(
            {"kind": "net", "count": 3, "stage": "pull"}, pending=1))

    def test_a_vault_conflict_still_says_id(self):
        """② 문서는 종전대로 id 로 푼다 — 두 사전을 섞지 않는다."""
        self.assertFalse(self.m._sync_path_is_doc("tests/a.py"))
        self.assertTrue(self.m._sync_path_is_doc("vault/requests/2026/09/REQ-1.md"))

    def test_a_good_pull_clears_the_record(self):
        """③ 지나간 충돌을 계속 짚으면 그 줄은 거짓이다."""
        self._both_fix_the_same_line()
        self._pull_and_fail()
        self.assertTrue(self.m.sync_conflict_last())
        self.m.sync_conflict_clear()
        self.assertEqual(self.m.sync_conflict_last(), {})
        self.assertEqual(self.m.sync_status_hint({"kind": "conflict"}),
                         "`s9 sync resolve <id> --take mine|theirs` 로 한쪽을 확정")

    def test_resolve_by_path_takes_theirs(self):
        """④ 사람이 git 명령을 치지 않고 한쪽을 확정한다 — origin 본."""
        self._both_fix_the_same_line()
        self._pull_and_fail()
        res = self.m.sync_resolve([], "theirs", paths=[self.code])
        self.assertTrue(res.get("ok"), res.get("error"))
        self.assertEqual(res["resolved"], [self.code])
        self.assertIn("남의 주석", self._read(self.code))
        self.assertNotIn("<<<<<<<", self._read(self.code))
        self.assertFalse(self.m._rebase_in_progress(), "rebase 가 남아 있다")
        # 진 쪽은 사라지지 않는다 — 경로의 구분자는 눕혀 한 파일로 둔다.
        self.assertTrue(any("%" in os.path.basename(p) for p in res["saved"]),
                        res["saved"])
        self.assertEqual(self.m.sync_conflict_last(), {}, "푼 충돌이 그대로 남았다")

    def test_resolve_by_path_takes_mine(self):
        """④ 반대쪽도 같은 한 줄로 — 내 본."""
        self._both_fix_the_same_line()
        self._pull_and_fail()
        res = self.m.sync_resolve([], "mine", paths=[self.code])
        self.assertTrue(res.get("ok"), res.get("error"))
        self.assertIn("내 주석", self._read(self.code))

    def test_unnamed_code_file_comes_back_as_a_path(self):
        """⑤ 돌려주는 것을 그대로 `--paths` 에 넣을 수 있어야 한다."""
        self._both_fix_the_same_line()
        other = os.path.join(self.tmp, "other")
        with open(os.path.join(other, "tests", "또.py"), "w", encoding="utf-8") as f:
            f.write("남\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "남의 또 하나")
        git(other, "push", "-q", "origin", "main")
        self._write("tests/또.py", "나\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "내 또 하나")
        res = self.m.sync_resolve([], "theirs", paths=[self.code])
        self.assertFalse(res.get("ok"))
        self.assertIn("tests/또.py", res.get("others") or [])
        self.assertFalse(self.m._rebase_in_progress())

    def test_paths_outside_the_repo_are_refused(self):
        """⑥ 이 명령이 저장소 밖에 파일을 쓰는 길이 되면 안 된다."""
        res = self.m.sync_resolve([], "theirs", paths=["../바깥.py"])
        self.assertFalse(res.get("ok"))
        self.assertIn("저장소 밖", res.get("error", ""))

    def test_untracked_paths_are_refused(self):
        """⑥ 추적하지 않는 경로는 충돌할 수 없다 — 오타를 조용히 받지 않는다."""
        self._write("tests/없던.py", "x\n")
        res = self.m.sync_resolve([], "theirs", paths=["tests/없던.py"])
        self.assertFalse(res.get("ok"))
        self.assertIn("추적하지 않는", res.get("error", ""))

    def test_nothing_named_is_refused(self):
        """경로도 id 도 없으면 확정할 것이 없다 — 종전 문구를 넓힌다."""
        with self.assertRaises(ValueError) as e:
            self.m.sync_resolve([], "theirs")
        self.assertIn("--paths", str(e.exception))

    def test_take_is_still_required(self):
        """`--take` 없이는 어느 쪽인지 기계가 고르지 않는다."""
        with self.assertRaises(ValueError):
            self.m.sync_resolve([], "", paths=[self.code])


if __name__ == "__main__":
    unittest.main(verbosity=2)
