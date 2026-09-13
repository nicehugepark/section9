"""프로젝트 초대 — 본문·발송·기록·API·CLI (REQ-20260913-010-62x6).

bin/s9_invite.py 한 모듈이 CLI(`s9 project invite`)와 POST /api/project/invite 를 함께
받친다. 발송은 시험 안의 SMTP 스텁(소켓 스레드, EHLO/AUTH/MAIL/RCPT/DATA)이 받는다 —
python 3.12 에는 smtpd 가 없다. 바깥으로 메일이 나가는 길은 없다(127.0.0.1 만).

격리: S9_ROOT=mktemp. s9 본체는 in-process 로 한 번 싣고(SourceFileLoader) 함수를 직접
부른다; 서버는 클래스당 1회. 실행: python3 tests/ project_invite
"""
import base64
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest

import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, pool_socket, wait_server  # noqa: E402

ORIGIN = "https://github.com/acme/team.git"


class SmtpStub(threading.Thread):
    """받은 것을 기록만 하는 SMTP 서버. reject_rcpt=True 면 RCPT 를 550 으로 거부한다."""

    def __init__(self):
        super().__init__(daemon=True)
        # 시험 포트는 풀에서 받는다 — 임시 포트(bind 0)는 test_port_pool 이 막는다
        # (윈도우 중계가 붙든 자리를 피하고, 풀 밖의 포트를 열지 않기 위해).
        self.sock = pool_socket()
        self.port = self.sock.getsockname()[1]
        self.sessions = []
        self.connections = 0
        self.reject_rcpt = False
        self.alive = True

    def run(self):
        while self.alive:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            try:
                self._serve(conn)
            except OSError:
                pass
            finally:
                conn.close()

    def _serve(self, conn):
        s = {"ehlo": "", "auth": "", "mail_from": "", "rcpt": [], "data": ""}
        self.sessions.append(s)
        f = conn.makefile("rb")

        def say(line):
            conn.sendall(line.encode() + b"\r\n")
        say("220 stub ESMTP")
        while True:
            raw = f.readline()
            if not raw:
                return
            line = raw.decode(errors="replace").rstrip("\r\n")
            up = line.upper()
            if up.startswith("EHLO"):
                s["ehlo"] = line[5:]
                conn.sendall(b"250-stub\r\n250-AUTH PLAIN LOGIN\r\n250 OK\r\n")
            elif up.startswith("HELO"):
                say("250 stub")
            elif up.startswith("AUTH PLAIN"):
                s["auth"] = line.split(" ", 2)[2] if line.count(" ") >= 2 else ""
                say("235 2.7.0 ok")
            elif up.startswith("MAIL FROM:"):
                s["mail_from"] = line[10:].strip().strip("<>")
                say("250 OK")
            elif up.startswith("RCPT TO:"):
                if self.reject_rcpt:
                    say("550 5.1.1 no such user")
                else:
                    s["rcpt"].append(line[8:].strip().strip("<>"))
                    say("250 OK")
            elif up == "DATA":
                say("354 End data with <CR><LF>.<CR><LF>")
                buf = []
                while True:
                    l2 = f.readline()
                    if not l2 or l2 == b".\r\n":
                        break
                    buf.append(l2)
                s["data"] = b"".join(buf).decode(errors="replace")
                say("250 OK queued")
            elif up in ("RSET", "NOOP"):
                say("250 OK")
            elif up == "QUIT":
                say("221 Bye")
                return
            else:
                say("502 not implemented")

    def stop(self):
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass


class TestProjectInvite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9invite-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_USER": "alice"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], env=cls.env, capture_output=True, timeout=30)
        for argv in (["init", "-q"], ["remote", "add", "origin", ORIGIN]):
            subprocess.run(["git", "-C", cls.tmp, *argv], capture_output=True, timeout=15)
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_USER"] = "alice"
        os.environ.pop("S9_SESSION", None)
        spec = importlib.util.spec_from_loader(
            "s9_inv", importlib.machinery.SourceFileLoader("s9_inv", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        m = cls.m
        m.do_user_add("alice", display="앨리스")
        m.do_user_add("bob")
        m.do_user_add("carol", emails=["carol@x.co"])
        m.do_project_add("demo", name="Demo", actor="alice")
        m.do_member_set("demo", "bob", role="maintainer", actor="alice")
        cls.inv = m.invite_module()
        cls.stub = SmtpStub()
        cls.stub.start()
        for k, v in (("smtp_host", "127.0.0.1"), ("smtp_port", str(cls.stub.port)),
                     ("smtp_user", "alice"), ("smtp_pass", "pw"), ("smtp_from", "alice@x.co")):
            m.secret_write("alice", k, v)
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        cls.stub.stop()

    # ── 도우미 ──────────────────────────────────────────────────────────
    @classmethod
    def _open(cls, req):
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode()
            except (ConnectionError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(0.3)

    @classmethod
    def post(cls, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{cls.port}{path}", data=json.dumps(payload).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        code, body = cls._open(req)
        return code, json.loads(body)

    def doc_text(self, slug="demo"):
        with open(os.path.join(self.tmp, "vault", "projects", slug + ".md"),
                  encoding="utf-8") as f:
            return f.read()

    def members(self, slug="demo"):
        return {x["user"]: x for x in self.m.load_project(slug)[0].get("members", [])}

    def compose(self, email="eve@x.co", **kw):
        kw.setdefault("role", "contributor")
        kw.setdefault("position", "")
        kw.setdefault("inviter", "alice")
        return self.inv.compose_invite(self.tmp, "demo", email, kw["role"],
                                       kw["position"], kw["inviter"])

    # ── S1 정상: 임시 본문의 치환 ─────────────────────────────────────────
    def test_s1_compose_fallback(self):
        mail = self.compose()
        posix = f"bin/s9 code --join {ORIGIN} --project demo"
        win = f"bin\\s9 code --join {ORIGIN} --project demo"
        self.assertEqual(mail["command_posix"], posix)
        self.assertEqual(mail["command_windows"], win)
        self.assertIn("Demo", mail["subject"])
        self.assertIn("앨리스", mail["subject"])
        for body in (mail["text"], mail["html"]):
            self.assertNotIn("{{", body)
            self.assertIn("앨리스", body)
            self.assertIn(ORIGIN, body)
            self.assertIn(posix, body)
            self.assertIn(win, body)
            self.assertIn(self.inv.RELEASE_URL, body)
            self.assertIn(self.inv.GUIDE_URL, body)
        self.assertIn("nicehugepark/section9/releases/latest", self.inv.RELEASE_URL)
        self.assertEqual(mail["said"], "")

    # ── S2 정상: 템플릿이 있으면 그것을 읽고 html 은 escape ───────────────
    def test_s2_templates_and_escape(self):
        self.m.do_project_add("neo", name="A<B", actor="alice")
        d = os.path.join(self.tmp, "harness", "common", "email")
        os.makedirs(d, exist_ok=True)
        keys = ("project", "inviter", "repo_url", "join_cmd_posix", "join_cmd_windows",
                "release_url", "guide_url")
        try:
            with open(os.path.join(d, "invite.txt"), "w", encoding="utf-8") as f:
                f.write("TXT " + " ".join("{{%s}}" % k for k in keys))
            with open(os.path.join(d, "invite.html"), "w", encoding="utf-8") as f:
                f.write("HTML {{logo}} " + " ".join("{{%s}}" % k for k in keys))
            mail = self.inv.compose_invite(self.tmp, "neo", "eve@x.co", "contributor", "", "alice")
            self.assertTrue(mail["text"].startswith("TXT "))
            self.assertTrue(mail["html"].startswith("HTML "))
            self.assertIn("A<B", mail["text"])
            self.assertIn("A&lt;B", mail["html"])
            self.assertNotIn("A<B", mail["html"])
            for body in (mail["text"], mail["html"]):
                self.assertNotIn("{{", body)
                self.assertIn("--project neo", body)
            self.assertIn("section9", mail["html"])          # 로고 자리 — 파일이 없으면 글자 마크
        finally:
            for fn in ("invite.txt", "invite.html"):
                os.remove(os.path.join(d, fn))

    # ── S3 경계: origin 없음 ─────────────────────────────────────────────
    def test_s3_no_origin(self):
        subprocess.run(["git", "-C", self.tmp, "remote", "remove", "origin"],
                       capture_output=True, timeout=15)
        try:
            self.assertEqual(self.inv.repo_origin(self.tmp), "")
            mail = self.compose()
            self.assertEqual(mail["said"], self.inv.NOT_LINKED)
            self.assertEqual((mail["command_posix"], mail["command_windows"]), ("", ""))
            self.assertNotIn("--join", mail["text"])
            res = self.inv.do_project_invite(self.tmp, "demo", "eve@x.co", actor="alice", send=True)
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], self.inv.NOT_LINKED)
            self.assertEqual(res["command"], {"posix": "", "windows": ""})
            self.assertNotIn("초대: eve@x.co", self.doc_text())
            st = self.inv.invite_state(self.tmp, "alice")
            self.assertEqual(st["repo"], {"origin": "", "linked": False})
        finally:
            subprocess.run(["git", "-C", self.tmp, "remote", "add", "origin", ORIGIN],
                           capture_output=True, timeout=15)

    # ── S4 정상: 기록 — History 한 줄·멤버 추가·재초대·등록 사용자 매칭 ─────
    def test_s4_record(self):
        r = self.inv.record_invite("demo", "frank@x.co", "contributor", "", "alice")
        self.assertEqual(r["member"], "frank@x.co")
        self.assertIn("초대: frank@x.co (contributor, by alice)", self.doc_text())
        self.assertEqual(self.members()["frank@x.co"]["role"], "contributor")
        self.inv.record_invite("demo", "frank@x.co", "viewer", "", "alice")   # 재초대
        self.assertEqual(sum(1 for u in self.members() if u == "frank@x.co"), 1)
        self.assertEqual(self.members()["frank@x.co"]["role"], "contributor")  # 역할은 안 바뀐다
        self.assertEqual(self.doc_text().count("초대: frank@x.co"), 2)
        r = self.inv.record_invite("demo", "Carol@X.co", "contributor", "QA", "alice")
        self.assertEqual(r["member"], "carol")                              # 프로필 emails 매칭
        self.assertEqual(self.members()["carol"]["position"], "QA")
        self.assertNotIn("Carol@X.co", self.members())

    # ── S5 실패: SMTP 준비물 없음 ─────────────────────────────────────────
    def test_s5_smtp_missing(self):
        res = self.inv.do_project_invite(self.tmp, "demo", "gina@x.co", actor="bob", send=True)
        self.assertFalse(res["ok"])
        self.assertFalse(res["sent"])
        self.assertEqual(res["error"], "SMTP 준비물 없음 — Settings › 외부 서비스")
        self.assertEqual(set(res["mail"]), {"subject", "text", "html"})
        self.assertIn("--join", res["mail"]["text"])
        self.assertNotIn("초대: gina@x.co", self.doc_text())
        self.assertNotIn("gina@x.co", self.members())
        self.assertEqual(self.inv.invite_state(self.tmp, "bob")["smtp"],
                         {"ready": False, "from": "", "host": "", "port": 587,
                          "has_user": False, "has_pass": False})

    # ── S6 정상: 스텁으로 발송 ───────────────────────────────────────────
    def test_s6_send_ok(self):
        n = len(self.stub.sessions)
        res = self.inv.do_project_invite(self.tmp, "demo", "hana@x.co", actor="alice",
                                         send=True, position="개발자")
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["sent"])
        self.assertTrue(res["recorded"])
        self.assertIn("hana@x.co", res["said"])
        self.assertEqual(len(self.stub.sessions), n + 1)
        s = self.stub.sessions[-1]
        self.assertEqual(s["mail_from"], "alice@x.co")
        self.assertEqual(s["rcpt"], ["hana@x.co"])
        self.assertIn(b"\x00alice\x00pw", base64.b64decode(s["auth"]))
        self.assertIn("multipart/alternative", s["data"])
        self.assertIn("text/plain", s["data"])
        self.assertIn("text/html", s["data"])
        self.assertIn("Subject:", s["data"])
        self.assertIn("To: hana@x.co", s["data"])
        self.assertIn("초대: hana@x.co (contributor, by alice)", self.doc_text())
        self.assertEqual(self.members()["hana@x.co"]["position"], "개발자")
        st = self.inv.invite_state(self.tmp, "alice")["smtp"]
        self.assertEqual(st, {"ready": True, "from": "alice@x.co", "host": "127.0.0.1",
                              "port": st["port"], "has_user": True, "has_pass": True})
        self.assertGreater(st["port"], 0)
        # 값은 새지 않는다 — 있다/없다 만 (REQ-20260913-025)
        self.assertNotIn("pw", json.dumps(st))

    # ── S7 실패: 입력 거부 ───────────────────────────────────────────────
    def test_s7_rejects(self):
        inv = self.inv
        with self.assertRaisesRegex(ValueError, "invalid email"):
            inv.do_project_invite(self.tmp, "demo", "not-an-email", actor="alice")
        with self.assertRaisesRegex(ValueError, "not found"):
            inv.do_project_invite(self.tmp, "nope", "eve@x.co", actor="alice")
        with self.assertRaisesRegex(ValueError, "invalid role"):
            inv.do_project_invite(self.tmp, "demo", "eve@x.co", role="boss", actor="alice")
        with self.assertRaisesRegex(ValueError, "권한 없음"):
            inv.do_project_invite(self.tmp, "demo", "eve@x.co", actor="carol")   # contributor
        with self.assertRaisesRegex(ValueError, "owner"):
            inv.do_project_invite(self.tmp, "demo", "eve@x.co", role="owner", actor="bob")

    # ── S8 서버: POST 미리보기·GET 상태·400 ───────────────────────────────
    def test_s8_server(self):
        code, res = self.post("/api/project/invite", {"slug": "demo", "email": "ivy@x.co", "send": False})
        self.assertEqual(code, 200, res)
        self.assertTrue(res["ok"])
        self.assertFalse(res["sent"])
        self.assertEqual(res["command"]["posix"], f"bin/s9 code --join {ORIGIN} --project demo")
        self.assertEqual(res["command"]["windows"], f"bin\\s9 code --join {ORIGIN} --project demo")
        self.assertEqual(set(res["mail"]), {"subject", "text", "html"})
        self.assertIn("said", res)
        self.assertNotIn("초대: ivy@x.co", self.doc_text())              # 미리보기는 기록하지 않는다
        code, res = self.post("/api/project/invite", {"slug": "demo", "email": "bad", "send": False})
        self.assertEqual(code, 400)
        self.assertFalse(res["ok"])
        self.assertIn("invalid email", res["error"])
        _c, body = self._open(f"http://127.0.0.1:{self.port}/api/invite/state")
        st = json.loads(body)
        self.assertEqual(set(st), {"smtp", "repo"})
        self.assertEqual(set(st["smtp"]), {"ready", "from", "host", "port", "has_user", "has_pass"})
        self.assertEqual(st["repo"], {"origin": ORIGIN, "linked": True})
        self.assertNotIn("pw", body)

    # ── S9 CLI: --print 는 본문과 기록, --send 는 준비물 없으면 rc≠0 ─────────
    def test_s9_cli(self):
        r = subprocess.run([S9, "project", "invite", "demo", "--to", "jin@x.co", "--print",
                            "--user", "alice"], env=self.env, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Subject:", r.stdout)
        self.assertIn(f"bin/s9 code --join {ORIGIN} --project demo", r.stdout)
        self.assertIn("초대: jin@x.co (contributor, by alice)", self.doc_text())
        r = subprocess.run([S9, "project", "invite", "demo", "--to", "kim@x.co", "--send",
                            "--user", "bob"], env=self.env, capture_output=True,
                           text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SMTP 준비물 없음", r.stdout + r.stderr)
        self.assertNotIn("초대: kim@x.co", self.doc_text())
        r = subprocess.run([S9, "project", "invite", "demo", "--to", "lee@x.co",
                            "--user", "alice"], env=self.env, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--print", r.stdout)                                   # 요약 — 기록 없음
        self.assertNotIn("초대: lee@x.co", self.doc_text())

    # ── S10 회귀: 발송 실패는 재시도하지 않고 기록도 없다 ────────────────────
    def test_s10_send_fail_no_retry(self):
        self.stub.reject_rcpt = True
        n = self.stub.connections
        try:
            res = self.inv.do_project_invite(self.tmp, "demo", "moon@x.co", actor="alice", send=True)
        finally:
            self.stub.reject_rcpt = False
        self.assertFalse(res["ok"])
        self.assertFalse(res["sent"])
        self.assertIn("SMTP 발송 실패", res["error"])
        self.assertEqual(res["said"], res["error"])
        self.assertEqual(set(res["mail"]), {"subject", "text", "html"})
        self.assertEqual(self.stub.connections, n + 1)
        self.assertNotIn("초대: moon@x.co", self.doc_text())
        self.assertNotIn("moon@x.co", self.members())


if __name__ == "__main__":
    unittest.main()
