"""Stop 캡처 오귀속·중복 방지 테스트 (REQ-20260825-066).

실사례: 무인 워커의 바인딩에 남은 stale last_req(다른 세션이 작업하던 REQ) 탓에
Stop 훅 완결 보고가 엉뚱한 문서에 2회 기록됐다. 가드는 두 겹:
(1) `last --active`는 문서의 session/sessions 승계 기록에 현 세션이 있는
    대상만 반환한다 — stale 포인터는 빈 값(캡처 스킵)으로 거부하고 세션 로그에 남긴다.
(2) `s9 note`는 좁은 창(NOTE_DUP_WINDOW_SEC) 안의 직전 노트와 동일 본문이면
    append 하지 않는다 — 훅 재발화/재시도 중복만 겨냥하고, 시간이 지난 재보고는 통과.
격리: S9_ROOT=mktemp. 실행: python3 tests/ note_guard
"""
import datetime
import glob
import json
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
SUBHOOK = os.path.join(HERE, "..", "bin", "s9-audit-subagent")


def make_cli(tmp):
    base = {**os.environ, "S9_ROOT": tmp, "S9_MACHINE": "testbox"}
    base.pop("S9_SESSION", None)

    def cli(sess, *argv):
        env = dict(base)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=15)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    return cli


class TestCaptureTarget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9noteg-")
        cls.cli = staticmethod(make_cli(cls.tmp))
        cli = cls.cli
        cli(None, "init")
        cli(None, "user", "add", "alice")
        mk = lambda sess, title: cli(
            sess, "new", "request", "--title", title, "--summary", "t",
            "--goal", "t", "--size", "S", "--user", "alice",
            "--body", "x").split()[0]
        # A: 세션 aaaa1111이 정식 클레임(set) — 문서에 aaaa1111 승계 스탬프
        cls.A = mk("aaaa1111", "owned")
        cli("aaaa1111", "last", cls.A)
        # B: --add 클레임용
        cls.B = mk("aaaa1111", "added")

    def binding(self, sess):
        p = os.path.join(self.tmp, "state", "sessions",
                         f"testbox__{sess}.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def write_binding(self, b):
        p = os.path.join(self.tmp, "state", "sessions",
                         f"testbox__{b['session']}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f)

    def doc_meta(self, doc_id):
        out = self.cli(None, "show", doc_id)
        head = out.split("---")[1]
        return head

    # N1. 승계 기록에 현 세션이 있으면 last_req 반환
    def test_test_capture_target(self):
        """TestCaptureTarget 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_owned_last_req"):
                out = self.cli("aaaa1111", "last", "--active").strip()
                self.assertEqual(out, self.A)

            # N2. stale last_req(승계 이력에 현 세션 없음) → 빈 값 + 세션 로그 기록
        with self.subTest("n2_stale_rejected"):
                self.write_binding({"machine": "testbox", "session": "bbbb2222",
                                    "user": "alice", "history": [],
                                    "last_req": self.A})
                out = self.cli("bbbb2222", "last", "--active").strip()
                self.assertEqual(out, "")
                # 거부가 세션 로그(SES 문서)에 드러난다
                b = self.binding("bbbb2222")
                ses = b.get("ses_doc", "")
                self.assertTrue(ses, b)
                log = self.cli(None, "show", ses)
                self.assertIn(self.A, log)

            # N3. stale last_req여도 현 세션이 승계한 active_req가 있으면 그쪽으로 폴백
        with self.subTest("n3_active_req_fallback"):
                self.write_binding({"machine": "testbox", "session": "cccc3333",
                                    "user": "alice", "history": [],
                                    "last_req": self.A})
                self.cli("cccc3333", "last", self.B, "--add")
                out = self.cli("cccc3333", "last", "--active").strip()
                self.assertEqual(out, self.B)

            # N4. --add 클레임도 문서에 세션 승계를 스탬프한다
        with self.subTest("n4_add_stamps_session"):
                self.cli("dddd4444", "last", self.B, "--add")
                self.assertIn("dddd4444", self.doc_meta(self.B))

            # N5. session 스탬프가 아예 없는 구문서는 소유로 간주 (하위호환)
        with self.subTest("n5_unstamped_doc_allowed"):
                c = self.cli(None, "new", "request", "--title", "legacy",
                             "--summary", "t", "--goal", "t", "--size", "S",
                             "--user", "alice", "--body", "x").split()[0]
                self.write_binding({"machine": "testbox", "session": "eeee5555",
                                    "user": "alice", "history": [], "last_req": c})
                out = self.cli("eeee5555", "last", "--active").strip()
                self.assertEqual(out, c)

            # N8. capture_paused는 여전히 빈 값 (회귀)
        with self.subTest("n8_paused_still_empty"):
                self.cli("aaaa1111", "last", "--pause")
                out = self.cli("aaaa1111", "last", "--active").strip()
                self.assertEqual(out, "")
                self.cli("aaaa1111", "last", self.A)  # 원복

            # N1b. 클레임이 전혀 없는 세션 → 빈 값 (기존 동작 유지)
        with self.subTest("n1b_no_claim_empty"):
            out = self.cli("ffff6666", "last", "--active").strip()
            self.assertEqual(out, "")

class TestDuplicateNote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9notedup-")
        cls.cli = staticmethod(make_cli(cls.tmp))
        cli = cls.cli
        cli(None, "init")
        cli(None, "user", "add", "alice")
        cls.R = cls.mkreq("dup")

    @classmethod
    def mkreq(cls, title):
        return cls.cli(None, "new", "request", "--title", title, "--summary",
                       "t", "--goal", "t", "--size", "S", "--user", "alice",
                       "--body", "x").split()[0]

    def entries(self, doc_id):
        """문서에 기록된 노트 엔트리 수 (타임스탬프 헤더 기준)."""
        return len(re.findall(r"(?m)^### \d{4}-",
                              self.cli(None, "show", doc_id)))

    def doc_path(self, doc_id):
        m = glob.glob(os.path.join(self.tmp, "vault", "**", doc_id + "*.md"),
                      recursive=True)
        self.assertEqual(len(m), 1, m)
        return m[0]

    def age_last_note(self, doc_id, seconds):
        """마지막 노트 헤더의 타임스탬프를 seconds만큼 과거로 돌린다."""
        path = self.doc_path(doc_id)
        with open(path, encoding="utf-8") as f:
            body = f.read()
        hdrs = list(re.finditer(r"(?m)^### (\d{4}-\S+) ", body))
        old = hdrs[-1].group(1)
        new = (datetime.datetime.fromisoformat(old)
               - datetime.timedelta(seconds=seconds)).isoformat(
                   timespec="seconds")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body[:hdrs[-1].start(1)] + new + body[hdrs[-1].end(1):])

    # N6. 동일 본문 2회 연속 → 두 번째는 억제, 문서에 1회만
    def test_test_duplicate_note(self):
        """TestDuplicateNote 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n6_duplicate_suppressed"):
                self.cli(None, "note", self.R, "완결 보고 본문", "--label", "response")
                out = self.cli(None, "note", self.R, "완결 보고 본문",
                               "--label", "response")
                self.assertIn("suppress", out.lower())
                doc = self.cli(None, "show", self.R)
                self.assertEqual(doc.count("완결 보고 본문"), 1, doc)

            # N7. 다른 본문은 정상 append — 2건 모두 기록된다
        with self.subTest("n7_distinct_appended"):
                r = self.mkreq("distinct")
                self.cli(None, "note", r, "본문 하나")
                self.cli(None, "note", r, "본문 둘")
                doc = self.cli(None, "show", r)
                self.assertIn("본문 하나", doc)
                self.assertIn("본문 둘", doc)
                self.assertEqual(self.entries(r), 2, doc)

            # N7b. 억제 창(NOTE_DUP_WINDOW_SEC) 밖의 동일 본문은 과잉 차단하지 않는다 —
            # 훅 재발화만 겨냥한 좁은 창이라는 설계 근거를 고정한다.
        with self.subTest("n7b_same_text_outside_window_appended"):
                r = self.mkreq("stale-dup")
                self.cli(None, "note", r, "재검증 완료")
                self.age_last_note(r, 3600)
                out = self.cli(None, "note", r, "재검증 완료")
                self.assertNotIn("suppress", out.lower())
                self.assertEqual(self.entries(r), 2, self.cli(None, "show", r))

            # N7c. 억제된 노트는 문서를 전혀 건드리지 않는다 (updated 포함)
        with self.subTest("n7c_suppressed_leaves_doc_intact"):
            r = self.mkreq("intact")
            self.cli(None, "note", r, "동일 보고")
            before = open(self.doc_path(r), encoding="utf-8").read()
            self.cli(None, "note", r, "동일 보고")
            self.assertEqual(open(self.doc_path(r), encoding="utf-8").read(),
                             before)

class TestSubagentCapture(unittest.TestCase):
    """SubagentStop 훅 캡처의 소유권 판정 (REQ-20260825-066 실측 2차).

    사고: 서브에이전트 보고에 남의 REQ id가 '언급'됐다는 이유만으로 그 문서에
    기록됐다 — done 상태인 REQ-20260824-065에 'Checking note timestamps in
    REQ-20260824-065.md' 가 붙었다. 언급(읽음/말함)을 작업으로 승격하면 안 된다.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9subcap-")
        cls.cli = staticmethod(make_cli(cls.tmp))
        cli = cls.cli
        cli(None, "init")
        cli(None, "user", "add", "alice")
        mk = lambda sess, t: cli(sess, "new", "request", "--title", t,
                                 "--summary", "t", "--goal", "t", "--size", "S",
                                 "--user", "alice", "--body", "x").split()[0]
        cls.OTHER = mk("0654aaaa", "남의 작업")   # 다른 세션이 승계한 REQ
        cli("0654aaaa", "last", cls.OTHER)
        cls.MINE = mk("104b4fe3", "내 작업")
        cli("104b4fe3", "last", cls.MINE, "--add")

    def fire(self, session, text, atype="subagent"):
        """SubagentStop 페이로드로 실제 훅을 발화한다."""
        env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox"}
        env.pop("S9_SESSION", None)
        payload = json.dumps({
            "session_id": session + "-1111-2222-3333-444444444444",
            "last_assistant_message": text, "agent_type": atype,
            "cwd": self.tmp})
        subprocess.run([SUBHOOK], input=payload, text=True, env=env, timeout=40)

    def notes(self, doc_id, needle):
        """본문(## Notes)에서만 센다 — 프론트매터에는 같은 문장이 항목 이름으로
        요약돼 들어간다(contributions, REQ-20260825-088). 그 파생물까지 세면
        기록 1건이 2건으로 보인다."""
        out = self.cli(None, "show", doc_id)
        body = out.split("\n---\n", 2)[-1] if out.startswith("---\n") else out
        return body.count(needle)

    def session_log(self, session):
        p = os.path.join(self.tmp, "state", "sessions", f"testbox__{session}.json")
        ses = json.load(open(p, encoding="utf-8")).get("ses_doc", "")
        return self.cli(None, "show", ses) if ses else ""

    def set_binding(self, session, **kw):
        p = os.path.join(self.tmp, "state", "sessions", f"testbox__{session}.json")
        b = json.load(open(p, encoding="utf-8"))
        b.update(kw)
        json.dump(b, open(p, "w", encoding="utf-8"), ensure_ascii=False)

    # N9. 클레임하지 않은 id가 본문에 언급돼도 그 문서에는 기록하지 않는다
    def test_test_subagent_capture(self):
        """SubagentStop 훅 캡처의 소유권 판정 (REQ-20260825-066 실측 2차)."""
        with self.subTest("n9_mention_is_not_ownership"):
                self.set_binding("104b4fe3", active_reqs=[self.MINE], last_req=self.MINE)
                self.fire("104b4fe3", f"Checking note timestamps in {self.OTHER}.md")
                self.assertEqual(self.notes(self.OTHER, "Checking note timestamps"), 0,
                                 self.cli(None, "show", self.OTHER))
                log = self.session_log("104b4fe3")
                self.assertIn("거부", log)
                self.assertIn(self.OTHER, log)

            # N10. 언급된 id를 이 세션이 승계했으면(클레임 포인터가 없어도) 기록한다
        with self.subTest("n10_owned_mention_recorded"):
                self.set_binding("104b4fe3", active_reqs=[], last_req="")  # 포인터 없이 스탬프만
                self.fire("104b4fe3", f"{self.MINE} 구현을 마쳤다")
                self.assertEqual(self.notes(self.MINE, "구현을 마쳤다"), 1,
                                 self.cli(None, "show", self.MINE))

            # N11. 언급이 없을 때의 last_req 폴백도 소유 확인을 거친다 (stale 차단)
        with self.subTest("n11_stale_last_req_fallback_blocked"):
            self.set_binding("104b4fe3", active_reqs=[], last_req=self.OTHER)
            self.fire("104b4fe3", "작업을 마쳤다는 보고", atype="staff-engineer")
            self.assertEqual(self.notes(self.OTHER, "작업을 마쳤다는 보고"), 0,
                             self.cli(None, "show", self.OTHER))

if __name__ == "__main__":
    unittest.main(verbosity=2)
