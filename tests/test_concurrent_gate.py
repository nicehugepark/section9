"""빠져나가는 경로는 증거를 받는다 (REQ-20260907-062).

작업자가 붙어 있는 중에 그 사이 바뀐 파일을 담으면 가드가 막는다. 그런데 그
검사를 통과시키는 값이 `1` 이었다 — 「읽었다」는 주장일 뿐이고 읽었는지는 아무도 안
봤다. 2026-09-07 18:26 에 리드가 검사가 없던 그 자리로 남의 진행 중 변경 셋을 제 커밋에
쓸어 담았다. **사람이 규율을 안 지킨 것이 아니라 지키지 않아도 지나갈 수
있었다.**

고정하는 계약 넷.
1. 표(token)를 손에 넣는 유일한 길이 목록을 보는 것이다 — 가드가 막으면서
   목록과 함께 알려 준다.
2. 옛 방식(`=1`)으로는 못 지나간다.
3. 목록이 바뀌면 표도 바뀐다 — 그 사이 남이 또 고쳤으면 다시 봐야 한다.
4. 지나간 사실은 commit 메시지에 남는다 — 지나간 것을 **보이게** 만든다.

실행: python3 tests/ concurrent_gate
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

TMP = tempfile.mkdtemp(prefix="s9-cgate-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT",)}
os.environ["S9_ROOT"] = TMP
try:
    spec = importlib.util.spec_from_loader(
        "s9_guard_cg", importlib.machinery.SourceFileLoader("s9_guard_cg", GUARD))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TheToken(unittest.TestCase):
    def test_the_same_set_gives_the_same_token(self):
        a = g.concurrent_token([("b.py", 3), ("a.py", 9)])
        b = g.concurrent_token([("a.py", 1), ("b.py", 2)])
        self.assertEqual(a, b, "순서·나이가 표를 바꾸면 안 된다 — 집합이 재료다")

    def test_a_different_set_gives_a_different_token(self):
        a = g.concurrent_token([("a.py", 1)])
        b = g.concurrent_token([("a.py", 1), ("c.py", 1)])
        self.assertNotEqual(a, b, "목록이 바뀌었는데 옛 표로 지나갈 수 있다")

    def test_it_is_short_enough_to_type(self):
        self.assertLessEqual(len(g.concurrent_token([("a.py", 1)])), 8)

    def test_the_same_input_twice_gives_the_same_token(self):
        """표는 계산할 때마다 흔들리지 않는다 — 시각·나이가 재료가 아니다."""
        self.assertEqual(g.concurrent_token([("a.py", 1)]),
                         g.concurrent_token([("a.py", 9)]))

    def test_it_survives_a_place_that_is_not_a_repository(self):
        """저장소가 아닌 자리에서도 표가 나온다 — 지문이 빈 값으로 떨어진다."""
        self.assertTrue(g.staged_fingerprint(["a.py"]) == ""
                        or isinstance(g.staged_fingerprint(["a.py"]), str))
        self.assertTrue(g.concurrent_token([("a.py", 1)]))


class TheTokenAttestsTheContent(unittest.TestCase):
    """목록이 같아도 **담긴 내용**이 달라지면 표가 죽는다 (REQ-20260909-101).

    2026-09-09 18:15: 리드가 `git apply --cached` 로 bin/s9.py 의 제 hunk 둘만
    담고 표를 받았다. 첫 커밋이 다른 검사에 막혀 4분이 흐르는 사이 같은 작업
    트리의 다른 작업자가 그 파일을 통째로 담았고, 파일 **목록**은 그대로여서
    표도 그대로였다 — 두 번째 커밋이 남의 hunk 아홉을 제 메시지로 실어 갔다.
    표가 증언할 것은 「이 파일들을 봤다」가 아니라 「지금 담긴 이 내용을 봤다」다.
    """
    def setUp(self):
        import subprocess
        self.repo = tempfile.mkdtemp(prefix="s9-ctok-")
        def git(*a):
            return subprocess.run(["git", *a], cwd=self.repo,
                                  capture_output=True, encoding="utf-8")
        self.git = git
        git("init", "-q", ".")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        with open(os.path.join(self.repo, "code.py"), "w") as f:
            f.write("one\n")
        git("add", "-A")
        git("commit", "-qm", "init")

    def _token(self):
        with mock.patch.object(g, "ROOT", self.repo):
            return g.concurrent_token([("code.py", 0)])

    def test_a_bigger_stage_of_the_same_file_kills_the_token(self):
        with open(os.path.join(self.repo, "code.py"), "w") as f:
            f.write("one\nmine\n")
        self.git("add", "code.py")
        mine = self._token()
        # 그 사이 남이 같은 파일을 더 담았다 — 목록은 그대로다
        with open(os.path.join(self.repo, "code.py"), "w") as f:
            f.write("one\nmine\nothers\n")
        self.git("add", "code.py")
        self.assertNotEqual(
            mine, self._token(),
            "담긴 내용이 늘었는데 옛 표로 지나갈 수 있다 — 남의 hunk 가 실린다")

    def test_an_unchanged_stage_keeps_the_token(self):
        with open(os.path.join(self.repo, "code.py"), "w") as f:
            f.write("one\nmine\n")
        self.git("add", "code.py")
        self.assertEqual(self._token(), self._token(),
                         "아무것도 안 바뀌었는데 표가 흔들리면 아무도 못 지나간다")


class TheGate(unittest.TestCase):
    """`concurrent_gate` 를 실제로 부른다 — 소스 글자를 대조하지 않는다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cgate-root-")
        self.f = "tests/남의것.py"
        p = os.path.join(self.root, self.f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()          # 방금 만든 파일 = 방금 바뀐 파일

    def _run(self, override=None, workers=("REQ-x (백그라운드 작업자 pid 1, 1분째)",)):
        env = {} if override is None else {g.OVERRIDE: override}
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.object(g, "live_workers", lambda: list(workers)), \
                mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop(g.OVERRIDE, None) if override is None else None
            return g.concurrent_gate([self.f])

    def test_no_worker_no_gate(self):
        self.assertIsNone(self._run(workers=()))

    def test_it_blocks_without_a_token(self):
        with self.assertRaises(SystemExit):
            self._run()

    def test_the_old_way_no_longer_passes(self):
        """`=1` 은 목록을 봤다는 증거가 아니다 — 이것이 이 요청의 전부다."""
        with self.assertRaises(SystemExit):
            self._run("1")

    def test_the_right_token_passes(self):
        tok = g.concurrent_token([(self.f, 0)])
        self.assertIsNone(self._run(tok))

    def test_a_stale_token_does_not_pass(self):
        with self.assertRaises(SystemExit):
            self._run(g.concurrent_token([("다른것.py", 0)]))

    def test_passing_records_what_was_swept(self):
        tok = g.concurrent_token([(self.f, 0)])
        self._run(tok)
        mark = os.path.join(self.root, "state", "concurrent-swept.txt")
        self.assertTrue(os.path.exists(mark), "지나간 사실이 남지 않았다")
        self.assertIn(self.f, open(mark, encoding="utf-8").read())


class TheCommitMessageSaysIt(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-cgate-msg-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.msg = os.path.join(self.root, "MSG")

    def _msg(self, text="고침 하나\n"):
        with open(self.msg, "w", encoding="utf-8") as f:
            f.write(text)
        with mock.patch.object(g, "ROOT", self.root):
            g.commit_msg_swept(self.msg)
        return open(self.msg, encoding="utf-8").read()

    def test_a_plain_commit_gets_no_tail(self):
        self.assertNotIn("S9_ALLOW_CONCURRENT", self._msg())

    def test_a_swept_commit_names_the_files(self):
        with open(os.path.join(self.root, "state", "concurrent-swept.txt"),
                  "w", encoding="utf-8") as f:
            f.write("tests/남의것.py\n")
        got = self._msg()
        self.assertIn("tests/남의것.py", got,
                      "쓸려 담긴 파일이 커밋 메시지에 없다 — 다음 사람이 까닭을 못 찾는다")

    def test_the_mark_is_used_once(self):
        # 표식이 남아 다음 커밋에도 붙으면 거짓말이 된다
        with open(os.path.join(self.root, "state", "concurrent-swept.txt"),
                  "w", encoding="utf-8") as f:
            f.write("tests/남의것.py\n")
        self._msg()
        self.assertNotIn("남의것", self._msg("다음 커밋\n"))


class DataOnlyCommits(unittest.TestCase):
    """문서만 담는 커밋은 이 검사가 막지 않는다 (REQ-20260908-049).

    2026-09-08 하루의 대부분, 동기화(sync)의 문서 커밋이 전부 이 검사에 막혔다 —
    서브에이전트가 하나라도 돌고 있으면 `vault/…` 한 파일을 담는 커밋조차 「다른
    작업자가 붙어 있는 중」으로 거부됐고, 다른 머신은 그만큼 뒤처졌다. 검사가
    지키려던 것은 남의 **코드**이지 문서가 아니다.
    """

    def test_the_paths_match_the_ones_sync_stages(self):
        # 두 곳이 갈리면 문서가 다시 막힌다 — bin/s9.py 의 SYNC_DATA_PATHS 가 원천
        src = open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8").read()
        line = [l for l in src.splitlines() if l.startswith("SYNC_DATA_PATHS")]
        self.assertTrue(line, "bin/s9.py 에 SYNC_DATA_PATHS 가 없다")
        names = set(eval(line[0].split("=", 1)[1].strip()))
        guard = set(x.rstrip("/") for x in g.DATA_PREFIXES) | set(g.DATA_FILES)
        self.assertEqual(names, guard,
                         "동기화가 담는 경로와 가드가 아는 경로가 갈렸다")

    def test_a_document_is_a_data_path(self):
        for rel in ("vault/requests/2026/09/REQ-1.md", "users/nice.md",
                    "projects/section9/CONTEXT.md", ".s9-sync"):
            self.assertTrue(g.is_data_path(rel), rel)

    def test_code_is_not(self):
        for rel in ("bin/s9.py", "web/app/app.js", "tests/test_x.py",
                    "harness/common/PROTOCOL.md", "CLAUDE.md"):
            self.assertFalse(g.is_data_path(rel), rel)

    def test_a_document_only_commit_passes_while_a_worker_runs(self):
        with mock.patch.object(g, "live_workers",
                               return_value=[("서브에이전트", "s1", 2)]), \
             mock.patch.object(g, "fresh_staged") as fresh:
            g.concurrent_gate(["vault/requests/2026/09/REQ-1.md", ".s9-sync"])
        self.assertEqual(fresh.call_count, 0,
                         "문서만 담았는데 검사가 돌았다 — 동기화가 또 막힌다")

    def test_one_code_file_mixed_in_still_stops_it(self):
        # 둘째 검사(`recent_foreign_commits`)는 **이 저장소의 진짜 이력**을 읽는다
        # (REQ-20260915-008-2n7g). 여기서 재는 것은 「코드가 섞이면 검사가 돈다」
        # 하나뿐이니 그 창은 닫아 둔다 — 열어 두면 이 시험은 bin/s9.py 를 담은
        # 커밋이 15분 안에 있었는지에 따라 갈린다(실제로 2026-09-15 전체 회차가
        # 그렇게 한 번 실패했다: 몇 분 전 커밋이 다른 세션 것으로 보였다).
        with mock.patch.object(g, "live_workers",
                               return_value=[("서브에이전트", "s1", 2)]), \
             mock.patch.object(g, "recent_foreign_commits",
                               return_value=([], [])), \
             mock.patch.object(g, "fresh_staged", return_value=[]) as fresh:
            g.concurrent_gate(["vault/requests/2026/09/REQ-1.md", "bin/s9.py"])
        self.assertEqual(fresh.call_count, 1,
                         "코드가 섞였는데 검사를 건너뛰었다 — 남의 변경이 쓸려 담긴다")


class TheCommitterIsNotAnother(unittest.TestCase):
    """커밋을 거는 당사자를 「다른 작업자」로 세지 않는다 (REQ-20260915-021).

    2026-09-15: worktree 에서 도는 무인 작업자가 제가 고친 파일을 담아 commit
    하자 검사가 막았고, 목록에 선 그 작업자가 커밋을 거는 프로세스 자신이었다.
    빠져나가는 길은 환경변수 접두라 무인 세션의 allowlist 에 안 맞고, 승인할
    사람도 없다 — 구조적으로 통과할 수 없는 검사였다.
    """

    def _workers(self, *lines):
        class R:
            stdout = "\n".join(lines) + "\n"
        with mock.patch.object(g.subprocess, "run", return_value=R()):
            return g.live_workers()

    def test_my_own_line_is_dropped(self):
        me = os.getpid()
        self.assertEqual(
            self._workers("- REQ-x (백그라운드 작업 pid %d, 3분째)" % me), [],
            "커밋하는 당사자가 목록에 남았다 — 자기 자신에게 막힌다")

    def test_someone_else_stays(self):
        other = [p for p in range(2, 4000) if p not in g.self_and_ancestors()][0]
        line = "- REQ-y (백그라운드 작업 pid %d, 3분째)" % other
        self.assertEqual(self._workers(line), [line],
                         "남을 뺐다 — 남의 미완성이 이 커밋에 쓸려 담긴다")

    def test_a_subagent_line_has_no_pid_and_stays(self):
        line = "- 서브에이전트 (세션 abc12345, 1분째) abc.jsonl"
        self.assertEqual(self._workers(line), [line],
                         "서브에이전트는 같은 트리를 만지는 진짜 다른 주체다")

    def test_only_me_means_no_worker_at_all(self):
        """목록의 유일한 줄이 나면 gate 는 환경변수 없이 통과한다."""
        me = os.getpid()
        class R:
            stdout = "- REQ-x (백그라운드 작업 pid %d, 3분째)\n" % me
        with mock.patch.object(g.subprocess, "run", return_value=R()), \
                mock.patch.object(g, "fresh_staged") as fresh:
            self.assertIsNone(g.concurrent_gate(["bin/s9.py"]))
        self.assertEqual(fresh.call_count, 0)


class WhoIsMe(unittest.TestCase):
    def test_i_am_in_my_own_set(self):
        self.assertIn(os.getpid(), g.self_and_ancestors())

    def test_my_parent_is_too(self):
        ppid = g._parent_pid(os.getpid())
        self.assertTrue(ppid > 0, "부모 pid 를 못 읽었다")
        self.assertIn(ppid, g.self_and_ancestors())

    def test_an_unreadable_parent_is_zero_not_a_guess(self):
        self.assertEqual(g._parent_pid(2 ** 31 - 1), 0)


if __name__ == "__main__":
    unittest.main()
