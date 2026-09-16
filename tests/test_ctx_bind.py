"""s9.py 를 가르는 이음매 — 부모가 이름공간을 건넨다 (REQ-20260916-018-62x6).

설계는 DOC-20260916-003-62x6. **값은 옮긴 여섯이 아니라 장치다** — 자식이 부모를
import 하지 않고 부모가 제 globals 를 건네므로, 다음 조각(동기화 전용 17개)이
전역과 남의 함수에 **엉킨 채로도** 옮겨진다. 옮기기만으로는 그 엉킴에 막힌다
(리드 실측: 공용이라던 20개 중 혼자 서는 것은 6개뿐이었다).

실행: python3 tests/ ctx_bind
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9.py")
CTX = os.path.join(HERE, "..", "bin", "s9_ctx.py")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TheParentHandsOverItsNamespace(unittest.TestCase):

    def setUp(self):
        self.ctx = _load("s9ctx_t", CTX)

    # n3 — 건네받은 뒤에는 부모의 이름을 읽는다
    def test_a_bound_name_is_read_back(self):
        self.ctx.bind({"ROOT": "/tmp/x", "SERVE_STARTED": ""})
        self.assertEqual("/tmp/x", self.ctx.g("ROOT"))

    # 사전 **자체**를 쥔다 — 뒤에 정해지는 이름도 보인다
    def test_a_name_set_after_bind_is_still_seen(self):
        ns = {"SERVE_STARTED": ""}
        self.ctx.bind(ns)
        ns["SERVE_STARTED"] = "2026-09-16T13:00:00+09:00"
        self.assertEqual("2026-09-16T13:00:00+09:00",
                         self.ctx.g("SERVE_STARTED"))

    # f1 — 모르는 것을 지어내지 않는다
    def test_an_unbound_name_raises(self):
        with self.assertRaises(KeyError):
            self.ctx.g("없는이름")

    # 이 장치가 있어야 설 수 있는 함수
    def test_the_helper_that_needs_the_parent_works(self):
        self.ctx.bind({"SERVE_STARTED": "", "_NOTICE_EPOCH": "바닥값"})
        self.assertEqual("바닥값", self.ctx._notice_epoch())
        self.ctx.bind({"SERVE_STARTED": "떴다", "_NOTICE_EPOCH": "바닥값"})
        self.assertEqual("떴다", self.ctx._notice_epoch())

    # b1 — 순환이 없다
    def test_the_child_does_not_import_the_parent(self):
        with open(CTX, encoding="utf-8") as f:
            src = f.read()
        for bad in ("import s9\n", "from s9 ", "s9.py"):
            if bad == "s9.py":
                continue          # 설명글에는 나온다 — 코드가 아니다
            self.assertNotIn(bad, src, "자식이 부모를 import 한다")


class TheParentStillAnswersToTheOldNames(unittest.TestCase):
    """시험 345개가 `s9.now_iso()` 처럼 부른다 — 그 이름이 그대로 들어야 한다."""

    def setUp(self):
        self.m = _load("s9_ctx_reexport", S9)

    def test_the_six_are_callable_on_the_parent(self):
        self.assertTrue(self.m.now_iso().startswith("20"))
        self.assertTrue(self.m.current_machine())
        self.assertEqual(0.0, self.m._iso_epoch("아님"))
        self.assertEqual(12, len(self.m._notice_sig("a", "b")))
        self.assertTrue(callable(self.m.die))

    def test_the_parent_bound_itself(self):
        # 부모가 제 이름공간을 건넸으므로 자식이 부모의 전역을 읽는다
        self.assertEqual(self.m.ROOT, self.m._ctx.g("ROOT"))

    def test_the_helper_needing_globals_works_through_the_parent(self):
        self.assertTrue(self.m._notice_epoch())

    # b3 — 자식을 캐시하지 않는다(시험이 S9_ROOT 를 바꿔 다시 올려 격리한다)
    def test_the_child_is_not_cached_in_sys_modules(self):
        import sys
        self.assertNotIn("s9_s9_ctx", sys.modules)


class TheSyncPrivatesMovedWithoutBeingRewritten(unittest.TestCase):
    """조각 2 — 동기화 전용 열일곱이 옮겨졌고 **코드는 안 바뀌었다**
    (REQ-20260916-019-62x6).

    그럴 수 있는 까닭이 bind 다: 부모가 이름을 자식의 전역으로 꽂으므로
    `ROOT` 를 `g("ROOT")` 로 바꿀 필요가 없다. 고른 근거는 센 값이다 —
    그 열일곱이 필요로 하는 35개 중 **늦게 정해지는 것이 0개**다.
    """

    MOVED = ("_ago_word", "_conflict_label", "_rebase_in_progress",
             "_session_docs", "commit_module", "git_run",
             "harness_id_from_transcript", "machine_recv_beat",
             "note_call_name", "parse_cross_session", "resolve_call_names")

    def setUp(self):
        self.m = _load("s9_p2", S9)

    def test_the_parent_still_answers_to_them(self):
        for n in self.MOVED:
            with self.subTest(n=n):
                self.assertTrue(callable(getattr(self.m, n, None)),
                                "%s 가 s9.py 에서 사라졌다" % n)

    def test_they_really_live_in_the_child(self):
        for n in self.MOVED:
            with self.subTest(n=n):
                self.assertIs(getattr(self.m, n), getattr(self.m._sync_mod, n))

    def test_the_child_sees_the_parents_names(self):
        # 이름이 꽂혔다 — 옮긴 코드가 그대로 도는 까닭
        self.assertEqual(self.m.ROOT, self.m._sync_mod.ROOT)
        self.assertTrue(callable(self.m._sync_mod._sync_git))

    def test_a_moved_function_actually_runs(self):
        # 글자가 아니라 **동작**을 잰다 — 부모의 전역·함수를 그대로 쓴다
        self.assertEqual("", self.m.parse_cross_session("사람이 친 말") or "")
        got = self.m.parse_cross_session(
            '<cross-session-message from="bridge:x" from-name="맥">\n안녕')
        self.assertEqual(("bridge:x", "맥"), got)
        self.assertEqual("없음", self.m._ago_word(0, 1_700_000_000.0))

    def test_the_child_stands_without_the_parent(self):
        """순환이 없다 — 자식만 따로 올려도 선다(부모를 import 하지 않으므로)."""
        child = _load("s9sync_alone", os.path.join(HERE, "..", "bin", "s9_sync.py"))
        self.assertTrue(callable(child.parse_cross_session))
        # 아직 아무 이름도 안 꽂혔다 — 부모가 건네야 도는 함수는 NameError 다
        with self.assertRaises(NameError):
            child.git_run(["status"])


if __name__ == "__main__":
    unittest.main()
