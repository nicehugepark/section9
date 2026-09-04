"""대시보드 열람 격리 테스트 (REQ-20260824-017, 신원 모델은 REQ-20260824-027).

가드레일 격리: 서버 파생 신원(whoami) 기준으로 GET API 응답에서 비가시 문서를
제거한다. 구모델의 ?me= 자기신고는 폐기 — 시점 통제는 서버 프로세스의 S9_USER
(whoami)와 admin 전용 ?as= 로 한다. 검증 의미(비멤버 비가시/멤버 가시/admin
전부/무소속 작성자만/audit 스코프)는 구모델 테스트와 동일하게 보존.
- /api/users?scope=machine → 이 머신(registered_on) 등록 계정만
- doc_visible: admin=전부, 프로젝트 문서=활성 멤버만, 무소속=작성자만

격리: S9_ROOT=mktemp + S9_MACHINE 고정 — 라이브 vault를 건드리지 않는다.
실행: python3 tests/test_access_isolation.py
"""
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
MACHINE = "TESTMACH"


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestAccessIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9iso-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": MACHINE,
                   "S9_REWORK_WATCH": "off"}
        cls.env.pop("S9_SESSION", None)
        cls.env.pop("S9_USER", None)

        def cli(*argv, expect=0):
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=cls.env, timeout=15)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                     f"{r.stdout}{r.stderr}")
            return r
        cls.cli = staticmethod(cli)

        cli("init")
        cli("user", "add", "boss", "--role", "admin")
        cli("user", "add", "alice")
        cli("user", "add", "bob")
        # 다른 머신에서 등록된 계정 — me 셀렉터 후보에서 빠져야 한다 (V1)
        cli("user", "add", "remote", "--machine", "OTHERMACH")

        cli("project", "add", "px", "--name", "PX", "--user", "alice")
        r = cli("new", "request", "--title", "px doc", "--summary", "px",
                "--goal", "t", "--project", "px", "--user", "alice",
                "--body", "zebra-token-px")
        cls.px_doc = re.search(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?", r.stdout).group(0)
        # 무소속 문서 — bob은 프로젝트가 없어 auto-assign이 안 걸린다 (V5)
        r = cli("new", "request", "--title", "solo doc", "--summary", "solo",
                "--goal", "t", "--user", "bob", "--body", "zebra-token-solo")
        cls.solo_doc = re.search(r"REQ-\d{8}-\d{3,}(?:-[0-9a-z]{4})?", r.stdout).group(0)
        # alice의 세션 audit 문서 (V7) — SES 문서는 project 없음 → 작성자만
        cli("log", "alice-private-event", "--session", "aaaa1111",
            "--user", "alice")

        # 신원은 서버 파생(whoami) — admin(boss) 서버에서 ?as= 로 시점을
        # 전환해 격리를 검증하고, 비admin 직접 시점은 bob 서버로 본다.
        cls.port = free_port()        # S9_USER=boss (admin)
        cls.port_bob = free_port()    # S9_USER=bob (비admin)
        cls.srvs = []
        for port, s9user in ((cls.port, "boss"), (cls.port_bob, "bob")):
            env = {**cls.env, "S9_USER": s9user}
            cls.srvs.append(subprocess.Popen(
                [S9, "serve", "--host", "127.0.0.1", "--port", str(port)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for port in (cls.port, cls.port_bob):
            wait_server(port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기

    @classmethod
    def tearDownClass(cls):
        for p in cls.srvs:
            p.terminate()
        for p in cls.srvs:
            p.wait(timeout=5)

    @classmethod
    def get(cls, path, port=None, **params):
        qs = urllib.parse.urlencode(params)
        url = f"http://127.0.0.1:{port or cls.port}{path}" \
              + (f"?{qs}" if qs else "")
        # WSL2 는 리스너가 있어도 공개 직후 잠깐 RST 를 던진다(portpool 머리말의
        # 실측 참조). 3회×0.3초로는 그 창을 못 넘겨 이 파일이 전체 스위트에서만
        # 간헐적으로 깨졌다 — 혼자 돌리면 통과했다. 대기 총량을 늘리되 두드리는
        # 횟수는 백오프로 아낀다(커넥션 하나가 호스트 동적 포트 하나다).
        delay, spent, last = 0.2, 0.0, None
        while spent < 12.0:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode())
            except (ConnectionError, urllib.error.URLError) as e:
                last = e
                time.sleep(delay)
                spent += delay
                delay = min(delay * 1.7, 2.0)
        raise last

    def catalog_ids(self, viewer):
        # admin(boss) whoami 서버에서 ?as=<viewer> 로 시점 전환 (admin 본인은 무지정)
        params = {} if viewer == "boss" else {"as": viewer}
        code, rows = self.get("/api/catalog", **params)
        self.assertEqual(code, 200)
        return {r["id"] for r in rows}

    # V1. me 셀렉터 후보 = 이 머신 등록 계정만
    def test_test_access_isolation(self):
        """TestAccessIsolation 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("v1_users_machine_scope"):
                code, d = self.get("/api/users", scope="machine")
                self.assertEqual(code, 200)
                names = {u["name"] for u in d["users"]}
                self.assertEqual(names, {"boss", "alice", "bob"})
                self.assertEqual(d.get("machine"), MACHINE)
                # scope 미지정(Settings 사용자 관리)은 전체 유지
                code, d = self.get("/api/users")
                self.assertIn("remote", {u["name"] for u in d["users"]})

            # V2. 비멤버에게 프로젝트 문서 비가시
        with self.subTest("v2_nonmember_hidden"):
                self.assertNotIn(self.px_doc, self.catalog_ids("bob"))
                code, g = self.get("/api/graph", **{"as": "bob"})
                self.assertEqual(code, 200)
                self.assertNotIn(self.px_doc, {n["id"] for n in g["nodes"]})
                for e in g["edges"]:
                    self.assertNotIn(self.px_doc, (e["from"], e["to"]))
                code, s = self.get("/api/search", q="zebra-token-px", **{"as": "bob"})
                self.assertEqual([r["id"] for r in s["results"]], [])
                code, _ = self.get("/api/doc", id=self.px_doc, **{"as": "bob"})
                self.assertEqual(code, 404)
                code, _ = self.get("/api/reqstream", id=self.px_doc, **{"as": "bob"})
                self.assertEqual(code, 404)
                code, p = self.get("/api/projects", **{"as": "bob"})
                self.assertNotIn("px", {x["slug"] for x in p["projects"]})

            # V2b. 비admin whoami 서버의 기본 시점 = 자기 자신 (as 없이도 격리 동작,
            #      비admin의 as 는 무시되어 상승 불가)
        with self.subTest("v2b_nonadmin_direct_view"):
                code, rows = self.get("/api/catalog", port=self.port_bob)
                self.assertEqual(code, 200)
                ids = {r["id"] for r in rows}
                self.assertNotIn(self.px_doc, ids)
                self.assertIn(self.solo_doc, ids)
                code, rows = self.get("/api/catalog", port=self.port_bob,
                                      **{"as": "boss"})
                self.assertNotIn(self.px_doc, {r["id"] for r in rows})

            # V3. 활성 멤버는 보인다
        with self.subTest("v3_member_visible"):
                self.assertIn(self.px_doc, self.catalog_ids("alice"))
                code, _ = self.get("/api/doc", id=self.px_doc, **{"as": "alice"})
                self.assertEqual(code, 200)
                code, s = self.get("/api/search", q="zebra-token-px", **{"as": "alice"})
                self.assertIn(self.px_doc, {r["id"] for r in s["results"]})
                code, p = self.get("/api/projects", **{"as": "alice"})
                self.assertIn("px", {x["slug"] for x in p["projects"]})

            # V4. 시스템 admin 은 전부
        with self.subTest("v4_admin_sees_all"):
                ids = self.catalog_ids("boss")
                self.assertIn(self.px_doc, ids)
                self.assertIn(self.solo_doc, ids)
                code, p = self.get("/api/projects")
                self.assertIn("px", {x["slug"] for x in p["projects"]})

            # V5. 무소속 문서 = 작성자만
        with self.subTest("v5_unassigned_author_only"):
                self.assertIn(self.solo_doc, self.catalog_ids("bob"))
                self.assertNotIn(self.solo_doc, self.catalog_ids("alice"))
                code, _ = self.get("/api/doc", id=self.solo_doc, **{"as": "alice"})
                self.assertEqual(code, 404)

            # V7. audit 이벤트는 해당 SES 문서 가시성 기준
        with self.subTest("v7_audit_scoped"):
            code, d = self.get("/api/audit", **{"as": "alice"})
            self.assertEqual(code, 200)
            self.assertTrue(any("alice-private-event" in e["text"]
                                for e in d["events"]))
            code, d = self.get("/api/audit", **{"as": "bob"})
            self.assertFalse(any("alice-private-event" in e["text"]
                                 for e in d["events"]))
            code, d = self.get("/api/audit")
            self.assertTrue(any("alice-private-event" in e["text"]
                                for e in d["events"]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
