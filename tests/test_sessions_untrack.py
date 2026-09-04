"""세션 바인딩 track 해제 (REQ-20260902-026, DOC-20260902-001 D7).

state/sessions 는 이 머신 것이다 — 다른 머신이 알아야 할 "누가 무엇을 맡았나"는
문서 frontmatter 의 lease 가 나른다. 두 겹 방어: .gitignore(실리포·인스턴스
템플릿 둘 다) + SYNC_DATA_PATHS. 열람(session_rows)은 로컬 바인딩으로 그대로다.
두 머신 왕복은 tests/test_two_machine.py S2 가 본다.

격리: 모듈 로드는 S9_ROOT=mktemp. 실리포는 git check-ignore(읽기)만.
실행: python3 tests/ sessions_untrack
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
S9 = os.path.join(ROOT, "bin", "s9")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _check_ignore(cwd, rel):
    r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=cwd,
                       capture_output=True, text=True)
    return r.returncode == 0


class TestSessionsUntrack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9su-")
        cls._saved = dict(os.environ)
        os.environ.update({"S9_ROOT": cls.tmp, "S9_MACHINE": "su-box",
                           "S9_USER": "tester"})
        os.environ.pop("S9_SESSION", None)
        cls.m = _load("s9_su_mod", S9)

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._saved)

    # S1. 이벤트 커밋 대상에서 빠졌다 — 지켜야 할 것은 그대로
    def test_test_sessions_untrack(self):
        """TestSessionsUntrack 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("s1_sync_paths"):
                m = self.m
                self.assertNotIn("state/sessions", m.SYNC_DATA_PATHS)
                for p in ("vault", "users", "projects"):
                    self.assertIn(p, m.SYNC_DATA_PATHS)

            # S2. .gitignore — 실리포와 인스턴스 템플릿 둘 다 state/sessions 를 막는다
        with self.subTest("s2_gitignore_real_and_template"):
                self.assertTrue(_check_ignore(ROOT, "state/sessions/x.json"),
                                "실리포 .gitignore 가 state/sessions 를 열어 두고 있다")
                self.assertNotIn("!state/sessions", open(os.path.join(ROOT, ".gitignore"),
                                                         encoding="utf-8").read())
                repo = tempfile.mkdtemp(prefix="s9su-inst-")
                subprocess.run(["git", "init", "-q", repo], check=True)
                with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as f:
                    f.write(self.m.INSTANCE_TRACK_GITIGNORE)
                self.assertTrue(_check_ignore(repo, "state/sessions/x.json"))
                self.assertFalse(_check_ignore(repo, "vault/requests/x.md"))   # 문서는 track
                self.assertFalse(_check_ignore(repo, "users/tester/machines.json"))

            # S4. 열람은 로컬 바인딩으로 그대로 — 파일을 놓으면 그 세션이 목록에 있다
        with self.subTest("s4_session_rows_from_local_binding"):
                m = self.m
                os.makedirs(m.STATE, exist_ok=True)
                with open(m.binding_path("su-box", "abcd1234"), "w", encoding="utf-8") as f:
                    json.dump({"machine": "su-box", "session": "abcd1234",
                               "user": "tester", "active_reqs": ["REQ-X"], "history": []}, f)
                rows = m.session_rows()
                self.assertIn("abcd1234", [r["sid"] for r in rows])
                row = next(r for r in rows if r["sid"] == "abcd1234")
                self.assertEqual(row["user"], "tester")
                self.assertEqual(row["reqs"], ["REQ-X"])

            # S5. docs/08 표 — state/sessions 행이 ignore 이고 lease 가 대체한다고 말한다
        with self.subTest("s5_docs08_row"):
            doc = open(os.path.join(ROOT, "docs", "08-git-sync.md"), encoding="utf-8").read()
            row = next((ln for ln in doc.splitlines()
                        if ln.startswith("| state/sessions/")), "")
            self.assertTrue(row, "docs/08 표에 state/sessions 행이 없다")
            self.assertIn("**ignore**", row)
            self.assertIn("lease", row)
            self.assertNotIn("해제 예정", row)

if __name__ == "__main__":
    unittest.main()
