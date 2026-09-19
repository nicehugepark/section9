"""가지에 담은 것은 main 에 닿아야 한다 (REQ-20260916-009-2n7g).

실측 2026-09-16 01:5x: `wt/*` 가지 여섯에 main 에 없는 commit 이 있었다. 그날
같은 자리에 두 번 물렸다 — 가지에서 이미 끝난 구현을 모르고 리드가 처음부터 다시
만들었고(REQ-20260915-009-2n7g), 확인 포인트가 「시험을 돌려 보라」인데 그 시험이
main 에 없어 사람이 무엇을 눌러도 볼 수 없는 채로 판정을 기다렸다
(REQ-20260916-004-2n7g).

담기지 않은 코드 가드(REQ-20260915-044-62x6)가 막는 것은 「작업 트리에만 있는
것」이고, 그 옆의 구멍이 이것이다: worktree 작업자는 제 가지에 commit 하면
「담았다」로 보고하는데 사람이 보는 자리는 main 이다.

막기만 하면 갇힌다 — 작업자의 손에는 git merge 가 없다. 그래서 review·done 전이가
옮기고, 못 옮기면(충돌) 그때 거절한다. 세는 것은 코드뿐이다: 데이터 경로는
동기화가 늘 담는 자리라 그것까지 세면 문서 한 줄에 전이가 막힌다.

격리: S9_ROOT=mktemp (그 자리에 git 저장소를 따로 세운다).
실행: python3 tests/ branch_reaches_main
"""
import json
import os
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

POINT = ("가지에만 있는 commit 을 두고 review 로 올리면 전이가 그것을 main 으로 "
         "옮깁니다. worktree 에서 고치고 `s9 status <id> review` 를 쳐 보세요. "
         "main 에서 그 파일이 보이면 승인, 가지에만 남아 있으면 반려입니다.")


class BranchReachesMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9brm-")
        self.env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")
        self.write(".gitignore", "state/\nindex/\n.s9.lock\n")
        self.write("bin/keep.py", "# 이미 담긴 코드\n")
        self.git("add", ".gitignore", "bin/keep.py")
        self.commit_here(self.tmp, "seed")
        self.base = self.git("rev-parse", "--abbrev-ref", "HEAD").strip()

    # --- 도구 ---

    def cli(self, *argv, expect=0, cwd=None, env=None):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env or self.env, cwd=cwd or self.tmp, timeout=120)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def git(self, *argv, cwd=None, check=True):
        r = subprocess.run(["git", "-C", cwd or self.tmp, *argv],
                           capture_output=True, text=True, timeout=60)
        if check:
            self.assertEqual(r.returncode, 0, f"git {' '.join(argv)}\n{r.stderr}")
        return r.stdout

    def commit_here(self, cwd, msg):
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", msg,
                 cwd=cwd)

    def write(self, rel, text, root=None):
        path = os.path.join(root or self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def mk(self):
        doc = self.cli("new", "request", "--title", "가지가 main 에 닿는다",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       "--user", "alice", "--body", "x").split()[0]
        self.cli("status", doc, "in-progress")
        return doc

    def body(self, doc_id):
        for root, _d, files in os.walk(os.path.join(self.tmp, "vault")):
            for fn in files:
                if fn.startswith(doc_id) and fn.endswith(".md"):
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        return f.read()
        raise AssertionError(f"문서 없음: {doc_id}")

    def mkwt(self, doc_id, name="w-test"):
        """이 요청 전용 worktree 를 세운다 — 주인 기록까지 (실제 스폰이 하는 그대로)."""
        path = os.path.join(self.tmp, "state", "worktrees", name)
        self.git("worktree", "add", "-q", "-b", f"wt/{name}", path)
        own = os.path.join(self.tmp, "state", "worktree_owners", name + ".json")
        os.makedirs(os.path.dirname(own), exist_ok=True)
        with open(own, "w", encoding="utf-8") as f:
            json.dump({"doc": doc_id, "created": time.time(),
                       "pid": os.getpid()}, f)
        return path

    def wt_commit(self, path, rel, text, msg):
        """그 worktree 의 가지에 한 건 담는다 — 작업자가 하는 그대로."""
        self.write(rel, text, root=path)
        self.git("add", rel, cwd=path)
        self.commit_here(path, msg)

    def in_main(self, rel):
        """main 의 HEAD 에 그 파일이 있나 — 사람이 보는 자리는 여기다."""
        r = subprocess.run(["git", "-C", self.tmp, "show", f"HEAD:{rel}"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else None

    # --- N. 정상 ---

    def test_n1_already_merged_passes_untouched(self):
        """가지의 commit 이 이미 main 에 있으면 종전대로 올라간다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(1)\n", "가지에서 고쳤다")
        self.git("merge", "--no-ff", "-m", "먼저 합쳤다", "wt/w-test")
        self.cli("status", doc, "review", "--note", POINT, cwd=wt)
        text = self.body(doc)
        self.assertIn("-> review", text)
        self.assertNotIn("main 으로 옮겼다", text)

    def test_n2_data_only_commit_is_not_counted(self):
        """가지에 데이터 commit 만 있으면 세지 않는다 — 동기화가 늘 담는 자리다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "vault/requests/stray.md", "x\n", "문서만 담았다")
        self.cli("status", doc, "review", "--note", POINT, cwd=wt)
        text = self.body(doc)
        self.assertIn("-> review", text)
        self.assertNotIn("main 으로 옮겼다", text)

    def test_n3_no_worktree_no_check(self):
        """worktree 가 없는 요청은 이 검사에 걸리지 않는다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", POINT)
        text = self.body(doc)
        self.assertIn("-> review", text)
        self.assertNotIn("main 으로 옮겼다", text)

    # --- B. 경계 ---

    def test_b1_review_from_worktree_lands_the_code(self):
        """worktree 에서 review 로 올리면 그 가지의 코드 commit 이 main 으로 간다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(1)\n", "가지에서 고쳤다")
        self.assertIsNone(self.in_main("bin/tool.py"))
        out = self.cli("status", doc, "review", "--note", POINT, cwd=wt)
        self.assertEqual(self.in_main("bin/tool.py"), "print(1)\n")
        self.assertIn("-> review", self.body(doc))
        self.assertIn("main 으로 옮겼다", self.body(doc) + out)

    def test_b2_main_repo_finds_the_docs_branch(self):
        """본 저장소에서 닫아도 그 요청이 가진 가지를 주인 기록으로 찾아 옮긴다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(2)\n", "가지에서 고쳤다")
        self.cli("status", doc, "review", "--note", POINT)
        self.assertEqual(self.in_main("bin/tool.py"), "print(2)\n")

    def test_b3_done_is_checked_too(self):
        """done 전이도 같은 검사를 받는다 — 닫힌 요청의 코드가 가지에 남으면 안 된다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(3)\n", "가지에서 고쳤다")
        self.cli("status", doc, "done", "--note", "goal 충족", cwd=wt)
        self.assertEqual(self.in_main("bin/tool.py"), "print(3)\n")
        self.assertIn("-> done", self.body(doc))

    def test_b4_worktree_survives_the_landing(self):
        """옮긴 뒤에도 그 자리는 남는다 — 실행 중인 작업자의 코드 사본을 치우지 않는다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(4)\n", "가지에서 고쳤다")
        self.cli("status", doc, "review", "--note", POINT, cwd=wt)
        self.assertTrue(os.path.isdir(wt))
        self.assertIn("wt/w-test", self.git("branch", "--list", "wt/w-test"))

    # --- F. 실패 ---

    def test_f1_conflict_is_refused_with_the_branch_named(self):
        """충돌해 못 옮기면 거절하고 가지 이름·commit·사유를 짚는다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/keep.py", "# 가지 쪽\n", "가지에서 고쳤다")
        self.write("bin/keep.py", "# main 쪽\n")
        self.git("add", "bin/keep.py")
        self.commit_here(self.tmp, "main 에서도 고쳤다")
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       cwd=wt)
        self.assertIn("wt/w-test", out)
        self.assertIn("main 에 없다", out)
        self.assertIn("합치지 못했다", out)

    def test_f2_document_untouched_when_refused(self):
        """막힌 전이는 문서에 아무것도 남기지 않고 본 저장소도 그대로다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/keep.py", "# 가지 쪽\n", "가지에서 고쳤다")
        self.write("bin/keep.py", "# main 쪽\n")
        self.git("add", "bin/keep.py")
        self.commit_here(self.tmp, "main 에서도 고쳤다")
        self.cli("status", doc, "review", "--note", POINT, expect=1, cwd=wt)
        text = self.body(doc)
        self.assertNotIn("-> review", text)
        self.assertIn("status: in-progress", text)
        # 실패한 merge 의 잔재가 남지 않는다 (--abort 로 걷는다) — 추적하는
        # 파일이 그대로이고, 반쯤 선 merge(MERGE_HEAD)도 없다.
        self.assertEqual(
            self.git("status", "--porcelain", "--untracked-files=no").strip(), "")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".git", "MERGE_HEAD")))

    # --- E. 예외 ---

    def test_e1_force_passes_and_leaves_a_line(self):
        """--force 는 지나가되 History 에 지나간 사실이 남는다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/keep.py", "# 가지 쪽\n", "가지에서 고쳤다")
        self.write("bin/keep.py", "# main 쪽\n")
        self.git("add", "bin/keep.py")
        self.commit_here(self.tmp, "main 에서도 고쳤다")
        self.cli("status", doc, "review", "--note", POINT, "--force", cwd=wt)
        text = self.body(doc)
        self.assertIn("-> review", text)
        self.assertIn("main 에 없는 채로 --force 로 지나갔다", text)
        self.assertIn("wt/w-test", text)

    def test_e2_leaving_review_is_not_checked(self):
        """review 를 떠나는 전이(반려·blocked)는 걸리지 않는다 — 올리는 전이가 아니다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.cli("status", doc, "review", "--note", POINT, cwd=wt)
        self.wt_commit(wt, "bin/tool.py", "print(5)\n", "반려 뒤에 고쳤다")
        self.cli("status", doc, "in-progress", "--note", "반려: 다시", cwd=wt)
        self.assertIn("review -> in-progress", self.body(doc))
        self.assertIsNone(self.in_main("bin/tool.py"))

    def test_e3_blocked_is_not_checked(self):
        """blocked 는 종전대로다 — 못 옮긴 것을 넘기는 자리가 그 자리다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(6)\n", "가지에서 고쳤다")
        self.cli("status", doc, "blocked", "--note", "충돌해 못 옮겼습니다", cwd=wt)
        self.assertIn("-> blocked", self.body(doc))

    # --- R. 회귀 ---

    def test_r1_uncommitted_guard_still_runs(self):
        """담기지 않은 코드 가드가 먼저 선다 — 담겼나, 그 다음 닿았나."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.write("bin/loose.py", "print(7)\n", root=wt)
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       cwd=wt)
        self.assertIn("담기지 않은 코드", out)
        self.assertIn("bin/loose.py", out)

    # --- W. 자리를 거둘 때 이름도 거둔다 ---

    def test_w1_rm_deletes_the_branch_when_nothing_is_stuck(self):
        """자리를 거두면 이름도 거둔다 — 남으면 다음 스폰의 `worktree add -b` 가 선다."""
        doc = self.mk()
        self.mkwt(doc)
        out = self.cli("worktree", "rm", "w-test")
        self.assertIn("가지 wt/w-test 도 지웠다", out)
        self.assertEqual(self.git("branch", "--list", "wt/w-test").strip(), "")

    def test_w2_rm_keeps_a_branch_that_still_holds_code(self):
        """main 에 없는 코드 commit 이 남은 가지는 지우지 않는다 — 그것이 소실이다."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(8)\n", "가지에서 고쳤다")
        out = self.cli("worktree", "rm", "w-test")
        self.assertIn("남겼다", out)
        self.assertIn("--force", out)
        self.assertIn("wt/w-test", self.git("branch", "--list", "wt/w-test"))

    def test_w3_force_drops_it_and_says_what_was_dropped(self):
        """--force 는 버리되 무엇을 버렸는지 적는다 — 이미 다른 구현이 main 에 섰을 때."""
        doc = self.mk()
        wt = self.mkwt(doc)
        self.wt_commit(wt, "bin/tool.py", "print(9)\n", "가지에서 고쳤다")
        out = self.cli("worktree", "rm", "w-test", "--force")
        self.assertIn("--force 로 버렸다", out)
        self.assertEqual(self.git("branch", "--list", "wt/w-test").strip(), "")

    def test_w4_rm_works_after_the_place_is_already_gone(self):
        """자리를 sweep 이 먼저 거둬도 이름을 치우러 온 사람을 오류로 돌려보내지 않는다."""
        doc = self.mk()
        path = self.mkwt(doc)
        self.git("worktree", "remove", path)
        out = self.cli("worktree", "rm", "w-test")
        self.assertIn("자리는 이미 없다", out)
        self.assertEqual(self.git("branch", "--list", "wt/w-test").strip(), "")

    def test_r2_is_code_path_draws_the_line(self):
        """코드와 데이터를 가르는 잣대는 한 벌이다 (담기지 않은 코드 가드와 같은 것)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "s9mod", os.path.join(HERE, "..", "bin", "s9.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for rel in ("bin/s9.py", "tests/t.py", "web/index.html", "README.md"):
            self.assertTrue(mod.is_code_path(rel), rel)
        for rel in ("vault/requests/x.md", "users/alice.md", "state/x",
                    "index/catalog.jsonl", "projects/p/CONTEXT.md"):
            self.assertFalse(mod.is_code_path(rel), rel)


if __name__ == "__main__":
    unittest.main()
