"""사람이 일을 세운다 — 세우기가 화면 손에 닿는다 (REQ-20260829-024 · 서버 몫).

사용자: "의도하지 않게 멈춘 작업들을 깨우려는 건데, 반대로 진행 중인 작업들을
강제로 중단하는 기능도 만들어라. 그래야 계정을 변경하거나 모델을 바꿀 때 그
기능을 같이 섞어서 사용할 수 있다."

021 이 낸 `worker_stop()` 은 **세션이 자기가 집은 문서의 작업자를 세우는 문**
이다. 화면에는 그 열쇠가 없다 — 대시보드에서 누르는 사람에게는 세션이 없고,
클레임을 요구하면 아무도 못 세운다. 그렇다고 화면이 자기 손으로 죽이면 게이트가
두 벌이 되고, 한 벌만 고쳐지는 사고가 시간 문제다.

그래서 이 라운드가 못 박는 것은 셋이다.
· 사람의 근거는 클레임이 아니라 **소유**다 — 같은 함수에 갈래 하나(owner)를
  낸다. 세션끼리의 규칙은 글자 그대로 그대로 둔다.
· 계정·모델을 바꾸는 걸음이 **도는 작업자를 남기지 않는다.** 옛 계정으로 도는
  작업자가 남으면 요금도 권한도 갈린다.
· 깨우기와 같은 모양으로 답한다 — 화면은 ok·action·message 셋만 읽는다.

실행: python3 tests/ stop_reach
"""
import importlib.machinery
import importlib.util
import inspect
import json
import os
import re
import shutil
import signal
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
SRC = open(S9_SRC, encoding="utf-8").read()

DOC = "REQ-20260829-999-62x6"
PID = 424242


def _fn(src, name):
    """화면 조각에서 함수 한 덩어리를 집는다 (test_wake_handle 의 그 손)."""
    m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


def _load(name="s9stop", root=None):
    old = os.environ.get("S9_ROOT")
    if root:
        os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if old is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = old


class TheOwnersDoor(unittest.TestCase):
    """S4~S5 — 사람의 권한은 클레임이 아니라 소유다."""

    def setUp(self):
        self.m = _load("s9stop_o")
        self.tmp = tempfile.mkdtemp(prefix="s9stopo-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.m._auto_dir = lambda: self.tmp
        self.marker()

    def marker(self, doc=DOC, pid=PID):
        with open(os.path.join(self.tmp, doc + ".json"), "w") as f:
            json.dump({"pid": pid, "last": 0}, f)

    def test_s4_the_owner_needs_no_claim(self):
        """화면에는 세션이 없다 — 클레임을 요구하면 아무도 못 세운다."""
        self.assertIn("owner", set(inspect.signature(self.m.worker_stop)
                                   .parameters),
                      "소유 갈래가 없다 — 화면은 이 문을 열 수 없다")
        sent = []
        alive = [True]

        def _alive(_p):
            v = alive[0]
            alive[0] = False       # SIGTERM 뒤에 물러난다
            return v
        r = self.m.worker_stop(DOC, session="", why="계정을 바꾼다", owner=True,
                               claims=lambda d, s: False,
                               kill=lambda p, s: sent.append((p, s)),
                               alive=_alive, wait=lambda _s: None,
                               note=lambda *a, **k: None)
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertTrue(r.get("stopped"))
        self.assertEqual([p for p, _ in sent], [PID],
                         "마커에 적힌 pid 가 아닌 것을 죽였다")

    def test_s4b_the_owner_still_owes_a_reason(self):
        """소유가 이유를 면제하지는 않는다 — 기록이 남아야 판정할 수 있다."""
        r = self.m.worker_stop(DOC, session="", why="  ", owner=True,
                               claims=lambda d, s: False,
                               kill=lambda *a: None, alive=lambda p: False,
                               note=lambda *a, **k: None)
        self.assertFalse(r.get("ok"))
        self.assertIn("이유", r.get("reason", ""))

    def test_s5_sessions_still_may_not_stop_each_other(self):
        """소유 갈래를 낸 김에 세션의 규칙이 헐거워지면 안 된다."""
        sent = []
        r = self.m.worker_stop(DOC, session="deadbeef", why="중복이다",
                               claims=lambda d, s: False,
                               kill=lambda p, s: sent.append((p, s)),
                               alive=lambda p: False,
                               note=lambda *a, **k: None)
        self.assertFalse(r.get("ok"))
        self.assertEqual(sent, [], "집지도 않은 세션이 작업자를 죽였다")


class TheScreenContract(unittest.TestCase):
    """S1~S3 · S9 — 화면은 깨우기와 같은 셋만 읽는다."""

    def setUp(self):
        self.m = _load("s9stop_c")
        self.tmp = tempfile.mkdtemp(prefix="s9stopc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.m._auto_dir = lambda: self.tmp

    def test_s1_the_shape_matches_wake(self):
        r = self.m.stop_request("REQ-does-not-exist-0000", actor="nicehugepark")
        self.assertEqual(set(("ok", "id", "action", "message")) - set(r), set())
        self.assertFalse(r["ok"])
        self.assertEqual(r["action"], "missing")

    def test_s2_pressing_twice_is_not_an_error(self):
        """도는 것이 없으면 '못 했다'가 아니라 '없다'다 — 멱등해야 손이 편하다."""
        self.m.locate = lambda _i: "/fake/doc.md"
        self.m.read_doc = lambda _p: ({"id": DOC, "type": "request",
                                       "status": "in-progress"}, "")
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(r.get("ok"), r.get("message"))
        self.assertEqual(r.get("action"), "none")

    def test_s2b_only_requests_are_stopped(self):
        self.m.locate = lambda _i: "/fake/doc.md"
        self.m.read_doc = lambda _p: ({"id": "DOC-x", "type": "knowledge"}, "")
        r = self.m.stop_request("DOC-x", actor="nicehugepark")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("action"), "not-request")

    def test_s3_the_screen_goes_through_the_one_door(self):
        """화면이 자기 손으로 죽이면 게이트가 두 벌이 된다."""
        i = SRC.find("def stop_request(")
        self.assertGreater(i, 0, "stop_request() 가 없다")
        j = SRC.find("\ndef ", i + 10)
        blk = SRC[i:j]
        self.assertIn("worker_stop", blk, "화면 몫이 worker_stop 을 안 지난다")
        for bad in ("SIGKILL", "SIGTERM", "os.kill"):
            self.assertNotIn(bad, blk, f"두 번째 죽이는 자리가 생겼다: {bad}")

    def test_s3b_the_press_carries_a_reason_and_the_owner_flag(self):
        """버튼에는 이유를 칠 자리가 없다 — 화면이 기본 사유를 싣는다."""
        seen = {}

        def fake(doc, **kw):
            seen.update(kw, doc=doc)
            return {"ok": True, "stopped": True, "pid": PID, "reason": "",
                    "message": "세웠다"}
        self.m.worker_stop = fake
        self.m.locate = lambda _i: "/fake/doc.md"
        self.m.read_doc = lambda _p: ({"id": DOC, "type": "request",
                                       "status": "in-progress"}, "")
        r = self.m.stop_request(DOC, actor="nicehugepark")
        self.assertTrue(seen.get("owner"), "소유 갈래로 부르지 않았다")
        self.assertTrue((seen.get("why") or "").strip(),
                        "이유 없이 불렀다 — worker_stop 이 거부한다")
        self.assertIn("nicehugepark", seen.get("why", ""),
                      "누가 눌렀는지가 사유에 없다")
        self.assertEqual(r.get("action"), "stopped")

    def test_s9_the_press_is_audited(self):
        i = SRC.find("def stop_request(")
        j = SRC.find("\ndef rework_watch_tick(", i)
        self.assertIn("_auto_log", SRC[i:j] if j > i else SRC[i:i + 3000],
                      "누른 것도 거부도 로그에 안 남는다")


class ManyAtOnce(unittest.TestCase):
    """S6 — 계정을 바꾸기 전에 도는 것을 한 번에 세운다."""

    def setUp(self):
        self.m = _load("s9stop_a")

    def test_s6_every_live_worker_is_stopped_and_counted(self):
        self.m.live_workers = lambda: [{"id": "REQ-a", "pid": 1, "age": 10},
                                       {"id": "REQ-b", "pid": 2, "age": 20}]
        stopped = []

        def fake(doc, **kw):
            stopped.append(doc)
            return {"ok": True, "stopped": True, "pid": 9, "reason": "",
                    "message": "세웠다"}
        self.m.worker_stop = fake
        r = self.m.stop_all_workers(actor="nicehugepark", why="계정을 바꾼다")
        self.assertTrue(r.get("ok"))
        self.assertEqual(sorted(r.get("ids") or []), ["REQ-a", "REQ-b"])
        self.assertEqual(r.get("count"), 2)
        self.assertEqual(sorted(stopped), ["REQ-a", "REQ-b"])

    def test_s6b_nothing_running_is_not_an_error(self):
        self.m.live_workers = lambda: []
        r = self.m.stop_all_workers(actor="nicehugepark", why="계정을 바꾼다")
        self.assertTrue(r.get("ok"))
        self.assertEqual(r.get("count"), 0)
        self.assertTrue(r.get("message"))

    def test_s6c_no_second_kill_site(self):
        i = SRC.find("def stop_all_workers(")
        self.assertGreater(i, 0, "stop_all_workers() 가 없다")
        blk = SRC[i:SRC.find("\ndef ", i + 10)]
        self.assertIn("worker_stop", blk)
        for bad in ("SIGKILL", "os.kill"):
            self.assertNotIn(bad, blk, f"두 번째 죽이는 자리가 생겼다: {bad}")


class MixedWithTheAccountSwitch(unittest.TestCase):
    """S7~S8 — 계정·모델을 바꾸는 걸음과 섞인다."""

    def test_mixed_with_the_account_switch(self):
        """S7~S8 — 계정·모델을 바꾸는 걸음과 섞인다."""
        with self.subTest("s7_restart_can_stop_the_workers_first"):
            m = _load("s9stop_r")
            self.assertIn("stop_workers",
                          set(inspect.signature(m.restart_session).parameters),
                          "계정·모델을 바꾸며 작업자를 세울 자리가 없다")
            i = SRC.find("def restart_session(")
            blk = SRC[i:SRC.find("\ndef ", i + 10)]
            self.assertIn("stop_all_workers", blk,
                          "재기동이 도는 작업자를 그대로 둔다 — 옛 계정으로 계속 돈다")
        with self.subTest("s7b_the_restart_route_carries_it"):
            i = SRC.find('parsed.path == "/api/session/restart"')
            self.assertGreater(i, 0)
            self.assertIn("stop_workers", SRC[i:i + 900],
                          "화면이 '세우고 바꾸기'를 보낼 자리가 없다")
        with self.subTest("s8_the_route_exists"):
            i = SRC.find('parsed.path == "/api/stop"')
            self.assertGreater(i, 0, "POST /api/stop 이 없다 — 화면 손이 닿지 않는다")
            blk = SRC[i:i + 900]
            self.assertTrue("stop_request" in blk and "stop_all_workers" in blk,
                            "한 건과 전부, 두 갈래가 다 없다")
        with self.subTest("s8b_the_cli_stops_them_all"):
            self.assertIn('wk.add_argument("--stop-all"', SRC,
                          "`s9 workers --stop-all` 이 파서에 없다")
            i = SRC.find("def cmd_workers(")
            self.assertIn("stop_all_workers", SRC[i:i + 1800],
                          "명령이 그 함수를 안 지난다")

class TheHandleOnTheScreen(unittest.TestCase):
    """S10~S14 — 손이 닿는 자리는 화면이다 (라운드3).

    라운드2 가 연 것은 서버의 문이었다. 그 문에 손잡이가 안 붙으면 사용자에게
    이 요청은 **없는 기능**이다 — 이 저장소가 깨우기에서 두 번 겪은 그 일이다
    (기능은 있었고, 화면에 버튼이 없었다).

    계약은 다섯이다.
      S10 조건은 서버가 준 `worker` 하나다. 점(`live_kind`)으로 대신하면
          클레임 뒤에 손잡이가 사라진다 — 정작 세울 것이 있을 때 없어진다.
      S11 카드와 문서가 **한 함수**로 짓는다 (깨우기가 세운 규칙).
      S12 되돌릴 수 없는 일은 먼저 묻는다. 깨우기에는 없던 걸음이다 —
          깨우기는 아무 일도 안 하던 것을 굴리고, 세우기는 일하는 것을 끝낸다.
      S13 화면이 이유를 짓지 않는다: 서버의 `message` 를 그대로 옮기고
          `action` 으로 문구를 갈라 쓰지 않는다.
      S14 계정·모델을 바꾸는 창이 도는 작업자를 알고, 사람이 고른 그 걸음을
          같은 요청에 실어 보낸다.
    """

    @classmethod
    def setUpClass(cls):
        from webasset import index_path
        with open(index_path(), encoding="utf-8") as f:
            cls.web = f.read()
        # 「진행 중」 줄이 「오래 걸림」 줄이 되고, ⏸ 는 그 줄을 떠나 id 줄의
        # 벨트로 갔다 (REQ-20260830-040). 계약은 그대로다 — 손잡이는 서버가 준
        # 사실 위에만 서고, 그리는 자리는 공용 조각 하나다.
        cls.workrow = _fn(cls.web, "slowRowHTML") + "\n" \
            + _fn(cls.web, "deedBeltHTML") + "\n" + _fn(cls.web, "holdTell")
        cls.stop = _fn(cls.web, "stopDoc")
        cls.stall = _fn(cls.web, "stallHTML")
        cls.restart = _fn(cls.web, "sessionRestart")

    def test_the_handle_on_the_screen(self):
        """S10~S14 — 손이 닿는 자리는 화면이다 (라운드3)."""
        with self.subTest("s10_the_row_stands_on_the_server_fact"):
            self.assertIn("r.worker", self.workrow,
                          "화면이 서버가 준 사실 말고 다른 것으로 손잡이를 세운다")
            # ⏸ 를 그리는 자리는 하나로 모였다 (REQ-20260830-035 — 갈래가 넷이라
            # 줄마다 베끼면 네 벌이 된다). 행의 사실을 읽는 계약은 그 조각이 진다.
            # wordy 는 얼굴 인자다 (REQ-20260830-046) — 조건이 아니라 같은 호출이다.
            self.assertIn("stopBtnHTML(r, wordy)", self.workrow, "벨트가 ⏸ 를 안 세운다")
            self.assertIn('data-stop="${esc(r.id)}"', _fn(self.web, "stopBtnHTML"))
            # 점으로 대신하면 클레임 뒤에 손잡이가 사라진다
            self.assertNotIn("live_kind", self.workrow,
                             "손잡이가 점의 값을 읽는다 — 클레임 뒤에 사라진다")
            # 서버가 그 사실을 행에 싣는 자리도 하나여야 한다
            i = SRC.find("def catalog_with_live(")
            self.assertGreater(i, 0)
            blk = SRC[i:SRC.find("\ndef ", i + 10)]
            self.assertIn('r["worker"]', blk, "행이 도는 작업자를 안 나른다")
            self.assertIn("worker_running(", blk,
                          "판정을 새로 지었다 — 워처와 화면이 다른 말을 하게 된다")
        with self.subTest("s11_board_and_document_grow_the_same_handle"):
            self.assertIn("stopBtnHTML(r, wordy)", _fn(self.web, "deedBeltHTML"),
                          "벨트가 세우기를 안 짓는다")
            for caller in ("cardHTML", "loadDoc"):
                seg = _fn(self.web, caller) if caller != "loadDoc" \
                    else self.web[self.web.index("async function loadDoc("):]
                self.assertIn("deedBeltHTML(", seg,
                              "%s 가 손잡이 벨트를 안 부른다" % caller)
                self.assertIn("stallHTML(", seg,
                              "%s 가 사실 줄을 안 부른다" % caller)
            # 자리는 둘이다 — 카드의 글리프(stopBtnHTML)와 문서의 낱말
            # (holdLockHTML). 갈래가 갈린 것은 뜻이 갈렸기 때문이고
            # (REQ-20260830-042: 도는 것을 끊는 행위 vs 앞으로 못 맡게 하는 정책),
            # 길은 하나다 — 둘 다 같은 data-stop 을 달고 같은 stopDoc 으로
            # 들어가며, 갈래는 data-kind 가 나른다.
            places = {n for n in ("stopBtnHTML", "holdLockHTML")
                      if 'data-stop="${esc(' in _fn(self.web, n)}
            self.assertEqual({"stopBtnHTML", "holdLockHTML"}, places,
                             "손잡이를 그리는 자리가 그 둘이 아니다")
            self.assertEqual(len(re.findall(r'data-stop="\$\{esc\(', self.web)), 2,
                             "손잡이를 그리는 자리가 또 늘었다 — 한 벌만 고쳐진다")
            for n in ("stopBtnHTML", "holdLockHTML"):
                self.assertIn("data-kind=", _fn(self.web, n),
                              "%s 가 갈래를 안 실어 stopKindOf 가 worker 로 떨어진다" % n)
            self.assertIn("stopDoc(sp.dataset.stop)", self.web,
                          "누른 것이 아무 데도 닿지 않는다")
        with self.subTest("s12_an_irreversible_press_asks_first"):
            self.assertIn('kind: "confirm"', self.stop, "묻지 않고 세운다")
            # 물음이 먼저다 — 확인 전에 요청이 나가면 묻는 시늉만 하는 창이다
            self.assertLess(self.stop.find('kind: "confirm"'),
                            self.stop.find('"/api/stop"'),
                            "확인을 받기 전에 이미 요청이 나갔다")
            self.assertIn("if (!go) return;", self.stop, "그만두기가 안 통한다")
            self.assertIn("if (stopPending(id)) return;", self.stop, "연타가 막히지 않는다")
            self.assertIn("STOP_HOLD", self.web, "잠금이 만료되지 않는다")
        with self.subTest("s13_the_screen_says_the_server_sentence"):
            self.assertIn("title: d.message", self.stop, "서버 문장이 창에 안 선다")
            self.assertNotIn("d.action", self.stop, "화면이 action 을 읽는다")
            for a in ("stopped", "none", "not-request", "missing"):
                self.assertNotIn('"%s"' % a, self.stop,
                                 "화면이 서버의 사유 낱말을 알고 있다: %s" % a)
            self.assertIn("stop: false", self.stop, "거절이 붉은 실패의 옷을 입는다")
            self.assertEqual(len(re.findall(r'"/api/stop"', self.web)), 1,
                             "세우기를 부르는 자리가 여럿이다")
        with self.subTest("s14_changing_the_account_can_stop_them_first"):
            self.assertIn("liveWorkerRows()", self.restart,
                          "계정·모델 창이 도는 작업자를 모른다")
            self.assertIn("stopWorkers: true", self.restart)
            self.assertIn("if (!go) return;", self.restart,
                          "물었는데 그만둘 자리가 없다")
            self.assertIn("stop_workers: !!req.stopWorkers", self.web,
                          "고른 것이 서버로 안 간다")
        with self.subTest("s15_it_reuses_what_the_card_already_wears"):
            self.assertIn('class="acts deedbelt"', self.workrow)
            # 뒤에 상태 갈래(`ico`·`busy`)가 붙는다 — REQ-20260830-032 로 손잡이
            # 얼굴이 ⏸ 글리프가 됐다. 무는 것은 낱말이 아니라 입은 옷이다.
            # 그리는 자리는 공용 조각 하나다 (REQ-20260830-035).
            self.assertRegex(_fn(self.web, "stopBtnHTML"), r'class="deed stop[ `$]')
            m = re.search(r"\.acts\.deedbelt\{([^}]*)\}", self.web)
            self.assertIsNotNone(m, ".acts.deedbelt 규칙이 없다")
            for banned in ("background", "animation", "border-left"):
                self.assertNotIn(banned, m.group(1),
                                 "세우기 줄이 %s 로 새 층을 만든다" % banned)
        with self.subTest("s16_the_handle_can_be_seen_on_purpose"):
            probe = _fn(self.web, "workProbe")
            self.assertIn("r.worker =", probe, "진단이 행에 값을 안 얹는다")
            self.assertIn("workProbe(rows)", _fn(self.web, "stallProbe"),
                          "진단이 화면 갱신 길에 서 있지 않다 — 아무 일도 안 한다")

class WhatWasStoppedCanStartAgain(unittest.TestCase):
    """R1~R7 — 세운 것을 사람이 되돌릴 수 있다 (라운드4 반려).

    사용자: "멈춰놓고선, 다시 시작할 수 있는 기능이 없다."

    맞는 지적이었고, 막고 있던 것은 둘이었다.
      · 세우면 그 사유가 문서에 적힌다 → 문서가 **방금** 움직인 것이 되어
        멈춤 판정이 15분간 서지 않는다 → 깨우기 손잡이가 안 그려진다.
      · 그 15분을 기다려도 per-REQ 쿨다운(600초)이 "방금 한 번 깨웠습니다"로
        막는다. 세운 사람이 자기가 세운 것을 되돌릴 수 없었다.

    그래서 세운 사실을 **표시로 남기고**, 그 표시가 있는 동안 ① 사람의 길은
    쿨다운을 지나가고 ② 기계(워처)의 길은 막는다. 사람이 세운 것을 30초 뒤에
    워처가 되살리면 세우기라는 행동 자체가 무의미해진다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9stopmark-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.m = _load("s9stop_m", self.root)
        self.tmp = tempfile.mkdtemp(prefix="s9stopmk-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.m._auto_dir = lambda: self.tmp

    def marker(self, doc=DOC, pid=PID, last=0):
        with open(os.path.join(self.tmp, doc + ".json"), "w") as f:
            json.dump({"pid": pid, "last": last}, f)

    def stop_it(self, why="계정을 바꾼다"):
        return self.m.worker_stop(DOC, session="", why=why, owner=True,
                                  claims=lambda d, s: False,
                                  kill=lambda *a: None, alive=lambda p: False,
                                  wait=lambda _s: None,
                                  note=lambda *a, **k: None)

    def test_r1_the_stop_leaves_a_mark(self):
        self.marker()
        self.stop_it()
        mk = self.m.stop_mark(DOC)
        self.assertTrue(mk, "세운 사실이 아무 데도 안 남는다")
        self.assertTrue(mk.get("at"))
        self.assertIn("계정", mk.get("why", ""))

    def test_r1b_stopping_nothing_marks_nothing(self):
        """세울 것이 없었으면 세운 것이 아니다 — 없는 사실을 남기지 않는다."""
        self.stop_it()
        self.assertFalse(self.m.stop_mark(DOC))

    def test_r2_the_person_is_not_held_by_the_cooldown(self):
        """쿨다운이 재는 것은 겹쳐 붙는 손인데, 세운 자리에는 붙은 손이 없다."""
        import time as _t
        self.marker(last=_t.time())          # 방금 스폰한 것으로 둔다
        self.assertTrue(self.m._auto_cap_block(DOC, {}, reason="wake"),
                        "세우기 전이라면 쿨다운이 막는 것이 맞다")
        self.stop_it()
        self.assertEqual(self.m._auto_cap_block(DOC, {}, reason="wake"), "",
                         "세워 둔 것을 사람이 다시 시작할 수 없다")

    def test_r2b_the_human_budget_still_holds(self):
        """쿨다운만 지나간다 — 하루치 예산까지 뚫으면 그건 문이 아니라 구멍이다."""
        import time as _t
        self.marker(last=_t.time())
        self.stop_it()
        import datetime as _dt
        with open(self.m._auto_global_path(), "w") as f:
            json.dump({"day": _dt.date.today().isoformat(),
                       "hour": int(_t.time() // 3600),
                       "wake_day_count": 99}, f)
        self.assertTrue(self.m._auto_cap_block(DOC, {}, reason="wake"),
                        "세운 표시가 하루 한도까지 뚫었다")

    def test_r3_the_watcher_does_not_revive_what_a_person_stopped(self):
        self.marker()
        self.stop_it()
        why = self.m._auto_cap_block(DOC, {})     # reason 없음 = 워처
        self.assertTrue(why, "사람이 세운 것을 워처가 도로 띄운다")
        self.assertNotIn("쿨다운", why)
        self.assertRegex(why, r"세[웠운]", "사유가 세운 사실을 말하지 않는다")

    def test_r4_starting_again_clears_the_mark(self):
        self.marker()
        self.stop_it()

        class P:
            pid = 777
        self.m._auto_mark_pid(DOC, P())
        self.assertFalse(self.m.stop_mark(DOC),
                         "다시 시작했는데도 '세워 둠' 이 남는다")

    def test_r5_the_mark_grows_old(self):
        """천장 없는 보호는 교착의 다른 이름이다 — 이 저장소가 두 번 배운 것."""
        self.marker()
        self.stop_it()
        p = self.m._stop_mark_path(DOC)
        with open(p) as f:
            mk = json.load(f)
        mk["at"] = mk["at"] - self.m.STOP_HOLD_WIN - 60
        with open(p, "w") as f:
            json.dump(mk, f)
        self.assertFalse(self.m.stop_mark(DOC), "늙은 표시가 아직 유효하다")
        self.assertEqual(self.m._auto_cap_block(DOC, {}), "",
                         "늙은 표시가 워처를 영원히 묶는다")

    def test_r6_wake_does_not_call_a_stopped_request_moving(self):
        """세운 그 자리가 곧 '조용하다'의 근거다 — 방금 적힌 사유가 아니라."""
        i = SRC.find("def wake_request(")
        blk = SRC[i:SRC.find("\ndef ", i + 10)]
        self.assertIn("stop_mark", blk,
                      "깨우기가 세운 표시를 모른다 — 세운 직후엔 moving 으로 거절한다")
        j = blk.find("stop_mark")
        k = blk.find("_wake_refusal")
        self.assertLess(j, k, "표시를 보기 전에 이미 거절한다")

    def test_r7_the_row_carries_the_stopped_fact(self):
        i = SRC.find("def catalog_with_live(")
        blk = SRC[i:SRC.find("\ndef ", i + 10)]
        self.assertIn('r["stopped"]', blk, "행이 세워 둔 사실을 안 나른다")
        # 도는 작업이 있으면 그건 세워 둔 것이 아니다 — 두 줄이 함께 서면 모순이다
        self.assertRegex(blk, r"if not wk[\s\S]{0,200}r\[\"stopped\"\]",
                         "작업이 도는 동안에도 '세워 둠' 을 싣는다")


class TheRestartHandle(unittest.TestCase):
    """R8 — 세워 둔 카드에 다시 시작할 손잡이가 선다."""

    @classmethod
    def setUpClass(cls):
        from webasset import index_path
        with open(index_path(), encoding="utf-8") as f:
            cls.web = f.read()
        cls.row = _fn(cls.web, "stoppedRowHTML")
        cls.stall = _fn(cls.web, "stallHTML")

    def test_the_restart_handle(self):
        """R8 — 세워 둔 카드에 다시 시작할 손잡이가 선다."""
        with self.subTest("r8_the_handle_takes_the_same_road_as_wake"):
            self.assertIn("r.stopped", self.row)
            # 손잡이는 줄을 떠나 id 줄의 벨트로 갔다 (REQ-20260830-040 규칙 4) —
            # 줄과 손잡이의 조건이 갈라지지 않게 술어(heldState) 하나를 함께 먹는다.
            self.assertIn("heldState(r)", self.row, "줄이 술어를 안 지난다")
            wake = _fn(self.web, "wakeBtnHTML")
            self.assertIn("heldState(r)", wake, "손잡이가 같은 술어를 안 지난다")
            self.assertIn("data-restart=", wake)
            # 낱말은 상수 한 곳에서 온다 — 글리프가 된 뒤로 이름은 눈에 보이는
            # 글자가 아니라 aria-label·title 이 나른다 (REQ-20260830-032). 원문에
            # 박힌 글자를 물면 주석 한 줄에도 통과하므로 상수를 문다.
            self.assertIn("WAKE_LABEL", wake, "손잡이의 낱말이 멈춘 카드와 다르다")
            self.assertRegex(wake, r'aria-label="\$\{[^"]*WAKE_LABEL',
                             "글리프 손잡이가 이름을 낭독기에 안 실어 보낸다")
            self.assertRegex(self.web, r"wakeDoc\(\w+\.dataset\.restart\)",
                             "다시 맡기는 손잡이가 자기만의 길을 판다")
            self.assertEqual(len(re.findall(r'"/api/wake"', self.web)), 1)
        with self.subTest("r8b_one_handle_per_card"):
            self.assertIn("stoppedRowHTML(r)", self.stall,
                          "카드·문서가 함께 부르는 그 함수가 이 줄을 안 짓는다")
            self.assertRegex(self.stall, r"if \(stopped\)[\s\S]{0,80}return",
                             "세워 둔 카드에 멈춤 줄과 다시 시작이 함께 선다")
        with self.subTest("r8c_the_press_paints_both_handles"):
            paint = _fn(self.web, "paintWake")
            self.assertIn("data-restart", paint,
                          "중단해 둔 카드의 손잡이는 눌러도 잠기지 않는다")
            # 낱말은 상수 한 곳에서 온다 — 글자를 두 곳에 두면 개명 한 번에 갈린다
            self.assertIn("WAKE_GOING", paint)

if __name__ == "__main__":
    unittest.main()
