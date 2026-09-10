"""못 받은 컴퓨터를 화면에 세운다 (REQ-20260910-002-t8rc).

이 컴퓨터가 못 받고 있는 것은 sync_status 가 말한다. **남의 컴퓨터**가 며칠째
못 받고 있는지는 어디에도 없었다 — 등록부에는 hostname·first_seen·root 뿐이라,
한 컴퓨터가 나흘 동안 한 줄도 못 받는 동안 다른 컴퓨터의 화면은 조용했다.

계약은 여섯이다.

  ① 받았다는 사실은 등록부의 제 줄(profile 의 machine_accounts.last_recv)로 나간다.
  ② 최소 간격(MACHINE_RECV_BEAT_SEC) — 그 안에는 다시 적지 않는다. 매 폴마다 적으면
     폴이 곧 commit 이 되어 동기화가 스스로를 먹는다.
  ③ 부르는 자리는 둘: 미는 회차(sync_run)에 얹히고, 조용한 컴퓨터는 그 간격을
     넘겼을 때 제가 한 번 민다. 실패한 폴은 적지 않는다.
  ④ 등록부에 제 줄이 없으면 만들지 않는다 — 계정 이력을 지어내지 않는다.
  ⑤ machine_table 이 컴퓨터마다 last_recv 를 내고, 이 컴퓨터 줄은 로컬 폴 도장이
     이긴다(등록부의 값은 길어야 그 간격만큼 과거다).
  ⑥ 화면은 임계를 넘은 줄만 낱말로 말한다 — 색면도 좌측 띠도 아니다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ machine_recv
"""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

import websrc                     # 공용 원문 도우미 (REQ-20260830-029)
from webasset import index_path   # 화면 계약은 이어 붙인 한 장을 본다

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
HOST = "recv-host-a"
ACCT = "recv-acct"
USER = "recvtester"


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RecvBeat(unittest.TestCase):
    """①~⑤ — 등록부에 적는 자리와 적지 않는 자리."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9recv-")
        os.makedirs(os.path.join(self.root, "state"))
        os.makedirs(os.path.join(self.root, "users", USER))
        os.environ["S9_ROOT"] = self.root
        self.m = _load("s9_recv", S9)
        self.profile = os.path.join(self.root, "users", USER, "profile.md")
        self.pushed = []

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    # ---------- 준비 ----------
    def write_profile(self, rows):
        self.m.write_doc(self.profile, {"name": USER, "type": "user",
                                        "machine_accounts": rows}, "")

    def rows(self):
        return self.m.user_profile(USER).get("machine_accounts") or []

    def stamp(self, epoch):
        with open(self.m._SYNC_PULL_TS, "w", encoding="utf-8") as f:
            f.write(str(epoch))

    def beat(self, **kw):
        m = self.m
        with mock.patch.object(m, "sync_mode", lambda: "remote"), \
                mock.patch.object(m, "_fp_user", lambda: USER), \
                mock.patch.object(m, "current_machine", lambda: HOST), \
                mock.patch.object(m.getpass, "getuser", lambda: ACCT), \
                mock.patch.object(m, "sync_run",
                                  lambda reason="": self.pushed.append(reason) or "ok"):
            return m.machine_recv_beat(**kw)

    def seed_row(self, **extra):
        self.write_profile([{"machine": HOST, "os": "Linux", "account": ACCT,
                             "first": "2026-09-01T00:00:00+09:00",
                             "last": "2026-09-10T00:00:00+09:00", **extra}])

    # ---------- ① 적는다 ----------
    def test_beat_records_last_recv_on_own_row(self):
        self.seed_row()
        got = time.time() - 5
        self.stamp(got)
        self.assertTrue(self.beat())
        row = self.rows()[0]
        self.assertAlmostEqual(self.m._epoch(row["last_recv"]), got, delta=1.5,
                               msg="받은 때가 등록부의 제 줄에 적히지 않았다")
        self.assertEqual(row["last"], "2026-09-10T00:00:00+09:00",
                         "받았다는 사실이 「여기서 일했다」까지 고쳐 썼다")

    # ---------- ② 최소 간격 ----------
    def test_second_beat_inside_the_gate_writes_nothing(self):
        self.seed_row()
        self.stamp(time.time() - 5)
        self.assertTrue(self.beat())
        before = open(self.profile, encoding="utf-8").read()
        self.stamp(time.time())                       # 다음 폴도 성공했다
        self.assertFalse(self.beat(), "최소 간격 안인데 다시 적었다 — 폴이 곧 commit 이 된다")
        self.assertEqual(open(self.profile, encoding="utf-8").read(), before)

    def test_beat_past_the_gate_records_and_pushes_itself(self):
        """③ 조용한 컴퓨터 — 밀어 주는 회차가 없으니 제가 한 번 민다."""
        old = time.time() - self.m.MACHINE_RECV_BEAT_SEC - 60
        self.seed_row(last_recv=self.m.datetime.datetime.fromtimestamp(old)
                      .astimezone().isoformat(timespec="seconds"))
        self.stamp(time.time())
        self.assertTrue(self.beat(push=True))
        self.assertEqual(self.pushed, ["recv-beat"], "적고도 밀지 않았다")

    def test_riding_round_does_not_push_again(self):
        """③ 미는 회차에 얹힐 때는 따로 밀지 않는다."""
        self.seed_row()
        self.stamp(time.time())
        self.assertTrue(self.beat())
        self.assertEqual(self.pushed, [])

    # ---------- ③ 실패한 폴은 적지 않는다 ----------
    def test_failed_poll_does_not_record(self):
        self.seed_row()
        m = self.m
        self.stamp(time.time() - 3600)      # 마지막으로 받은 것은 한 시간 전이다
        seen = []
        with mock.patch.object(m, "sync_mode", lambda: "remote"), \
                mock.patch.object(m, "_sync_poll_once", lambda timeout=8: "net"), \
                mock.patch.object(m, "_sync_poll_record", lambda *a, **k: None), \
                mock.patch.object(m, "machine_recv_beat",
                                  lambda **kw: seen.append(kw) or True):
            self.assertEqual(m.sync_poll(), "net")
        self.assertEqual(seen, [], "못 받았는데 받았다고 적었다")

    def test_successful_poll_records(self):
        m = self.m
        seen = []
        with mock.patch.object(m, "sync_mode", lambda: "remote"), \
                mock.patch.object(m, "_sync_poll_once", lambda timeout=8: "none"), \
                mock.patch.object(m, "_sync_poll_record", lambda *a, **k: None), \
                mock.patch.object(m, "machine_recv_beat",
                                  lambda **kw: seen.append(kw) or True):
            self.assertEqual(m.sync_poll(), "none")
        self.assertEqual(seen, [{"push": True}],
                         "받고도 등록부에 올리지 않았다 — 조용한 컴퓨터는 영영 안 보인다")

    # ---------- ④ 없는 줄을 만들지 않는다 ----------
    def test_no_row_no_invention(self):
        self.write_profile([{"machine": "other-host", "os": "macOS",
                             "account": "someone", "first": "2026-09-01T00:00:00+09:00",
                             "last": "2026-09-01T00:00:00+09:00"}])
        self.stamp(time.time())
        self.assertFalse(self.beat())
        rows = self.rows()
        self.assertEqual(len(rows), 1, "받았다는 사실 하나로 계정 이력을 지어냈다")
        self.assertNotIn("last_recv", rows[0])

    def test_never_received_records_nothing(self):
        self.seed_row()
        self.assertFalse(self.beat(), "한 번도 받은 적이 없는데 받았다고 적었다")
        self.assertNotIn("last_recv", self.rows()[0])

    # ---------- ⑤ 표로 나온다 ----------
    def test_table_carries_last_recv_and_local_stamp_wins(self):
        m = self.m
        theirs = "2026-09-06T11:35:00+09:00"
        self.write_profile([
            {"machine": HOST, "os": "Linux", "account": ACCT,
             "first": "2026-09-01T00:00:00+09:00", "last": "2026-09-10T00:00:00+09:00",
             "last_recv": "2026-09-10T00:00:00+09:00"},
            {"machine": "mac-far", "os": "macOS", "account": "someone",
             "first": "2026-09-01T00:00:00+09:00", "last": "2026-09-06T11:35:00+09:00",
             "last_recv": theirs}])
        got = time.time() - 3
        self.stamp(got)
        with mock.patch.object(m, "current_machine", lambda: HOST):
            table = m.machine_table(USER)
        self.assertEqual(table["mac-far"]["last_recv"], theirs,
                         "남의 컴퓨터가 마지막으로 받은 때가 표에 없다")
        self.assertAlmostEqual(m._epoch(table[HOST]["last_recv"]), got, delta=1.5,
                               msg="이 컴퓨터 줄은 로컬 폴 도장이 이겨야 한다")

    def test_level_thresholds(self):
        m, now = self.m, time.time()
        self.assertEqual(m.machine_recv_level("", now), "",
                         "적힌 적 없는 것을 사고라고 말한다")
        self.assertEqual(m.machine_recv_level(m.now_iso(), now), "")
        late = now - m.MACHINE_RECV_WARN_SEC - 60
        stale = now - m.MACHINE_RECV_ALERT_SEC - 60
        iso = lambda e: m.datetime.datetime.fromtimestamp(e).astimezone().isoformat()
        self.assertEqual(m.machine_recv_level(iso(late), now), "late")
        self.assertEqual(m.machine_recv_level(iso(stale), now), "stale")
        # 임계는 적는 간격보다 넉넉해야 한다 — 정상이 사고로 보이면 아무도 안 믿는다
        self.assertGreater(m.MACHINE_RECV_WARN_SEC, m.MACHINE_RECV_BEAT_SEC)
        self.assertGreater(m.MACHINE_RECV_ALERT_SEC, m.MACHINE_RECV_WARN_SEC)

    def test_cli_lines_speak_only_about_the_late_ones(self):
        m = self.m
        now = time.time()
        iso = lambda e: m.datetime.datetime.fromtimestamp(e).astimezone().isoformat()
        table = {"here": {"machine": "here", "os": "Linux", "names": [],
                          "last_recv": iso(now - 10)},
                 "far": {"machine": "far", "os": "macOS", "names": [],
                         "last_recv": iso(now - m.MACHINE_RECV_ALERT_SEC - 600)},
                 "mute": {"machine": "mute", "os": "", "names": [], "last_recv": ""}}
        with mock.patch.object(m, "machine_table", lambda user=None: table):
            lines = m.machine_recv_lines(USER, now)
        self.assertEqual(len(lines), 2, "적힌 적 없는 컴퓨터까지 줄을 세운다")
        far = next(ln for ln in lines if ln.startswith("far"))
        self.assertIn("사고", far, "오래 못 받은 컴퓨터가 그냥 한 줄로 지나간다")
        here = next(ln for ln in lines if ln.startswith("here"))
        self.assertNotIn("주의", here, "괜찮은 컴퓨터까지 떠든다")


class RecvScreen(unittest.TestCase):
    """⑥ — Settings 「컴퓨터·계정 이력」 표의 받음 칸."""

    @classmethod
    def setUpClass(cls):
        with open(index_path(), encoding="utf-8") as f:
            cls.src = f.read()
        with open(os.path.join(HERE, "..", "bin", "s9.py"), encoding="utf-8") as f:
            cls.s9 = f.read()

    def test_column_stands_and_speaks_in_words(self):
        fn = websrc.fn(self, self.src, "machineHistoryHTML")
        self.assertRegex(fn, r"<th[^>]*>마지막 받음</th>", "받음 칸이 표에 없다")
        self.assertIn("recvCellHTML(r.last_recv)", fn, "서버가 주는 값을 읽지 않는다")
        cell = websrc.fn(self, self.src, "recvCellHTML")
        self.assertIn("못 받음", cell, "임계를 넘은 컴퓨터가 낱말로 말하지 않는다")
        # 적힌 적 없는 컴퓨터에는 아무 말도 하지 않는다
        self.assertIn('return `<span class="mel"', cell)
        self.assertNotIn("못 받음`", cell.split("if (!t)")[1].split("\n")[0])

    def test_thresholds_match_the_server(self):
        cell = websrc.fn(self, self.src, "recvCellHTML")
        self.assertIn("MACHINE_RECV_ALERT_MS", cell)
        self.assertIn("MACHINE_RECV_WARN_MS", cell)
        js = dict(re.findall(r"const (MACHINE_RECV_\w+_MS) = ([^;]+);", self.src))
        self.assertEqual(len(js), 2, "화면 임계를 찾지 못했다")
        py = dict(re.findall(r"^(MACHINE_RECV_\w+_SEC) = (\d+)", self.s9, re.M))
        for k in ("WARN", "ALERT"):
            secs = int(py[f"MACHINE_RECV_{k}_SEC"])
            self.assertEqual(eval(js[f"MACHINE_RECV_{k}_MS"]), secs * 1000,
                             f"{k} 임계가 화면과 서버에서 갈린다")

    def test_mark_is_ink_not_a_color_block(self):
        m = re.search(r"\.mhtbl \.mrl[^\n]*\n\.mhtbl \.mrs[^\n]*", self.src)
        self.assertIsNotNone(m, "받음 표시의 잉크 규칙이 없다")
        block = m.group(0)
        self.assertIn("var(--c-blocked)", block)
        self.assertNotIn("background", block, "색면으로 칠했다 — 색은 글자에 쓴다")
        self.assertNotIn("border-left", block, "좌측 띠를 세웠다")

    def test_demo_can_be_opened_without_hands(self):
        demo = websrc.fn(self, self.src, "machineDemo")
        self.assertIn("last_recv", demo, "받음 칸의 모습을 손으로 볼 길이 없다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
