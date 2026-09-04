"""손길 하트비트 — 진전은 아니지만 붙어 있음은 안다 (REQ-20260830-019).

실사고 2026-08-30 (REQ-20260830-012): 리드가 037 을 조용히 파는 동안 문서가
안 바뀌어 보드가 「멈춤 74분」을 그렸다 — 사용자: "만약 037을 진행 중이었으면
왜 화면에서는 멈춤으로 떠 있던거야". 진전의 시계(updated)는 문서 쓰기뿐이라
일하는 손이 안 보였다.

이 스위트가 붙잡는 계약 (설계 DOC-20260830-003 v3):
  · 손길은 **문서를 고치는 CLI 명령**만 남긴다 — show·ls 조회는 아니다 (H1,
    C1·C6: 남의 문서 열람이 멈춤 경보를 끄면 안 된다). in-process 호출(서버·
    워처)은 dispatch 를 안 지나므로 아예 못 남긴다.
  · 손길은 **attached 까지만이다** (H2, C2): moving 이 아니고 stalled_mins 를
    만들지 않는다(깨우기 손잡이 안 섬) — 조용한 시간은 그대로 보인다.
  · 무신호(디렉토리 없음·미래 mtime·낡은 손길)면 현행과 완전히 같다 (H4·H5·H7,
    C3·C7). 쓰기 실패는 원 명령을 못 죽인다 (H6, C9).
  · terminal 전이가 손길을 거둔다 (H8).

실행: python3 tests/ heartbeat
"""
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name="s9hb"):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("S9_ROOT", "S9_MACHINE", "S9_SESSION",
                                 "S9_USER")}
        self.root = tempfile.mkdtemp(prefix="s9hb-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = "testbox"
        os.environ.pop("S9_SESSION", None)
        self.env = {**os.environ}
        self.cli("init")
        self.cli("user", "add", "alice")
        self.m = _load()
        self.hbdir = os.path.join(self.root, "state", "heartbeat")

    def tearDown(self):
        import shutil
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, stdin=subprocess.DEVNULL, timeout=30)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    def mkreq(self, title="손길"):
        rid = self.cli("new", "request", "--title", title, "--summary", "s",
                       "--size", "S", "--user", "alice", "--goal", "g",
                       "--body", "x").stdout.split()[0]
        self.cli("status", rid, "in-progress", "--note", "t")
        return rid

    def hb(self, rid):
        return self.m.heartbeat_path(rid)

    def age_doc(self, rid, mins):
        """문서의 updated 를 과거로 되감고 색인을 다시 짓는다 — '조용한 문서'."""
        path = self.m.locate(rid)
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        import datetime
        old = (datetime.datetime.now().astimezone()
               - datetime.timedelta(minutes=mins)).isoformat(timespec="seconds")
        txt = re.sub(r"(?m)^updated: .*$", f"updated: {old}", txt, count=1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        self.cli("index", "rebuild")
        return old

    def row(self, rid, mins_quiet):
        return {"id": rid, "status": "in-progress",
                "updated": self.age_doc(rid, mins_quiet)}

    def live_session(self, sid="cafe1234"):
        """살아 있는 세션 하나 — 손길은 그 세션이 살아 있을 때만 선다."""
        tp = os.path.join(self.root, f"tr-{sid}.jsonl")
        with open(tp, "w") as f:
            f.write("{}\n")
        self.m.write_binding({"machine": "testbox", "session": sid,
                              "transcript_path": tp})
        return sid


class TheStamp(Base):
    """H1 — 쓰기 명령만 손길이다. 조회도, in-process 호출도 아니다."""

    def test_h1_write_stamps_read_does_not(self):
        rid = self.mkreq()
        p = self.hb(rid)
        self.assertTrue(os.path.exists(p),
                        "in-progress 전이(쓰기)가 손길을 안 남겼다")
        before = os.path.getmtime(p)
        time.sleep(0.05)
        self.cli("show", rid)
        self.assertEqual(os.path.getmtime(p), before,
                         "조회(show)가 손길을 갱신했다 — 남의 문서를 열람만 "
                         "해도 멈춤 경보가 숨는다 (C6)")
        # in-process: 카탈로그 폴링은 dispatch 를 안 지난다 (C1)
        os.unlink(p)
        self.m.catalog_with_live()
        self.assertFalse(os.path.exists(p),
                         "서버 폴링 경로가 손길을 만들었다 (C1 위반)")

    def test_h6_write_failure_is_harmless(self):
        rid = self.mkreq()
        import shutil
        shutil.rmtree(self.hbdir, ignore_errors=True)
        with open(self.hbdir, "w") as f:    # 디렉토리 자리를 파일로 막는다
            f.write("x")
        r = self.cli("note", rid, "그래도 된다")   # expect=0 이 곧 검증(C9)
        self.assertEqual(r.returncode, 0)


class TheVerdict(Base):
    """H2·H4·H5·H7 — attached 까지만, 무신호면 현행."""

    def test_the_verdict(self):
        """H2·H4·H5·H7 — attached 까지만, 무신호면 현행."""
        with self.subTest("h2_fresh_touch_means_attached_not_moving"):
            rid = self.mkreq()
            r = self.row(rid, mins_quiet=60)         # 문서는 60분 조용
            sid = self.live_session()
            self.m.heartbeat_touch(rid, session=sid)   # 손길은 방금, 주인은 살아 있다
            v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
            self.assertEqual(v["state"], "attached", v)
            self.assertIsNone(v["mins"], "stalled_mins 가 생겼다 — 손잡이가 선다")
            self.assertGreaterEqual(v["quiet_mins"], 59,
                                    "조용한 시간을 감췄다 — REQ-034 의 반대편 병")
            # 낱말 통일 (REQ-20260831-005 tech-writer): 만지다/손대다 두 이름 →
            # 「손대다」 하나. 손길 문장은 다른 창이 언제 손댔는지를 말한다.
            self.assertIn("손댔습니다", v["why"])
        with self.subTest("h2b_a_dead_sessions_touch_does_not_attach"):
            # REQ-034 재발 방지선: 깨운 워커가 클레임만 하고 죽으면 그 도장은
            # 세션과 함께 죽는다 — 경보가 15분 꺼진 채 남지 않는다.
            rid = self.mkreq()
            r = self.row(rid, mins_quiet=60)
            self.m.heartbeat_touch(rid, session="dead0000")   # 바인딩 없는 세션
            v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
            self.assertEqual(v["state"], "stalled", v)
        with self.subTest("h2c_an_anonymous_touch_does_not_attach"):
            # 귀속 없는 손길은 손길이 아니다 — 근원 B 와 같은 원칙.
            rid = self.mkreq()
            r = self.row(rid, mins_quiet=60)
            self.m.heartbeat_touch(rid)                        # 세션 없음
            v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
            self.assertEqual(v["state"], "stalled", v)
        with self.subTest("h4_no_signal_is_stalled_as_before"):
            rid = self.mkreq()
            r = self.row(rid, mins_quiet=60)
            import shutil
            shutil.rmtree(self.hbdir, ignore_errors=True)   # C3: 디렉토리 자체가 없다
            v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
            self.assertEqual(v["state"], "stalled", v)
            self.assertGreaterEqual(v["mins"], 59)
        with self.subTest("h5_future_mtime_is_no_signal"):
            rid = self.mkreq()
            r = self.row(rid, mins_quiet=60)
            self.m.heartbeat_touch(rid, session=self.live_session())
            t = time.time() + 3600
            os.utime(self.hb(rid), (t, t))           # C7: 미래 시각
            v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
            self.assertEqual(v["state"], "stalled", v)
        with self.subTest("h7_old_touch_does_not_attach"):
            rid = self.mkreq()
            r = self.row(rid, mins_quiet=60)
            self.m.heartbeat_touch(rid, session=self.live_session())
            t = time.time() - self.m.HEARTBEAT_ATTACH_WIN - 60
            os.utime(self.hb(rid), (t, t))
            v = self.m.stall_verdict(r, time.time(), self.m.STALLED_WIN)
            self.assertEqual(v["state"], "stalled", v)

class TheWake(Base):
    """H3 — attached 카드는 깨워지지 않고, 사유가 사람 말로 나간다."""

    def test_h3_wake_on_attached_refuses_without_spawn(self):
        rid = self.mkreq()
        self.age_doc(rid, 60)
        self.m.heartbeat_touch(rid, session=self.live_session())

        def boom(*a, **kw):
            raise AssertionError("attached 인데 스폰했다 — 일하는 손 위의 두 번째 손")
        with mock.patch.object(self.m, "_spawn_wake", boom):
            res = self.m.wake_request(rid, actor="alice")
        self.assertFalse(res["ok"], res)
        self.assertTrue(res.get("message"), "사유 없는 거부 — 제일 나쁜 답")


class TheGC(Base):
    """H8 — 닫힌 문서의 손길은 거둔다."""

    def test_h8_terminal_transition_collects_the_touch(self):
        rid = self.mkreq()
        self.assertTrue(os.path.exists(self.hb(rid)))
        self.cli("status", rid, "done", "--note", "goal 충족: g 를 확인했다")
        self.assertFalse(os.path.exists(self.hb(rid)),
                         "done 문서에 손길이 남았다 — 뜻 없는 attached 신호")


if __name__ == "__main__":
    unittest.main(verbosity=2)
