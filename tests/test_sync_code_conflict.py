"""코드 파일 충돌에 갇힌 sync (REQ-20260915-009-2n7g).

실제 사고 2026-09-15 17:13~18:55: 두 컴퓨터가 같은 시험의 같은 줄을 같은 값으로
고쳤고(주석만 달랐다) 맥의 sync 는 240초마다 같은 자리에서 서며 물러났다 —
못 받은 커밋이 112건까지 쌓였다. 빠져나갈 길이 없었다: `s9 sync resolve` 는
**문서 id** 만 받아 코드 파일에는 댈 것이 없었고, 화면은 「충돌 — s9 sync
resolve 필요」한 줄만 말해 무엇이 충돌했는지는 로그를 열어야 나왔다.

여기서 재는 것 셋:
  ① 코드 파일도 `--paths` 로 확정된다 — 사람이 git 명령을 치지 않는다
  ② 같은 고침이 따로 담긴 것은 스스로 알아본다(완전히 같으면 지나가고,
     거의 같으면 짚는다)
  ③ 막힌 사실이 파일 이름·두 commit 과 함께 선다 (상태 줄·다음 행동·칩 툴팁)

**충돌은 흉내 내지 않는다** — bare origin + 클론 둘로 실제로 만든 뒤 잰다.

실행: python3 tests/ sync_code_conflict
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

CODE = "tests/test_thing.py"
DOC = "vault/requests/2026/09/{id}.md"


def sh(*argv, cwd=None, env=None, check=False):
    r = subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True,
                       text=True, timeout=60, stdin=subprocess.DEVNULL)
    if check and r.returncode != 0:
        raise AssertionError("%s 실패: %s%s" % (" ".join(argv), r.stdout, r.stderr))
    return r


def code_text(assertion, comment):
    return ("class T:\n"
            "    def test_one(self):\n"
            f"        # {comment}\n"
            f"        assert {assertion}\n")


def doc_text(doc_id, body):
    return (f"---\nid: {doc_id}\ntype: request\ntitle: t\nstatus: open\n"
            f"user: tester\nupdated: 2026-09-15T10:00:00+09:00\n---\n\n"
            f"## Original\n\n{body}\n\n## Notes\n\n## History\n")


class CodeConflict(unittest.TestCase):
    """bare origin + 클론 A(S9_ROOT) + 클론 B."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9cc-")
        cls.bare = os.path.join(cls.base, "origin.git")
        sh("git", "init", "-q", "--bare", "-b", "main", cls.bare, check=True)
        cls.a = os.path.join(cls.base, "a")
        cls.b = os.path.join(cls.base, "b")
        for d in (cls.a, cls.b):
            os.makedirs(d)
            for c in (["git", "init", "-q", "-b", "main"],
                      ["git", "config", "user.name", "t"],
                      ["git", "config", "user.email", "t@t"],
                      ["git", "remote", "add", "origin", cls.bare]):
                sh(*c, cwd=d, check=True)
        os.makedirs(os.path.join(cls.a, "state"), exist_ok=True)
        with open(os.path.join(cls.a, ".s9-sync"), "w") as f:
            f.write("remote\n")
        # state/ 는 이 머신의 살림살이다 — 실제 저장소와 같은 무시 규칙을 둔다.
        # 없으면 진 쪽을 남긴 사본(state/sync-conflict/)이 커밋에 섞여 들어가
        # 다음 rebase 를 막는다.
        cls.put(cls.a, ".gitignore", "state/*\n")
        cls.put(cls.a, "seed.txt", "seed\n")
        sh("git", "add", "-A", cwd=cls.a, check=True)
        sh("git", "commit", "-q", "-m", "seed", cwd=cls.a, check=True)
        sh("git", "push", "-q", "-u", "origin", "main", cwd=cls.a, check=True)
        sh("git", "pull", "-q", "origin", "main", cwd=cls.b, check=True)
        sh("git", "branch", "-q", "--set-upstream-to=origin/main", "main",
           cwd=cls.b, check=True)
        os.environ["S9_ROOT"] = cls.a
        os.environ.setdefault("S9_USER", "tester")
        spec = importlib.util.spec_from_loader(
            "s9_cc", importlib.machinery.SourceFileLoader("s9_cc", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.base, ignore_errors=True)

    @staticmethod
    def put(root, rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def commit(self, root, msg):
        sh("git", "add", "-A", cwd=root, check=True)
        sh("git", "commit", "-q", "-m", msg, cwd=root, check=True)

    def read(self, root, rel):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return f.read()

    def setUp(self):
        """A 를 origin 과 맞춘다 — 시험 사이의 바닥."""
        if self.m._rebase_in_progress():
            sh("git", "rebase", "--abort", cwd=self.a)
        sh("git", "fetch", "-q", cwd=self.a)
        sh("git", "reset", "-q", "--hard", "@{upstream}", cwd=self.a)
        sh("git", "pull", "-q", "--rebase", cwd=self.b)
        for n in (".sync-conflict.json", "sync.jsonl", ".sync-pull.ts",
                  ".sync-fail.ts", ".sync-queue", ".sync-alert.json"):
            try:
                os.remove(os.path.join(self.a, "state", n))
            except OSError:
                pass

    # --- 충돌 만들기 ---------------------------------------------------------
    def _base_code(self):
        self.put(self.a, CODE, code_text('x == "old"', "옛 문구"))
        self.commit(self.a, "code base")
        sh("git", "push", "-q", cwd=self.a, check=True)
        sh("git", "pull", "-q", "--rebase", cwd=self.b, check=True)

    def _code_conflict(self):
        """같은 줄을 같은 값으로 고치고 **주석만 다르다** — 그날의 그 모양."""
        self._base_code()
        self.put(self.b, CODE, code_text('x == "new"', "B 가 적은 까닭"))
        self.commit(self.b, "B edit")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.put(self.a, CODE, code_text('x == "new"', "A 가 적은 까닭"))
        self.commit(self.a, "A edit")

    def _resolve(self, ids=(), take="mine", paths=()):
        with mock.patch.object(self.m, "rebuild_index", lambda quiet=True: None):
            return self.m.sync_resolve(list(ids), take, paths=list(paths))

    # --- 1·2. 코드 파일을 --paths 로 확정한다 --------------------------------
    def test_1_paths_take_mine(self):
        self._code_conflict()
        res = self._resolve(paths=[CODE], take="mine")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["resolved"], [CODE])
        self.assertIn("A 가 적은 까닭", self.read(self.a, CODE))
        self.assertFalse(self.m._rebase_in_progress())
        self.assertEqual(res["pushed"], "ok")
        self.assertEqual(self.m.sync_status()["pending"], 0)
        # 진 쪽이 사라지지 않는다 — 경로를 편 이름으로 남는다
        cdir = os.path.join(self.a, "state", "sync-conflict")
        flat = CODE.replace("/", "__")
        self.assertIn("B 가 적은 까닭",
                      self.read(cdir, flat + ".theirs"))
        self.assertIn("A 가 적은 까닭", self.read(cdir, flat + ".mine"))

    def test_2_paths_take_theirs(self):
        self._code_conflict()
        res = self._resolve(paths=[CODE], take="theirs")
        self.assertTrue(res["ok"], res)
        self.assertIn("B 가 적은 까닭", self.read(self.a, CODE))
        # 내 커밋에 남는 것이 없으니 그대로 지나간다 (중복 판정)
        self.assertEqual(len(res["skipped"]), 1, res)
        self.assertEqual(self.m.sync_status()["pending"], 0)
        sh("git", "pull", "-q", "--rebase", cwd=self.b, check=True)
        self.assertIn("B 가 적은 까닭", self.read(self.b, CODE))

    # --- 3. 문서 id 와 파일 경로를 섞어 지목한다 ------------------------------
    def test_3_mixed_id_and_path(self):
        did = "REQ-20260915-901-test"
        self.put(self.a, DOC.format(id=did), doc_text(did, "base"))
        self._base_code()          # code base + push (문서도 함께 담긴다)
        self.put(self.b, DOC.format(id=did), doc_text(did, "from B"))
        self.put(self.b, CODE, code_text('x == "new"', "B"))
        self.commit(self.b, "B both")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.put(self.a, DOC.format(id=did), doc_text(did, "from A"))
        self.put(self.a, CODE, code_text('x == "new2"', "A"))
        self.commit(self.a, "A both")
        res = self._resolve(ids=[did], paths=[CODE], take="mine")
        self.assertTrue(res["ok"], res)
        self.assertEqual(sorted(res["resolved"]), sorted([did, CODE]))
        self.assertIn("from A", self.read(self.a, DOC.format(id=did)))
        self.assertIn('x == "new2"', self.read(self.a, CODE))

    # --- 4. CLI 도 같은 길 ---------------------------------------------------
    def test_4_cli_resolve_paths(self):
        self._code_conflict()
        env = dict(os.environ, S9_ROOT=self.a)
        r = sh(S9, "sync", "resolve", "--paths", CODE, "--take", "theirs",
               cwd=self.a, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("확정", r.stdout)
        self.assertIn("B 가 적은 까닭", self.read(self.a, CODE))

    # --- 5. 지목하지 않은 자리는 기계가 고르지 않는다 -------------------------
    def test_5_undesignated_returns_path(self):
        self._base_code()
        self.put(self.b, "bin/other.py", "b = 1\n")
        self.put(self.b, CODE, code_text('x == "B"', "B"))
        self.commit(self.b, "B two")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.put(self.a, "bin/other.py", "a = 1\n")
        self.put(self.a, CODE, code_text('x == "A"', "A"))
        self.commit(self.a, "A two")
        res = self._resolve(paths=[CODE], take="mine")
        self.assertFalse(res["ok"], res)
        # 코드 파일은 **경로 그대로** 불러야 사람이 그 이름을 다시 칠 수 있다
        self.assertIn("bin/other.py", res.get("others", []))
        self.assertFalse(self.m._rebase_in_progress())
        res = self._resolve(paths=[CODE, "bin/other.py"], take="mine")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.read(self.a, "bin/other.py"), "a = 1\n")

    # --- 6. 지목 없이 친 resolve 는 막힌 것을 보여 준다 -----------------------
    def test_6_cli_lists_conflict(self):
        self._code_conflict()
        env = dict(os.environ, S9_ROOT=self.a)
        self.m.sync_run("test")                      # 충돌로 서고 사실을 적는다
        r = sh(S9, "sync", "resolve", cwd=self.a, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(CODE, r.stdout)
        self.assertIn("A edit", r.stdout)            # 내 commit
        self.assertIn("B edit", r.stdout)            # origin 의 commit
        self.assertIn("--paths " + CODE, r.stdout)   # 그대로 칠 수 있는 명령
        self.assertIn("중복일 수 있습니다", r.stdout)  # 두 쪽이 거의 같다
        sh("git", "rebase", "--abort", cwd=self.a)

    # --- 7. 완전히 같은 고침은 충돌이 아니라 중복이다 -------------------------
    def test_7_identical_patch_passes(self):
        self._base_code()
        same = code_text('x == "new"', "같은 까닭")
        self.put(self.b, CODE, same)
        self.commit(self.b, "B same")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.put(self.a, CODE, same)
        self.commit(self.a, "A same")
        r = self.m._sync_pull_cmd(timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.m._rebase_in_progress())
        self.assertEqual(self.m.sync_status()["pending"], 0)

    # --- 8·9·10·11. 막힌 사실이 파일 이름과 함께 선다 -------------------------
    def test_8_conflict_is_recorded_and_surfaced(self):
        self._code_conflict()
        self.assertEqual(self.m.sync_run("test"), "pull-conflict")
        c = self.m.sync_conflict_state()
        self.assertEqual(c["paths"], [CODE])                       # ⑧ 파일 이름
        self.assertIn("A edit", c["mine"])                         # ⑧ 두 commit
        self.assertIn("B edit", c["theirs"])
        self.assertEqual(c["near"], [CODE])                        # 거의 같다
        st = self.m.sync_status()
        self.assertEqual(st["kind"], "conflict")
        self.assertEqual(st["conflict"]["paths"], [CODE])          # ⑨
        # ⑨ 상태 줄은 한 줄이라 **파일 이름만** 싣는다 — 경로 전부는 바로 뒤에
        # 서는 확정 명령이 말한다
        line = self.m.sync_status_line(st)
        self.assertIn(os.path.basename(CODE), line)
        self.assertNotIn(CODE, line)
        hint = self.m.sync_status_hint(st)
        self.assertIn("--paths " + CODE, hint)                     # ⑩ 칠 명령
        self.assertIn("거의 같다", hint)
        chip = self.m.sync_alert_text({"kind": "conflict", "count": 3,
                                       "stage": "pull"}, 2)
        self.assertIn(CODE, chip)                                  # ⑪ 칩 툴팁
        self.assertIn("A edit", chip)
        sh("git", "rebase", "--abort", cwd=self.a)

    # --- 13. 받는 데 성공하면 그 기록은 지워진다 ------------------------------
    def test_13_record_cleared_on_success(self):
        self._code_conflict()
        self.m.sync_run("test")
        self.assertTrue(self.m.sync_conflict_state())
        res = self._resolve(paths=[CODE], take="mine")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.m.sync_conflict_state(), {})
        # 상태 줄도 다시 조용해진다
        self.assertNotIn(os.path.basename(CODE),
                         self.m.sync_status_line(self.m.sync_status()))

    # --- 회귀. 이 길에는 작업 트리를 되돌리는 git 명령이 없다 ------------------
    def test_14_no_tree_reverting_git(self):
        with open(S9 + ".py", encoding="utf-8") as f:
            src = f.read()
        a = src.index("멈춤 표시와 복구 (REQ-20260902-025)")
        b = src.index("# 문서 의미 병합 (REQ-20260902-024")
        zone = src[a:b]
        self.assertIn("def sync_conflict_state", zone)
        self.assertIn("def _sync_conflict_record", zone)
        for bad in ('"--hard"', '"checkout"', '"stash"', '"restore"', '"clean"'):
            self.assertNotIn(bad, zone, bad)


class ConflictWords(unittest.TestCase):
    """문구 고정점 — git 도 저장소도 필요 없는 자리."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9cw-")
        os.environ["S9_ROOT"] = cls.base
        spec = importlib.util.spec_from_loader(
            "s9_cw", importlib.machinery.SourceFileLoader("s9_cw", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_words(self):
        c = {"paths": ["a.py", "b.py", "c.py", "d.py"]}
        self.assertEqual(self.m.sync_conflict_words(c), "a.py, b.py, c.py 외 1건")
        self.assertEqual(self.m.sync_conflict_words({}), "")
        # 상태 줄이 쓰는 짧은 갈래 — 파일 이름만, 둘까지
        self.assertEqual(
            self.m.sync_conflict_words({"paths": ["tests/a.py", "bin/b.py",
                                                  "web/c.js"]},
                                       limit=2, short=True),
            "a.py, b.py 외 1건")
        # 문서는 id 로, 코드는 경로로 — 한 명령에 둘이 함께 선다
        cmd = self.m.sync_conflict_cmd(
            {"paths": ["vault/requests/2026/09/REQ-1.md", "bin/s9.py"]})
        self.assertEqual(
            cmd, "s9 sync resolve REQ-1 --paths bin/s9.py --take mine|theirs")
        self.assertIn("--paths", self.m.sync_conflict_cmd({}))
        # 지목이 없으면 종전 한 줄 — 무엇을 칠지는 여전히 말한다
        self.assertIn("resolve", self.m.sync_status_hint({"kind": "conflict"}))

    def test_state_file_is_ignored_when_broken(self):
        p = os.path.join(self.base, "state", ".sync-conflict.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("{ 망가진 json")
        self.assertEqual(self.m.sync_conflict_state(), {})
        with open(p, "w") as f:
            json.dump({"paths": []}, f)
        self.assertEqual(self.m.sync_conflict_state(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
