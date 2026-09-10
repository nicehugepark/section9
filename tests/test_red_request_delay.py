"""실패 요청은 30분 안 못 고칠 때만 (REQ-20260909-060).

전체 테스트 실패마다 요청이 서던 규칙(REQ-20260906-029)은 나흘에 34건을 세웠고 그중
28건이 7분 안에 닫혔다(quality-assurance 실측, REQ-20260909-053). 여기서 못박는 것:
통지·커밋 차단·부모 노트는 즉시 그대로, 요청 문서는 (a) 30분 안에 통과 회차가 없거나
(b) 같은 파일이 두 회차 연속 실패할 때만 — 그리고 세울 때는 sha 를 모두 적는다.
시각은 전부 `now` 인자로 넣어 재현한다 — 벽시계에 기대는 시험은 재현이 안 된다.

실행: python3 tests/ red_request_delay
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

ROOT = tempfile.mkdtemp(prefix="s9rrd-")
MACHINE = "testbox"
os.environ["S9_ROOT"] = ROOT
os.environ["S9_MACHINE"] = MACHINE
for k in ("S9_SESSION", "S9_TESTS_ASYNC", "S9_TESTS_ASYNC_SHA"):
    os.environ.pop(k, None)


def _load(name, path):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


an = _load("s9_async_notify_rrd", os.path.join(HERE, "async_notify.py"))

T = 1_700_000_000.0          # 기준 시각 — 값은 아무것이나, 차이만 뜻이 있다
MIN = 60.0


def env_for(**over):
    e = dict(os.environ)
    e["S9_ROOT"] = ROOT
    e["S9_MACHINE"] = MACHINE
    for k in ("S9_SESSION", "S9_TESTS_ASYNC", "S9_TESTS_ASYNC_SHA"):
        e.pop(k, None)
    e.update(over)
    return e


def pin_env():
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


def bind(sid, active=()):
    os.makedirs(os.path.join(ROOT, "state", "sessions"), exist_ok=True)
    tp = os.path.join(ROOT, f"transcript-{sid}.jsonl")
    with open(tp, "w", encoding="utf-8") as f:
        f.write("{}\n")
    b = {"session": sid, "machine": MACHINE, "user": "alice",
         "active_reqs": list(active), "transcript_path": tp}
    with open(os.path.join(ROOT, "state", "sessions", f"{MACHINE}__{sid}.json"), "w",
              encoding="utf-8") as f:
        json.dump(b, f)


def req_docs():
    return sorted(glob.glob(os.path.join(ROOT, "vault", "requests", "**", "REQ-*.md"),
                            recursive=True))


def marker(sha):
    return os.path.join(ROOT, "state", "tests-async", f"{sha}.req")


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


class RedRequestDelay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pin_env()
        cli("init")
        cli("user", "add", "alice")
        cls.req = cli("new", "request", "--title", "실패 부모", "--summary", "s",
                      "--size", "S", "--user", "alice", "--goal", "g",
                      "--body", "x").split()[0]
        bind("sess1234", active=[cls.req])
        cls.on = env_for(S9_TESTS_ASYNC="1")

    def setUp(self):
        pin_env()
        an.clear_pending(ROOT)

    def red_round(self, sha, files, now, req=None):
        return an.notify_full_result(False, files, 100, 297, where="원격 머신", root=ROOT,
                                     env=self.on, sha=sha, req=self.req if req is None else req,
                                     now=now)

    def ok(self, sha, now):
        return an.notify_full_result(True, [], 90, 297, where="원격 머신", root=ROOT,
                                     env=self.on, sha=sha, req=self.req, now=now)

    def test_r1_first_failure_records_pending_not_request(self):
        """R1. 실패 1회 → 요청 없음 · pending 기록 · 통지와 부모 노트는 즉시."""
        n = len(req_docs())
        r = self.red_round("aaa0001", ["test_a.py"], T)
        self.assertEqual(r["new_req"], "")
        self.assertEqual(len(req_docs()), n)
        self.assertFalse(os.path.exists(marker("aaa0001")))
        pend = an.read_pending(ROOT)
        self.assertEqual(pend["shas"], ["aaa0001"])
        self.assertEqual(pend["files"], ["test_a.py"])
        self.assertEqual(pend["at"], T)
        self.assertEqual(pend["req"], self.req)
        self.assertEqual(pend["new_req"], "")
        rows = [l for l in inbox("sess1234") if "aaa0001" in l["text"]]
        self.assertEqual(len(rows), 1)
        self.assertIn("실패 · test_a.py — 커밋 차단이 걸렸다", rows[0]["text"])
        self.assertIn("30분", rows[0]["text"])
        self.assertIn("전체 테스트 실패(원격 머신 100초) — aaa0001", cli("show", self.req))

    def test_r2_pass_within_grace_clears_pending_without_request(self):
        """R2. 30분 안 통과 → 요청 없음 · pending 삭제."""
        self.red_round("bbb0001", ["test_b.py"], T)
        n = len(req_docs())
        r = self.ok("bbb0002", T + 10 * MIN)
        self.assertEqual(r["new_req"], "")
        self.assertIsNone(an.read_pending(ROOT))
        self.assertEqual(len(req_docs()), n)
        # 30분을 넘긴 뒤의 통과도 같다 — 통과가 왔으니 세우지 않는다
        self.red_round("bbb0003", ["test_b.py"], T + 20 * MIN)
        self.ok("bbb0004", T + 60 * MIN)
        self.assertIsNone(an.read_pending(ROOT))
        self.assertEqual(len(req_docs()), n)

    def test_r3_same_file_two_rounds_registers_at_once_with_both_shas(self):
        """R3. 다음 회차도 같은 파일 실패 → 즉시 요청(sha 둘) · 그 뒤 같은 묶음은 그 id."""
        n = len(req_docs())
        self.assertEqual(self.red_round("ccc0001", ["test_c.py"], T)["new_req"], "")
        r = self.red_round("ccc0002", ["test_c.py", "test_d.py"], T + 5 * MIN)
        self.assertTrue(r["new_req"].startswith("REQ-"), r)
        self.assertEqual(len(req_docs()), n + 1)
        child = cli("show", r["new_req"])
        self.assertIn('title: "전체 테스트 실패: ccc0001 · ccc0002"', child)
        self.assertIn(f"parent: {self.req}", child)
        self.assertIn("state/tests-async/ccc0001.log", child)
        self.assertIn("state/tests-async/ccc0002.log", child)
        self.assertIn("test_d.py", child)
        for sha in ("ccc0001", "ccc0002"):
            with open(marker(sha), encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), r["new_req"])
        self.assertEqual(an.read_pending(ROOT)["new_req"], r["new_req"])
        rows = [l for l in inbox("sess1234") if "ccc0002" in l["text"]]
        self.assertIn(f"후속 요청 {r['new_req']}", rows[0]["text"])
        # 세 번째 회차 — 요청은 더 서지 않고 그 id 를 가리킨다, 표식은 남긴다
        r3 = self.red_round("ccc0003", ["test_c.py"], T + 9 * MIN)
        self.assertEqual(r3["new_req"], r["new_req"])
        self.assertEqual(len(req_docs()), n + 1)
        self.assertTrue(os.path.exists(marker("ccc0003")))
        self.assertEqual(an.read_pending(ROOT)["shas"], ["ccc0001", "ccc0002", "ccc0003"])

    def test_r4_grace_elapsed_without_round_tick_registers(self):
        """R4. 30분 지남 + 회차 없음 → 워처 틱이 요청을 세운다(sha 전부)."""
        n = len(req_docs())
        self.red_round("ddd0001", ["test_e.py"], T)
        self.red_round("ddd0002", ["test_f.py"], T + 2 * MIN)        # 다른 파일 — 합쳐지기만
        self.assertEqual(len(req_docs()), n)
        self.assertEqual(an.pending_red_tick(ROOT, now=T + 29 * MIN, env=self.on), "")
        self.assertEqual(len(req_docs()), n)
        new_id = an.pending_red_tick(ROOT, now=T + 30 * MIN, env=self.on)
        self.assertTrue(new_id.startswith("REQ-"), new_id)
        self.assertEqual(len(req_docs()), n + 1)
        child = cli("show", new_id)
        self.assertIn('title: "전체 테스트 실패: ddd0001 · ddd0002"', child)
        self.assertIn("test_e.py", child)
        self.assertIn("test_f.py", child)
        self.assertEqual(an.read_pending(ROOT)["new_req"], new_id)
        self.assertEqual(an.pending_red_tick(ROOT, now=T + 31 * MIN, env=self.on), "")
        self.assertEqual(len(req_docs()), n + 1)
        # 배선: serve 워처가 30초마다 부르는 bin/s9.py red_request_tick 이 같은 답을 낸다
        an.clear_pending(ROOT)
        self.red_round("ddd0003", ["test_g.py"], T)
        s9 = an._load_s9(ROOT)
        self.assertEqual(s9.red_request_tick(now=T + 29 * MIN), "")
        got = s9.red_request_tick(now=T + 30 * MIN)
        self.assertTrue(got.startswith("REQ-"), got)
        self.assertEqual(len(req_docs()), n + 2)
        self.assertEqual(s9.red_request_tick(now=T + 40 * MIN), "")

    def test_r5_block_and_notify_stay_immediate_and_hand_run_is_silent(self):
        """R5. 회귀: 커밋 차단은 요청·묶음과 무관하게 실패 기록만으로 즉시 · 손 실행은
        pending 도 안 만든다."""
        g = _load("s9_guard_rrd_r5", GUARD)
        red = {"at": T, "files": ["test_a.py"], "fingerprint": ""}
        # 요청이 서기 전(묶음만 있는 30분 안)에도 code 커밋은 막힌다
        self.red_round("eee0001", ["test_a.py"], T)
        self.assertEqual(an.read_pending(ROOT)["new_req"], "")
        stop, files = g.red_ratchet(["bin/s9.py"], red=red, green_age=10 * MIN, now=T + MIN,
                                    fix_env="")
        self.assertEqual((stop, files), (True, ["test_a.py"]))
        # 실패한 시험을 담은 커밋과 S9_FIX_RED 는 그대로 지나간다
        self.assertFalse(g.red_ratchet(["tests/test_a.py"], red=red, green_age=10 * MIN,
                                       now=T + MIN, fix_env="")[0])
        self.assertFalse(g.red_ratchet(["bin/s9.py"], red=red, green_age=10 * MIN,
                                       now=T + MIN, fix_env=self.req)[0])
        an.clear_pending(ROOT)
        off = env_for()
        self.assertIsNone(an.notify_full_result(False, ["test_h.py"], 1, 1, root=ROOT, env=off,
                                                sha="eee0002", req=self.req, now=T))
        self.assertIsNone(an.read_pending(ROOT))

    def test_r6_commit_msg_warns_without_cause_line(self):
        """R6. commit-msg: 실패 기록이 통과보다 새롭고 「원인:」 줄이 없으면 경고, 막지 않음."""
        g = _load("s9_guard_rrd", GUARD)
        red = {"at": T, "files": ["test_a.py"], "fingerprint": ""}
        warn = g.red_cause_warning("guard: 검사 하나 고침\n\n본문", red, green_age=None, now=T + MIN)
        self.assertIn("원인:", warn)
        self.assertIn("test_a.py", warn)
        self.assertIn("막지 않습니다", warn)
        self.assertEqual(g.red_cause_warning("고침\n\n원인: 계약을 바꾸고 시험을 안 담았다\n",
                                             red, None, T + MIN), "")
        self.assertNotEqual(g.red_cause_warning("고침\n\n원인:   \n", red, None, T + MIN), "",
                            "빈 원인 줄은 없는 것이다")
        # 실패 뒤에 통과가 있었다 → 조용 · 이름 없는 기록 → 조용
        self.assertEqual(g.red_cause_warning("고침", red, green_age=10, now=T + MIN), "")
        self.assertEqual(g.red_cause_warning("고침", {"at": T, "files": []}, None, T + MIN), "")
        self.assertEqual(g.red_cause_warning("고침", None, None, T), "")
        # 배선: 훅이 부르는 commit_msg_red_cause — 기록 자리와 마지막 통과를 인자 없이
        # 읽으므로 둘을 임시 뿌리로 돌려 놓고 부른다(실제 state/ 는 건드리지 않는다).
        # 경고는 stderr 로, 종료 코드는 0 (막지 않는다).
        import contextlib
        import io
        red_path = os.path.join(ROOT, "state", "tests-last-red.json")
        os.makedirs(os.path.dirname(red_path), exist_ok=True)
        with open(red_path, "w", encoding="utf-8") as f:
            json.dump(red, f)
        g.LAST_RED = red_path
        g.full_green_age = lambda: None
        path = os.path.join(ROOT, "COMMIT_EDITMSG")

        def hook(msg):
            with open(path, "w", encoding="utf-8") as f:
                f.write(msg)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = g.commit_msg_red_cause(path)
            return rc, err.getvalue()

        rc, err = hook("고침\n")
        self.assertEqual(rc, 0)
        self.assertIn("원인:", err)
        self.assertIn("test_a.py", err)
        rc, err = hook("고침\n\n원인: 계약을 바꾸고 시험을 안 담았다\n")
        self.assertEqual((rc, err), (0, ""))
        g.full_green_age = lambda: 10.0          # 실패 뒤에 통과가 있었다 → 조용
        self.assertEqual(hook("고침\n"), (0, ""))
        os.unlink(red_path)
        self.assertEqual(hook("고침\n"), (0, ""))   # 기록이 없으면 조용


class TheParentIsNotACondition(unittest.TestCase):
    """부모 하나 때문에 요청이 안 서거나, 반쯤 선 문서가 남지 않는다 (REQ-20260910-051).

    실제 사고 2026-09-10: commit 메시지에서 뽑은 부모 id 는 컴퓨터 표식이 없는
    짧은 꼴(`REQ-20260910-009`)인데 같은 번호가 두 컴퓨터에 있었다. `s9 new` 는
    문서를 다 쓴 **뒤에** 부모를 찾다 「모호한 id」로 죽었고, 부르는 워처는
    실패로 읽어 30초마다 다시 걸었다 — 같은 요청이 여섯 개 섰고 전부 부모가
    풀리지 않은 채였다. 여기서 못박는 것 둘: 실패한 `s9 new` 는 **아무것도
    남기지 않는다** · 실패 요청은 부모를 못 이어도 **한 번은** 선다.
    """

    @classmethod
    def setUpClass(cls):
        pin_env()
        cls.req = cli("new", "request", "--title", "부모 후보", "--summary", "s",
                      "--size", "S", "--user", "alice", "--goal", "g",
                      "--body", "x").split()[0]
        # 같은 번호·다른 컴퓨터 표식 — 모호함을 만든다.
        src = an._load_s9(ROOT).locate(cls.req)
        cls.twin = cls.req.rsplit("-", 1)[0] + "-zz99"
        dst = os.path.join(os.path.dirname(src), cls.twin + ".md")
        with open(src, encoding="utf-8") as f:
            body = f.read()
        with open(dst, "w", encoding="utf-8") as f:
            f.write(body.replace(cls.req, cls.twin))
        cli("index", "rebuild")
        cls.short = cls.req.rsplit("-", 1)[0]      # 표식을 뗀 짧은 꼴

    def setUp(self):
        pin_env()
        an.clear_pending(ROOT)

    def _new(self, *extra):
        return subprocess.run(
            [S9, "new", "request", "--title", "부모 시험", "--summary", "s", "--size", "S",
             "--user", "alice", "--goal", "g", "--body", "b", *extra],
            capture_output=True, text=True, env=env_for(), stdin=subprocess.DEVNULL)

    def test_n1_a_missing_parent_leaves_nothing_behind(self):
        """N1. 없는 부모 — 죽되 문서는 하나도 안 생긴다."""
        n = len(req_docs())
        r = self._new("--parent", "REQ-20200101-999")
        self.assertNotEqual(0, r.returncode, r.stdout)
        self.assertEqual(n, len(req_docs()),
                         "실패했는데 문서가 남았다 — 반쯤 쓴 문서는 다음 회차를 부른다")

    def test_n2_an_ambiguous_parent_leaves_nothing_behind(self):
        """N2. 모호한 부모(같은 번호가 두 컴퓨터에) — 죽되 문서는 안 생긴다."""
        n = len(req_docs())
        r = self._new("--parent", self.short)
        self.assertNotEqual(0, r.returncode, r.stdout)
        self.assertIn("모호한 id", r.stderr + r.stdout)
        self.assertEqual(n, len(req_docs()))

    def test_n3_a_good_parent_still_links_both_ways(self):
        """N3. 회귀 — 제대로 된 부모는 그대로 이어지고 부모의 children 에 든다."""
        n = len(req_docs())
        r = self._new("--parent", self.req)
        self.assertEqual(0, r.returncode, r.stderr)
        new_id = r.stdout.split()[0]
        self.assertEqual(n + 1, len(req_docs()))
        self.assertIn(f"parent: {self.req}", cli("show", new_id, "--meta"))
        self.assertIn(new_id, cli("show", self.req, "--meta"))

    def test_r7_a_red_request_stands_even_when_the_parent_will_not_resolve(self):
        """R7. 부모가 모호해도 실패 요청은 선다 — 부모 없이, 그 사실을 본문에 적고."""
        n = len(req_docs())
        an.notify_full_result(False, ["test_z.py"], 100, 297, where="원격 머신", root=ROOT,
                              env=self.on if hasattr(self, "on") else env_for(S9_TESTS_ASYNC="1"),
                              sha="eee0001", req=self.short, now=T)
        new_id = an.pending_red_tick(ROOT, now=T + 30 * MIN, env=env_for(S9_TESTS_ASYNC="1"))
        self.assertTrue(new_id.startswith("REQ-"), f"부모 하나 때문에 요청이 안 섰다: {new_id!r}")
        self.assertEqual(n + 1, len(req_docs()))
        doc = cli("show", new_id)
        self.assertIn("부모를 잇지 못했다", doc, "못 이은 사실이 본문에 없다")
        self.assertIn(self.short, doc, "어느 부모였는지가 본문에 없다")

    def test_r8_it_does_not_stand_again_on_the_next_tick(self):
        """R8. 그 뒤 틱은 다시 세우지 않는다 — 30초마다 쌓이던 자리다."""
        an.notify_full_result(False, ["test_y.py"], 100, 297, where="원격 머신", root=ROOT,
                              env=env_for(S9_TESTS_ASYNC="1"), sha="fff0001",
                              req=self.short, now=T)
        first = an.pending_red_tick(ROOT, now=T + 30 * MIN, env=env_for(S9_TESTS_ASYNC="1"))
        self.assertTrue(first.startswith("REQ-"))
        n = len(req_docs())
        for k in range(1, 4):
            self.assertEqual("", an.pending_red_tick(
                ROOT, now=T + (30 + k) * MIN, env=env_for(S9_TESTS_ASYNC="1")))
        self.assertEqual(n, len(req_docs()), "틱마다 같은 요청이 또 섰다")


if __name__ == "__main__":
    unittest.main()
