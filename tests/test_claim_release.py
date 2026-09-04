"""클레임을 푸는 길 — `s9 claim <id> --release` (REQ-20260829-033-62x6).

실사고 2026-08-29 17:36 (REQ-20260828-041 라운드2 검증 중): 우발적으로 뜬 무인
워커가 프롬프트 지시대로 `s9 last <id> --add --session 0755c082` 로 클레임하고
확인만 하고 물러났다. 그 세션은 죽었지만 문서에는 `session: 0755c082` ·
`sessions: [ …, 0755c082 ]` 가 그대로 남았다.

남은 문제는 **되돌릴 명령이 없다**는 것이었다. `s9 claim` 은 있는데 푸는 짝이
없고, `s9 last --clear` 는 세션 쪽 포인터만 지운다 — 문서 프론트매터를 사람이
고칠 길은 파일을 직접 여는 것뿐이었다. 그래서 죽은 세션이 소유자 목록에
영구히 남아, 캡처 귀속(`_session_owns`)이 늘어난 채로 굳었다.

여기서 잠그는 계약은 **지우는 것이 아니라 옮기는 것**이라는 점이다: 도장은
문서에서 걷히되 근거 한 줄이 History 에 남아야 한다.

실행: python3 tests/ claim_release
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

DOC = "REQ-20260829-033-62x6"
DEAD = "0755c082"      # 실사고의 그 세션
LIVE = "911949e0"      # 계속 일하고 있던 리드 세션


def s9mod(root):
    os.environ["S9_ROOT"] = root
    name = "s9rel_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ago(sec):
    return (datetime.datetime.now().astimezone()
            - datetime.timedelta(seconds=sec)).isoformat(timespec="seconds")


class ClaimRelease(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9rel-")
        self.env = {**os.environ, "S9_ROOT": self.tmp,
                    "S9_MACHINE": "testbox", "S9_USER": "tester"}
        self.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env=self.env, timeout=60, stdin=subprocess.DEVNULL)
        self.m = s9mod(self.tmp)
        self.m.current_machine = lambda: "testbox"
        os.makedirs(self.m.STATE, exist_ok=True)
        self.path = self.doc()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 픽스처 --------------------------------------------------------
    # 1230 = 20분 30초. **분 경계에 세우지 않는다** — 1200(정확히 20분)이면
    # 문서를 쓰고 재는 사이에 1초만 흘러도 floor 가 19 를 내어 R5 가 이따금
    # 붉어진다(실측 2026-09-04: 전체 실행 하나를 그것으로 잃었다). 재는 값이
    # 경계에 있으면 그 시험은 계약이 아니라 시계를 재는 것이 된다.
    def doc(self, *, session=DEAD, sessions=(LIVE, DEAD), quiet_sec=1230):
        path = os.path.join(self.m.VAULT, "requests", "2026", "08", DOC + ".md")
        meta = {"id": DOC, "type": "request", "title": "클레임을 푸는 길이 없다",
                "summary": "s", "status": "in-progress", "size": "S",
                "user": "tester", "machine": "testbox",
                "created": ago(quiet_sec + 60), "updated": ago(quiet_sec),
                "status_since": ago(quiet_sec + 30), "priority": 50}
        if session:
            meta["session"] = session
        if sessions:
            meta["sessions"] = list(sessions)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        self.m.rebuild_index(quiet=True)
        return path

    def binding(self, sid, reqs, *, last=""):
        b = {"machine": "testbox", "session": sid, "user": "tester",
             "history": [], "active_reqs": list(reqs),
             "claim_at": {r: ago(1200) for r in reqs}}
        if last:
            b["last_req"] = last
        with open(os.path.join(self.m.STATE, f"testbox__{sid}.json"), "w") as f:
            json.dump(b, f)
        return b

    def run_s9(self, *args, session=None):
        env = dict(self.env)
        if session:
            env["S9_SESSION"] = session
        return subprocess.run([S9, *args], capture_output=True, text=True,
                              env=env, timeout=60, stdin=subprocess.DEVNULL)

    def read(self):
        return self.m.read_doc(self.path)

    # ---- R1/R2 ---------------------------------------------------------
    def test_r1_the_session_leaves_the_owner_list(self):
        """R1. 지목한 세션이 `sessions` 에서 빠진다."""
        r = self.run_s9("claim", DOC, "--release", "--session", DEAD)
        self.assertEqual(r.returncode, 0, r.stderr)
        meta, _ = self.read()
        self.assertNotIn(DEAD, meta.get("sessions") or [])
        self.assertNotEqual(meta.get("session"), DEAD)

    def test_r2_the_pointer_falls_back_to_who_is_left(self):
        """R2. `session`(단수)이 그 세션이면 남은 소유자에게 넘어간다."""
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        meta, _ = self.read()
        self.assertEqual(meta.get("session"), LIVE)

    def test_r2b_releasing_the_last_owner_empties_it(self):
        """R2b. 마지막 소유자를 풀면 아무도 없는 상태로 돌아간다."""
        self.doc(session=DEAD, sessions=())
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        meta, _ = self.read()
        self.assertFalse(meta.get("session"))
        self.assertFalse(meta.get("sessions"))

    # ---- R3 (근거가 남는다) --------------------------------------------
    def test_r3_the_reason_lands_in_history(self):
        """R3. 지우는 것이 아니라 옮기는 것 — History 에 근거 한 줄."""
        self.run_s9("claim", DOC, "--release", "--session", DEAD,
                    "--reason", "워커가 확인만 하고 죽었다")
        _meta, body = self.read()
        hist = body.split("## History", 1)[1]
        line = next((ln for ln in hist.splitlines() if DEAD in ln), "")
        self.assertTrue(line, "해제가 History 에 아무 흔적도 안 남겼다")
        self.assertIn("release", line)
        self.assertIn("tester", line, "누가 풀었는지가 없다")
        self.assertIn("워커가 확인만 하고 죽었다", line)
        self.assertIn(LIVE, line, "남은 소유자가 안 적혔다 — 상태를 되짚을 수 없다")

    def test_r3b_history_survives_without_a_reason(self):
        """R3b. `--reason` 이 없어도 시각·누가·어느 세션은 남는다."""
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        _meta, body = self.read()
        self.assertIn(f"claim release {DEAD}", body)

    # ---- R4 (캡처 귀속 회복) -------------------------------------------
    def test_r4_ownership_flips_off(self):
        """R4. 죽은 세션은 더 이상 이 문서의 주인이 아니다."""
        self.assertTrue(self.m._session_owns(DOC, DEAD), "전제가 깨졌다")
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        self.m.rebuild_index(quiet=True)
        self.assertFalse(self.m._session_owns(DOC, DEAD),
                         "풀었는데 캡처는 여전히 그 세션 것으로 붙는다")
        self.assertTrue(self.m._session_owns(DOC, LIVE),
                        "남은 주인의 캡처까지 끊겼다")

    # ---- R5 (푸는 것도 진전이 아니다) ----------------------------------
    def test_r5_release_does_not_rewind_the_stall_clock(self):
        """R5. 해제는 `updated` 를 건드리지 않는다 (034 와 대칭).

        푼 것만으로 멈춤 경보가 15분 꺼지면, 되돌리는 명령이 되돌릴 수 없는
        상태를 하나 더 만드는 셈이다.
        """
        before = self.read()[0]["updated"]
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        self.assertEqual(self.read()[0]["updated"], before)
        row = next(r for r in self.m.catalog_with_live() if r["id"] == DOC)
        self.assertEqual(row.get("stalled_mins"), 20)

    # ---- R6 (바인딩도 걷힌다) ------------------------------------------
    def test_r6_the_binding_lets_go_too(self):
        """R6. 세션 바인딩의 `active_reqs`·`claim_at`·`last_req` 에서도 빠진다."""
        other = "REQ-20260829-099-62x6"
        self.binding(DEAD, [DOC, other], last=DOC)
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        b = self.m.read_binding("testbox", DEAD)
        self.assertNotIn(DOC, b.get("active_reqs") or [])
        self.assertNotIn(DOC, b.get("claim_at") or {})
        self.assertFalse(b.get("last_req"))
        self.assertIn(other, b.get("active_reqs") or [],
                      "남의 클레임까지 걷어냈다")

    def test_r6b_other_sessions_keep_their_bindings(self):
        """R6b. 다른 세션의 바인딩은 손대지 않는다."""
        self.binding(LIVE, [DOC], last=DOC)
        self.run_s9("claim", DOC, "--release", "--session", DEAD)
        b = self.m.read_binding("testbox", LIVE)
        self.assertIn(DOC, b.get("active_reqs") or [])
        self.assertEqual(b.get("last_req"), DOC)

    # ---- R7~R9 (멱등·기본값·거부) --------------------------------------
    def test_r7_releasing_a_non_owner_is_a_no_op_that_says_so(self):
        """R7. 소유가 아닌 세션으로 풀면 문서는 그대로고 현재 소유자를 알려준다."""
        before = open(self.path, encoding="utf-8").read()
        r = self.run_s9("claim", DOC, "--release", "--session", "deadbeef")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(self.path, encoding="utf-8").read(), before)
        self.assertIn(LIVE, r.stdout, "현재 소유자를 안 알려주면 오타를 못 잡는다")
        self.assertIn(DEAD, r.stdout)

    def test_r7b_release_is_idempotent(self):
        """R7b. 두 번 풀어도 폭발하지 않는다."""
        self.assertEqual(
            self.run_s9("claim", DOC, "--release", "--session", DEAD)
            .returncode, 0)
        r = self.run_s9("claim", DOC, "--release", "--session", DEAD)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_r8_session_defaults_to_the_environment(self):
        """R8. `--session` 을 생략하면 `S9_SESSION` 을 쓴다."""
        r = self.run_s9("claim", DOC, "--release", session=DEAD)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(DEAD, self.read()[0].get("sessions") or [])

    def test_r9_a_missing_doc_is_refused(self):
        """R9. 없는 문서는 조용히 성공하지 않는다."""
        r = self.run_s9("claim", "REQ-19990101-001-zzzz", "--release",
                        "--session", DEAD)
        self.assertNotEqual(r.returncode, 0)

    def test_r9b_a_non_request_is_refused(self):
        """R9b. 요청이 아닌 문서는 거부한다 — 도장이 사는 자리가 아니다."""
        kid = "DOC-20260829-001-62x6"
        p = os.path.join(self.m.VAULT, "knowledge", "2026", "08", kid + ".md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        self.m.write_doc(p, {"id": kid, "type": "knowledge", "title": "k",
                             "status": "done", "user": "tester",
                             "created": ago(10), "updated": ago(10)},
                         "\n## Notes\n\n## History\n")
        self.m.rebuild_index(quiet=True)
        r = self.run_s9("claim", kid, "--release", "--session", DEAD)
        self.assertNotEqual(r.returncode, 0)

    def test_r9c_claim_and_release_still_share_one_command(self):
        """R9c. 거는 갈래는 그대로다 — `--release` 가 클레임을 망가뜨리지 않는다."""
        r = self.run_s9("claim", DOC, session="cafebabe")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cafebabe", self.read()[0].get("sessions") or [])


if __name__ == "__main__":
    unittest.main()
