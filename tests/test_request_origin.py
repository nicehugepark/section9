"""누가 만들었나 — 사람인가, 에이전트인가, 누구의 요청을 처리하다 나왔나 (REQ-20260902-018).

`user` 는 담당자다(코드 전반이 그 뜻으로 읽는다, DOC-20260902-001 D2). 생성 시
확정되는 넷 creator/origin/origin_actor/origin_req 를 따로 적는다. 사람 입구
(훅·채팅·화면)만 `--origin human` 을 붙이고 나머지는 cmd_new 한 곳이 가른다.

실행: python3 tests/ request_origin
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


class RequestOrigin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9origin-")
        cls.base = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_JOB_REQ", "S9_USER"):
            cls.base.pop(k, None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.base)
        for u in ("alice", "bob"):
            subprocess.run([S9, "user", "add", u], capture_output=True,
                           env=cls.base, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_origin", importlib.machinery.SourceFileLoader("s9_origin", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def new(self, *extra, env=None):
        e = {**self.base, **(env or {})}
        r = subprocess.run([S9, "new", "request", "--title", "t", "--summary", "s",
                            "--size", "S", "--goal", "g", "--body", "b", *extra],
                           capture_output=True, text=True, env=e,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rid = r.stdout.split()[0]
        return rid, self.m.read_doc(self.m.locate(rid))[0]

    # O1. 사람 입구
    def test_request_origin(self):
        """RequestOrigin 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("o1_human_entrance"):
                rid, meta = self.new("--origin", "human", "--user", "alice",
                                     env={"S9_SESSION": "leadsess"})
                self.assertEqual(meta["origin"], "human")
                self.assertEqual(meta["creator"], "alice")
                self.assertEqual(meta["user"], "alice")
                self.assertEqual(meta.get("origin_actor", ""), "")   # 빈 값은 키 생략
                # 훅·채팅 입구가 그 플래그를 붙인다
                with open(os.path.join(HERE, "..", "bin", "s9-audit-prompt"), encoding="utf-8") as f:
                    self.assertIn('"--origin", "human"', f.read())
                with open(S9, encoding="utf-8") as f:
                    self.assertIn('"--user", sender or "dashboard", "--origin", "human"', f.read())

            # O2. 에이전트 파생
        with self.subTest("o2_agent_derived_from_parent"):
                parent, _ = self.new("--origin", "human", "--user", "alice")
                rid, meta = self.new("--parent", parent, "--user", "alice",
                                     env={"S9_SESSION": "leadsess"})
                self.assertEqual(meta["origin"], "derived")
                self.assertEqual(meta["origin_req"], parent)
                self.assertEqual(meta["origin_actor"], "lead")

            # O3. 무인 워커
        with self.subTest("o3_worker_env"):
                parent, _ = self.new("--origin", "human", "--user", "bob")
                rid, meta = self.new(env={"S9_AUTO_RESUME": "1", "S9_JOB_REQ": parent,
                                          "S9_USER": "bob"})
                self.assertEqual(meta["origin"], "derived")
                self.assertEqual(meta["origin_req"], parent)
                self.assertEqual(meta["origin_actor"], "worker:auto-resume")
                self.assertEqual((meta["creator"], meta["user"]), ("bob", "bob"))

            # O4. 에이전트 자발 + --agent
        with self.subTest("o4_agent_spontaneous"):
                rid, meta = self.new("--user", "alice", env={"S9_SESSION": "leadsess"})
                self.assertEqual(meta["origin"], "agent")
                self.assertEqual(meta["origin_actor"], "lead")
                rid, meta = self.new("--user", "alice", "--agent", "designer",
                                     env={"S9_SESSION": "leadsess"})
                self.assertEqual(meta["origin_actor"], "sub:designer")

            # O5. 옛 문서
        with self.subTest("o5_legacy_read_rules"):
                self.assertEqual(self.m.doc_creator({"user": "carol"}), "carol")
                self.assertEqual(self.m.doc_origin({"user": "carol"}), "")
                self.assertEqual(self.m.doc_creator({"user": "carol", "creator": "dave"}), "dave")

            # O6. 담당자 지정
        with self.subTest("o6_assignee"):
                rid, meta = self.new("--origin", "human", "--user", "alice",
                                     "--assignee", "bob")
                self.assertEqual(meta["user"], "bob")
                self.assertEqual(meta["creator"], "alice")

            # O7·O8. 카탈로그·왕복
        with self.subTest("o7_o8_catalog_and_roundtrip"):
            parent, _ = self.new("--origin", "human", "--user", "alice")
            rid, meta = self.new("--parent", parent, "--user", "alice",
                                 env={"S9_SESSION": "leadsess"})
            row = [r for r in self.m.load_catalog() if r["id"] == rid][0]
            self.assertEqual(row["creator"], "alice")
            self.assertEqual(row["origin"], "derived")
            self.assertEqual(row["origin_actor"], "lead")
            self.assertEqual(row["origin_req"], parent)
            back = self.m.fm_parse(self.m.fm_dump(meta) + "\n---\n")[0]
            for k in ("creator", "origin", "origin_actor", "origin_req"):
                self.assertEqual(back[k], meta[k], k)

if __name__ == "__main__":
    unittest.main()
