"""담당자 변경은 한 경로를 지난다 (REQ-20260902-019).

`s9 assign <id> <user>` 와 `POST /api/assign` 이 do_assign 하나를 부른다 —
담당자(user) 갱신 + 생성자 불변 + History 한 줄 + 옛 자리의 클레임·리스 회수.

실행: python3 tests/ assign
"""
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
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


class Assign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9assign-")
        cls.base = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER"):
            cls.base.pop(k, None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.base)
        for u in ("alice", "bob", "carol", "root", "eve"):
            subprocess.run([S9, "user", "add", u], capture_output=True,
                           env=cls.base, stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "role", "root", "admin"], capture_output=True,
                       env={**cls.base, "S9_USER": "root"}, stdin=subprocess.DEVNULL)
        subprocess.run([S9, "user", "role", "eve", "viewer"], capture_output=True,
                       env={**cls.base, "S9_USER": "root"}, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "testbox"
        spec = importlib.util.spec_from_loader(
            "s9_assign", importlib.machinery.SourceFileLoader("s9_assign", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def cli(self, *argv, user=None, expect=0):
        env = dict(self.base)
        if user:
            env["S9_USER"] = user
        r = subprocess.run([S9, *argv], capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL)
        if expect is not None:
            self.assertEqual(r.returncode, expect, r.stdout + r.stderr)
        return r

    def new(self, user="alice"):
        r = self.cli("new", "request", "--title", "t", "--summary", "s", "--size", "S",
                     "--goal", "g", "--body", "b", "--origin", "human", "--user", user)
        return r.stdout.split()[0]

    def meta(self, rid):
        return self.m.read_doc(self.m.locate(rid))

    # A1. 정상
    def test_assign(self):
        """Assign 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("a1_assign_changes_user_keeps_creator_writes_history"):
                rid = self.new("alice")
                r = self.cli("assign", rid, "bob", "--why", "휴가", user="alice")
                self.assertIn("alice → bob", r.stdout)
                meta, body = self.meta(rid)
                self.assertEqual(meta["user"], "bob")
                self.assertEqual(meta["creator"], "alice")
                self.assertIn("assignee: alice -> bob (by alice) — 휴가", body)
                row = [x for x in self.m.load_catalog() if x["id"] == rid][0]
                self.assertEqual(row["user"], "bob")

            # A2. 권한
        with self.subTest("a2_permission"):
                rid = self.new("alice")
                r = self.cli("assign", rid, "bob", user="carol", expect=None)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("권한 없음", r.stdout + r.stderr)
                self.assertEqual(self.meta(rid)[0]["user"], "alice")
                self.cli("assign", rid, "bob", user="root")           # admin
                self.assertEqual(self.meta(rid)[0]["user"], "bob")
                self.cli("assign", rid, "carol", user="bob")          # 현 담당자
                self.assertEqual(self.meta(rid)[0]["user"], "carol")
                self.cli("assign", rid, "bob", user="alice")          # 생성자
                self.assertEqual(self.meta(rid)[0]["user"], "bob")

            # A3. 거부·no-op
        with self.subTest("a3_refusals_and_noop"):
                rid = self.new("alice")
                for who, msg in (("nobody", "등록되지 않은"), ("eve", "관찰 계정")):
                    r = self.cli("assign", rid, who, user="alice", expect=None)
                    self.assertNotEqual(r.returncode, 0)
                    self.assertIn(msg, r.stdout + r.stderr)
                r = self.cli("assign", rid, "alice", user="alice")
                self.assertIn("그대로", r.stdout)
                self.cli("status", rid, "cancelled", "--note", "x", "--force", user="alice")
                r = self.cli("assign", rid, "bob", user="alice", expect=None)
                self.assertNotEqual(r.returncode, 0)

            # A4. 옛 자리의 클레임·리스 회수
        with self.subTest("a4_claims_and_lease_are_released"):
                rid = self.new("alice")
                self.cli("status", rid, "in-progress", "--note", "t", user="alice")
                os.makedirs(self.m.STATE, exist_ok=True)
                bp = os.path.join(self.m.STATE, "testbox__oldsess1.json")
                with open(bp, "w", encoding="utf-8") as f:
                    json.dump({"machine": "testbox", "session": "oldsess1", "user": "alice",
                               "history": [], "active_reqs": [rid]}, f)
                path = self.m.locate(rid)
                meta, body = self.m.read_doc(path)
                meta["lease"] = {"user": "alice", "machine": "testbox", "session": "oldsess1"}
                self.m.write_doc(path, meta, body)
                self.m.do_assign(rid, "bob", actor="alice", why="넘김")
                meta, _ = self.meta(rid)
                self.assertNotIn("lease", meta)
                with open(bp, encoding="utf-8") as f:
                    self.assertNotIn(rid, json.load(f).get("active_reqs") or [])

            # A5. 화면도 같은 경로
        with self.subTest("a5_api_uses_the_same_path"):
                with open(S9_SRC, encoding="utf-8") as f:
                    src = f.read()
                self.assertIn('parsed.path == "/api/assign"', src)
                self.assertIn('via="dashboard")', src.split('parsed.path == "/api/assign"', 1)[1][:600])
                rid = self.new("alice")
                res = self.m.do_assign(rid, "bob", actor="root", why="화면", via="dashboard")
                self.assertTrue(res["changed"])
                self.assertIn("(by root via dashboard) — 화면", self.meta(rid)[1])

            # A6. 맡는 사람은 그 프로젝트의 활성 멤버여야 한다 (REQ-20260902-064)
            #
            # 사용자 신고: "현재 프로젝트에 할당된 사용자가 2명 밖에 없는데 요청 담당자
            # 목록에는 프로젝트에 할당되지 않은 인원까지 표시된다." 화면은 이미 후보를
            # 좁혔지만(web/app/card.js assignPick) 서버가 안 막으면 CLI·API 로 그대로
            # 들어온다 — 화면이 뺀 것을 서버가 세워야 규칙이다.
        with self.subTest("a6_only_project_members_can_be_assigned"):
                self.cli("project", "add", "acme", "--name", "Acme", user="alice")
                self.cli("project", "member", "acme", "add", "bob", "--role",
                         "contributor", user="alice")
                r = self.cli("new", "request", "--title", "t", "--summary", "s",
                             "--size", "S", "--goal", "g", "--body", "b",
                             "--origin", "human", "--user", "alice",
                             "--project", "acme")
                rid = r.stdout.split()[0]
                # S2 실패: 미참여자는 거부되고 담당은 그대로다
                r = self.cli("assign", rid, "carol", user="alice", expect=None)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("활성 멤버가 아니라", r.stdout + r.stderr)
                self.assertEqual(self.meta(rid)[0]["user"], "alice")
                # S1 정상: 멤버는 맡는다
                self.cli("assign", rid, "bob", user="alice")
                self.assertEqual(self.meta(rid)[0]["user"], "bob")

            # A7. admin 우회는 「바꾸는 사람」 축이지 「맡는 사람」 축이 아니다 (S6)
        with self.subTest("a7_admin_may_move_it_but_not_onto_an_outsider"):
                self.cli("project", "add", "beta", "--name", "Beta", user="alice")
                self.cli("project", "member", "beta", "add", "bob", "--role",
                         "contributor", user="alice")
                r = self.cli("new", "request", "--title", "t", "--summary", "s",
                             "--size", "S", "--goal", "g", "--body", "b",
                             "--origin", "human", "--user", "bob", "--project", "beta")
                rid = r.stdout.split()[0]
                r = self.cli("assign", rid, "carol", user="root", expect=None)
                self.assertNotEqual(r.returncode, 0, "admin 이 비멤버를 앉혔다")
                self.assertEqual(self.meta(rid)[0]["user"], "bob")

            # A8b. 만료된 멤버는 담당을 맡지 못한다 (S4) — 활성만 멤버다
        with self.subTest("a8b_expired_member_cannot_be_assigned"):
                self.cli("project", "add", "gamma", "--name", "Gamma", user="alice")
                self.cli("project", "member", "gamma", "add", "bob", "--role",
                         "contributor", user="alice")
                self.cli("project", "member", "gamma", "add", "carol", "--role",
                         "contributor", "--until", "2000-01-01", user="alice")
                r = self.cli("new", "request", "--title", "t", "--summary", "s",
                             "--size", "S", "--goal", "g", "--body", "b",
                             "--origin", "human", "--user", "bob", "--project", "gamma")
                rid = r.stdout.split()[0]
                r = self.cli("assign", rid, "carol", user="bob", expect=None)
                self.assertNotEqual(r.returncode, 0, "만료 멤버가 담당을 맡았다")
                self.assertEqual(self.meta(rid)[0]["user"], "bob")

            # A8. 미등록 프로젝트는 강제하지 않는다 — 정책 부재는 금지가 아니다 (S3)
        with self.subTest("a8_unregistered_project_is_not_enforced"):
            r = self.cli("new", "request", "--title", "t", "--summary", "s",
                         "--size", "S", "--goal", "g", "--body", "b",
                         "--origin", "human", "--user", "alice",
                         "--project", "nowhere")
            rid = r.stdout.split()[0]
            self.cli("assign", rid, "carol", user="alice")
            self.assertEqual(self.meta(rid)[0]["user"], "carol")


class TheMachineGoesWithTheAssignee(unittest.TestCase):
    """담당자를 바꾸면 담당 컴퓨터도 함께 간다 (REQ-20260911-007-62x6).

    주인 물음 2026-09-11 12:31: 「담당자를 바꾸게 되면 어떻게 되는거지? … 아니면
    담당자를 바꾸었는데도, 담당 머신은 내 머신으로 되는건가?」 — 그때 답은
    후자였다. 요청은 세운 컴퓨터에 못박히는데(REQ-20260911-004-2n7g) 그 못이
    그대로 남아, 넘겨받은 사람이 안 쓰는 컴퓨터에 요청이 갇혔다: 집는 규칙은
    담당 컴퓨터와 담당자를 **둘 다** 보므로 그 조합을 만족하는 세션이 세상에
    없어진다.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9asgm-")
        cls.base = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "alice-pc"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER"):
            cls.base.pop(k, None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.base)
        for u in ("alice", "bob", "dave"):
            subprocess.run([S9, "user", "add", u], capture_output=True,
                           env=cls.base, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = cls.root
        os.environ["S9_MACHINE"] = "alice-pc"
        spec = importlib.util.spec_from_loader(
            "s9_asgm", importlib.machinery.SourceFileLoader("s9_asgm", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        # bob 은 두 컴퓨터를 썼고 bob-new 가 더 나중이다. dave 는 쓴 적이 없다.
        cls._seen("bob", [("bob-old", "2026-09-01T10:00:00+09:00"),
                          ("bob-new", "2026-09-10T22:00:00+09:00")])
        cls._seen("alice", [("alice-pc", "2026-09-11T09:00:00+09:00")])

    @classmethod
    def _seen(cls, user, pairs):
        pp = os.path.join(cls.root, "users", user, "profile.md")
        meta, body = cls.m.read_doc(pp)
        meta["machine_accounts"] = [
            {"machine": mv, "os": "Linux", "account": user,
             "first": ts, "last": ts} for mv, ts in pairs]
        cls.m.write_doc(pp, meta, body)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        os.environ.pop("S9_MACHINE", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def cli(self, *argv, user=None, expect=0):
        env = dict(self.base)
        if user:
            env["S9_USER"] = user
        r = subprocess.run([S9, *argv], capture_output=True, text=True, env=env,
                           stdin=subprocess.DEVNULL)
        if expect is not None:
            self.assertEqual(r.returncode, expect, r.stdout + r.stderr)
        return r

    def new(self, user="alice", *extra):
        r = self.cli("new", "request", "--title", "t", "--summary", "s", "--size", "S",
                     "--goal", "g", "--body", "b", "--origin", "human",
                     "--user", user, *extra)
        return r.stdout.split()[0]

    def meta(self, rid):
        return self.m.read_doc(self.m.locate(rid))[0]

    def test_a1_the_nail_moves_to_the_new_assignees_last_machine(self):
        rid = self.new("alice")
        self.assertEqual("alice-pc", self.meta(rid).get("needs_machine"),
                         "세운 컴퓨터에 못이 안 박혔다 — 전제가 무너졌다")
        self.cli("assign", rid, "bob", user="alice")
        self.assertEqual("bob-new", self.meta(rid).get("needs_machine"),
                         "담당자만 바뀌고 못은 옛 컴퓨터에 남았다 — 아무도 못 집는다")

    def test_a2_no_machine_of_their_own_pulls_the_nail(self):
        """쓴 컴퓨터가 없으면 못을 뽑는다 — 아무도 못 집는 자리에 두지 않는다."""
        rid = self.new("alice")
        self.cli("assign", rid, "dave", user="alice")
        self.assertEqual("", self.meta(rid).get("needs_machine") or "",
                         "쓴 적 없는 사람의 자리에 못을 남겼다")

    def test_a3_a_machine_they_already_use_stays(self):
        rid = self.new("alice")
        # 못을 직접 박는다 — `do_set` 은 **지금 담당자**가 아는 컴퓨터만 받으므로
        # (alice 는 bob-old 를 모른다) 여기서는 그 검사를 지나지 않는다.
        # 재는 것은 do_assign 의 판정이지 do_set 의 검사가 아니다.
        path = self.m.locate(rid)
        meta, body = self.m.read_doc(path)
        meta["needs_machine"] = "bob-old"
        self.m.write_doc(path, meta, body)
        self.cli("assign", rid, "bob", user="alice")
        self.assertEqual("bob-old", self.meta(rid).get("needs_machine"),
                         "이미 그가 쓰는 컴퓨터인데 옮겼다 — 옮길 이유가 없다")

    def test_a4_a_request_with_no_nail_gets_none(self):
        """못이 없던 요청에는 새로 박지 않는다 — 넘기는 일이 범위를 좁힐 까닭이 없다."""
        rid = self.new("alice", "--any-machine")
        self.assertEqual("", self.meta(rid).get("needs_machine") or "")
        self.cli("assign", rid, "bob", user="alice")
        self.assertEqual("", self.meta(rid).get("needs_machine") or "")

    def test_a5_the_history_says_what_moved_and_why(self):
        rid = self.new("alice")
        self.cli("assign", rid, "bob", user="alice")
        body = self.m.read_doc(self.m.locate(rid))[1]
        self.assertIn("needs_machine: alice-pc -> bob-new", body)
        self.assertIn("담당자가 바뀌어", body, "왜 옮겼는지가 없다")

    def test_r1_the_rest_of_the_handover_is_unchanged(self):
        rid = self.new("alice")
        self.m.do_set(rid, {"needs_machine": "alice-pc"}, actor="alice")
        self.cli("assign", rid, "bob", user="alice")
        meta = self.meta(rid)
        self.assertEqual("bob", meta["user"])
        self.assertEqual("alice", meta.get("creator"))
        self.assertNotIn("lease", meta, "옛 자리의 실행권이 남았다")


if __name__ == "__main__":
    unittest.main()
