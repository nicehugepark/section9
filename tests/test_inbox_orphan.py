"""수신함 고아 인계 테스트 (REQ-20260826-023).

수신함은 세션별 파일인데 대시보드의 대상 선택은 수시로 옮겨간다. 유휴 세션
앞으로 큐잉된 줄은 대상이 옮겨간 순간 아무도 다시 보지 않는다 — 그 세션의
claude 가 살아 있어도 그렇다(SessionStart 주입은 지났고 tail 은 없다).
실사고 2026-08-26 21:06:45 "011 진행이 왜 멈췄지?" 가 그렇게 유실됐다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ inbox_orphan
"""
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def iso(delta_sec=0):
    t = datetime.datetime.now().astimezone() \
        + datetime.timedelta(seconds=delta_sec)
    return t.isoformat(timespec="seconds")


class TestInboxOrphan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9orphan-")
        self.env = {**os.environ, "S9_ROOT": self.tmp, "S9_MACHINE": "testbox",
                    "S9_USER": "tester"}
        self.env.pop("S9_SESSION", None)
        self.dir = os.path.join(self.tmp, "state", "terminal")
        os.makedirs(self.dir, exist_ok=True)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env=self.env, timeout=30, stdin=subprocess.DEVNULL)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- helpers ---------------------------------------------------------
    def write_inbox(self, sid, *lines):
        p = os.path.join(self.dir, f"inbox-{sid}.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            for l in lines:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
        return p

    def chat(self, text, ago=3600, kind="chat"):
        return {"ts": iso(-ago), "from": "hgpark", "kind": kind, "text": text}

    def inbox(self, sid="me", *extra):
        r = subprocess.run([S9, "inbox", "--sid", sid, *extra],
                           capture_output=True, text=True, env=self.env,
                           timeout=20, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def seen(self, sid):
        p = os.path.join(self.dir, f"inbox-{sid}.jsonl.seen")
        try:
            with open(p, encoding="utf-8") as f:
                return int(f.read().strip() or 0)
        except (OSError, ValueError):
            return None

    # ---- 시나리오 --------------------------------------------------------
    def test_orphan_adopted(self):
        """1. 대상이 옮겨가 갇힌 kind=chat 줄은 새 세션이 거둔다."""
        self.write_inbox("dead", self.chat("011 진행이 왜 멈췄지?"))
        got = self.inbox("me")["orphans"]
        self.assertEqual([g["sid"] for g in got], ["dead"])
        self.assertEqual(got[0]["lines"][0]["text"], "011 진행이 왜 멈췄지?")

    def test_adopted_once_only(self):
        """2. 같은 줄이 두 세션에 중복 주입되지 않는다 (커서 전진 = 소비)."""
        self.write_inbox("dead", self.chat("한 번만"))
        self.assertEqual(len(self.inbox("me")["orphans"]), 1)
        self.assertEqual(self.inbox("other")["orphans"], [])

    def test_self_inbox_never_orphan(self):
        """3. 자기 수신함은 고아가 아니다 — pending 으로만 나온다."""
        self.write_inbox("me", self.chat("내 것"))
        d = self.inbox("me")
        self.assertEqual(d["orphans"], [])
        self.assertEqual(len(d["pending"]), 1)

    def test_listening_session_untouched(self):
        """4. 수신 대기(tail) 중인 세션의 수신함은 훔쳐오지 않는다.

        워커가 리드 메시지를 가로채던 REQ-010·012 사고의 반대 방향 재현 금지.
        커서도 전진시키지 않아야 그 세션이 나중에 온전히 받는다.
        """
        self.write_inbox("busy", self.chat("주인이 받을 것"))
        tail = subprocess.Popen(
            ["tail", "-f", os.path.join(self.dir, "inbox-busy.jsonl")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                if os.path.exists(f"/proc/{tail.pid}"):
                    break
            self.assertEqual(self.inbox("me")["orphans"], [])
            self.assertIsNone(self.seen("busy"))
        finally:
            tail.terminate()
            tail.wait(timeout=5)

    def test_grace_defers_fresh_lines(self):
        """5. 유예 안의 줄은 대상 세션에 맡긴다 — 이중 처리 방지."""
        self.write_inbox("dead", self.chat("방금 온 것", ago=5))
        self.assertEqual(self.inbox("me")["orphans"], [])
        self.assertIsNone(self.seen("dead"))
        # 유예를 0으로 두면 즉시 거둔다
        self.assertEqual(len(self.inbox("me", "--grace", "0")["orphans"]), 1)

    def test_stale_lines_dropped_but_consumed(self):
        """6. 창 밖(오래된) 줄은 되살리지 않되 커서는 전진한다."""
        self.write_inbox("dead", self.chat("이틀 전 이야기", ago=48 * 3600))
        d = self.inbox("me")
        self.assertEqual(d["orphans"], [])
        self.assertGreater(self.seen("dead"), 0)   # 다음 세션이 또 집지 않게

    def test_only_chat_kind_adopted(self):
        """7. 낡은 전이 통지(kind=event)는 되살리지 않는다."""
        self.write_inbox("dead",
                         self.chat("[전이 통지] 승인", kind="event"),
                         self.chat("진짜 사용자 말"))
        got = self.inbox("me")["orphans"]
        self.assertEqual([l["text"] for l in got[0]["lines"]],
                         ["진짜 사용자 말"])

    def test_hook_injects_orphans_with_origin(self):
        """8. 훅이 고아를 주입하고, 출처 세션·시각을 함께 보여준다.

        '지금 온 말'로 착각하면 이미 지난 맥락에 엉뚱하게 답한다.
        """
        self.write_inbox("dead", self.chat("갇혀 있던 말"))
        hook = os.path.join(HERE, "..", "bin", "s9-audit-session")
        payload = json.dumps({"session_id": "me000000", "source": "startup"})
        r = subprocess.run([hook, "start"], input=payload,
                           capture_output=True, text=True,
                           env={**self.env, "S9_PORT": "1"}, timeout=60)
        ctx = json.loads(r.stdout or "{}").get(
            "hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("갇혀 있던 말", ctx)
        self.assertIn("dead", ctx)          # 어느 세션 것인지
        self.assertIn("· 세션 dead]", ctx)  # 시각·출처가 붙어 나온다


if __name__ == "__main__":
    unittest.main(verbosity=2)
