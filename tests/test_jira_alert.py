"""준비물로 막힌 Jira 발신함을 사람에게 알린다 (REQ-20260914-013-62x6).

실제 사고 2026-09-09~14: API token 이 만료된 뒤 발신함 112건이 50번씩 재시도하며
문서 프론트매터의 last_error 에만 「준비물이 없다」를 적었다 — 대시보드·수신함·doctor
어디에도 서지 않아 주인은 닷새를 몰랐다. 판정은 jira_block_info 한 곳이고 세 자리가
그 값을 싣는다: whoami(대시보드 머리) · 리드 세션 수신함 kind=event(처음 한 번, 그 뒤
하루 한 번) · s9 doctor 의 Jira 줄. Jira 서버는 부르지 않는다 — 준비물 판정은 만료일
(jira_token_expires)로 실제 함수(jira_auth_header)가 내린다.

실행: python3 tests/ jira_alert
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
S9CLI = os.path.join(HERE, "..", "bin", "s9")
DOCTOR = os.path.join(HERE, "..", "bin", "s9-doctor")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")

_dspec = importlib.util.spec_from_loader(
    "s9doctor_jira", importlib.machinery.SourceFileLoader("s9doctor_jira", DOCTOR))
doctor = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(doctor)

EXPIRED = "API token(만료됨 — 재발급)"
SETTINGS = "Settings › 외부 서비스 › Jira"
SID = "abcd1234"


class JiraAlert(unittest.TestCase):

    def setUp(self):
        self._env = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_USER", "S9_AUTO_RESUME", "S9_SESSION")}
        self.root = tempfile.mkdtemp(prefix="s9ja-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_USER"] = "hong"
        for k in ("S9_AUTO_RESUME", "S9_SESSION"):
            os.environ.pop(k, None)
        name = "s9ja_" + os.path.basename(self.root)
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        m = self.m
        m.cmd_init(type("A", (), {})())
        m.do_user_add("hong", role="admin")
        m.do_project_add("pay", name="결제", summary="", actor="hong")
        # 수신함 대상: 살아 있는 리드 세션 하나를 흉내 낸다 (test_takeover_handoff 와 같은 자리)
        m.chat_target = lambda sid8=None, user=None: {"session": SID}
        m._inbox_watch_alive = lambda sid: bool(sid)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    # ── 준비 ──────────────────────────────────────────────────────────────
    def link_jira(self, expires="2099-12-31"):
        """프로젝트에 Jira 를 잇고 준비물 넷을 채운다 — 만료일만 시나리오가 정한다."""
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

    def inbox_events(self):
        p = os.path.join(self.root, "state", "terminal", f"inbox-{SID}.jsonl")
        try:
            with open(p, encoding="utf-8") as f:
                return [json.loads(ln) for ln in f if ln.strip()]
        except OSError:
            return []

    def cli(self, *a):
        env = {**os.environ, "S9_ROOT": self.root, "S9_USER": "hong"}
        return subprocess.run([S9CLI, "jira", *a], capture_output=True, text=True,
                              env=env, timeout=20)

    # ── S1·S2·S3·S5: 막힘 → 세 자리 · 수신함은 처음 한 번, 하루 한 번 · 풀리면 사라짐 ──
    def test_blocked_outbox_reaches_people(self):
        m = self.m
        self.link_jira(expires="2000-01-01")           # 만료된 token → 준비물 없음
        ids = [self.new_request(f"환불 API {i}") for i in range(3)]
        self.assertEqual(len(m.jira_outbox_read()), 3, "요청 셋이 발신함에 실려야 한다")

        with self.subTest("s1_block_info_and_whoami"):
            info = m.jira_block_info()
            self.assertIsNotNone(info)
            self.assertEqual(info["count"], 3)
            self.assertEqual(info["reason"], EXPIRED)
            self.assertEqual(info["user"], "hong")
            self.assertTrue(info["since"])
            self.assertIn(SETTINGS, info["fix"])
            # 만료일이 발신함 항목보다 이르면 since 는 그날이다 — 쓸기가 항목을 새로 놓아
            # `at` 만 보면 「1일」로 나오던 것(실제는 닷새)
            self.assertTrue(info["since"].startswith("2000-01-01"), info["since"])
            self.assertGreater(info["age_sec"], 20 * 365 * 86400)
            w = m.whoami_info()
            self.assertEqual(w["user"], "hong")
            self.assertEqual(w["jira_block"]["count"], 3)
            self.assertEqual(w["jira_block"]["reason"], EXPIRED)

        with self.subTest("s1_cli_quiet_line_and_json"):
            r = self.cli("outbox", "--quiet")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith("Jira 발신함 3건 준비물 없음 — " + EXPIRED),
                            r.stdout)
            self.assertIn(SETTINGS, r.stdout)
            j = json.loads(self.cli("outbox", "--json").stdout)
            self.assertEqual((j["rows"], j["enabled"], j["block"]["count"]), (3, True, 3))

        with self.subTest("s1_doctor_line"):
            v = doctor.jira_verdict(doctor.jira_info(root=self.root))
            self.assertIn(v["level"], ("warn", "critical"))
            self.assertIn("3건", v["line"])
            self.assertIn(EXPIRED, v["line"])
            self.assertIn(SETTINGS, v["advice"])

        t0 = time.time()
        with self.subTest("s2_first_tick_writes_one_event"):
            m.jira_outbox_tick(now=t0)                 # 준비물 없음 → 네트워크 없이 실패
            ev = self.inbox_events()
            self.assertEqual(len(ev), 1, ev)
            self.assertEqual(ev[0]["kind"], "event")
            self.assertEqual(ev[0]["from"], "jira")
            self.assertIn("Jira 발신함 3건 준비물 없음", ev[0]["text"])
            self.assertIn(EXPIRED, ev[0]["text"])
            with open(os.path.join(self.root, "state", "jira-alert.json"), encoding="utf-8") as f:
                st = json.load(f)
            self.assertEqual(st["day"], time.strftime("%Y-%m-%d", time.localtime(t0)))

        with self.subTest("s3_same_day_is_silent_next_day_speaks"):
            m.jira_outbox_tick(now=t0 + 60)
            self.assertEqual(len(self.inbox_events()), 1, "같은 날 두 번째 틱은 다시 쓰지 않는다")
            m.jira_outbox_tick(now=t0 + 86400 + 60)
            self.assertEqual(len(self.inbox_events()), 2, "다음 날에는 다시 한 줄")

        with self.subTest("s5_refilled_token_clears_everything"):
            m.do_user_config_set("hong", "jira_token_expires", "2099-12-31")
            self.assertIsNone(m.jira_block_info())
            self.assertNotIn("jira_block", m.whoami_info())
            self.assertEqual(self.cli("outbox", "--quiet").stdout, "")
            m.jira_block_notify(m.jira_block_info())   # 틱의 끝이 하는 일 — 상태 파일이 지워진다
            self.assertFalse(os.path.exists(os.path.join(self.root, "state", "jira-alert.json")))
            self.assertEqual(len(self.inbox_events()), 2)
            v = doctor.jira_verdict(doctor.jira_info(root=self.root))
            self.assertEqual(v["level"], "ok")
            self.assertEqual(v["line"], "Jira: 준비물 OK · 발신함 3건")
            self.assertEqual(len(ids), 3)

    # ── S4 회귀: Jira 를 잇지 않은 저장소에는 아무것도 서지 않는다 ─────────────
    def test_repo_without_jira_stays_silent(self):
        m = self.m
        self.new_request("환불 API")
        self.assertEqual(m.jira_outbox_read(), [])
        self.assertIsNone(m.jira_block_info())
        self.assertNotIn("jira_block", m.whoami_info())
        m.jira_outbox_tick()
        self.assertEqual(self.inbox_events(), [])
        self.assertEqual(self.cli("outbox", "--quiet").stdout, "")
        v = doctor.jira_verdict(doctor.jira_info(root=self.root))
        self.assertEqual((v["level"], v["line"]), ("ok", "Jira: 연동 안 함"))

    # ── S6 훅: 매 턴 주입 한 줄 (test_sync_status s17 과 같은 원천 계약) ─────────
    def test_hook_injects_block_line(self):
        with open(HOOK, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('run(env, "jira", "outbox", "--quiet")', src)
        self.assertIn("{jira_block}", src)
        self.assertIn('f" ◈ {jb.stdout.strip()}', src)

    # ── S7 doctor 순수 판정 ────────────────────────────────────────────────
    def test_doctor_verdict_grades(self):
        block = {"reason": EXPIRED, "count": 3, "age_sec": 600, "fix": SETTINGS + " 에 token 재발급"}
        with self.subTest("small_and_fresh_is_warn"):
            v = doctor.jira_verdict({"rows": 3, "enabled": True, "block": block})
            self.assertEqual(v["level"], "warn")
            self.assertIn("3건", v["line"])
            self.assertIn(EXPIRED, v["line"])
            self.assertEqual(v["advice"], SETTINGS + " 에 token 재발급")
        with self.subTest("many_rows_is_critical"):
            v = doctor.jira_verdict({"rows": 112, "enabled": True,
                                     "block": {**block, "count": 112}})
            self.assertEqual(v["level"], "critical")
        with self.subTest("over_a_day_is_critical"):
            v = doctor.jira_verdict({"rows": 2, "enabled": True,
                                     "block": {**block, "count": 2, "age_sec": 5 * 86400}})
            self.assertEqual(v["level"], "critical")
            self.assertIn("5일", v["line"])
        with self.subTest("ready_and_not_configured"):
            v = doctor.jira_verdict({"rows": 4, "enabled": True, "block": None})
            self.assertEqual((v["level"], v["line"]), ("ok", "Jira: 준비물 OK · 발신함 4건"))
            v = doctor.jira_verdict({"rows": 0, "enabled": False, "block": None})
            self.assertEqual((v["level"], v["line"]), ("ok", "Jira: 연동 안 함"))
            self.assertEqual(doctor.jira_verdict(None)["level"], "unknown")


if __name__ == "__main__":
    unittest.main()
