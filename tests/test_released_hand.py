"""놓은 손은 문서가 기억한다 (REQ-20260919-011-62x6).

실사고 2026-09-19 11:21. REQ-20260919-004-62x6 을 맡던 백그라운드 작업자가
`s9 claim --release` 로 손을 놓으면서 사유를 노트로 남겼습니다. 그 뒤 11분 동안
아무도 집지 않았고, 주인이 11:31 에 「왜 004만 돌아?」로 물었을 때 실제로는
그것마저 돌고 있지 않았습니다.

구멍은 둘이었습니다.

① **놓았다는 사실을 아무 기계도 읽지 않았다.** 그 사실은 History 의 글줄로만
   남았고, 이어받기의 유예는 「조용한 것과 사라진 것이 밖에서 같아 보인다」는
   불확실함 때문에 15분이었습니다. 놓은 것은 그 세션이 스스로 적은 사실이라
   그 불확실함이 없는데도 같은 15분을 기다렸고, 게다가 놓으면서 남긴 노트가
   문서의 마지막 손길이 되어 그 15분을 제 손으로 되감았습니다.

② **클레임을 살려 두는 것이 「누구든」의 손이었다.** `claim_dead` 의 생존
   신호는 「문서가 클레임 이후에 한 번이라도 바뀌었나」였는데, 그 물음은 누가
   바꿨는지를 묻지 않습니다. 그래서 남이 쓴 노트 한 줄이 잡아만 두고 손을 뗀
   남의 클레임을 영영 살려 두었고, 카드는 그 클레임을 근거로 「지금 이 요청을
   맡아 일하고 있습니다」라고 적었습니다.

고친 자리: 놓은 도장(`released`)이 문서·카탈로그에 남고, 워처가 그것을 읽어
유예를 반려와 같은 30초로 줄이고, 카드가 조용한 시간을 기다리지 않고 곧바로
「아무도 붙어 있지 않습니다」라고 말합니다. 클레임의 시계는 제 손에 묶습니다.

격리: 임시 S9_ROOT + Popen 모킹(실스폰 방지).
실행: python3 tests/ released_hand
"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import subprocess as real_subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
FULLSID = "5151aaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SID = "5151aaaa"


def _ago(secs):
    return (datetime.datetime.now().astimezone()
            - datetime.timedelta(seconds=secs)).isoformat(timespec="seconds")


class ReleasedHand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9rel-")
        os.environ["S9_ROOT"] = cls.tmp          # 모듈 import 전에 고정
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "alice"
        for k in ("S9_SESSION", "S9_AUTO_RESUME", "S9_AUTO_RESUME_DISABLE"):
            os.environ.pop(k, None)
        spec = importlib.util.spec_from_loader(
            "s9rel", importlib.machinery.SourceFileLoader("s9rel", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.env = {**os.environ}

        def cli(sess, *argv, expect=0):
            env = dict(cls.env)
            if sess:
                env["S9_SESSION"] = sess
            r = real_subprocess.run([S9, *argv], capture_output=True, text=True,
                                    env=env, timeout=30)
            if expect is not None and r.returncode != expect:
                raise AssertionError(f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
            return r.stdout + r.stderr
        cls.cli = staticmethod(cli)

        cli(None, "init")
        cli(None, "user", "add", "alice")
        cli(None, "user", "config", "alice", "auto_resume", "on")
        cli(None, "user", "config", "alice", "auto_resume_cooldown_sec", "0")
        cli(None, "user", "config", "alice", "auto_resume_global_per_hour", "50")
        cli(None, "user", "config", "alice", "auto_resume_global_per_day", "100")
        cls.transcript = os.path.join(cls.tmp, FULLSID + ".jsonl")
        with open(cls.transcript, "w") as f:
            f.write("{}\n")
        cli(SID, "bind", "transcript_path", cls.transcript)
        cli(SID, "bind", "cwd", cls.tmp)

    # ------------------------------------------------------------ 도구
    def started(self, title):
        doc = self.cli(SID, "new", "request", "--title", title,
                       "--summary", "t", "--goal", "t", "--size", "S",
                       "--user", "alice", "--body", "x").split()[0]
        self.cli(SID, "status", doc, "in-progress", "--note", "착수")
        self.cli(SID, "last", doc, "--add")
        return doc

    def doc_path(self, rid):
        for dp, _dn, fns in os.walk(os.path.join(self.tmp, "vault")):
            for fn in fns:
                if fn.startswith(rid) and fn.endswith(".md"):
                    return os.path.join(dp, fn)
        raise AssertionError(f"문서 없음: {rid}")

    def binding_path(self, sid=SID):
        return os.path.join(self.tmp, "state", "sessions",
                            f"testbox__{sid}.json")

    def drop_claim(self, rid):
        """놓은 도장 **없이** 손만 뗀다 — 대조군을 만드는 유일한 길이다.
        (`s9 claim --release` 는 도장을 남기므로 이 자리에 쓸 수 없다.)"""
        p = self.binding_path()
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
        b["active_reqs"] = [x for x in (b.get("active_reqs") or []) if x != rid]
        if b.get("last_req") == rid:
            b["last_req"] = ""
        b["claim_at"] = {k: v for k, v in (b.get("claim_at") or {}).items()
                         if k != rid}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)

    def row(self, rid):
        return next(r for r in self.mod.load_catalog() if r["id"] == rid)

    def tick(self, **kw):
        calls = []

        def fake_popen(argv, **kwargs):
            calls.append(argv)
            return mock.Mock()
        with mock.patch("subprocess.Popen", side_effect=fake_popen):
            spawned = self.mod.rework_watch_tick(**kw)
        return spawned, calls

    # ------------------------------------------------ N. 도장이 남는다
    def test_release_leaves_a_mark_on_the_document(self):
        doc = self.started("놓을 것")
        self.cli(SID, "claim", doc, "--release", "--reason", "여기선 못 고칩니다")
        meta = self.mod.read_doc(self.doc_path(doc))[0]
        mark = self.mod.release_mark(meta)
        self.assertIsNotNone(mark, "놓았는데 문서에 아무것도 안 남았다")
        self.assertEqual(mark["session"], SID)
        self.assertIn("못 고칩니다", mark["reason"])
        # 카드가 문서를 다시 열지 않고 읽는다
        self.assertTrue(self.row(doc).get("released"))

    def test_a_new_hand_clears_the_mark(self):
        """다시 잡으면 걷힌다 — 걷히지 않으면 일하는 요청이 계속 놓인 것으로 보인다."""
        doc = self.started("다시 잡을 것")
        self.cli(SID, "claim", doc, "--release")
        self.assertTrue(self.row(doc).get("released"))
        self.cli(SID, "last", doc, "--add")
        self.assertFalse(self.row(doc).get("released"),
                         "새 손이 잡았는데 놓은 도장이 남아 있다")

    def test_the_mark_does_not_move_the_progress_clock(self):
        """도장을 걷는 것은 진전이 아니다 — `updated` 를 되감으면 경보가 꺼진다."""
        doc = self.started("시계 건드리지 않기")
        self.cli(SID, "claim", doc, "--release")
        before = self.row(doc).get("updated")
        self.cli(SID, "last", doc, "--add")
        self.assertEqual(self.row(doc).get("updated"), before)

    # ------------------------------------------------ W. 워처가 읽는다
    def test_the_watcher_resumes_a_released_request_on_the_short_clock(self):
        """놓은 손은 확실하다 — 반려와 같은 30초 시계로 이어받는다.

        놓으면서 남긴 노트가 문서의 마지막 손길이 되게 만든다: 종전 시계
        (마지막 손길로부터 15분)로 재면 이 요청은 뜨지 않는다."""
        doc = self.started("놓인 채 남은 것")
        self.cli(SID, "note", doc, "여기선 못 고칩니다", "--label", "blocked")
        self.cli(SID, "claim", doc, "--release", "--reason", "자리를 옮겨야 한다")
        with self.subTest("w1_within_the_grace_it_holds"):
            # 방금 놓았다 — 살아 있는 세션이 먼저 집을 30초는 그대로다.
            spawned, _ = self.tick()
            self.assertNotIn(doc, spawned, spawned)
        with self.subTest("w2_past_the_short_grace_it_is_resumed"):
            # 5분 뒤의 시계로 본다. 종전 시계(마지막 손길로부터 15분)로 재면
            # 이 요청은 아직 뜨지 않는다 — 그 차이가 이 시험의 전부다.
            spawned, calls = self.tick(now=time.time() + 300)
            self.assertIn(doc, spawned, (spawned, calls))
            argv = [a for a in calls if doc in " ".join(map(str, a))]
            self.assertTrue(argv, calls)
            prompt = [s for s in argv[0] if isinstance(s, str) and doc in s][0]
            self.assertIn("이어서 끝내는 일", prompt)
            self.assertIn("놓았다", prompt)

    def test_an_unreleased_request_keeps_the_long_clock(self):
        """놓지 않은 자리의 15분은 그대로다 — 짧은 시계가 넓은 자리를 덮지 않는다.

        조용한 것과 사라진 것은 밖에서 같아 보이므로, 그 자리에서는 살아 있는
        세션이 먼저 집을 기회를 뺏지 않는다. 앞 시험과 **같은 시계**로 본다."""
        doc = self.started("놓지 않은 것")
        self.cli(SID, "note", doc, "진행 중", "--label", "response")
        self.drop_claim(doc)      # 붙은 손은 없되, 놓았다고 적지도 않았다
        spawned, _ = self.tick(now=time.time() + 300)
        self.assertNotIn(doc, spawned, spawned)
        self.assertGreater(self.mod.abandon_grace({"user": "alice"}),
                           self.mod.rework_grace({"user": "alice"}))

    # ------------------------------------------------ C. 카드가 말한다
    def test_the_card_says_nobody_is_holding_it_right_away(self):
        """조용한 시간을 기다리지 않는다 — 방금 놓았어도 곧바로 말한다."""
        m = self.mod
        r = {"id": "REQ-1", "status": "in-progress", "updated": _ago(10),
             "released": {"at": _ago(10), "session": SID, "reason": ""}}
        v = m.stall_verdict(r, time.time(), m.STALLED_WIN, hands=[], assigned={})
        self.assertEqual(v["state"], "stalled", v)
        self.assertIn("놓았습니다", v["why"])

    def test_a_hand_that_is_really_there_wins(self):
        """실제로 붙은 손은 이긴다 — 도장이 일하는 카드를 멈춤으로 그리지 않는다."""
        m = self.mod
        r = {"id": "REQ-2", "status": "in-progress", "updated": _ago(10),
             "live": True, "live_kind": "direct", "live_age": 3,
             "released": {"at": _ago(600), "session": SID, "reason": ""}}
        v = m.stall_verdict(r, time.time(), m.STALLED_WIN, hands=[], assigned={})
        self.assertNotEqual(v["state"], "stalled", v)

    def test_without_the_mark_the_quiet_window_is_unchanged(self):
        """도장이 없으면 종전대로 — 방금 움직인 것은 멈춤이 아니다."""
        m = self.mod
        r = {"id": "REQ-3", "status": "in-progress", "updated": _ago(10)}
        v = m.stall_verdict(r, time.time(), m.STALLED_WIN, hands=[], assigned={})
        self.assertEqual(v["state"], "moving", v)

    def test_the_screen_says_the_same_sentence(self):
        """화면과 서버가 같은 말을 한다 — 두 벌이면 한쪽만 고쳐진다.

        카드는 수(`stalled_mins`)로 「멈춤 N분째 진전 없음」을 그리는데, 놓은
        직후에는 그 수가 0 이라 정작 말해야 할 사실을 못 나른다. 그래서 그
        줄만 문장을 바꾼다 — 새 시각 언어를 들이지 않는다."""
        with open(os.path.join(HERE, "..", "web", "app", "card.js"),
                  encoding="utf-8") as f:
            js = f.read()
        self.assertIn("아무도 붙어 있지 않습니다", js)
        self.assertIn("r.released", js)
        # 행이 화면까지 가야 한다 — 응답 경계에서 깎이면 줄이 영영 안 선다.
        mark = {"at": _ago(5), "session": SID, "reason": ""}
        wire = self.mod.catalog_wire_row({"id": "REQ-9", "released": mark})
        self.assertEqual(wire.get("released"), mark)
        # 빈 값은 깎는다 — 없는 사실로 줄을 세우지 않는다.
        self.assertNotIn("released",
                         self.mod.catalog_wire_row({"id": "REQ-9",
                                                    "released": ""}))

    # ------------------------------------------------ K. 클레임의 시계
    def test_only_my_own_hand_renews_my_claim(self):
        """남이 쓴 노트가 남의 클레임을 살리지 못한다 — 실사고의 뿌리."""
        m = self.mod
        doc = self.started("식은 클레임")
        bp = self.binding_path()
        with open(bp, encoding="utf-8") as f:
            b = json.load(f)
        b["claim_at"] = {doc: _ago(m.CLAIM_GRACE + 600)}
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        # 남이 문서를 고친다 — 이것으로는 안 살아난다
        self.cli("77776666", "note", doc, "남이 씁니다", "--label", "response")
        with open(bp, encoding="utf-8") as f:
            b = json.load(f)
        self.assertTrue(m.claim_dead(b, doc))
        self.assertNotIn(doc, m.binding_req_ids(b))
        # 워처의 물음은 다르다 — 두 번째 손을 붙이지 않으려 넓게 본다
        self.assertIn(doc, m.binding_req_ids(b, stale_ok=True))
        # 제 손이 닿으면 되살아난다
        self.cli(SID, "note", doc, "제가 이어서 합니다", "--label", "response")
        with open(bp, encoding="utf-8") as f:
            b = json.load(f)
        self.assertFalse(m.claim_dead(b, doc))


if __name__ == "__main__":
    unittest.main()
