"""기계가 만들고 바로 버린 것만 자동으로 지운다 (REQ-20260915-073-62x6).

designer 실측 2026-09-15: 휴지통 122건 중 66건이 틀 제목이었고 그중 53건은
만들어진 지 **1분 안에** 버려졌다(표본: 17:38:36 만들고 17:38:42 삭제, 6초).
나이로만 가르면 사람이 하루 넘게 들고 있다 버린 것까지 함께 지운다 — 그래서
**셋을 모두** 만족할 때만 자동의 몫이다. 하나라도 어긋나면 손대지 않는다.

리드 실측 2026-09-16(이 고침 뒤): 휴지통 137건 중 틀 제목 81건, 그중 자동의
몫은 **59건**뿐이다 — 9건은 누가 손댔고 13건은 1분 밖이다. 이 22건을 남기는
것이 이 잣대가 정직하다는 증거다.

이 저장소에는 「지우는 것은 자동이 아니다」라는 규칙이 이미 있다
(`trash_keep_days`). 이것이 그 유일한 예외이고, 그 함수의 설명에 함께 적었다 —
두 규칙이 조용히 어긋나면 언젠가 한쪽만 고쳐진다.

실행: python3 tests/ trash_auto_purge
"""
import datetime
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")


def _now():
    return datetime.datetime.now().astimezone()


class OnlyTheMachineMadeAndUntouchedGoes(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9autopurge-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        spec = importlib.util.spec_from_loader(
            "s9_ap", importlib.machinery.SourceFileLoader("s9_ap", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def row(self, **kw):
        made = _now() - datetime.timedelta(days=30)
        e = {"id": "REQ-1", "type": "request",
             "title": '<agent-message from="ae0…',
             "created": made.isoformat(timespec="seconds"),
             "deleted": (made + datetime.timedelta(seconds=6)).isoformat(
                 timespec="seconds"),
             "untouched": True, "auto_purge_keep": False}
        e.update(kw)
        return e

    # 정상 — 셋을 다 만족하면 자동의 몫
    def test_all_three_make_it_a_candidate(self):
        self.assertTrue(self.m.auto_purge_candidate(self.row()))

    # ① 제목 — 사람이 지은 제목은 손대지 않는다
    def test_a_human_title_is_never_a_candidate(self):
        self.assertFalse(self.m.auto_purge_candidate(
            self.row(title="휴지통 자동 비우기")))
        self.assertFalse(self.m.auto_purge_candidate(self.row(title="")))

    # ② 1분 — 하루 들고 있다 버린 것은 사람이 판단한 것이다
    def test_thrown_away_later_than_a_minute_is_left_alone(self):
        made = _now() - datetime.timedelta(days=30)
        self.assertFalse(self.m.auto_purge_candidate(self.row(
            created=made.isoformat(timespec="seconds"),
            deleted=(made + datetime.timedelta(seconds=61)).isoformat(
                timespec="seconds"))))

    # ③ 손댄 적 — 노트·첨부·전이가 하나라도 있으면 남긴다
    def test_a_touched_document_is_left_alone(self):
        self.assertFalse(self.m.auto_purge_candidate(self.row(untouched=False)))

    # 사람의 손 — 한 번 남겨두기를 누르면 영영 빠진다
    def test_keep_takes_it_out_forever(self):
        self.assertFalse(self.m.auto_purge_candidate(
            self.row(auto_purge_keep=True)))

    # 모르면 손대지 않는다
    def test_unknown_times_are_never_purged(self):
        self.assertFalse(self.m.auto_purge_candidate(self.row(created="")))
        self.assertFalse(self.m.auto_purge_candidate(self.row(deleted="")))

    # 수명 — 자동의 몫이어도 7일을 넘겨야 지운다
    def test_a_fresh_candidate_is_not_due_yet(self):
        made = _now() - datetime.timedelta(days=1)
        e = self.row(created=made.isoformat(timespec="seconds"),
                     deleted=(made + datetime.timedelta(seconds=6)).isoformat(
                         timespec="seconds"))
        self.assertTrue(self.m.auto_purge_candidate(e))
        self.assertFalse(self.m.auto_purge_due(e), "하루 된 것을 지우려 한다")

    def test_an_old_candidate_is_due(self):
        self.assertTrue(self.m.auto_purge_due(self.row()))

    # 본문 판정 — 노트 한 줄이나 전이 한 줄이면 손댄 것이다
    def test_the_body_tells_whether_anyone_touched_it(self):
        bare = ("## Original\n\nx\n\n## Notes\n\n## History\n"
                "- 2026-09-15T17:38:36+09:00 created by nicehugepark\n")
        self.assertTrue(self.m._untouched_body(bare))
        noted = bare.replace("## Notes\n", "## Notes\n\n### 2026-09-15 노트\n\n내용\n")
        self.assertFalse(self.m._untouched_body(noted), "노트가 있는데 안 손댔다고 한다")
        moved = bare + "- 2026-09-15T17:39:00+09:00 status: open -> in-progress\n"
        self.assertFalse(self.m._untouched_body(moved), "전이가 있는데 안 손댔다고 한다")

    # 틀 제목 판정 — 잘린 제목에도 듣는다(제목은 20자에서 잘려 온다)
    def test_a_clipped_frame_title_still_counts(self):
        for t in ('<agent-message from="ae0…', "<cross-session-message f…",
                  "<future-frame kind=…"):
            self.assertTrue(self.m.frame_title(t), t)
        for t in ("<div class=…", "<b>굵게</b>", "휴지통", "<", "<a href=…"):
            self.assertFalse(self.m.frame_title(t), t)


class TheScreenSaysItBefore(unittest.TestCase):
    """지워지기 **전에** 말한다 — 지워진 뒤에 아는 것은 통보다."""

    def setUp(self):
        with open(os.path.join(HERE, "..", "web", "app", "tidy.js"),
                  encoding="utf-8") as f:
            self.src = f.read()

    def test_the_footer_promises_the_automatic_removal(self):
        self.assertIn("저절로 지워집니다", self.src, "약속을 안 한다")
        self.assertIn("남겨두기", self.src, "빠지는 길을 안 준다")

    def test_no_promise_is_made_while_it_is_off(self):
        """**기본은 끔**이고, 꺼져 있으면 지키지 않을 약속을 하지 않는다.

        실제 사고 2026-09-16 10:39: 되돌릴 수 없는 삭제를 사람 없는 자리에서
        돌게 해 놓고, 예고 시계를 「버린 때」로만 쟀다 — 규칙이 서는 순간
        이미 7일을 넘긴 것들이 예고와 **동시에** 지워졌다.
        """
        self.assertIn("tidyAuto.on", self.src, "켜짐 여부를 안 본다")
        self.assertIn("저절로 사라지지는 않습니다", self.src,
                      "꺼져 있을 때의 말이 없다")
        i = self.src.index("const footLine")
        seg = self.src[i:i + 1200]
        self.assertLess(seg.index("tidyAuto.n && tidyAuto.on"),
                        seg.index("if (tidyAuto.n)\n"),
                        "켜진 갈래를 먼저 보지 않는다")

    def test_the_count_and_days_come_from_the_server(self):
        # 화면이 같은 잣대를 한 벌 더 들면 언젠가 한 벌만 고쳐진다
        self.assertIn("j.auto_purge", self.src)
        self.assertIn("j.auto_purge_after_days", self.src)
        self.assertNotIn("r.created", self.src.split("footLine")[-1][:800],
                         "화면이 제 손으로 1분을 재고 있다")

    def test_the_keep_handle_sends_the_shared_op(self):
        i = self.src.index('what === "keepauto"')
        seg = self.src[i:i + 500]
        self.assertIn('tidySend("keep"', seg, "서버의 같은 길로 안 간다")
        self.assertIn("r.auto_purge", seg, "무엇을 남기는지 서버 판정을 안 읽는다")

    def test_the_promise_is_not_made_when_there_is_nothing(self):
        # 지키지 않을 약속은 적지 않는다
        i = self.src.index("const footLine")
        self.assertIn("if (tidyAuto.n)", self.src[i:i + 900])


class NothingIsDeletedUnattendedByDefault(unittest.TestCase):
    """사람이 켜기 전에는 스스로 지우지 않는다 (REQ-20260915-073-62x6).

    이 저장소의 규칙(「지우는 것은 자동이 아니다」)과 이 요청의 goal 이
    부딪힌다 — 되돌릴 수 없는 쪽의 판정을 코드가 혼자 하지 않는다.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9apoff-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.environ["S9_ROOT"] = self.root
        self.addCleanup(os.environ.pop, "S9_ROOT", None)
        spec = importlib.util.spec_from_loader(
            "s9_apoff", importlib.machinery.SourceFileLoader("s9_apoff", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_it_is_off_unless_someone_turns_it_on(self):
        self.assertFalse(self.m.trash_auto_purge_on("nobody"))

    def test_the_round_does_nothing_while_it_is_off(self):
        self.assertEqual([], self.m.auto_purge_tick(me="nobody"))

    def test_the_notice_clock_starts_when_it_is_first_shown(self):
        """예고 시계는 **버린 때**가 아니라 이 컴퓨터가 처음 말한 때부터다."""
        t = 1_700_000_000.0
        self.assertAlmostEqual(t, self.m.auto_purge_notice_at(now=t), places=1)
        # 한 번 찍힌 뒤에는 움직이지 않는다 — 켤 때마다 시계가 되감기면 안 된다
        self.assertAlmostEqual(
            t, self.m.auto_purge_notice_at(now=t + 99999), places=1)


class TheRuleAndItsExceptionAreWrittenTogether(unittest.TestCase):
    """「지우는 것은 자동이 아니다」 옆에 그 예외가 적혀 있다.

    두 규칙이 서로 다른 자리에 따로 있으면 언젠가 한쪽만 고쳐진다.
    """

    def test_the_exception_is_recorded_where_the_rule_is(self):
        with open(S9, encoding="utf-8") as f:
            src = f.read()
        i = src.index("def trash_keep_days(")
        seg = src[i:i + 1400]
        self.assertIn("지우는 것은 자동이 아니다", seg)
        self.assertIn("auto_purge_candidate", seg,
                      "예외가 그 규칙 옆에 안 적혀 있다")


if __name__ == "__main__":
    unittest.main()
