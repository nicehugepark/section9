"""부르는 이름은 세션 문서에 적힌다 (REQ-20260908-019-62x6).

`s9 peer` 는 이 머신의 `state/peers.json` 에만 있어서 다른 컴퓨터로 가면 다시
물어야 했다. 그런데 그 이름은 이미 vault 안에 있다 — 다른 자리의 세션이 보낸
프롬프트 머리에 하네스가 `<cross-session-message from=… from-name=…>` 을 붙이고,
그 줄이 세션 문서 History 에 남는다. 이름을 문서에 적으면 git 을 타고 머신
사이를 따라다닌다.

두 걸음을 시험한다. ① 자기 이름표(`harness_session`)는 transcript 에 하네스가
적어 둔 것만 읽어 제 문서에 적는다. ② 받은 표식의 이름은 그 이름표를 가진
문서의 `call_name` 이 된다. 지어낸 이름은 적지 않는다 — 본문에 인용된 표식은
근거가 아니다.

실행: python3 tests/ call_name
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s9cli  # noqa: E402  (윈도우에서 확장자 없는 bin/s9 를 부르게 한다)

s9cli.install()
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")

TAG = ('<cross-session-message from="bridge:session_MAC1" '
       'from-name="맥 리드" from-mode="prompting">')


class CallNamesTravelInTheVault(unittest.TestCase):
    """모듈을 한 번만 올리고 문서를 직접 놓는다 — s9 프로세스를 아낀다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9-callname-")
        os.environ["S9_ROOT"] = cls.root
        cls.s9 = SourceFileLoader("s9_callname_mod",
                                  os.path.join(REPO, "bin", "s9.py")).load_module()
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_SESSION": "aaaa1111"}

    def setUp(self):
        m = self.s9
        self.docdir = os.path.join(m.VAULT, "sessions", "2026", "09")
        os.makedirs(self.docdir, exist_ok=True)
        for fn in os.listdir(self.docdir):
            os.remove(os.path.join(self.docdir, fn))
        if os.path.exists(m.CALL_PENDING):
            os.remove(m.CALL_PENDING)
        if os.path.exists(m.PEERS):
            os.remove(m.PEERS)

    def put_doc(self, ses_id="SES-20260908-001-2n7g", session="bbbb2222",
                machine="MAC-01", **extra):
        m = self.s9
        meta = {"id": ses_id, "type": "session", "title": f"세션 {session}@{machine}",
                "summary": "session", "status": "published", "user": "tester",
                "machine": machine, "session": session, "tags": ["session-log"],
                "created": "2026-09-08T10:00:00+09:00",
                "updated": "2026-09-08T10:00:00+09:00"}
        meta.update(extra)
        path = os.path.join(self.docdir, ses_id + ".md")
        m.write_doc(path, meta, "\n## Notes\n\n## History\n")
        return path

    def meta_of(self, path):
        return self.s9.read_doc(path)[0]

    # S1 ────────────────────────────────────────────────────────────────
    def test_name_from_the_prompt_head_lands_on_that_session_doc(self):
        """정상 — 표식의 이름이 그 이름표를 가진 문서의 call_name 이 된다."""
        path = self.put_doc(harness_session="bridge:session_MAC1")
        pair = self.s9.parse_cross_session(TAG + "\n맥에서 캡처 부탁합니다")
        self.assertEqual(pair, ("bridge:session_MAC1", "맥 리드"))
        self.s9.note_call_name(*pair)
        self.assertEqual(self.meta_of(path).get("call_name"), "맥 리드")

    # S2 ────────────────────────────────────────────────────────────────
    def test_own_label_is_read_from_the_transcript_not_invented(self):
        """원천 — 이름표는 하네스가 transcript 에 적어 둔 것만 읽는다."""
        m = self.s9
        tp = os.path.join(self.root, "t.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write('{"x":"see https://claude.ai/code/session_ME9 for this"}\n')
        self.assertEqual(m.harness_id_from_transcript(tp), "bridge:session_ME9")
        self.assertEqual(m.harness_id_from_transcript(
            os.path.join(self.root, "none.jsonl")), "")

        # 세션 로그를 적는 그 자리에서 제 문서에 적힌다 (프로세스를 더 띄우지 않는다)
        machine = m.current_machine()
        path = self.put_doc(ses_id="SES-20260908-002-2n7g", session="aaaa1111",
                            machine=machine)
        m.write_binding({"machine": machine, "session": "aaaa1111", "user": "tester",
                         "history": [], "ses_doc": "SES-20260908-002-2n7g",
                         "transcript_path": tp})
        out = subprocess.run([S9, "log", "시험 기동"], capture_output=True,
                             encoding="utf-8", errors="replace", env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.meta_of(path).get("harness_session"), "bridge:session_ME9")

    # S3 ────────────────────────────────────────────────────────────────
    def test_a_tag_quoted_in_the_body_is_not_evidence(self):
        """실패 경로 — 본문에 인용된 표식으로는 아무 이름도 적지 않는다."""
        path = self.put_doc(harness_session="bridge:session_MAC1")
        quoted = "다음 표식을 보세요: " + TAG + " 이런 모양입니다"
        self.assertIsNone(self.s9.parse_cross_session(quoted))
        self.assertNotIn("call_name", self.meta_of(path))

    # S4 ────────────────────────────────────────────────────────────────
    def test_an_unmatched_name_waits_instead_of_being_thrown_away(self):
        """경계 — 짝지을 문서가 없으면 대기했다가 이름표가 오면 채운다."""
        m = self.s9
        self.assertEqual(m.note_call_name("bridge:session_MAC1", "맥 리드"), "")
        self.assertEqual(m.read_call_pending()["bridge:session_MAC1"]["name"], "맥 리드")

        path = self.put_doc(harness_session="bridge:session_MAC1")
        self.assertEqual(m.resolve_call_names(), ["SES-20260908-001-2n7g"])
        self.assertEqual(self.meta_of(path).get("call_name"), "맥 리드")
        self.assertEqual(m.read_call_pending(), {}, "채우고도 대기에 남아 있다")

    # S5 ────────────────────────────────────────────────────────────────
    def test_peer_ls_shows_the_document_and_the_document_wins(self):
        """peer 와의 관계 — 문서가 사실, peers.json 은 이 머신의 목록이다."""
        self.put_doc(harness_session="bridge:session_MAC1", call_name="맥 리드")
        self.s9.write_peers({"맥 리드": {"machine": "손으로-적은-머신",
                                         "os": "macOS", "note": "Safari 검증"}})
        out = subprocess.run([S9, "peer", "ls"], capture_output=True,
                             encoding="utf-8", errors="replace", env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("맥 리드", out.stdout)
        self.assertIn("machine=MAC-01", out.stdout, "문서의 machine 이 아니다")
        self.assertNotIn("손으로-적은-머신", out.stdout)
        self.assertIn("Safari 검증", out.stdout, "손으로 적은 note 가 사라졌다")

    # S6 ────────────────────────────────────────────────────────────────
    def test_a_name_that_would_break_the_front_matter_is_refused(self):
        """경계 — 개행·제어문자·빈 이름은 적지 않는다."""
        m = self.s9
        path = self.put_doc(harness_session="bridge:session_MAC1")
        for bad in ("", "   ", "두\n줄", "제어\x07문자"):
            self.assertEqual(m.clean_call_name(bad), "", f"거부하지 않았다: {bad!r}")
            self.assertEqual(m.note_call_name("bridge:session_MAC1", bad), "")
        self.assertNotIn("call_name", self.meta_of(path))
        self.assertIsNone(m.parse_cross_session(
            '<cross-session-message from="bridge:x" from-name="">'))

    # S7 ────────────────────────────────────────────────────────────────
    def test_an_ordinary_prompt_changes_nothing(self):
        """회귀 — 표식이 없는 보통 프롬프트는 이름을 만들지 않는다."""
        path = self.put_doc(harness_session="bridge:session_MAC1")
        self.assertIsNone(self.s9.parse_cross_session("맥에서 캡처 부탁합니다"))
        self.assertEqual(self.s9.call_names_from_vault(), {})
        self.assertNotIn("call_name", self.meta_of(path))

    # S8 ────────────────────────────────────────────────────────────────
    def test_it_can_be_rebuilt_from_what_the_vault_already_holds(self):
        """재생성 — state/ 의 대기는 파생물이고 원천은 문서 History 다."""
        m = self.s9
        path = self.put_doc(harness_session="bridge:session_MAC1")
        other = self.put_doc(ses_id="SES-20260908-003-62x6", session="cccc3333",
                             machine="DESK-01")
        # History 줄은 제목을 40자로 자르므로 표식이 통째로 남지 않는다 — 원문을
        # 보존하는 요청 문서 본문이 원천이고, 거기서는 표식이 줄머리에 선다.
        reqdir = os.path.join(m.VAULT, "requests", "2026", "09")
        os.makedirs(reqdir, exist_ok=True)
        with open(os.path.join(reqdir, "REQ-20260908-001-62x6.md"), "w",
                  encoding="utf-8") as f:
            f.write(f"---\nid: REQ-20260908-001-62x6\ntype: request\n---\n\n"
                    f"## Original\n{TAG}\n맥에서 캡처 부탁합니다\n\n"
                    f"인용된 것은 근거가 아니다: {TAG} 이런 모양\n")
        meta, body = m.read_doc(other)
        m.write_doc(other, meta, body + "- 2026-09-08T10:05:00+09:00 prompt "
                    "REQ-20260908-001-62x6 기록: 맥에서 캡처 (by t)\n")
        tagged, named = m.sync_call_names()
        self.assertEqual(named, 1, f"History 에서 못 읽었다 (이름표 {tagged}건)")
        self.assertEqual(self.meta_of(path).get("call_name"), "맥 리드")
        self.assertEqual(m.call_names_from_vault()["맥 리드"]["machine"], "MAC-01")


if __name__ == "__main__":
    unittest.main()
