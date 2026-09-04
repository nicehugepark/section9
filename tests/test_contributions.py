"""actor 규격·기여 이력 테스트 (REQ-20260825-088-62x6).

설계 근거: DOC-20260825-003-62x6.
문서에 "누가 참여했다"만 남고 "어느 항목을 어디까지"는 노트 본문에 흩어져 있어,
이어받는 세션이 매번 재구성해야 했다. contributions 는 그 재구성을 없앤다.

격리: S9_ROOT=mktemp — 라이브 vault를 건드리지 않는다.
실행: python3 tests/ contributions
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

_spec = importlib.util.spec_from_loader(
    "s9mod", importlib.machinery.SourceFileLoader("s9mod", S9))
s9 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s9)


class ActorSpecTest(unittest.TestCase):
    """A1~A3: --agent 값을 lead/sub/wf/worker 규격으로 좁히되 기존 값은 관대하게."""

    def test_actor_spec_test(self):
        """A1~A3: --agent 값을 lead/sub/wf/worker 규격으로 좁히되 기존 값은 관대하게."""
        with self.subTest("a1_spec_forms_pass_through"):
            for v in ("lead:claude-opus-5", "sub:designer:a1fefd40",
                      "wf:review:9c0f1122", "worker:auto-resume"):
                self.assertEqual(s9.normalize_actor(v), v)
        with self.subTest("a2_legacy_is_read_leniently"):
            self.assertEqual(s9.normalize_actor("subagent"), "sub:subagent")
            self.assertEqual(s9.normalize_actor("designer"), "sub:designer")
            self.assertEqual(s9.normalize_actor("lead:claude-fable-5"),
                             "lead:claude-fable-5")
            self.assertEqual(s9.normalize_actor(""), "")
            self.assertEqual(s9.normalize_actor(None), "")
        with self.subTest("a3_boundaries_never_raise"):
            # 콜론 과다·공백·유니코드·과길이 — 어떤 입력도 한 줄 문자열을 낸다.
            for v in ("sub:a:b:c:d", "  worker : 손으로 적음  ", "리드", "x" * 500):
                out = s9.normalize_actor(v)
                self.assertIsInstance(out, str)
                self.assertNotIn("\n", out)
                self.assertLessEqual(len(out), s9.ACTOR_MAX)
        with self.subTest("a3_kind_extraction"):
            self.assertEqual(s9.actor_kind("sub:designer:a1fefd40"), "sub")
            self.assertEqual(s9.actor_kind("lead:claude-opus-5"), "lead")
            self.assertEqual(s9.actor_kind("wf:x:y"), "wf")
            self.assertEqual(s9.actor_kind("worker:auto-resume"), "worker")
            self.assertEqual(s9.actor_kind("garbage"), "")

class ContribAccumTest(unittest.TestCase):
    """A4~A8: 문서 프론트매터 contributions 누적 규칙 (단일 쓰기 경로)."""

    def test_contrib_accum_test(self):
        """A4~A8: 문서 프론트매터 contributions 누적 규칙 (단일 쓰기 경로)."""
        with self.subTest("a4_one_note_one_entry"):
            meta = {}
            s9.record_contribution(meta, "sub:designer:aaaa1111", item="N1 스킨",
                                   result="done", transcript="/tmp/a.out",
                                   ts="2026-08-25T21:00:00+09:00")
            c = meta["contributions"]
            self.assertEqual(len(c), 1)
            for k in ("actor", "item", "started", "ended", "result", "transcript"):
                self.assertIn(k, c[0])
            self.assertEqual(c[0]["result"], "done")
        with self.subTest("a5_same_actor_and_item_merges"):
            meta = {}
            s9.record_contribution(meta, "sub:designer:aaaa1111", item="N1",
                                   result="running", ts="2026-08-25T21:00:00+09:00")
            s9.record_contribution(meta, "sub:designer:aaaa1111", item="N1",
                                   result="done", ts="2026-08-25T21:10:00+09:00")
            c = meta["contributions"]
            self.assertEqual(len(c), 1, "같은 actor+item 연속 노트는 병합돼야 한다")
            self.assertEqual(c[0]["started"], "2026-08-25T21:00:00+09:00")
            self.assertEqual(c[0]["ended"], "2026-08-25T21:10:00+09:00")
            self.assertEqual(c[0]["result"], "done")
        with self.subTest("a5_different_item_appends"):
            meta = {}
            s9.record_contribution(meta, "sub:designer:aaaa1111", item="N1",
                                   ts="2026-08-25T21:00:00+09:00")
            s9.record_contribution(meta, "sub:designer:aaaa1111", item="N2",
                                   ts="2026-08-25T21:05:00+09:00")
            self.assertEqual(len(meta["contributions"]), 2)
        with self.subTest("a6_item_defaults_to_first_line"):
            item = s9.item_from_text("## 구현 완료\n\n두 번째 줄은 무시한다")
            self.assertTrue(item)
            self.assertNotIn("\n", item)
            self.assertIn("구현 완료", item)
            self.assertEqual(s9.item_from_text(""), "")
        with self.subTest("a7_open_running_entry_is_closed"):
            meta = {}
            s9.record_contribution(meta, "sub:qa:bbbb2222", item="테스트 작성",
                                   result="running", ts="2026-08-25T21:00:00+09:00")
            s9.record_contribution(meta, "sub:qa:bbbb2222", item="회귀 확인",
                                   result="done", ts="2026-08-25T21:20:00+09:00")
            c = meta["contributions"]
            self.assertEqual(len(c), 2)
            self.assertEqual(c[0]["result"], "done",
                             "선행 running 항목이 닫히지 않았다")
            self.assertEqual(c[0]["ended"], "2026-08-25T21:20:00+09:00")
        with self.subTest("a8_cap"):
            meta = {}
            for i in range(s9.CONTRIB_MAX + 5):
                s9.record_contribution(meta, "sub:x:%04d" % i, item="i%d" % i,
                                       ts="2026-08-25T21:00:00+09:00")
            self.assertEqual(len(meta["contributions"]), s9.CONTRIB_MAX)
            self.assertEqual(meta["contributions"][-1]["item"],
                             "i%d" % (s9.CONTRIB_MAX + 4))

class NoteIntegrationTest(unittest.TestCase):
    """A4/A6 종단: 실제 `s9 note` 실행이 문서에 contributions 를 남기는가."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9contrib")
        self.env = {**os.environ, "S9_ROOT": self.root,
                    "S9_SESSION": "deadbeef", "S9_AUDIT": "off"}
        self.env.pop("S9_PORT", None)
        self.s9run("init")
        out = self.s9run("new", "request", "--title", "기여 이력 테스트",
                       "--summary", "s", "--body", "b")
        self.doc = out.stdout.split()[0].strip()

    def s9run(self, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def doc_meta(self):
        r = self.s9run("show", self.doc, "--meta")
        return s9.fm_parse(r.stdout if r.stdout.startswith("---")
                           else "---\n" + r.stdout + "\n---\n")[0]

    def test_note_records_contribution(self):
        self.s9run("note", self.doc, "N1 파서 구현 완료", "--label", "response",
                 "--agent", "designer", "--item", "N1")
        meta = self.doc_meta()
        c = meta.get("contributions")
        self.assertTrue(c, "note 가 contributions 를 남기지 않았다")
        self.assertEqual(c[0]["actor"], "sub:designer")
        self.assertEqual(c[0]["item"], "N1")

    def test_note_without_item_uses_first_line(self):
        self.s9run("note", self.doc, "첫 줄이 항목이 된다\n둘째 줄", "--agent",
                 "sub:qa:cccc3333")
        c = self.doc_meta().get("contributions")
        self.assertTrue(c)
        self.assertIn("첫 줄이 항목이 된다", c[0]["item"])

    def test_note_without_agent_records_nothing(self):
        """actor 없는 노트는 기여로 세지 않는다 — 사람이 남긴 메모까지
        에이전트 이력으로 승격되면 헬스체크가 오염된다."""
        self.s9run("note", self.doc, "사람이 손으로 남긴 메모")
        self.assertFalse(self.doc_meta().get("contributions"))


class AgentHookTest(unittest.TestCase):
    """A9~A10: PostToolUse(Agent) 훅이 클레임·transcript·running 기여를 자동 등록."""

    def setUp(self):
        path = os.path.join(HERE, "..", "bin", "s9-audit-agent")
        if not os.path.exists(path):
            self.skipTest("s9-audit-agent 미구현")
        spec = importlib.util.spec_from_loader(
            "s9agenthook", importlib.machinery.SourceFileLoader(
                "s9agenthook", path))
        self.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hook)

    def test_a9_extracts_agent_id_and_output_file(self):
        resp = ("Agent started.\nagentId: af69449b\n"
                "output_file: /tmp/tasks/af69449b.output\n")
        self.assertEqual(self.hook.parse_agent_result(resp),
                         ("af69449b", "/tmp/tasks/af69449b.output"))
        # dict 형태 응답도 받는다 (하네스 판올림 대비)
        self.assertEqual(
            self.hook.parse_agent_result(
                {"agentId": "af69449b",
                 "output_file": "/tmp/tasks/af69449b.output"}),
            ("af69449b", "/tmp/tasks/af69449b.output"))

    def test_a9_actor_is_spec_form(self):
        self.assertEqual(
            self.hook.actor_for("designer", "af69449b1234"),
            "sub:designer:af69449b")

    def test_a10_broken_payload_is_silent(self):
        self.assertEqual(self.hook.parse_agent_result(None), ("", ""))
        self.assertEqual(self.hook.parse_agent_result("무관한 텍스트"), ("", ""))

    def test_a10_hook_exits_zero_on_garbage_stdin(self):
        r = subprocess.run([os.path.join(HERE, "..", "bin", "s9-audit-agent")],
                           input="not json", capture_output=True, text=True,
                           timeout=30, env={**os.environ, "S9_AUDIT": "off"})
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
