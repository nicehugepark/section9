"""출처(origin)는 사람 입구마다 붙고, 틀리면 바로잡을 수 있다 (REQ-20260909-109).

2026-09-09 21:19 주인이 대시보드 채팅으로 「미묘하게 … 계속 거슬린다」고 지시했다.
분류기가 그것을 물음으로 갈라 QST 를 세웠는데 origin=agent·origin_actor=lead 로
적혔다 — 채팅→요청 갈래는 `--origin human` 을 넘기고 채팅→물음 갈래만 안 넘겨,
cmd_new 가 「세션 안이니 agent」로 판정한 것이다. 리드가 그 물음을 요청으로 세우니
「만든 사람 리드」가 됐고, Jira 내보내기 검사(origin=human 만)가 티켓을 안 냈다.
주인: 「이건 명백하게 내가 지시한것 같은데 타치코마가 만든걸로 나오네.」

계약 둘.
  O1 세션 안에서 `--origin human` 을 주면 human 이고 origin_actor 가 없다 — 물음
     경로가 이것을 넘긴다(test_chat_question_ingest 가 실제 경로를 잰다).
  O2 `s9 set <id> --origin human` 이 잘못 적힌 출처를 바로잡고 origin_actor 를
     걷으며 History 에 한 줄 남긴다. 멱등이고, 값은 human·agent 뿐이다.

실행: python3 tests/ origin_set
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class OriginSet(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9-origin-")
        self._prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE", "S9_SESSION", "S9_USER")}
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        os.environ["S9_SESSION"] = "deadbeef"      # 세션 안 — 명시가 없으면 agent 로 판정되는 조건
        spec = importlib.util.spec_from_loader(
            "s9_origin", importlib.machinery.SourceFileLoader("s9_origin", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_init(types.SimpleNamespace())

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def _new(self, origin=None):
        # test_here_watch 의 new_request 와 같은 필드 묶음 — cmd_new 가 읽는 이름 그대로
        args = types.SimpleNamespace(
            doc_type="request", title="출처 시험", summary="s", goal="g", status="open", size="S",
            priority=None, user="tester", assignee=None, tag_list=[], parent=None, derived_from=None,
            relates=None, why="", ref_doc=None, ref_link=None, ref_file=None, needs_os="",
            from_chat="", project=None, project_tag=None, body="b", body_file=None,
            origin=origin, agent="", origin_req=None, jira_key=None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.m.cmd_new(args)
        return buf.getvalue().split()[0]

    def _meta(self, rid):
        return self.m.read_doc(self.m.find_path(rid))[0]

    def test_o1_explicit_human_wins_inside_a_session(self):
        rid = self._new(origin="human")
        meta = self._meta(rid)
        self.assertEqual(meta.get("origin"), "human")
        self.assertFalse(meta.get("origin_actor"), "human 인데 origin_actor 가 남았다")

    def test_o1b_without_the_flag_a_session_writes_agent(self):
        """이것이 사고의 조건이다 — 명시가 없으면 세션 안은 agent 다."""
        rid = self._new(origin=None)
        self.assertEqual(self._meta(rid).get("origin"), "agent")

    def test_o2_set_origin_human_fixes_a_wrong_record(self):
        rid = self._new(origin=None)
        self.assertEqual(self._meta(rid).get("origin"), "agent")
        res = self.m.do_set(rid, {"origin": "human"}, actor="tester")
        self.assertIn("origin", res.get("changed", []))
        meta, body = self.m.read_doc(self.m.find_path(rid))
        self.assertEqual(meta.get("origin"), "human")
        self.assertNotIn("origin_actor", meta, "바로잡았는데 origin_actor 가 남았다")
        self.assertIn("origin: agent -> human", body, "History 에 남지 않았다")

    def test_o2b_it_is_idempotent(self):
        rid = self._new(origin="human")
        res = self.m.do_set(rid, {"origin": "human"}, actor="tester")
        self.assertNotIn("origin", res.get("changed", []), "바뀐 것이 없는데 바뀌었다고 한다")

    def test_o2c_only_human_or_agent(self):
        rid = self._new(origin=None)
        with self.assertRaises(ValueError):
            self.m.do_set(rid, {"origin": "derived"}, actor="tester")
        r = subprocess.run([S9, "set", rid, "--origin", "bogus"], capture_output=True,
                           encoding="utf-8", env=dict(os.environ))
        self.assertNotEqual(r.returncode, 0, "argparse 가 엉뚱한 값을 받았다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
