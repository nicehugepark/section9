"""백그라운드 전체 실행의 결과가 스스로 도착한다 (REQ-20260906-029).

post-commit 이 띄운 전체 실행의 결과는 로그에만 남았고, 리드는 Monitor 로 기다리다
세 번 놓쳤다(2026-09-06). 여기서 못박는 것: 전체 판정 직후 ① 그 커밋 REQ 에 노트
② 클레임 세션 수신함에 kind=event 한 줄 ③ 실패면 후속 요청 — 같은 파일이 두 회차 연속 실패할 때(REQ-20260909-060,
30분 규칙은 test_red_request_delay) — 그리고 손 실행(S9_TESTS_ASYNC 없음)에서는 아무것도 하지 않는다.

실행: python3 tests/ async_result_notify
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")
GUARD = os.path.join(REPO, "bin", "s9-guard")
RUNNER = os.path.join(HERE, "__main__.py")

ROOT = tempfile.mkdtemp(prefix="s9arn-")
MACHINE = "testbox"
os.environ["S9_ROOT"] = ROOT          # 모듈 로드 전에 — s9.py 의 ROOT 는 import 때 정해진다
os.environ["S9_MACHINE"] = MACHINE
os.environ.pop("S9_SESSION", None)
os.environ.pop("S9_TESTS_ASYNC", None)
os.environ.pop("S9_TESTS_ASYNC_SHA", None)

_spec = importlib.util.spec_from_loader(
    "s9_async_notify_t", importlib.machinery.SourceFileLoader(
        "s9_async_notify_t", os.path.join(HERE, "async_notify.py")))
an = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(an)


def env_for(**over):
    """이 시험이 부르는 s9 의 환경 — 뿌리와 머신을 **인자로 못박는다**
    (REQ-20260908-060).

    모듈 최상위의 `os.environ["S9_ROOT"]` 하나에 기대면 전체 실행에서만 진다:
    러너는 클래스 경계마다 S9_* 를 discovery 직후의 기준선으로 되돌리는데
    (tests/__main__.py env_restore·EnvIsolatingSuite), 그 기준선은 **마지막으로
    import 된 모듈**이 남긴 값이다. 이 파일과 한 샤드에 묶인 다른 시험 파일이
    제 임시 뿌리를 남겨 두면 setUpClass 는 남의 뿌리에 문서를 세우고,
    `notify_full_result(root=ROOT)` 는 제 뿌리에서 그 문서를 못 찾는다
    (`s9: error: document not found`). 단독 실행은 덮는 모듈이 없어 늘 통과한다.
    """
    e = dict(os.environ)
    e["S9_ROOT"] = ROOT
    e["S9_MACHINE"] = MACHINE
    e.pop("S9_SESSION", None)
    e.pop("S9_TESTS_ASYNC", None)
    e.pop("S9_TESTS_ASYNC_SHA", None)
    e.update(over)
    return e


def pin_env():
    """프로세스 안에서 도는 갈래(`an.target_sessions` → `s9.current_machine()`)도
    같은 뿌리·머신을 보게 한다. 클래스가 세운 값은 그 클래스 안에서 산다."""
    os.environ["S9_ROOT"] = ROOT
    os.environ["S9_MACHINE"] = MACHINE


def cli(*a):
    r = subprocess.run([S9, *a], capture_output=True, text=True, env=env_for(),
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
    b = {"session": sid, "machine": MACHINE, "user": "alice",
         "active_reqs": list(active), "transcript_path": tp}
    if ended:
        b["ended"] = True
    with open(os.path.join(ROOT, "state", "sessions", f"{MACHINE}__{sid}.json"), "w",
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
        pin_env()
        cli("init")
        cli("user", "add", "alice")
        cls.req = cli("new", "request", "--title", "알림 대상", "--summary", "s",
                      "--size", "S", "--user", "alice", "--goal", "g",
                      "--body", "x").split()[0]
        bind("sess1234", active=[cls.req])      # 클레임한 세션
        bind("other999")                        # 활성이지만 클레임 없음
        bind("ended000", active=[cls.req], ended=True)
        cls.on = env_for(S9_TESTS_ASYNC="1")

    def setUp(self):
        pin_env()

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
        # 못 남겼으면 **까닭부터** 말한다 (REQ-20260908-060) — 이 시험이 전체
        # 실행에서 가끔 졌을 때 사람이 본 것은 「문서에서 못 찾았다」뿐이었고,
        # 까닭은 샤드 로그에 묻혀 두 번을 그냥 넘겼다.
        self.assertEqual(r.get("note_err", ""), "", "노트를 못 남겼다")
        d = self.doc()
        self.assertIn("전체 테스트 통과(원격 96초)", d)
        self.assertIn("test-runner", d)
        self.assertEqual(len(req_docs()), before)
        self.assertEqual(r["new_req"], "")

    def test_s2_fail_notifies_and_registers_child_request(self):
        """S2. 실패 → 실패 파일이 든 줄 + 부모 노트는 즉시; 요청은 **같은 파일이 두 회차
        연속 실패할 때** parent=REQ 로 하나(sha 둘) + 두 sha 의 표식 (REQ-20260909-060)."""
        an.clear_pending(ROOT)
        r = an.notify_full_result(False, ["test_x.py", "test_y.py"], 210.2, 297,
                                  where="로컬", root=ROOT, env=self.on,
                                  sha="def5678", req=self.req, now=1_000_000.0)
        rows = [l for l in inbox("sess1234") if "def5678" in l["text"]]
        self.assertEqual(len(rows), 1)
        self.assertIn("[전체 테스트] def5678 실패 · test_x.py, test_y.py — 커밋 차단이 걸렸다",
                      rows[0]["text"])
        self.assertEqual(r["new_req"], "")          # 첫 실패는 적기만 한다
        self.assertFalse(os.path.exists(os.path.join(ROOT, "state", "tests-async", "def5678.req")))
        d = self.doc()
        self.assertIn("전체 테스트 실패(로컬 210초)", d)
        self.assertIn("test_x.py, test_y.py", d)
        # 다음 회차도 test_y.py 가 실패 → 그 자리에서 요청
        r2 = an.notify_full_result(False, ["test_y.py"], 200, 297, where="로컬", root=ROOT,
                                   env=self.on, sha="def9999", req=self.req, now=1_000_300.0)
        self.assertTrue(r2["new_req"].startswith("REQ-"), r2)
        rows = [l for l in inbox("sess1234") if "def9999" in l["text"]]
        self.assertIn(r2["new_req"], rows[0]["text"])
        for sha in ("def5678", "def9999"):
            marker = os.path.join(ROOT, "state", "tests-async", f"{sha}.req")
            with open(marker, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), r2["new_req"])
        child = self.doc(r2["new_req"])
        self.assertIn('title: "전체 테스트 실패: def5678 · def9999"', child)
        self.assertIn(f"parent: {self.req}", child)
        self.assertIn("test_x.py", child)
        self.assertIn("size: S", child)

    def test_s3_same_sha_registers_only_once(self):
        """S3. 같은 sha 로 두 번 → 새 회차가 아니다: 요청은 더 서지 않고 수신함 줄은 2건."""
        an.clear_pending(ROOT)
        a = an.notify_full_result(False, ["test_z.py"], 1, 3, root=ROOT, env=self.on,
                                  sha="0000dup", req=self.req, now=2_000_000.0)
        n = len(req_docs())
        b = an.notify_full_result(False, ["test_z.py"], 1, 3, root=ROOT, env=self.on,
                                  sha="0000dup", req=self.req, now=2_000_100.0)
        self.assertEqual((a["new_req"], b["new_req"]), ("", ""))
        self.assertEqual(len(req_docs()), n)
        self.assertEqual(an.read_pending(ROOT)["shas"], ["0000dup"])
        self.assertEqual(len([l for l in inbox("sess1234") if "0000dup" in l["text"]]), 2)

    def test_s4_manual_run_is_silent(self):
        """S4. S9_TESTS_ASYNC 없음(손 실행) → 수신함·문서·요청 어느 것도 안 바뀐다."""
        off = env_for()          # 표식 없음 — env_for 가 이미 걷어 준다
        self.assertNotIn("S9_TESTS_ASYNC", off)
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
        an.clear_pending(ROOT)
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
            # 자르지 않는다 — 이 값은 로그 파일의 이름이다 (REQ-20260915-020)
            self.assertEqual(an.commit_sha(g, {"S9_TESTS_ASYNC_SHA": "abcdef0123"}),
                             "abcdef0123")
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

    def test_s7_another_modules_root_does_not_move_this_test(self):
        """S7. 같은 프로세스의 다른 시험 파일이 S9_ROOT 를 제 것으로 덮어써도,
        노트·수신함은 이 시험의 임시 뿌리에 선다 (REQ-20260908-060).

        전체 실행에서만 지던 자리를 그대로 만든다: 러너가 클래스 경계에서
        되돌리는 기준선이 남의 뿌리일 때가 이것이다. 머신 이름은 setUp 이
        못박는다 — 수신함 후보를 고르는 갈래는 프로세스 안에서 돌아
        os.environ 을 그때 읽는다."""
        decoy = tempfile.mkdtemp(prefix="s9arn-decoy-")
        try:
            os.environ["S9_ROOT"] = decoy
            before = len(req_docs())
            r = an.notify_full_result(True, [], 7.0, 12, where="원격", root=ROOT,
                                      env=self.on, sha="leak000", req=self.req)
            self.assertEqual(r["sessions"], ["sess1234"])
            rows = [l for l in inbox("sess1234") if "leak000" in l["text"]]
            self.assertEqual(len(rows), 1)
            self.assertIn("전체 테스트 통과(원격 7초)", self.doc())
            self.assertEqual(len(req_docs()), before)
            # 남의 뿌리에는 아무것도 안 생겼다
            self.assertEqual(glob.glob(os.path.join(decoy, "vault", "**", "REQ-*.md"),
                                       recursive=True), [])
        finally:
            pin_env()
            shutil.rmtree(decoy, ignore_errors=True)


class TheLogPointerNamesAFileThatExists(unittest.TestCase):
    """알림과 후속 요청이 가리키는 로그는 **실제로 있는 파일**이어야 한다
    (REQ-20260915-020).

    실제 사고 2026-09-15: post-commit(bin/s9-guard)이 `git rev-parse --short` 로
    지은 로그 이름은 `c3ec38946` 였다 — 이 저장소는 커져서 git 이 7 자로는 유일하지
    않다고 보고 9 자를 낸다. 그런데 알림이 그 값을 `[:7]` 로 잘라
    `state/tests-async/c3ec389.log` 를 가리켰고, 그 파일은 없다. 그렇게 선
    REQ-20260915-020-62x6 을 집은 작업자가 무엇이 실패했는지 읽지 못했다.

    사람이 읽는 짧은 꼴(7 자)과 **파일 이름**은 다른 것이다 — 짧은 꼴은
    `ran_label` 이 따로 만든다.
    """
    SHA_A = "c3ec38946"        # 사고 그대로 — git 이 9 자를 낸 자리
    SHA_B = "c3ec38947"

    # 제 뿌리를 쓴다 — AsyncResultNotify 의 tearDownClass 가 ROOT 를 거두고,
    # 클래스 실행 순서는 이름순이라 그 뒤에 온다.
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9arn-log-")
        cls.env = dict(os.environ, S9_ROOT=cls.root, S9_MACHINE=MACHINE)
        cls.env.pop("S9_SESSION", None)
        cls.on = dict(cls.env, S9_TESTS_ASYNC="1")
        cls._cli("init")
        cls._cli("user", "add", "alice")
        cls.dir = os.path.join(cls.root, "state", "tests-async")
        os.makedirs(cls.dir, exist_ok=True)
        for sha in (cls.SHA_A, cls.SHA_B):
            with open(os.path.join(cls.dir, f"{sha}.log"), "w", encoding="utf-8") as f:
                f.write("[원격] 실패 rc=97\n")     # 훅이 지은 그 이름으로

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def _cli(cls, *a):
        r = subprocess.run([S9, *a], capture_output=True, text=True, env=cls.env,
                           stdin=subprocess.DEVNULL)
        assert r.returncode == 0, f"{a}: {r.stderr}"
        return r.stdout.strip()

    def setUp(self):
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = MACHINE
        an.clear_pending(self.root)

    def _new_req(self, title):
        return self._cli("new", "request", "--title", title, "--summary", "s",
                         "--size", "S", "--user", "alice", "--goal", "g",
                         "--body", "x").split()[0]

    def _pointed_paths(self, text):
        return re.findall(r"state/tests-async/\S+?\.log", text)

    def test_l1_the_name_is_not_truncated(self):
        """L1. 환경으로 받은 sha 를 자르지 않는다 — 그 값이 곧 파일 이름이다."""
        self.assertEqual(an.commit_sha(self.root, {"S9_TESTS_ASYNC_SHA": self.SHA_A}),
                         self.SHA_A)

    def test_l2_the_note_points_at_a_log_that_exists(self):
        """L2. 실패 노트가 적은 로그 경로를 열면 파일이 있다 — 사고의 본체."""
        req = self._new_req("로그 가리키기")
        an.notify_full_result(False, ["test_x.py"], 45, 20, where="원격 머신",
                              root=self.root, env=self.on, sha=self.SHA_A,
                              req=req, now=3_000_000.0)
        pointed = self._pointed_paths(self._cli("show", req))
        self.assertTrue(pointed, "노트에 로그 경로가 없다")
        for rel in pointed:
            self.assertTrue(os.path.exists(os.path.join(self.root, rel)),
                            f"노트가 없는 파일을 가리킨다: {rel} — c3ec389.log 사고 그대로")

    def test_l3_the_follow_up_request_points_at_logs_that_exist(self):
        """L3. 두 회차 연속 실패로 선 후속 요청의 로그 경로도 전부 실재한다."""
        req = self._new_req("로그 가리키기2")
        common = dict(root=self.root, env=self.on, req=req)
        an.notify_full_result(False, ["test_x.py"], 45, 20, sha=self.SHA_A,
                              now=3_100_000.0, **common)
        r2 = an.notify_full_result(False, ["test_x.py"], 45, 20, sha=self.SHA_B,
                                   now=3_100_300.0, **common)
        self.assertTrue(r2["new_req"].startswith("REQ-"), r2)
        pointed = self._pointed_paths(self._cli("show", r2["new_req"]))
        self.assertEqual(len(pointed), 2, "회차 둘의 로그가 다 적혀야 한다")
        for rel in pointed:
            self.assertTrue(os.path.exists(os.path.join(self.root, rel)),
                            f"후속 요청이 없는 파일을 가리킨다: {rel}")
        # 표식(.req)도 훅이 지은 이름으로 — 잘린 이름이면 같은 묶음을 못 알아본다
        for sha in (self.SHA_A, self.SHA_B):
            self.assertTrue(os.path.exists(os.path.join(self.dir, f"{sha}.req")),
                            f"{sha}.req 표식이 없다")

    def test_l4_the_human_label_stays_short(self):
        """L4. 자르지 않는 것은 **경로**뿐 — 사람이 읽는 줄은 7 자 그대로다."""
        self.assertEqual(an.ran_label(self.SHA_A, ""), "c3ec389")

    def test_l5_the_hook_names_the_log_with_the_sha_it_hands_over(self):
        """L5. 훅이 로그 이름에 쓴 값과 러너에 넘기는 값은 **같은 하나**여야 한다 —
        둘이 갈리면 어느 쪽을 잘라도 이 사고가 돌아온다."""
        guard = _read(GUARD)
        i = guard.index("def after_commit(")
        seg = guard[i:i + 4000]
        self.assertIn('rev-parse", "--short"', seg, "로그 이름은 git 이 정한다")
        self.assertIn('f"{sha}.log"', seg)
        self.assertIn('env["S9_TESTS_ASYNC_SHA"] = sha', seg,
                      "넘기는 값이 로그 이름과 다른 변수다")


if __name__ == "__main__":
    unittest.main()


class TheReportNamesWhatActuallyRan(unittest.TestCase):
    """알림이 가리키는 커밋은 거짓이 없어야 한다 (REQ-20260907-064).

    post-commit 훅은 제가 잡은 커밋으로 로그 이름을 짓고 sha 를 넘기는데, 러너는
    HEAD 를 새로 읽어 돈다. commit 훅이 노트를 자동 커밋하므로 코드 커밋 직후
    HEAD 는 거의 언제나 한 칸 앞이다 — 「3fc7a5e 실패」라 알린 회차가 실제로는
    1초 뒤의 f7230df 를 돌았다. 함수를 **불러서** 잰다(소스 글자 대조 없음).
    """

    def test_same_commit_is_said_once(self):
        self.assertEqual(an.ran_label("3fc7a5e0", "3fc7a5e0abcdef"), "3fc7a5e")

    def test_different_commits_are_both_said(self):
        got = an.ran_label("3fc7a5e0", "f7230df0")
        self.assertIn("3fc7a5e", got)
        self.assertIn("f7230df", got)
        self.assertIn("시작", got)
        self.assertIn("돌았다", got)

    def test_no_started_sha_hand_run_says_head_only(self):
        # 사람이 손으로 돌린 실행 — 훅이 넘긴 시작 sha 가 없다
        self.assertEqual(an.ran_label("", "f7230df0"), "f7230df")
        self.assertEqual(an.ran_label(None, "f7230df0"), "f7230df")

    def test_unknown_ran_sha_falls_back_to_started(self):
        self.assertEqual(an.ran_label("3fc7a5e0", ""), "3fc7a5e")
        self.assertEqual(an.ran_label("", ""), "head")

    def test_long_and_short_forms_compare_as_one_commit(self):
        # 7자로 왔든 40자로 왔든 같은 커밋이면 하나만 적는다
        self.assertEqual(an.ran_label("3fc7a5e", "3fc7a5e0" + "0" * 32), "3fc7a5e")

    def test_notify_message_carries_both_when_they_differ(self):
        """문장 조립까지 — 사람이 읽는 [알림] 한 줄에 둘이 다 실리고,
        로그·후속 요청을 잇는 sha 는 시작 커밋 그대로다."""
        import contextlib
        import io

        class StubS9:
            def chat_send(self, *a, **k):
                return "sid1"

        err = io.StringIO()
        with mock.patch.object(an, "commit_req", lambda *a, **k: ""), \
                mock.patch.object(an, "_load_s9", lambda root: StubS9()), \
                mock.patch.object(an, "target_sessions", lambda s9, req: []), \
                contextlib.redirect_stderr(err):
            r = an.notify_full_result(True, [], 12.0, 361, where="원격 머신",
                                      root=REPO, env={"S9_TESTS_ASYNC": "1",
                                                      "S9_TESTS_ASYNC_SHA": "3fc7a5e0"},
                                      ran_sha="f7230df0")
        self.assertIsNotNone(r)
        # 자르지 않은 그대로 — 로그 파일의 이름이다 (REQ-20260915-020)
        self.assertEqual(r.get("sha"), "3fc7a5e0", "로그·후속 요청은 시작 sha 로 잇는다")
        line = err.getvalue()
        self.assertIn("3fc7a5e", line)
        self.assertIn("f7230df", line, "실제로 돈 커밋이 알림에 없다 — 사람이 잘못된 커밋을 뒤진다")
