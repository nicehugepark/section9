"""판정 대기가 얼마나 오래됐나 (REQ-20260910-010).

실측 2026-09-10: 그날 done 32건 중 review 를 탄 넷이 판정 칸에서만 440분(건당
중앙값 112분)을 썼고, 리드가 검증해 바로 닫은 28건은 중앙값 14.8분이었다. 규칙
(PROTOCOL 12조 ①)은 이미 있었고 없던 것은 「이 건이 몇 분째 대기 중인가」다 —
세션 시작 주입에도 매 턴 주입에도 `s9 review` 에도 나이가 없었다.

여기서 재는 것 넷: ① 나이 계산의 축(status_since, 없으면 updated·created),
② 사람이 읽는 표기(「37분째」·「1시간 52분째」), ③ 임계(30분)를 넘긴 줄의 표시와
목록 끝의 짚는 한 줄, ④ 세 자리(`s9 review` · `--quiet` 훅 주입 · `s9 digest`)가
같은 값을 낸다.

실행: python3 tests/ review_age
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
S9PY = os.path.join(ROOT, "bin", "s9.py")


def load(path, root, name):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, path))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class ReviewAgeText(unittest.TestCase):
    """계산과 표기 — 파일 없이 행 하나로 잰다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9ra-")
        cls.m = load(S9PY, cls.tmp, "s9_review_age")

    def row(self, mins, **extra):
        """지금으로부터 mins 분 전에 review 로 들어간 행."""
        import datetime
        at = (datetime.datetime.now().astimezone()
              - datetime.timedelta(minutes=mins))
        r = {"id": "REQ-20260910-999", "title": "t", "user": "alice",
             "status_since": at.isoformat()}
        r.update(extra)
        r["waited_min"] = self.m.review_wait_min(r)
        return r

    # S1/S2 -----------------------------------------------------------
    def test_s1_minutes(self):
        self.assertEqual(self.m.review_wait_text(0), "0분째")
        self.assertEqual(self.m.review_wait_text(37), "37분째")
        self.assertIn("판정 대기 12분째", self.m.review_age_text(self.row(12)))

    def test_s2_hours_and_minutes(self):
        self.assertEqual(self.m.review_wait_text(60), "1시간 0분째")
        self.assertEqual(self.m.review_wait_text(112), "1시간 52분째")
        self.assertIn("판정 대기 2시간 0분째", self.m.review_age_text(self.row(120)))

    # S3 --------------------------------------------------------------
    def test_s3_threshold_marks_the_line(self):
        self.assertEqual(self.m.REVIEW_STALE_MIN, 30)
        under = self.m.review_age_text(self.row(29))
        over = self.m.review_age_text(self.row(30))
        self.assertNotIn("⚠", under, under)
        self.assertIn("⚠", over, over)
        self.assertIn("30분 넘김", over)

    # S4 --------------------------------------------------------------
    def test_s4_nudge_only_when_any_over(self):
        self.assertEqual(self.m.review_stale_nudge([self.row(5), self.row(29)]), "")
        old = self.row(200, id="REQ-20260910-001")
        nudge = self.m.review_stale_nudge([self.row(3), old])
        self.assertIn("1건", nudge)
        self.assertIn("REQ-20260910-001", nudge)
        self.assertIn("리드가 지금", nudge)
        self.assertEqual(self.m.review_stale_nudge([]), "")

    def test_s4b_nudge_lists_at_most_six(self):
        rows = [self.row(90, id=f"REQ-20260910-{i:03d}") for i in range(1, 9)]
        nudge = self.m.review_stale_nudge(rows)
        self.assertIn("요청 8건", nudge)
        self.assertIn("외 2건", nudge)
        self.assertNotIn("REQ-20260910-007", nudge)

    # S6 --------------------------------------------------------------
    def test_s6_missing_or_broken_timestamp_does_not_raise(self):
        self.assertEqual(self.m.review_wait_min({}), 0)
        self.assertEqual(self.m.review_wait_min({"status_since": "깨진 값"}), 0)
        self.assertIn("판정 대기 0분째", self.m.review_age_text({"id": "x"}))
        # status_since 가 없으면 updated 로, 그것도 없으면 created 로
        import datetime
        at = (datetime.datetime.now().astimezone()
              - datetime.timedelta(minutes=45)).isoformat()
        self.assertEqual(self.m.review_wait_min({"updated": at}), 45)
        self.assertEqual(self.m.review_wait_min({"created": at}), 45)


class ReviewAgeCommands(unittest.TestCase):
    """세 자리가 같은 값을 낸다 — `s9 review` · `--quiet` · `s9 digest`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9rac-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_SESSION": "ra000000"}
        cls.env.pop("S9_AUTO_RESUME", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        cls.cli("user", "switch", "alice")
        cls.m = load(S9PY, cls.tmp, "s9_review_age_cmd")

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=60)
        if expect is not None:
            assert r.returncode == expect, f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}"
        return r

    @classmethod
    def mk_review(cls, title, minutes_ago):
        """review 상태로 세우고 status_since 를 minutes_ago 분 전으로 되돌린다."""
        import datetime
        doc = cls.cli("new", "request", "--title", title, "--summary", "s",
                      "--goal", "g", "--size", "S", "--user", "alice",
                      "--body", "x", "--root").stdout.split()[0]
        cls.cli("status", doc, "in-progress", "--note", "착수")
        cls.cli("status", doc, "review", "--note",
                "무엇이 달라졌나: 목록에 나이가 실린다. 어디서 보나: s9 review. "
                "무엇이 보이면 승인인가: 분이 보이면 승인.", "--force")
        path = cls.m.locate(doc)
        at = (datetime.datetime.now().astimezone()
              - datetime.timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        head, rest = text.split("\n---\n", 1)
        head = "\n".join(ln if not ln.startswith("status_since:")
                         else f"status_since: {at}" for ln in head.splitlines())
        with open(path, "w", encoding="utf-8") as f:
            f.write(head + "\n---\n" + rest)
        cls.cli("index", "rebuild")
        return doc

    # S1/S3/S4/S5/S7 --------------------------------------------------
    def test_s1_s7_all_three_places_show_age(self):
        fresh = self.mk_review("갓 올린 판정 건", 3)
        old = self.mk_review("오래 대기한 판정 건", 150)

        out = self.cli("review").stdout
        self.assertIn("판정 대기 3분째", out, out)
        self.assertIn("판정 대기 2시간 30분째", out, out)
        self.assertIn("⚠ 30분 넘김", out, out)
        # 짚는 줄은 임계를 넘긴 것만 세고, 갓 올린 것은 세지 않는다
        self.assertIn("요청 1건", out, out)

        # S7 — 훅 주입 경로: 확인 포인트는 봉투 안, 짚는 줄은 봉투 밖 한 줄
        q = self.cli("review", "--quiet").stdout
        self.assertIn("판정 대기 2시간 30분째", q, q)
        self.assertIn("확인 포인트", q, q)
        nudge_lines = [ln for ln in q.splitlines() if ln.startswith("⚠")]
        self.assertEqual(len(nudge_lines), 1, q)
        self.assertIn(old, nudge_lines[0])
        self.assertNotIn(fresh, nudge_lines[0])

        # S5 — 세션 시작 주입(digest)
        d = self.cli("digest").stdout
        self.assertIn("판정 대기 3분째", d, d)
        self.assertIn("판정 대기 2시간 30분째", d, d)
        self.assertIn(f"{self.m.REVIEW_STALE_MIN}분 넘게 판정을 기다리는 요청", d, d)


class ReviewAgeEmpty(unittest.TestCase):
    """S8 회귀 — 판정 대기가 하나도 없으면 출력이 그대로다 (제 저장소에서 잰다)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9rae-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_SESSION": "ra111111"}
        cls.env.pop("S9_AUTO_RESUME", None)
        subprocess.run([S9, "init"], capture_output=True, text=True,
                       env=cls.env, timeout=60, check=True)

    def cli(self, *argv):
        return subprocess.run([S9, *argv], capture_output=True, text=True,
                              env=self.env, timeout=60).stdout

    def test_s8_empty_list_unchanged(self):
        self.assertIn("(확인 대기 없음)", self.cli("review"))
        self.assertEqual(self.cli("review", "--quiet").strip(), "")


if __name__ == "__main__":
    unittest.main()
