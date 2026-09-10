"""워처가 이 판의 open 요청을 집는다 (REQ-20260909-012).

다른 기계가 needs_os 로 남긴 요청은 그 판의 대시보드 워처가 스스로 집는다 — 담당자의
auto_resume 이 켜져 있고, 유예가 지났고, 아무도 클레임하지 않았을 때만.

실행: python3 tests/ here_watch
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


class HereWatch(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_SYNC", "S9_USER", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9here-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_SYNC"] = "off"
        for k in ("S9_USER", "S9_SESSION"):
            os.environ.pop(k, None)
        name = "s9here_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.cmd_init(type("A", (), {})())
        self.m.do_user_add("hong", role="admin")
        self.m.do_project_add("pay", name="결제", summary="", actor="hong")
        self.spawned = []

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def new_request(self, needs_os="macOS", needs_machine=""):
        import contextlib, io, types
        args = types.SimpleNamespace(
            doc_type="request", title="맥에서 볼 것", summary="s", goal="g", status="open", size="S",
            priority=None, user="hong", assignee=None, tag_list=[], parent=None, derived_from=None,
            relates=None, why="", ref_doc=None, ref_link=None, ref_file=None, needs_os=needs_os,
            needs_machine=needs_machine,
            from_chat="", project="pay", project_tag=None, body="b", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def tick(self, platform="macOS", grace=0, machine="thisbox", user="hong"):
        return self.m.here_watch_tick(now=time.time() + 1, grace=grace, platform=platform,
                                      machine=machine, user=user,
                                      _spawn=lambda did, meta: self.spawned.append(did) or True)

    def test_h1_the_watcher_picks_and_spawns(self):
        self.m.do_user_config_set("hong", "auto_resume", "on")
        rid = self.new_request()
        self.assertEqual(self.tick(), [rid])
        meta, body = self.m.read_doc(self.m.find_path(rid))
        self.assertEqual(meta["status"], "in-progress")
        self.assertIn("[auto]", body)
        self.assertIn("워처가 집었다", body)
        self.assertEqual(self.spawned, [rid])

    def test_h2_other_platform_off_switch_grace_and_claimed_are_skipped(self):
        rid = self.new_request()
        self.assertEqual(self.tick(), [], "auto_resume 이 꺼졌는데 집었다")
        self.m.do_user_config_set("hong", "auto_resume", "on")
        self.assertEqual(self.tick(platform="Linux"), [], "다른 판의 요청을 집었다")
        self.assertEqual(self.tick(grace=3600), [], "유예 안인데 집었다")
        real = self.m.rework_claimed
        self.m.rework_claimed = lambda rid_, win=120: True
        try:
            self.assertEqual(self.tick(), [], "클레임된 것을 집었다")
        finally:
            self.m.rework_claimed = real
        self.assertEqual(self.m.read_doc(self.m.find_path(rid))[0]["status"], "open")

    def test_h4_the_watcher_picks_only_on_the_assigned_machine(self):
        """담당 머신(needs_machine)이 이 머신이고 담당자도 맞을 때만 집는다 (REQ-20260910-016).

        머신이 다르면 몇 번을 돌아도 영영 집지 않는다 — 시한도 자동 해제도
        다른 머신으로의 폴백도 없다."""
        self.m.do_user_config_set("hong", "auto_resume", "on")
        self.m.write_peers({"저 머신": {"machine": "thatbox"}})
        rid = self.new_request(needs_os="", needs_machine="저 머신")
        self.assertEqual(self.m.read_doc(self.m.find_path(rid))[0]["needs_machine"], "thatbox")
        for _ in range(3):
            self.assertEqual(self.tick(), [], "담당 머신이 아닌데 집었다")
        self.assertEqual(self.m.read_doc(self.m.find_path(rid))[0]["status"], "open")
        self.assertEqual(self.tick(machine="thatbox", user="someone"), [],
                         "담당자가 다른데 집었다")
        self.assertEqual(self.tick(machine="thatbox"), [rid])
        self.assertEqual(self.spawned, [rid])
        meta, body = self.m.read_doc(self.m.find_path(rid))
        self.assertEqual(meta["status"], "in-progress")
        # 화면·기록의 낱말은 「컴퓨터」다 (REQ-20260910-017 용어 판정)
        self.assertIn("담당 컴퓨터", body)

    def test_h5_the_watcher_picks_the_unassigned_one_anywhere(self):
        """담당 컴퓨터도 판도 안 적힌 요청은 담당자가 같은 아무 컴퓨터나 집는다
        (REQ-20260910-009). 남는 History 한 줄은 담당 컴퓨터로 지정된 경우와
        구분돼야 한다 — 왜 여기서 돌았는지가 문서에만 남는다."""
        self.m.do_user_config_set("hong", "auto_resume", "on")
        rid = self.new_request(needs_os="", needs_machine="")
        self.assertEqual(self.tick(platform="Linux", machine="anybox"), [rid])
        meta, body = self.m.read_doc(self.m.find_path(rid))
        self.assertEqual(meta["status"], "in-progress")
        self.assertIn("담당 컴퓨터가 정해지지 않은 요청", body)
        self.assertNotIn("담당 컴퓨터로 지정된 요청", body)
        self.assertEqual(self.spawned, [rid])

    def test_h7_a_request_held_by_another_machine_is_left_alone(self):
        """다른 컴퓨터가 쥔(신선한 리스) 요청은 전이도 스폰도 하지 않는다
        (REQ-20260910-009). 담당 없는 요청이 여러 컴퓨터의 목록에 함께 들면서
        생긴 겹침을 문서 리스가 막는다 — 전이 자체가 리스를 보지 않기 때문에
        워처가 먼저 본다."""
        self.m.do_user_config_set("hong", "auto_resume", "on")
        rid = self.new_request(needs_os="", needs_machine="")
        path = self.m.find_path(rid)
        meta, body = self.m.read_doc(path)
        now = self.m.now_iso()
        meta["lease"] = {"user": "hong", "machine": "thatbox", "session": "aaaa1111",
                         "since": now, "renewed": now}
        self.m.write_doc(path, meta, body)
        self.m.rebuild_index(quiet=True)
        self.assertEqual(self.tick(platform="Linux", machine="anybox"), [])
        self.assertEqual(self.m.read_doc(path)[0]["status"], "open")
        self.assertEqual(self.spawned, [])

    def test_h6_the_unassigned_one_is_not_picked_for_someone_else(self):
        """담당자가 다르면 집지 않는다 — 같은 저장소를 쓰는 남의 요청이다."""
        self.m.do_user_config_set("hong", "auto_resume", "on")
        rid = self.new_request(needs_os="", needs_machine="")
        self.assertEqual(self.tick(platform="Linux", machine="anybox", user="someone"), [])
        self.assertEqual(self.m.read_doc(self.m.find_path(rid))[0]["status"], "open")

    def test_h3_in_progress_ones_are_not_the_here_ticks_business(self):
        self.m.do_user_config_set("hong", "auto_resume", "on")
        rid = self.new_request()
        self.m.do_transition(rid, "in-progress", note="사람이 집음", user="hong")
        self.assertEqual(self.tick(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
