"""감시 기록을 화면에 내주는 계약 (REQ-20260826-018-62x6, 서버측).

designer 가 `web/index.html` 을 만들며 명세를 정하고(그 문서의 decision 노트),
리드가 `bin/s9` 에 넣었다 — 같은 시각 다른 에이전트가 `bin/s9` 를 잡고 있어
파일을 나눈 것이다. 그래서 **이 테스트가 두 사람 사이의 계약서**다: 화면은 이
모양을 전제로 이미 쓰여 있고, 서버가 그 모양을 어기면 화면이 조용히 아무것도
안 그린다(designer 가 그렇게 만들었다 — 무응답을 '사건 없음'으로 오독하지
않기 위해서).

지키는 원칙 둘:
  ① **서버는 사실만, 화면이 정책을.** "이 사건을 사람에게 보여줄 만큼
     최근인가"는 표시 정책이라 서버가 판정하지 않는다. `recovered` 같은
     필드를 주기 시작하면 그 판단이 두 곳으로 갈린다.
  ② **응답에 서버 시각을 담는다.** 신선도 기준이 브라우저 시계면 시계가
     틀어진 기기에서 "6시간 전 사건"이 "방금"으로 보인다.

실행: python3 tests/ serve_guard_api
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
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
PORT = 19919


class ServeGuardApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9gapi-")
        os.environ["S9_ROOT"] = cls.tmp
        spec = importlib.util.spec_from_loader(
            "s9gapi", importlib.machinery.SourceFileLoader("s9gapi", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def write_log(self, *records):
        p = self.m._guard_paths(PORT)
        os.makedirs(p["state"], exist_ok=True)
        with open(p["log"], "w", encoding="utf-8") as f:
            for r in records:
                f.write(r if isinstance(r, str)
                        else json.dumps(r, ensure_ascii=False))
                f.write("\n")
        return p["log"]

    def report(self, alive=None):
        with mock.patch.object(self.m, "_guard_alive", return_value=alive):
            return self.m.guard_report(PORT)

    def setUp(self):
        try:
            os.remove(self.m._guard_paths(PORT)["log"])
        except OSError:
            pass

    def test_g1_no_log_is_not_an_error(self):
        """G1. 기록이 없으면 빈 보고다 — 오류가 아니라 **사건이 없는 것**이다.

        여기서 404 나 예외를 내면 화면이 '서버가 이상하다'로 읽는다. 아무 일도
        없었다는 것과 물어볼 수 없다는 것은 다른 사실이다.
        """
        r = self.report(alive=None)
        self.assertEqual(r["guard"], "none")
        self.assertIsNone(r["guard_pid"])
        self.assertIsNone(r["last_death"])
        self.assertEqual(r["restarts"], 0)
        self.assertEqual(r["events"], [])

    def test_g2_server_time_is_included(self):
        """G2. 응답이 서버 시각을 담는다 — 화면 신선도의 유일한 기준이다."""
        r = self.report(alive=None)
        self.assertRegex(r["now"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_g3_server_does_not_judge_freshness(self):
        """G3. 서버가 표시 정책을 판정하지 않는다.

        `recovered`·`attention` 같은 필드가 생기는 순간 같은 판단이 서버와
        화면 두 곳에 있게 되고, 둘이 갈리면 어느 쪽도 못 믿는다.
        """
        r = self.report(alive=None)
        for k in ("state", "recovered", "attention", "banner", "level"):
            self.assertNotIn(k, r, f"서버가 표시 정책을 판정한다: {k}")

    def test_g4_watching_reports_the_pid(self):
        """G4. 감시자가 살아 있으면 watching + 그 pid."""
        self.write_log({"ts": "2026-08-27T00:00:00+09:00", "event": "start"})
        r = self.report(alive=4242)
        self.assertEqual(r["guard"], "watching")
        self.assertEqual(r["guard_pid"], 4242)
        self.assertEqual(r["guard_since"], "2026-08-27T00:00:00+09:00")

    def test_g5_gave_up_is_distinct_from_none(self):
        """G5. '포기했다'와 '애초에 없다'는 다른 사실이다.

        둘을 같은 값으로 뭉치면 화면이 "사람이 봐야 한다"를 말할 수 없다 —
        자동 복구가 멈춘 것은 사람을 불러야 하는 상태다.
        """
        self.write_log({"ts": "2026-08-27T00:00:00+09:00", "event": "start"},
                       {"ts": "2026-08-27T00:05:00+09:00", "event": "gave-up"})
        self.assertEqual(self.report(alive=None)["guard"], "gave-up")
        self.write_log({"ts": "2026-08-27T00:00:00+09:00", "event": "start"})
        self.assertEqual(self.report(alive=None)["guard"], "none")

    def test_g6_restarts_count_only_this_watch(self):
        """G6. 되살린 횟수는 **마지막 감시 시작 이후**만 센다.

        어제 죽은 횟수를 오늘 감시자의 성적으로 보고하면 숫자가 거짓말을 한다.
        """
        self.write_log(
            {"ts": "2026-08-26T10:00:00+09:00", "event": "start"},
            {"ts": "2026-08-26T10:01:00+09:00", "event": "died"},
            {"ts": "2026-08-26T10:02:00+09:00", "event": "died"},
            {"ts": "2026-08-27T00:00:00+09:00", "event": "start"},
            {"ts": "2026-08-27T00:01:00+09:00", "event": "died"})
        self.assertEqual(self.report(alive=1)["restarts"], 1)

    def test_g7_broken_line_does_not_kill_the_rest(self):
        """G7. 깨진 한 줄이 나머지 기록을 죽이지 않는다.

        사고 기록은 사고 중에 쓰인다 — 마지막 줄이 반쯤 쓰이다 만 상태가
        정상이다. 그 한 줄 때문에 "왜 죽었나"를 통째로 못 읽으면 안 된다.
        """
        self.write_log({"ts": "2026-08-27T00:00:00+09:00", "event": "start"},
                       '{"ts": "2026-08-27T00:01:00+09:00", "event": "di',
                       {"ts": "2026-08-27T00:02:00+09:00", "event": "died",
                        "reason": "signal SIGTERM"})
        r = self.report(alive=1)
        self.assertEqual(r["restarts"], 1)
        self.assertEqual(r["last_death"]["reason"], "signal SIGTERM")

    def test_g8_unknown_keys_pass_through(self):
        """G8. 로그 줄의 필드를 그대로 통과시킨다.

        서버가 아는 키만 골라 내보내면, 기록에 새 근거가 늘어도 화면은 영영
        못 본다. 모르는 키를 버리지 않는 쪽이 사고 조사에 강하다.
        """
        self.write_log({"ts": "2026-08-27T00:00:00+09:00", "event": "start"},
                       {"ts": "2026-08-27T00:02:00+09:00", "event": "died",
                        "tail": ["Traceback", "MemoryError"],
                        "장래에_추가될_키": "보존"})
        d = self.report(alive=1)["last_death"]
        self.assertEqual(d["tail"], ["Traceback", "MemoryError"])
        self.assertEqual(d["장래에_추가될_키"], "보존")

    def test_g9_events_are_newest_first(self):
        """G9. 사건은 최신순이다 — 화면이 뒤집어 그리지 않아도 되게."""
        self.write_log({"ts": "2026-08-27T00:00:00+09:00", "event": "start"},
                       {"ts": "2026-08-27T00:01:00+09:00", "event": "died"},
                       {"ts": "2026-08-27T00:02:00+09:00", "event": "died"})
        ev = self.report(alive=1)["events"]
        self.assertEqual(ev[0]["ts"], "2026-08-27T00:02:00+09:00")

    def test_g10_route_is_wired(self):
        """G10. 라우트가 실제로 붙어 있다 — 함수만 있고 길이 없으면 화면은
        영영 404 를 받는다(designer 가 그 상태를 '조용히 아무것도 안 그림'으로
        만들어 둬서, 붙지 않아도 아무도 모른다)."""
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('parsed.path == "/api/serveguard"', src)
        self.assertIn("guard_report(s9_port())", src)


if __name__ == "__main__":
    unittest.main()
