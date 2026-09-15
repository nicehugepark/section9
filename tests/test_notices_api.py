"""대시보드 알림 줄의 서버 사실 — GET /api/notices (REQ-20260915-001-62x6).

주인 반려 2026-09-15 09:49: 머리의 신원 옆에 눈에 띄는 색의 글 한 줄로 얹은 Jira 만료 경고는
경고가 아니다 — 외부 서비스는 Jira 만이 아니고 Jira 는 선택이다. 그래서 흩어져 있던
머리 경고(whoami 의 jira_block·jira_expiry · serveinfo 의 stale · 칩의 sync_alert ·
미등록 계정)를 `notices_info()` 한 곳으로 모으고 화면은 그리기만 한다.

계약: {"notices": [{id, sev, source, say, go, since, sig, title, body, note}, …]}
  · sev 는 halt(막힘) · warn(주의) · note(정보), 정렬은 halt → warn → note, 같은
    등급은 since 오래된 것 먼저
  · source 는 주체 이름(값) — 문구 표(NOTICE_TEXT)에는 서비스 이름이 글자로 없다
  · go 는 하나: 화면 안 자리(screen) 또는 복사할 명령(cmd)
  · sig 는 조건의 지문 — 같은 조건이면 같고, 핵심 값이 바뀌면 바뀐다
  · /api/boot 의 notices 조각은 /api/notices 와 같은 값이다

실행: python3 tests/ notices_api
"""
import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"
sys.path.insert(0, HERE)

from portpool import free_port, wait_server  # noqa: E402

REQUIRED = ("id", "sev", "source", "say", "go", "since", "sig")


def load_s9(root, user):
    os.environ["S9_ROOT"] = root
    os.environ["S9_USER"] = user
    for k in ("S9_AUTO_RESUME", "S9_SESSION"):
        os.environ.pop(k, None)
    name = "s9nt_" + os.path.basename(root)
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9_SRC))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class NoticesFacts(unittest.TestCase):
    """모듈을 바로 불러 판정한다 — s9 subprocess 는 쓰지 않는다(빠른 테스트 규칙)."""

    def setUp(self):
        self._env = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_USER", "S9_AUTO_RESUME", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9nt-")
        self.m = load_s9(self.root, "hong")
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        m.chat_target = lambda sid8=None, user=None: {"session": "sid00000"}
        m._inbox_watch_alive = lambda sid: bool(sid)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    # ── 준비 ──────────────────────────────────────────────────────────────
    def link_jira(self, expires):
        m = self.m
        m.do_project_jira_set("pay", actor="hong", site="https://ex.atlassian.net",
                              project_key="MP1")
        m.do_user_config_set("hong", "jira_site", "https://ex.atlassian.net")
        m.do_user_config_set("hong", "jira_email", "hong@example.com")
        m.secret_write("hong", m.JIRA_SECRET_KEY, "fake-token-for-tests-0123456789")
        m.do_user_config_set("hong", "jira_token_expires", expires)

    def new_request(self, title):
        args = types.SimpleNamespace(
            doc_type="request", title=title, summary="환불을 돕는다", goal="환불이 된다",
            status="open", size="S", priority=None, user="hong", assignee=None,
            tag_list=[], parent=None, derived_from=None, relates=None, why="",
            ref_doc=None, ref_link=None, ref_file=None, needs_os="", from_chat="",
            project="pay", project_tag=None, body="본문", body_file=None,
            origin="human", agent="")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.cmd_new(args)
        return out.getvalue().split()[0]

    def in_days(self, n):
        return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()

    def notices(self):
        return self.m.notices_info()["notices"]

    def by_source(self, src):
        return [n for n in self.notices() if n["source"] == src]

    def make_stale_server(self):
        """서버가 옛 코드로 도는 상황 — 기동 지문을 디스크보다 한 발 앞선 값으로 둔다."""
        m = self.m
        cur = m.running_code_stamp()
        m.SERVE_STARTED = "2026-09-15T09:12:00+09:00"
        m.SERVE_CODE_STAMP = {"s9": {"mtime": cur["s9"]["mtime"] - 60, "size": cur["s9"]["size"]},
                              "hook": dict(cur["hook"])}

    # ── S1 정상·정렬 ────────────────────────────────────────────────────────
    def test_s1_halt_and_warn_stand_in_order(self):
        m = self.m
        self.link_jira(expires="2000-01-01")           # 만료된 token → 발신함이 막힌다
        self.new_request("환불 API")
        self.make_stale_server()
        ns = self.notices()
        self.assertEqual([n["sev"] for n in ns], ["halt", "warn"], ns)
        for n in ns:
            for k in REQUIRED:
                self.assertIn(k, n)
            self.assertIn(n["go"]["kind"], ("screen", "cmd"))
        jb, oc = ns
        self.assertEqual(jb["source"], "Jira")
        self.assertTrue(jb["say"].startswith("Jira 발신함 막힘 — 1건이 "), jb["say"])
        self.assertIn("째 못 갔습니다 — 빠진 것은 API token(만료됨 — 재발급)입니다.", jb["say"])
        self.assertEqual(jb["go"], {"kind": "screen", "label": "외부 서비스 › Jira 열기",
                                    "target": "settings:external:jira", "act": "준비물 채우기"})
        self.assertTrue(jb["since"].startswith("2000-01-01"), jb["since"])
        self.assertEqual(oc["source"], "서버")
        self.assertEqual(oc["say"], "서버 재시작 필요 — 09:12에 시작한 뒤 프로그램이 바뀌었습니다.")
        self.assertEqual(oc["go"], {"kind": "cmd", "text": "s9 serve --restart"})
        self.assertEqual(oc["note"], "재시작은 진행 중 요청과 실시간 연결을 끊습니다")
        # 정렬 함수 — 서버가 아직 싣지 않는 정보(note)까지 넣어 세 등급의 순서를 본다
        rows = [{"sev": "note", "since": "2026-09-01T00:00:00+09:00"},
                {"sev": "warn", "since": "2026-09-03T00:00:00+09:00"},
                {"sev": "halt", "since": "2026-09-05T00:00:00+09:00"},
                {"sev": "warn", "since": "2026-09-02T00:00:00+09:00"}]
        got = [(r["sev"], r["since"][8:10]) for r in m.notices_sorted(rows)]
        self.assertEqual(got, [("halt", "05"), ("warn", "02"), ("warn", "03"), ("note", "01")])

    # ── S2 경계·지문 ────────────────────────────────────────────────────────
    def test_s2_sig_is_stable_until_the_value_changes(self):
        self.link_jira(expires=self.in_days(3))
        a = self.by_source("Jira")[0]
        b = self.by_source("Jira")[0]
        self.assertEqual(a["sig"], b["sig"], "같은 조건인데 지문이 다르다")
        self.m.do_user_config_set("hong", "jira_token_expires", self.in_days(2))
        c = self.by_source("Jira")[0]
        self.assertNotEqual(a["sig"], c["sig"], "만료일이 바뀌었는데 지문이 그대로다")
        # 막힘도 마찬가지 — 건수가 늘면 지문이 바뀐다
        self.m.do_user_config_set("hong", "jira_token_expires", "2000-01-01")
        self.new_request("환불 API 1")
        d = self.by_source("Jira")[0]
        self.new_request("환불 API 2")
        e = self.by_source("Jira")[0]
        self.assertEqual(d["sev"], "halt")
        self.assertNotEqual(d["sig"], e["sig"])
        self.assertIn("2건이", e["say"])

    # ── S3 실패: Jira 를 잇지 않은 저장소 ─────────────────────────────────────
    def test_s3_repo_without_jira_has_no_notice_at_all(self):
        self.new_request("환불 API")
        self.assertEqual(self.notices(), [])

    # ── S4 회귀: 미등록 계정 ────────────────────────────────────────────────
    def test_s4_unregistered_account_is_halt_until_added(self):
        os.environ["S9_USER"] = "ghost"
        ns = self.notices()
        self.assertEqual(len(ns), 1, ns)
        n = ns[0]
        self.assertEqual((n["sev"], n["source"]), ("halt", "이 컴퓨터"))
        self.assertEqual(n["say"], "미등록 계정 — 지금 설정은 이 브라우저에만 저장됩니다.")
        self.assertEqual(n["go"], {"kind": "cmd", "text": "s9 user add ghost"})
        self.assertEqual(n["note"], "터미널에 붙여넣어 실행합니다")
        self.assertTrue(n["since"])
        self.m.do_user_add("ghost")
        self.assertEqual(self.notices(), [])

    # ── S5 회귀: 서비스 이름은 값 자리 ───────────────────────────────────────
    def test_s5_service_name_only_as_a_value(self):
        m = self.m
        self.assertNotIn("Jira", json.dumps(m.NOTICE_TEXT, ensure_ascii=False),
                         "문구 표에 서비스 이름이 글자로 박혔다 — {서비스} 값 자리여야 한다")
        self.link_jira(expires=self.in_days(3))
        n = self.by_source("Jira")[0]
        self.assertTrue(n["say"].startswith("Jira token 만료 임박"), n["say"])
        self.assertEqual(n["title"].replace("Jira", "{서비스}"), m.NOTICE_TEXT["jira_soon"][0])

    # ── S6 Jira token 만료 ──────────────────────────────────────────────────
    def test_s6_expiry_wording_and_block_wins(self):
        m = self.m
        self.link_jira(expires=self.in_days(3))
        n = self.by_source("Jira")[0]
        d = datetime.date.today() + datetime.timedelta(days=3)
        self.assertEqual(n["sev"], "warn")
        self.assertEqual(n["say"], f"Jira token 만료 임박 — 3일 뒤({d.month}월 {d.day}일) 만료됩니다.")
        self.assertEqual(n["go"]["act"], "새 token 넣기")
        m.do_user_config_set("hong", "jira_token_expires", self.in_days(0))
        self.assertIn(" — 오늘(", self.by_source("Jira")[0]["say"])
        m.do_user_config_set("hong", "jira_token_expires", self.in_days(1))
        self.assertIn(" — 내일(", self.by_source("Jira")[0]["say"])
        m.do_user_config_set("hong", "jira_token_expires", self.in_days(90))
        self.assertEqual(self.by_source("Jira"), [], "멀리 남았으면 조용하다")
        # 만료됐는데 발신함은 비어 있다 — 막힌 일이 없으니 주의로 선다
        m.do_user_config_set("hong", "jira_token_expires", self.in_days(-1))
        n = self.by_source("Jira")[0]
        self.assertEqual(n["sev"], "warn")
        self.assertTrue(n["say"].startswith("Jira token 만료됨 — "), n["say"])
        self.assertIn("에 만료돼 Jira에 보내지 못합니다.", n["say"])
        self.assertEqual(n["note"], "만료일도 함께 고칩니다")
        # 발신함이 막히면 막힘 하나만 — 둘을 같이 싣지 않는다
        self.new_request("환불 API")
        js = self.by_source("Jira")
        self.assertEqual(len(js), 1, js)
        self.assertEqual((js[0]["id"], js[0]["sev"]), ("jira:block", "halt"))
        self.assertNotIn("token 만료됨", js[0]["say"])   # 빠진 것의 값 안 「만료됨」은 값이다

    # ── S7 동기화 멈춤 ──────────────────────────────────────────────────────
    def test_s7_sync_fail_streak_is_halt(self):
        m = self.m
        st = m.SyncFailStreak(kind="net", count=3, told=True, line="fatal: x",
                              since="2026-09-14T08:00:00+09:00", stage="push")
        st.save()
        ns = self.by_source("동기화")
        self.assertEqual(len(ns), 1, ns)
        n = ns[0]
        self.assertEqual(n["sev"], "halt")
        self.assertEqual(n["say"], "동기화 멈춤 — 3번 잇따라 실패해 커밋 0건이 아직 못 갔습니다.")
        self.assertEqual(n["go"], {"kind": "cmd", "text": "s9 sync"})
        self.assertEqual(n["since"], "2026-09-14T08:00:00+09:00")
        st.success("push")
        st.save()
        self.assertEqual(self.by_source("동기화"), [])

    # ── S8 치워 둔 작업 ─────────────────────────────────────────────────────
    def test_s8_autostash_left_in_stash_is_warn(self):
        git = ["git", "-C", self.root]
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}

        def run(*a):
            r = subprocess.run(git + list(a), capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(r.returncode, 0, (a, r.stderr))
            return r.stdout
        run("init", "-q")
        with open(os.path.join(self.root, "f.txt"), "w") as f:
            f.write("a\n")
        run("add", "f.txt")
        run("commit", "-q", "-m", "one")
        self.assertEqual(self.by_source("동기화"), [], "보관함이 비었으면 아무 말도 없다")
        with open(os.path.join(self.root, "f.txt"), "w") as f:
            f.write("b\n")
        # rebase --autostash 가 되돌리지 못한 것과 같은 꼴 — 메시지가 autostash 다
        sha = run("stash", "create").strip()
        run("stash", "store", "-m", "autostash", sha)
        ns = self.by_source("동기화")
        self.assertEqual(len(ns), 1, ns)
        n = ns[0]
        self.assertEqual(n["sev"], "warn")
        self.assertEqual(n["say"], "치워 둔 작업 — 동기화가 잠시 치워 둔 1건이 아직 남아 있습니다.")
        self.assertEqual(n["go"], {"kind": "cmd", "text": "s9 doctor"})
        self.assertTrue(n["since"].startswith("20"), n["since"])

    # ── S9 정리: whoami 는 신원만 ───────────────────────────────────────────
    def test_s9_whoami_no_longer_carries_jira_keys(self):
        self.link_jira(expires="2000-01-01")
        self.new_request("환불 API")
        w = self.m.whoami_info()
        self.assertNotIn("jira_block", w)
        self.assertNotIn("jira_expiry", w)
        self.assertEqual(self.by_source("Jira")[0]["sev"], "halt")


class NoticesTransport(unittest.TestCase):
    """실서버 한 번 — GET /api/notices 와 /api/boot 의 조각이 같은 값이다 (S10)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9ntsrv-")
        base = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                "S9_PORT_GUARD": "off"}
        base.pop("S9_SESSION", None)
        r = subprocess.run([S9, "init"], capture_output=True, env={**base, "S9_USER": "alice"},
                           timeout=30)
        assert r.returncode == 0, r.stderr.decode(errors="replace")[-400:]
        # 서버는 등록되지 않은 계정으로 띄운다 — 알림이 최소 한 건(미등록 계정) 선다
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**base, "S9_USER": "ghost"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def getj(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req, timeout=20) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("application/json", r.headers.get("Content-Type", ""))
            return json.loads(r.read().decode())

    def test_s10_api_and_boot_piece_agree(self):
        body = self.getj("/api/notices")
        self.assertEqual(list(body), ["notices"])
        ns = body["notices"]
        self.assertTrue(ns, "미등록 계정인데 알림이 없다")
        for n in ns:
            for k in REQUIRED:
                self.assertIn(k, n)
        self.assertEqual([n["sev"] for n in ns],
                         sorted((n["sev"] for n in ns), key={"halt": 0, "warn": 1, "note": 2}.get))
        unreg = [n for n in ns if n["id"] == "identity:unreg"]
        self.assertEqual(len(unreg), 1)
        self.assertEqual(unreg[0]["go"], {"kind": "cmd", "text": "s9 user add ghost"})
        boot = self.getj("/api/boot")
        self.assertEqual(boot["notices"], body)
        self.assertNotIn("jira_block", boot["whoami"])


if __name__ == "__main__":
    unittest.main()
