"""쓰고 있으면 잡은 것이다 (REQ-20260903-011-62x6).

실사고 2026-09-03. REQ-20260902-035 는 한 시간 넘게 실제로 돌고 있었는데
보드에서는 멈춤이었다. live 등록이 **상태 전이에만** 달려 있었기 때문이다 —
이미 in-progress 인 문서를 이어받아 일하는 세션은 전이를 하지 않으므로
아무것도 등록하지 않고, 사람이 `s9 last <id> --add` 를 기억해야만 살아났다.

리스 쪽에는 이미 옳은 규칙이 있었다: 「진전 쓰기가 곧 하트비트」
(REQ-20260902-020). 그 규칙을 live 포인터까지 잇는다.

실행: python3 tests/ progress_claims
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class ProgressWriteIsAClaim(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9pc-")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_MACHINE": "testbox"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")
        # 담당자(alice)가 잡아 둔 문서를 **다른 세션이 이어받는** 판을 만든다.
        self.rid = self.mk("도는 것")
        self.cli("status", self.rid, "in-progress", "--note", "t",
                 sess="oldsess1")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def mk(self, title):
        return self.cli("new", "request", "--title", title, "--summary", "s",
                        "--size", "S", "--user", "alice", "--goal", "g",
                        "--body", "x").split()[0]

    def cli(self, *a, sess=None, expect=0):
        env = dict(self.env)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *a], capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL)
        if expect is not None:
            assert r.returncode == expect, f"{a}: rc={r.returncode} {r.stderr}"
        return r.stdout.strip()

    def binding(self, sid):
        p = os.path.join(self.root, "state", "sessions",
                         "testbox__%s.json" % sid)
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return {}

    def active(self, sid):
        return self.binding(sid).get("active_reqs") or []

    # S1. 노트 한 줄이 곧 클레임이다 — 전이는 없다.
    def test_s1_a_note_alone_registers_the_session(self):
        self.assertNotIn(self.rid, self.active("newsess1"))
        self.cli("note", self.rid, "이어받아 일하는 중", sess="newsess1")
        self.assertIn(self.rid, self.active("newsess1"),
                      "일하고 있는데 보드에는 아무도 안 붙은 것으로 보인다")

    # S2. 두 번 남겨도 중복되지 않고 처음 잡은 시각이 보존된다.
    def test_s2_second_note_keeps_the_first_claim_time(self):
        self.cli("note", self.rid, "첫 줄", sess="newsess1")
        first = self.binding("newsess1")["claim_at"][self.rid]
        self.cli("note", self.rid, "둘째 줄", sess="newsess1")
        b = self.binding("newsess1")
        self.assertEqual(b["active_reqs"].count(self.rid), 1, "중복 등록")
        self.assertEqual(b["claim_at"][self.rid], first,
                         "다시 쓸 때마다 잡은 시각이 밀리면 '언제부터' 를 잃는다")

    # B1. 끝난 문서는 노트로도 되살아나지 않는다.
    def test_b1_a_closed_doc_is_never_claimed(self):
        self.cli("status", self.rid, "done", "--note", "끝", sess="oldsess1")
        self.cli("note", self.rid, "뒤늦은 기록", sess="newsess1")
        self.assertNotIn(self.rid, self.active("newsess1"),
                         "끝난 문서를 잡고 있다고 말하면 보드가 거짓이 된다")

    # B2. 진행 중이 아닌 것은 도는 것이 아니다.
    def test_b2_only_in_progress_counts(self):
        opened = self.mk("아직 안 집은 것")
        self.cli("note", opened, "메모", sess="newsess1")
        self.assertNotIn(opened, self.active("newsess1"))
        self.cli("status", self.rid, "blocked", "--note", "막힘",
                 sess="oldsess1")
        self.cli("note", self.rid, "사유 보충", sess="newsess2")
        self.assertNotIn(self.rid, self.active("newsess2"))

    # B3. 세션을 모르면(대시보드·외부) 아무것도 등록하지 않는다.
    def test_b3_no_session_registers_nothing(self):
        self.cli("note", self.rid, "밖에서 남긴 줄")
        names = os.listdir(os.path.join(self.root, "state", "sessions"))
        for n in names:
            with open(os.path.join(self.root, "state", "sessions", n),
                      encoding="utf-8") as f:
                b = json.load(f)
            self.assertNotIn(self.rid, [x for x in (b.get("active_reqs") or [])
                                        if b.get("session") != "oldsess1"],
                             "실행 세션을 모르는데 누군가를 붙였다")

    # F1. 남의 담당 문서에 남긴 노트는 클레임이 아니다 (REQ-20260902-016).
    def test_f1_a_reviewers_note_is_not_a_claim(self):
        self.cli("user", "add", "bob")
        self.cli("user", "switch", "bob", sess="bobsess1")
        try:
            self.cli("note", self.rid, "검토 의견", sess="bobsess1")
            self.assertNotIn(self.rid, self.active("bobsess1"),
                             "검토자의 노트가 클레임이 되면 담당자의 자리가 "
                             "'이미 누가 잡았다' 로 물러선다")
        finally:
            self.cli("user", "switch", "alice", sess="bobsess1")

    # F2. 계기가 기록을 막지 않는다 — 등록이 죽어도 노트는 남는다.
    def test_f2_the_note_survives_a_broken_registrar(self):
        ro = os.path.join(self.root, "state", "sessions")
        mode = os.stat(ro).st_mode
        os.chmod(ro, 0o500)            # 바인딩을 못 쓰게 만든다
        try:
            self.cli("note", self.rid, "그래도 남아야 한다", sess="newsess1")
        finally:
            os.chmod(ro, mode)
        p = self.cli("show", self.rid)
        self.assertIn("그래도 남아야 한다", p, "계기가 기록을 막았다")

    # R1. 전이 경로는 그대로다 — 들어가면 등록, 떠나면 제거.
    def test_r1_transition_path_unchanged(self):
        self.assertIn(self.rid, self.active("oldsess1"))
        self.cli("status", self.rid, "review", "--note",
                 "무엇이 달라졌나. 어디서 무엇을 눌러 보나. 무엇이 보이면 승인인가.",
                 "--force", sess="oldsess1")
        self.assertNotIn(self.rid, self.active("oldsess1"))


if __name__ == "__main__":
    unittest.main()
