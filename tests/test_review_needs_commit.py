"""review 는 담긴 것만 올린다 (REQ-20260915-044-62x6).

실제 사고 2026-09-15: 고친 코드가 작업 트리에만 있는 채로 요청이 review 로
올라갔다. 확인 포인트는 「commit 을 두 번 걸어 보라」였는데, 사람이 그 자리에서
볼 수 있는 것은 아무것도 없었다. 주인 지적: 「이걸 또 내가 해야하나?」

규칙은 이미 둘 다 글로 있었다 — 담기지 않은 것은 다른 컴퓨터에서는 없는 것이고
(REQ-20260910-038), 리드가 판정할 수 있는 것은 리드가 닫는다(PROTOCOL 12조 ①).
글로 적힌 규칙이 세 번째로 지켜지지 않았으니 이제 기계가 막는다.

세는 것은 코드뿐이다 — 데이터 경로(vault/·users/·projects/)는 동기화가 늘 담는
자리라, 그것까지 세면 문서 한 줄을 고칠 때마다 review 가 막힌다.

좁히는 규칙이 이 시험의 절반이다. 본 저장소의 작업 트리는 여럿이 함께 쓴다 —
남의 미커밋 변경까지 세면 아무도 review 를 못 올린다. 그래서 요청 전용 worktree
에서는 전부 막고, 본 저장소에서는 그 세션의 transcript 가 고친 파일로 좁히며,
좁힐 길이 없으면 막지 않고 History 에 한 줄로 알린다.

격리: S9_ROOT=mktemp (그 자리에 git 저장소를 따로 세운다).
실행: python3 tests/ review_needs_commit
"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PROTO = os.path.join(HERE, "..", "harness", "common", "PROTOCOL.md")

POINT = ("담기지 않은 코드를 두고 review 로 올리면 전이가 막습니다. "
         "고친 파일을 담지 않은 채 `s9 status <id> review` 를 쳐 보세요. "
         "파일 이름을 짚은 거절이 뜨면 승인, 그대로 올라가면 반려입니다.")


class ReviewNeedsCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9rnc-")
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
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "seed")

    # --- 도구 ---

    def cli(self, *argv, expect=0, cwd=None, env=None):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env or self.env, cwd=cwd or self.tmp, timeout=60)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def git(self, *argv, cwd=None):
        r = subprocess.run(["git", "-C", cwd or self.tmp, *argv],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"git {' '.join(argv)}\n{r.stderr}")
        return r.stdout

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def mk(self):
        doc = self.cli("new", "request", "--title", "담긴 것만 올린다",
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

    def transcript(self, sid, edited):
        """그 세션이 고친 파일들을 기록한 transcript 를 세우고 바인딩에 건다."""
        path = os.path.join(self.tmp, f"tr-{sid}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for rel in edited:
                f.write(json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": os.path.join(self.tmp, rel)}}]}}) + "\n")
        self.cli("bind", "transcript_path", path, "--session", sid)
        return path

    def with_session(self, sid):
        return {**self.env, "S9_SESSION": sid}

    def mine(self, *edited, sid="aaaa0001"):
        """「이 세션이 이 파일들을 고쳤다」를 세우고 그 세션의 환경을 돌려준다 —
        실제 세션이 늘 서 있는 자리(훅이 transcript 를 적어 둔다)를 그대로 흉내낸다."""
        self.transcript(sid, list(edited))
        return self.with_session(sid)

    # --- N. 정상 ---

    def test_n1_clean_tree_passes(self):
        """담을 것이 없으면 종전대로 통과한다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", POINT)
        self.assertIn("-> review", self.body(doc))

    def test_n2_data_paths_dont_block(self):
        """미커밋이 데이터 경로뿐이면 막지 않는다 — 동기화가 담는 자리다."""
        doc = self.mk()
        self.write("vault/requests/stray.md", "x\n")
        self.write("projects/p/CONTEXT.md", "x\n")
        self.cli("status", doc, "review", "--note", POINT)
        self.assertIn("-> review", self.body(doc))

    def test_n3_outside_git_does_not_block(self):
        """git 저장소가 아닌 자리에서는 막지 않는다 — 모르는 것과 깨끗한 것은 다르다."""
        tmp2 = tempfile.mkdtemp(prefix="s9rnc-nogit-")
        env = {**os.environ, "S9_ROOT": tmp2, "S9_MACHINE": "testbox"}
        env.pop("S9_SESSION", None)
        self.cli("init", env=env, cwd=tmp2)
        self.cli("user", "add", "alice", env=env, cwd=tmp2)
        doc = self.cli("new", "request", "--title", "git 없는 자리",
                       "--summary", "s", "--goal", "g", "--size", "S",
                       "--user", "alice", "--body", "x",
                       env=env, cwd=tmp2).split()[0]
        self.cli("status", doc, "in-progress", env=env, cwd=tmp2)
        self.cli("status", doc, "review", "--note", POINT, env=env, cwd=tmp2)

    # --- B. 경계 ---

    def test_b1_untracked_code_blocks(self):
        """추적되지 않는 새 코드 파일 하나만 있어도 막는다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       env=self.mine("bin/new_thing.py"))
        self.assertIn("담기지 않은 코드", out)
        self.assertIn("bin/new_thing.py", out)

    def test_b2_staged_but_not_committed_blocks(self):
        """담아만 두고 commit 하지 않은 것도 막는다 — staged 는 committed 가 아니다."""
        doc = self.mk()
        self.write("bin/keep.py", "# 고쳤다\n")
        self.git("add", "bin/keep.py")
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       env=self.mine("bin/keep.py"))
        self.assertIn("bin/keep.py", out)

    def test_b3_only_code_is_named(self):
        """코드와 데이터가 섞이면 코드만 짚는다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        self.write("vault/requests/stray.md", "x\n")
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       env=self.mine("bin/new_thing.py",
                                     "vault/requests/stray.md"))
        self.assertIn("bin/new_thing.py", out)
        self.assertNotIn("vault/requests/stray.md", out)
        self.assertIn("담기지 않은 코드 1개", out)

    # --- F. 실패 ---

    def test_f1_message_says_how_to_fix(self):
        """거절은 '무엇을 치면 되는가'까지 말한다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       env=self.mine("bin/new_thing.py"))
        self.assertIn("s9 commit", out)
        self.assertIn("--force", out)

    def test_f2_document_untouched_when_blocked(self):
        """막힌 전이는 문서에 아무것도 남기지 않는다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        self.cli("status", doc, "review", "--note", POINT, expect=1,
                 env=self.mine("bin/new_thing.py"))
        text = self.body(doc)
        self.assertNotIn("-> review", text)
        self.assertIn("status: in-progress", text)

    def test_f3_commit_then_review_passes(self):
        """담고 나면 올라간다 — 이 검사가 여는 길은 하나이고 그것은 commit 이다."""
        doc = self.mk()
        env = self.mine("bin/new_thing.py")
        self.write("bin/new_thing.py", "print(1)\n")
        self.cli("status", doc, "review", "--note", POINT, expect=1, env=env)
        self.git("add", "bin/new_thing.py")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "fix")
        self.cli("status", doc, "review", "--note", POINT, env=env)
        self.assertIn("-> review", self.body(doc))

    # --- E. 예외 ---

    def test_e1_force_passes_and_leaves_a_line(self):
        """--force 는 지나가되 History 에 지나간 사실이 남는다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        self.cli("status", doc, "review", "--note", POINT, "--force",
                 env=self.mine("bin/new_thing.py"))
        text = self.body(doc)
        self.assertIn("-> review", text)
        self.assertIn("담기지 않은 코드 1개를 --force 로 지나갔다", text)
        self.assertIn("bin/new_thing.py", text)

    def test_e2_judge_is_not_blocked(self):
        """사람 판정은 이 검사에 걸리지 않는다 — 승인·반려는 올리는 전이가 아니다."""
        doc = self.mk()
        self.cli("status", doc, "review", "--note", POINT)
        self.write("bin/new_thing.py", "print(1)\n")
        self.cli("status", doc, "in-progress", "--note", "반려: 다시")
        self.assertIn("review -> in-progress", self.body(doc))

    def test_e3_other_statuses_not_blocked(self):
        """막는 자리는 review 하나다 — blocked·done 은 종전대로다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        self.cli("status", doc, "blocked", "--note", "왜 막혔는지")
        self.assertIn("-> blocked", self.body(doc))

    # --- R. 좁힘 ---

    def test_r1_shared_tree_narrows_to_this_session(self):
        """본 저장소에서는 그 세션이 고친 파일만 막는다 — 남의 미커밋은 세지 않는다."""
        doc = self.mk()
        self.write("bin/mine.py", "print(1)\n")
        self.write("bin/theirs.py", "print(2)\n")
        self.transcript("aaaa1111", ["bin/mine.py"])
        out = self.cli("status", doc, "review", "--note", POINT,
                       expect=1, env=self.with_session("aaaa1111"))
        self.assertIn("담기지 않은 코드 1개", out)
        self.assertIn("bin/mine.py", out)

    def test_r2_others_files_alone_do_not_block(self):
        """그 세션이 고치지 않은 미커밋 코드만 있으면 막지 않는다 — 대신 알린다."""
        doc = self.mk()
        self.write("bin/theirs.py", "print(2)\n")
        self.transcript("bbbb2222", [])
        out = self.cli("status", doc, "review", "--note", POINT,
                       env=self.with_session("bbbb2222"))
        self.assertIn("-> review", self.body(doc))
        self.assertIn("가릴 수 없었다", out)
        self.assertIn("bin/theirs.py", self.body(doc))

    def test_r3_no_transcript_warns_instead_of_blocking(self):
        """좁힐 길이 없으면 막지 않고 History 에 한 줄로 남긴다."""
        doc = self.mk()
        self.write("bin/new_thing.py", "print(1)\n")
        self.cli("status", doc, "review", "--note", POINT,
                 env=self.with_session("cccc3333"))
        text = self.body(doc)
        self.assertIn("-> review", text)
        self.assertIn("가릴 수 없었다", text)
        self.assertIn("bin/new_thing.py", text)

    def test_r4_reads_only_edits_not_reads(self):
        """읽기는 만진 것이 아니다 — Read 만 한 파일로는 막지 않는다."""
        doc = self.mk()
        self.write("bin/looked.py", "print(1)\n")
        path = os.path.join(self.tmp, "tr-dddd4444.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": os.path.join(self.tmp, "bin/looked.py")}}]}}) + "\n")
        self.cli("bind", "transcript_path", path, "--session", "dddd4444")
        self.cli("status", doc, "review", "--note", POINT,
                 env=self.with_session("dddd4444"))
        self.assertIn("-> review", self.body(doc))

    def test_r5_worktree_blocks_everything_in_it(self):
        """요청 전용 worktree 에서는 그 자리의 미커밋 코드 전부가 이 요청의 것이다."""
        doc = self.mk()
        wt = os.path.join(self.tmp, "state", "worktrees", "w-test")
        self.git("worktree", "add", "-q", "-b", "wt/w-test", wt)
        with open(os.path.join(wt, "bin", "wt_only.py"), "w",
                  encoding="utf-8") as f:
            f.write("print(3)\n")
        # 좁힐 transcript 가 있어도 worktree 는 좁히지 않는다
        self.transcript("eeee5555", [])
        out = self.cli("status", doc, "review", "--note", POINT, expect=1,
                       cwd=wt, env=self.with_session("eeee5555"))
        self.assertIn("bin/wt_only.py", out)

    # --- G. 회귀 ---

    def test_g1_rule_is_written_in_protocol(self):
        """글과 코드가 갈리지 않는다 — 리드가 읽는 자리에 규칙이 있다."""
        with open(PROTO, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("review 는 담긴 것만 올린다", txt)

    def test_g2_existing_review_guards_survive(self):
        """확인 포인트 길이 가드가 그대로 산다 — 새 검사가 앞의 것을 덮지 않는다."""
        doc = self.mk()
        out = self.cli("status", doc, "review", "--note", "가" * 400, expect=1)
        self.assertIn("확인 포인트", out)


if __name__ == "__main__":
    unittest.main()
