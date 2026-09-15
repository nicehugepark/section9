"""방금 남이 담은 파일 (REQ-20260915-008-2n7g).

실제 사고 2026-09-15: 세션 A 가 13:59:50 에 commit 230e94a68 로
tests/test_stdlib_only.py 를 닫았고, 세션 B 가 14:01 에 19926f3bd 로 같은 파일을
덮었다(내용이 같아 잃은 것은 없었다). 종전 검사(concurrent_gate)가 보는 것은
**작업 트리**라 — A 는 이미 commit 을 마쳐 작업 트리에 아무것도 남기지 않았고,
검사에 걸릴 것이 없었다. 「남이 아직 쓰는 중」은 보지만 「남이 방금 써서
넣었다」는 못 봤다.

고정하는 계약 넷.
1. 담기는 코드 파일을 최근 15분 안에 **다른 세션**이 담았으면 그 commit 해시를
   짚어 멈춘다.
2. 내가 담은 것은 막지 않는다 — 제 일이 제 앞을 막으면 검사는 곧 손잡이가 된다.
3. 누가 담았는지 **기록이 없는** commit(다른 컴퓨터에서 pull 로 온 것)은
   짚어 보여 주되 막지 않는다.
4. 빠져나가는 표는 하나다 — 두 검사가 짚은 파일 전부를 그 표가 덮는다.

실행: python3 tests/ recent_commit_gate
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")

spec = importlib.util.spec_from_loader(
    "s9_guard_rcg", importlib.machinery.SourceFileLoader("s9_guard_rcg", GUARD))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

MINE = "bbbbbbbb"
OTHER = "aaaaaaaa"


class RepoCase(unittest.TestCase):
    """코드 파일 하나를 담은 저장소 — 그 파일을 다시 담으려는 자리에서 잰다."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="s9-rcg-")
        os.makedirs(os.path.join(self.repo, "state"), exist_ok=True)
        self.git("init", "-q", ".")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write("code.py", "one\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "남의 고침 하나")
        self.sha = self.git("rev-parse", "HEAD").stdout.strip()
        # 담을 것: 같은 파일을 다시 고쳐 담는다
        self.write("code.py", "one\ntwo\n")
        self.git("add", "code.py")

    def git(self, *a, **kw):
        return subprocess.run(["git", *a], cwd=self.repo, capture_output=True,
                              encoding="utf-8", errors="replace", **kw)

    def write(self, rel, text):
        p = os.path.join(self.repo, rel)
        if os.path.dirname(rel):
            os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def ledger(self, sha, session, machine="Mac"):
        with open(os.path.join(self.repo, "state", "commit-sessions.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps({"sha": sha, "session": session,
                                "machine": machine, "ts": int(time.time())}) + "\n")

    @contextlib.contextmanager
    def guard(self, session=MINE, workers=(), override=None):
        env = {} if override is None else {g.OVERRIDE: override}
        with mock.patch.object(g, "ROOT", self.repo), \
                mock.patch.object(g, "live_workers", lambda: list(workers)), \
                mock.patch.object(g, "my_binding", lambda: {"session": session,
                                                            "machine": "Mac"}), \
                mock.patch.dict(os.environ, env, clear=False):
            if override is None:
                os.environ.pop(g.OVERRIDE, None)
            yield

    def gate(self, staged=("code.py",), **kw):
        err = io.StringIO()
        with self.guard(**kw), contextlib.redirect_stderr(err):
            g.concurrent_gate(list(staged))
        return err.getvalue()


class ItStopsOnSomeoneElsesCommit(RepoCase):
    def test_a_foreign_commit_a_minute_ago_stops_the_commit(self):
        self.ledger(self.sha, OTHER)
        err = io.StringIO()
        with self.assertRaises(SystemExit) as e:
            with self.guard(), contextlib.redirect_stderr(err):
                g.concurrent_gate(["code.py"])
        self.assertEqual(e.exception.code, 1)
        self.assertIn(self.sha[:9], err.getvalue(),
                      "멈추면서 그 commit 해시를 짚지 않으면 사람이 찾아갈 곳이 없다")
        self.assertIn("남의 고침 하나", err.getvalue(), "그 commit 의 메시지가 없다")
        self.assertIn(OTHER, err.getvalue(), "누가 담았는지가 없다")

    def test_my_own_commit_does_not_stop_me(self):
        self.ledger(self.sha, MINE)
        self.assertEqual(self.gate(), "", "내가 담은 것을 내가 못 담으면 검사가 아니라 벽이다")

    def test_an_old_commit_is_outside_the_window(self):
        old = time.strftime("%Y-%m-%dT%H:%M:%S",
                            time.localtime(time.time() - g.RECENT_COMMIT_SEC - 600))
        self.write("code.py", "one\nold\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "오래된 고침",
                 env={**os.environ, "GIT_AUTHOR_DATE": old, "GIT_COMMITTER_DATE": old})
        self.ledger(self.git("rev-parse", "HEAD").stdout.strip(), OTHER)
        self.write("code.py", "one\nold\nmine\n")
        self.git("add", "code.py")
        self.assertEqual(self.gate(), "", "창 밖의 commit 까지 막으면 아무것도 못 담는다")

    def test_a_document_only_commit_is_not_our_business(self):
        self.ledger(self.sha, OTHER)
        self.write("vault/doc.md", "x\n")
        self.git("add", "-A")
        self.assertEqual(self.gate(staged=("vault/doc.md",)), "",
                         "문서만 담는 커밋을 막으면 동기화가 선다 (REQ-20260908-049)")

    def test_an_unrecorded_commit_is_shown_but_not_blocked(self):
        """다른 컴퓨터에서 pull 로 온 commit 이 전부 여기 든다 — 막지 않고 짚는다."""
        err = self.gate()
        self.assertIn(self.sha[:9], err, "무엇을 덮으려는지는 보여야 한다")
        self.assertIn("기록이 없다", err)


class OneTokenOpensBoth(RepoCase):
    """표는 하나다 — 두 검사가 짚은 파일 전부를 덮는다."""

    def setUp(self):
        super().setUp()
        self.ledger(self.sha, OTHER)
        self.write("other.py", "fresh\n")      # 방금 만든 파일 = 방금 바뀐 파일
        self.git("add", "other.py")

    def _token(self):
        with mock.patch.object(g, "ROOT", self.repo):
            return g.concurrent_token([("code.py", 0), ("other.py", 0)])

    def test_the_token_covers_the_files_of_both_checks(self):
        staged = ("code.py", "other.py")
        workers = ("REQ-x (백그라운드 작업자 pid 1, 1분째)",)
        with self.assertRaises(SystemExit):
            self.gate(staged=staged, workers=workers)
        self.assertEqual(self.gate(staged=staged, workers=workers,
                                   override=self._token()), "",
                         "두 검사가 함께 서면 표 하나로는 못 지나간다 — 손잡이가 둘이 된다")
        swept = os.path.join(self.repo, "state", "concurrent-swept.txt")
        got = open(swept, encoding="utf-8").read()
        self.assertIn("code.py", got)
        self.assertIn("other.py", got, "지나간 사실이 커밋 메시지로 갈 목록에 없다")

    def test_a_stale_token_does_not_pass(self):
        with mock.patch.object(g, "ROOT", self.repo):
            stale = g.concurrent_token([("code.py", 0)])
        with self.assertRaises(SystemExit):
            self.gate(staged=("code.py", "other.py"),
                      workers=("REQ-x (백그라운드 작업자 pid 1, 1분째)",),
                      override=stale)

    def test_the_preview_gives_the_token_the_gate_demands(self):
        """조회와 검사가 같은 값을 본다 (REQ-20260907-070) — 갈리면 표가 안 듣는다."""
        out = io.StringIO()
        with self.guard(workers=("REQ-x (백그라운드 작업자 pid 1, 1분째)",)):
            g.concurrent_report(["code.py", "other.py"], out=out)
        self.assertIn(self._token(), out.getvalue())


class TheLedger(RepoCase):
    def test_after_commit_writes_who_staged_it(self):
        with self.guard():
            g.after_commit(self.sha)
        with mock.patch.object(g, "ROOT", self.repo):
            rows = g.commit_sessions()
        self.assertIn(self.sha, rows, "post-commit 이 누가 담았는지 안 적었다")
        self.assertEqual(rows[self.sha]["session"], MINE)

    def test_a_session_without_an_id_writes_nothing(self):
        with mock.patch.object(g, "ROOT", self.repo), \
                mock.patch.object(g, "my_binding", dict):
            g.note_commit_session(self.sha)
            self.assertEqual(g.commit_sessions(), {},
                             "모르는 것을 적으면 다음 세션이 그것을 믿는다")

    def test_it_does_not_grow_without_end(self):
        path = os.path.join(self.repo, "state", "commit-sessions.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for i in range(g.LEDGER_KEEP * 3):
                f.write(json.dumps({"sha": f"{i:040x}", "session": OTHER,
                                    "ts": 0, "pad": "x" * 200}) + "\n")
        with mock.patch.object(g, "ROOT", self.repo):
            g.trim_commit_sessions()
            self.assertEqual(len(open(path, encoding="utf-8").readlines()),
                             g.LEDGER_KEEP)

    def test_the_ledger_is_machine_housekeeping(self):
        """기록은 state/ 에 산다 — 이력(commit trailer)을 더럽히지 않는다."""
        self.assertEqual(g.COMMIT_SESSIONS[0], "state")


class OnTheRealRepository(unittest.TestCase):
    """임시 저장소가 아니라 **이 저장소의 진짜 이력**에서도 읽힌다.

    이력을 읽는 자리는 판이 다르면 조용히 빈 손이 된다(병합 커밋·이름이 바뀐
    파일·긴 제목). 무엇이 나오는지는 그때그때 다르니 값을 못박지 않고, 읽다가
    터지지 않는지와 돌려주는 모양만 잰다.
    """

    def test_it_reads_this_repositorys_history(self):
        with mock.patch.object(g, "live_workers", lambda: []):
            stop, unknown = g.recent_foreign_commits(["bin/s9-guard"])
        for item in list(stop) + list(unknown):
            self.assertEqual(len(item), 5)
            self.assertLess(item[2], g.RECENT_COMMIT_SEC, "창 밖의 commit 이 섞였다")

    def test_the_newest_commit_here_is_found_by_its_own_files(self):
        """방금 담긴 파일이 실제로 잡히나 — 최신 commit 이 창 안일 때만 잰다."""
        root = os.path.dirname(HERE)
        r = subprocess.run(["git", "log", "-n", "10", "--format=%x1f%H %ct",
                            "--name-only"], cwd=root, capture_output=True,
                           encoding="utf-8")
        if r.returncode != 0:
            self.skipTest("이력을 못 읽는 자리다")
        sha, ct, files, seen = "", 0, [], []
        for line in (r.stdout or "").splitlines():
            if line.startswith("\x1f"):
                if files:
                    break                      # 최신부터 — 코드가 든 첫 commit 이면 된다
                seen = line[1:].split()
            elif line.strip() and not g.is_data_path(line.strip()):
                sha, ct = seen[0], int(seen[1])
                files.append(line.strip())
        if not files:
            self.skipTest("최근 열 commit 이 문서만 담았다")
        if time.time() - ct >= g.RECENT_COMMIT_SEC:
            self.skipTest("코드를 담은 마지막 commit 이 창 밖이다 — 잴 것이 없다")
        got = g._recent_commits_touching(files[:3])
        self.assertTrue(got, "방금 담긴 코드 파일을 이력에서 못 찾았다")
        self.assertIn(sha, {v[0] for v in got.values()})

    def test_the_preview_does_not_block_anything(self):
        out = io.StringIO()
        with mock.patch.object(g, "live_workers", lambda: []):
            self.assertEqual(g.concurrent_report(["bin/s9-guard"], out=out), 0)
        self.assertTrue(out.getvalue().strip(), "조회가 아무것도 말하지 않았다")


class WhoAmI(unittest.TestCase):
    """세션을 가르는 신호는 프로세스의 계보다 — commit 의 author 가 아니다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-rcg-who-")
        self.d = os.path.join(self.root, "state", "sessions")
        os.makedirs(self.d, exist_ok=True)

    def _bind(self, sid, pid):
        with open(os.path.join(self.d, f"Mac__{sid}.json"), "w", encoding="utf-8") as f:
            json.dump({"machine": "Mac", "session": sid, "user": "nice",
                       "attach_pid": str(pid)}, f)

    def test_the_session_that_launched_this_process_is_me(self):
        self._bind(MINE, os.getpid())
        self._bind(OTHER, 999999)
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("S9_SESSION", None)
            self.assertEqual(g.my_binding().get("session"), MINE)

    def test_no_binding_no_guess(self):
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("S9_SESSION", None)
            self.assertEqual(g.my_binding(), {})

    def test_a_broken_binding_does_not_break_the_commit(self):
        with open(os.path.join(self.d, "Mac__zzzz.json"), "w", encoding="utf-8") as f:
            f.write("{ 부서진 json")
        with mock.patch.object(g, "ROOT", self.root), \
                mock.patch.dict(os.environ, {"S9_SESSION": MINE}, clear=False):
            self.assertEqual(g.my_binding().get("session"), MINE)


if __name__ == "__main__":
    unittest.main()
