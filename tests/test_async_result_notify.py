"""백그라운드 전체 실행의 결과가 스스로 도착한다 (REQ-20260906-029).

post-commit 이 띄운 전체 실행의 결과는 로그에만 남았고, 리드는 Monitor 로 기다리다
세 번 놓쳤다(2026-09-06). 여기서 못박는 것: 전체 판정 직후 ① 그 커밋 REQ 에 노트
② 클레임 세션 수신함에 kind=event 한 줄 ③ 실패면 후속 요청 자동 등록(같은 sha 는
한 번) — 그리고 손 실행(S9_TESTS_ASYNC 없음)에서는 아무것도 하지 않는다.

실행: python3 tests/ async_result_notify
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
GUARD = os.path.join(REPO, "bin", "s9-guard")
RUNNER = os.path.join(HERE, "__main__.py")

ROOT = tempfile.mkdtemp(prefix="s9arn-")
os.environ["S9_ROOT"] = ROOT          # 모듈 로드 전에 — s9.py 의 ROOT 는 import 때 정해진다
os.environ["S9_MACHINE"] = "testbox"
os.environ.pop("S9_SESSION", None)
os.environ.pop("S9_TESTS_ASYNC", None)
os.environ.pop("S9_TESTS_ASYNC_SHA", None)

_spec = importlib.util.spec_from_loader(
    "s9_async_notify_t", importlib.machinery.SourceFileLoader(
        "s9_async_notify_t", os.path.join(HERE, "async_notify.py")))
an = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(an)


def cli(*a):
    r = subprocess.run([S9, *a], capture_output=True, text=True, env=os.environ,
                       stdin=subprocess.DEVNULL)
    assert r.returncode == 0, f"{a}: {r.stderr}"
    return r.stdout.strip()


def inbox(sid):
    p = os.path.join(ROOT, "state", "terminal", f"inbox-{sid}.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def bind(sid, active=(), ended=False):
    os.makedirs(os.path.join(ROOT, "state", "sessions"), exist_ok=True)
    tp = os.path.join(ROOT, f"transcript-{sid}.jsonl")
    with open(tp, "w", encoding="utf-8") as f:
        f.write("{}\n")
    b = {"session": sid, "machine": "testbox", "user": "alice",
         "active_reqs": list(active), "transcript_path": tp}
    if ended:
        b["ended"] = True
    with open(os.path.join(ROOT, "state", "sessions", f"testbox__{sid}.json"), "w",
              encoding="utf-8") as f:
        json.dump(b, f)


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _put(g, body):
    with open(os.path.join(g, "a"), "w", encoding="utf-8") as f:
        f.write(body)


def req_docs():
    return sorted(glob.glob(os.path.join(ROOT, "vault", "requests", "**", "REQ-*.md"),
                            recursive=True))


class AsyncResultNotify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cli("init")
        cli("user", "add", "alice")
        cls.req = cli("new", "request", "--title", "알림 대상", "--summary", "s",
                      "--size", "S", "--user", "alice", "--goal", "g",
                      "--body", "x").split()[0]
        bind("sess1234", active=[cls.req])      # 클레임한 세션
        bind("other999")                        # 활성이지만 클레임 없음
        bind("ended000", active=[cls.req], ended=True)
        cls.on = {**os.environ, "S9_TESTS_ASYNC": "1"}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(ROOT, ignore_errors=True)

    def doc(self, rid=None):
        return cli("show", rid or self.req)

    def test_s1_pass_notifies_claimed_session_and_notes_req(self):
        """S1. 통과 → 클레임 세션 수신함 1줄 + REQ 노트, 새 요청 없음, 다른 세션은 조용."""
        before = len(req_docs())
        r = an.notify_full_result(True, [], 96.4, 297, where="원격", root=ROOT,
                                  env=self.on, sha="abc1234", req=self.req)
        self.assertEqual(r["sessions"], ["sess1234"])
        rows = [l for l in inbox("sess1234") if "abc1234" in l["text"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "event")
        self.assertEqual(rows[0]["from"], "dashboard")
        self.assertEqual(rows[0]["text"], "[전체 테스트] abc1234 통과 · 297파일 96초")
        self.assertEqual([l for l in inbox("other999") if "abc1234" in l["text"]], [])
        self.assertEqual(inbox("ended000"), [])
        d = self.doc()
        self.assertIn("전체 테스트 통과(원격 96초)", d)
        self.assertIn("test-runner", d)
        self.assertEqual(len(req_docs()), before)
        self.assertEqual(r["new_req"], "")

    def test_s2_fail_notifies_and_registers_child_request(self):
        """S2. 실패 → 실패 파일이 든 줄 + parent=REQ 인 후속 요청 + 표식."""
        r = an.notify_full_result(False, ["test_x.py", "test_y.py"], 210.2, 297,
                                  where="로컬", root=ROOT, env=self.on,
                                  sha="def5678", req=self.req)
        rows = [l for l in inbox("sess1234") if "def5678" in l["text"]]
        self.assertEqual(len(rows), 1)
        self.assertIn("[전체 테스트] def5678 실패 · test_x.py, test_y.py — 커밋 차단이 걸렸다",
                      rows[0]["text"])
        self.assertTrue(r["new_req"].startswith("REQ-"), r)
        self.assertIn(r["new_req"], rows[0]["text"])
        marker = os.path.join(ROOT, "state", "tests-async", "def5678.req")
        with open(marker, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), r["new_req"])
        child = self.doc(r["new_req"])
        self.assertIn('title: "전체 테스트 실패: def5678"', child)
        self.assertIn(f"parent: {self.req}", child)
        self.assertIn("test_x.py", child)
        self.assertIn("size: S", child)
        d = self.doc()
        self.assertIn("전체 테스트 실패(로컬 210초)", d)
        self.assertIn("test_x.py, test_y.py", d)

    def test_s3_same_sha_registers_only_once(self):
        """S3. 같은 sha 로 두 번 → 요청은 1건(표식), 수신함 줄은 2건."""
        a = an.notify_full_result(False, ["test_z.py"], 1, 3, root=ROOT, env=self.on,
                                  sha="0000dup", req=self.req)
        n = len(req_docs())
        b = an.notify_full_result(False, ["test_z.py"], 1, 3, root=ROOT, env=self.on,
                                  sha="0000dup", req=self.req)
        self.assertEqual(a["new_req"], b["new_req"])
        self.assertEqual(len(req_docs()), n)
        self.assertEqual(len([l for l in inbox("sess1234") if "0000dup" in l["text"]]), 2)

    def test_s4_manual_run_is_silent(self):
        """S4. S9_TESTS_ASYNC 없음(손 실행) → 수신함·문서·요청 어느 것도 안 바뀐다."""
        off = {k: v for k, v in os.environ.items() if k != "S9_TESTS_ASYNC"}
        before, nbefore = self.doc(), len(req_docs())
        r = an.notify_full_result(False, ["test_q.py"], 5, 9, root=ROOT, env=off,
                                  sha="quiet00", req=self.req)
        self.assertIsNone(r)
        self.assertEqual([l for l in inbox("sess1234") if "quiet00" in l["text"]], [])
        self.assertEqual(self.doc(), before)
        self.assertEqual(len(req_docs()), nbefore)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "state", "tests-async", "quiet00.req")))

    def test_s5_no_claim_goes_to_all_fresh_sessions_and_no_req_skips_note(self):
        """S5. 클레임이 없으면 활성 세션 전부에, REQ 가 없으면 노트·요청 없이 수신함만."""
        nbefore = len(req_docs())
        r = an.notify_full_result(False, ["test_w.py"], 2, 4, root=ROOT, env=self.on,
                                  sha="noreq00", req="")
        self.assertEqual(sorted(r["sessions"]), ["other999", "sess1234"])
        self.assertEqual(r["new_req"], "")
        self.assertEqual(len(req_docs()), nbefore)
        self.assertEqual(inbox("ended000"), [])
        # 커밋 메시지에서 REQ 를 뽑는다 — 없으면 ''
        g = tempfile.mkdtemp(prefix="s9arn-git-")
        try:
            def git(*a):
                return subprocess.run(["git", "-C", g, *a], capture_output=True, text=True,
                                      check=True).stdout.strip()
            git("init", "-q", "-b", "main")
            _put(g, "1")
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
                f"고친다 ({self.req})")
            sha = git("rev-parse", "--short", "HEAD")
            self.assertEqual(an.commit_req(g, sha), self.req)
            _put(g, "2")
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "문서만")
            self.assertEqual(an.commit_req(g, "HEAD"), "")
            self.assertEqual(an.commit_sha7(g, {"S9_TESTS_ASYNC_SHA": "abcdef0123"}), "abcdef0")
        finally:
            shutil.rmtree(g, ignore_errors=True)

    def test_s6_wiring_guard_passes_flag_and_runner_calls_notify(self):
        """S6. post-commit 이 백그라운드 실행에 S9_TESTS_ASYNC=1·sha 를 넘기고, 러너의 원격·로컬
        전체 판정 직후에 notify_full_result 가 있다."""
        guard = _read(GUARD)
        i = guard.index("def after_commit(")
        seg = guard[i:i + 4000]
        self.assertIn('env["S9_TESTS_ASYNC"] = "1"', seg)
        self.assertIn('env["S9_TESTS_ASYNC_SHA"]', seg)
        src = _read(RUNNER)
        self.assertGreaterEqual(src.count("notify_full_result("), 2,
                                "원격 경로와 로컬 병렬 경로 둘 다에서 부른다")
        self.assertIn("async_notify.take_env()", src, "표식은 자식에게 물려주지 않는다")
        os.environ["S9_TESTS_ASYNC"] = "1"
        try:
            snap = an.take_env()
        finally:
            os.environ.pop("S9_TESTS_ASYNC", None)
        self.assertTrue(an.active(snap))
        self.assertFalse(an.active())
        # 러너 자신은 tty 를 보지 않는다 — 판정은 env 한 줄(async_notify.active)뿐
        self.assertIn("S9_TESTS_ASYNC", _read(os.path.join(HERE, "async_notify.py")))


if __name__ == "__main__":
    unittest.main()
