"""이 컴퓨터 몫인데 못 띄우는 요청은 세션이 안다 (REQ-20260912-001-2n7g).

실사고 2026-09-12: 016 은 담당이 맥으로 바뀐 뒤 6시간, 001 은 7시간 섰다. 워처는
스폰 상한(SKIP(cap))에 막힌 채 요청을 in-progress 로만 바꿔 두었고, 어쩌다 뜬
작업자는 주간 한도가 찬 기본 계정으로 떠서 즉사했으며, 이 컴퓨터의 라이브 세션은
아무 통지도 못 받았다. 뿌리 셋을 붙잡는다: ① 한도가 남은 계정으로 띄운다 ② 띄울 수
없으면 집지 않는다 ③ 못 띄우면 세션 수신함에 알리고 매 턴 훅이 짚는다.

실행: python3 tests/ here_notify
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


def _load(root):
    prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
    os.environ["S9_ROOT"] = root
    os.environ["S9_MACHINE"] = "thisbox"
    try:
        spec = importlib.util.spec_from_loader(
            "s9_hn", importlib.machinery.SourceFileLoader("s9_hn", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return m


def _usage(pct):
    return {"ok": True, "limits": [{"kind": "weekly_all", "percent": pct}]}


class HereNotify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9hn-")
        cls.m = _load(cls.tmp)
        os.makedirs(cls.m._auto_dir(), exist_ok=True)

    def test_n1_a_blocked_account_yields_to_one_with_room(self):
        """핵심 ① — 고른 계정이 100% 면 남은 계정을 고른다; 다 막히면 None."""
        m = self.m
        home = os.path.join(self.tmp, "home"); other = os.path.join(self.tmp, "prof-b")
        os.makedirs(other, exist_ok=True)
        usage = {home: _usage(100), other: _usage(3)}
        emails = {os.path.abspath(home): "a@x", os.path.abspath(other): "b@x"}
        with mock.patch.object(m, "account_home_dir", lambda: home), \
             mock.patch.object(m, "profiles_base", lambda: os.path.dirname(other)), \
             mock.patch.object(m, "claude_profiles", lambda: [os.path.basename(other)]), \
             mock.patch.object(m, "account_of", lambda p: emails.get(os.path.abspath(p), "")), \
             mock.patch.object(m, "claude_usage", lambda cfg, **kw: usage.get(os.path.abspath(cfg), _usage(100))), \
             mock.patch.object(m, "account_key_of_dir", lambda p: "a@x"):
            path, key, frm = m.account_with_room(home)
            self.assertEqual(os.path.abspath(path), os.path.abspath(other), "막힌 계정으로 그대로 띄운다")
            self.assertEqual((key, frm), ("b@x", "a@x"))
            usage[other] = _usage(100)
            self.assertEqual(m.account_with_room(home)[0], None, "다 막혔는데 띄운다")
            usage[home] = _usage(40)
            self.assertEqual(os.path.abspath(m.account_with_room(home)[0]), os.path.abspath(home))

    def test_n2_unknown_usage_does_not_block(self):
        """경계 — 조회 실패(ok=false)는 한도가 아니다: 고른 계정 그대로."""
        m = self.m
        home = os.path.join(self.tmp, "home2")
        with mock.patch.object(m, "claude_usage", lambda cfg, **kw: {"ok": False}), \
             mock.patch.object(m, "account_key_of_dir", lambda p: "a@x"):
            self.assertEqual(os.path.abspath(m.account_with_room(home)[0]), os.path.abspath(home))

    def test_n3_notify_writes_one_event_per_hour(self):
        """핵심 ③ — 라이브 세션의 수신함에 kind=event 한 줄, 한 시간에 한 번."""
        m = self.m
        inbox = os.path.join(self.tmp, "inbox-abc.jsonl")
        with mock.patch.object(m, "locate", lambda _i: ""), \
             mock.patch.object(m, "chat_target", lambda *_a, **_k: {"session": "abcdefgh"}), \
             mock.patch.object(m, "_inbox_watch_alive", lambda _s: True), \
             mock.patch.object(m, "chat_inbox_path", lambda sid, make=False: inbox):
            self.assertEqual(m._notify_here("REQ-20260912-001-t", "상한"), "abcdefgh")
            self.assertEqual(m._notify_here("REQ-20260912-001-t", "상한"), "", "같은 요청에 줄을 쌓는다")
        lines = [json.loads(x) for x in open(inbox, encoding="utf-8").read().splitlines()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["kind"], "event")
        self.assertIn("s9 last REQ-20260912-001-t --add", lines[0]["text"])
        self.assertIn("상한", lines[0]["text"])

    def test_n4_watcher_does_not_start_what_it_cannot_spawn(self):
        """핵심 ② — 상한에 막히면 in-progress 로 바꾸지 않고 알린다(소스 계약)."""
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("def here_watch_tick(")
        body = src[i:src.index("def rework_watch_tick(")]
        self.assertLess(body.index("_auto_cap_block("), body.index("do_transition("),
                        "상한 판정이 전이 뒤에 있다 — 못 띄우는 요청을 진행 중으로 바꾼다")
        self.assertIn("_notify_here(", body)

    def test_n6_without_a_recorded_choice_the_worker_follows_the_live_session(self):
        """① — 선택 기록이 없으면 이 컴퓨터에서 그 사람이 쓰는 세션의 계정(바인딩 cfg_dir)으로 뜬다."""
        m = self.m
        prof = os.path.join(self.tmp, "prof-live"); os.makedirs(prof, exist_ok=True)
        with mock.patch.object(m, "code_account_choice", lambda owner=None: ""), \
             mock.patch.object(m, "_owner_session_cfg_dir", lambda owner: prof), \
             mock.patch.object(m, "account_key_of_dir", lambda p: "live@x"):
            env = {}
            r = m.code_account_apply(env, "hong")
        self.assertEqual(r["source"], "live")
        self.assertEqual(env.get("CLAUDE_CONFIG_DIR"), prof, "작업자가 기본 계정으로 떨어진다")
        with mock.patch.object(m, "code_account_choice", lambda owner=None: ""), \
             mock.patch.object(m, "_owner_session_cfg_dir", lambda owner: ""):
            self.assertEqual(m.code_account_apply({}, "hong")["source"], "home")

    def test_n7_no_choice_is_not_a_default_account(self):
        """① — 고른 계정도 뜬 세션도 없으면 ~/.claude 로 짐작하지 않는다(explicit=False)."""
        m = self.m
        with mock.patch.object(m, "code_account_choice", lambda owner=None: ""), \
             mock.patch.object(m, "_owner_session_cfg_dir", lambda owner: ""):
            r = m.code_account_apply({}, "hong")
        self.assertEqual((r["source"], r.get("explicit")), ("home", False))
        with mock.patch.object(m, "code_account_choice", lambda owner=None: m.ACCOUNT_HOME_KEY):
            r = m.code_account_apply({}, "hong")
        self.assertEqual((r["source"], r.get("explicit")), ("home", True), "골라서 온 기본 자리는 explicit 다")
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("def _spawn_worker(")
        self.assertIn('not _wacct.get("explicit")', src[i:i + 40000],
                      "작업자가 고른 적 없는 ~/.claude 계정으로 뜬다")

    def test_n8_spawn_path_leaves_a_mark_and_the_tick_delivers_it(self):
        """③ — 스폰 경로는 표만 남기고(프로세스 표를 읽지 않는다) 워처 틱이 보낸다."""
        m = self.m
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("def _spawn_worker("); body = src[i:src.index("\ndef ", i + 10)]
        self.assertNotIn("_notify_here(", body, "스폰 경로가 곧바로 알린다 — ps 가 스폰 경로에 낀다")
        self.assertIn("_notify_later(", body)
        sent = []
        with mock.patch.object(m, "_notify_here", lambda d, t, every=3600: sent.append((d, t)) or "abcdefgh"):
            m._notify_later("REQ-20260912-009-t", "상한")
            self.assertEqual(m._notify_flush(), 1)
            self.assertEqual(sent, [("REQ-20260912-009-t", "상한")])
            self.assertEqual(m._notify_flush(), 0, "보낸 표가 남아 다시 보낸다")

    def test_n9_a_held_request_wakes_nobody(self):
        """③ — 리스를 쥔 세션이 이 컴퓨터에서 실행 중이면 통지하지 않는다.

        실제 사고 2026-09-15 13:58 (REQ-20260915-004-2n7g): 세션 A 가 16분째
        고치고 있던 요청의 「집어 직접 착수하라」 통지가 같은 맥의 세션 B 에게
        갔고, B 가 그대로 집어 같은 파일을 덮었다. 고르는 자리가 문서의 리스를
        보지 않은 것이 전부다."""
        m = self.m
        inbox = os.path.join(self.tmp, "inbox-held.jsonl")
        held = {"user": "tester", "machine": "thisbox", "session": "aaaa1111",
                "since": m.now_iso(), "renewed": m.now_iso()}
        with mock.patch.object(m, "locate", lambda _i: "/x/doc.md"), \
             mock.patch.object(m, "read_doc", lambda _p: ({"lease": held, "user": "tester"}, "")), \
             mock.patch.object(m, "_session_alive_here", lambda sid: sid == "aaaa1111"), \
             mock.patch.object(m, "chat_target", lambda *_a, **_k: {"session": "bbbb2222"}), \
             mock.patch.object(m, "_inbox_watch_alive", lambda _s: True), \
             mock.patch.object(m, "chat_inbox_path", lambda sid, make=False: inbox):
            self.assertEqual(m._notify_here("REQ-20260915-004-t", "상한"), "",
                             "쥔 세션이 있는데 다른 세션을 깨운다")
            self.assertFalse(os.path.exists(inbox))
            # 쥔 세션이 죽었으면 종전대로 알린다 — 그때는 이어받을 자리가 맞다
            with mock.patch.object(m, "_session_alive_here", lambda sid: False):
                self.assertEqual(m._notify_here("REQ-20260915-004-t", "상한"), "bbbb2222")
            self.assertTrue(os.path.exists(inbox))

    def test_n5_next_json_marks_claimed_and_the_hook_lists_the_rest(self):
        """③ — s9 next --json 이 claimed 를 실고, 훅이 안 잡힌 것만 매 턴 짚는다."""
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("def cmd_next(")
        self.assertIn('"claimed": bool(rework_claimed(', src[i:i + 1500])
        hook = open(HOOK, encoding="utf-8").read()
        self.assertIn("아무 세션도 집지 않은 요청", hook)
        self.assertIn("{here_txt}", hook, "짚은 줄이 주입문에 실리지 않는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
