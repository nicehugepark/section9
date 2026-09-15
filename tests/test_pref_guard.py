"""개인 선호를 쓰는 자리의 검사 셋 (REQ-20260915-045-62x6 점검에서 나온 것).

이 값은 보통 설정이 아니다 — **매 턴 프롬프트의 지시문 자리에 그대로 실린다**
(REQ-20260824-006). 그래서 쓰는 자리의 검사가 곧 그 세션이 무엇을 읽느냐의 검사다.

지키는 것 셋.

  ① **남의 것은 본인이나 admin 만** (REQ-20260915-048-62x6). 대시보드 POST 는 이
     판정을 했지만 CLI 는 그 자리를 지나지 않아, 등록된 member 가
     `s9 user config <남> pref_x '<문장>'` 로 남의 세션에 매 턴 실릴 문장을 넣을 수
     있었다. 판정은 **설정을 쓰는 단 하나의 함수**에 선다 — 두 길이 한 자리에서
     막힌다(REQ-20260902-029 가 role 에서 겪은 갈림의 되풀이를 여기서 끊는다).
  ② **상한** (REQ-20260915-050-62x6). 실측에서 5천자가 검사 없이 저장되고 전량
     주입됐다. 붙여넣기 사고 하나가 모든 턴의 자리를 먹는다.
  ③ **사람이 아닌 주체는 제 길로 지나간다.** actor 자리에는 이 컴퓨터의 동작이
     오기도 한다(「dashboard model change」·「s9 env inherit」) — 그것까지 막으면
     화면의 평범한 저장이 멎는다.

실행: python3 tests/ pref_guard
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class PrefGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9-prefguard-")
        cls._prev = os.environ.get("S9_ROOT")
        os.environ["S9_ROOT"] = cls.root
        spec = importlib.util.spec_from_loader(
            "s9_pref_guard", importlib.machinery.SourceFileLoader("s9_pref_guard", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        os.makedirs(os.path.join(cls.root, "users"), exist_ok=True)
        for name, role in (("alice", "member"), ("bob", "member"),
                           ("root9", "admin"), ("val", "viewer")):
            cls.m.do_user_add(name, role=role)

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = cls._prev
        shutil.rmtree(cls.root, ignore_errors=True)

    def cfg(self, name):
        p = os.path.join(self.root, "users", name, "config", "settings.json")
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return {}

    # ── ① 남의 것 ────────────────────────────────────────────────────────
    def test_a_member_cannot_write_another_persons_preference(self):
        with self.assertRaises(ValueError) as e:
            self.m.do_user_config_set("bob", "pref_말투", "아주 짧게", actor="alice")
        self.assertIn("admin", str(e.exception))
        self.assertNotIn("pref_말투", self.cfg("bob"), "남의 설정이 써졌다")

    def test_my_own_is_mine(self):
        self.m.do_user_config_set("alice", "pref_말투", "짧게", actor="alice")
        self.assertEqual(self.cfg("alice").get("pref_말투"), "짧게")

    def test_a_viewer_can_still_write_their_own(self):
        self.m.do_user_config_set("val", "pref_말투", "짧게", actor="val")
        self.assertEqual(self.cfg("val").get("pref_말투"), "짧게")

    def test_an_admin_may_write_for_someone_else(self):
        self.m.do_user_config_set("bob", "pref_보고", "표로", actor="root9")
        self.assertEqual(self.cfg("bob").get("pref_보고"), "표로")

    def test_a_machine_actor_passes_as_before(self):
        """사람 이름이 아닌 주체(이 컴퓨터의 동작)는 종전대로 — 화면의 평범한
        저장이 이 길로 온다(「dashboard model change」)."""
        self.m.do_user_config_set("alice", "last_model_choice", "opus",
                                  actor="dashboard model change")
        self.assertEqual(self.cfg("alice").get("last_model_choice"), "opus")

    # ── ② 상한 ──────────────────────────────────────────────────────────
    def test_a_preference_longer_than_the_cap_is_refused(self):
        big = "나" * (self.m.PREF_VALUE_MAX + 1)
        with self.assertRaises(ValueError) as e:
            self.m.do_user_config_set("alice", "pref_긴값", big, actor="alice")
        self.assertIn(str(self.m.PREF_VALUE_MAX), str(e.exception))
        self.assertNotIn("pref_긴값", self.cfg("alice"))

    def test_the_cap_does_not_cut_lines(self):
        """여러 줄은 막지 않는다 — 사람이 줄을 나눠 적을 자리다."""
        self.m.do_user_config_set("alice", "pref_여러줄", "첫 줄\n둘째 줄", actor="alice")
        self.assertEqual(self.cfg("alice").get("pref_여러줄"), "첫 줄\n둘째 줄")

    def test_a_machine_value_is_not_capped(self):
        long_fp = "f" * (self.m.PREF_VALUE_MAX + 50)
        self.m.do_user_config_set("alice", "machine_fp", long_fp, actor="alice")
        self.assertEqual(self.cfg("alice").get("machine_fp"), long_fp)

    # ── 회귀 ────────────────────────────────────────────────────────────
    def test_the_old_contracts_still_hold(self):
        self.m.do_user_config_set("alice", "pref_응답 형식", "표로", actor="alice")
        self.assertEqual(self.cfg("alice").get("pref_응답 형식"), "표로")
        self.m.do_user_config_set("alice", "pref_응답 형식", "", actor="alice")
        self.assertNotIn("pref_응답 형식", self.cfg("alice"), "빈 값이 지우지 않았다")
        with self.assertRaises(ValueError):
            self.m.do_user_config_set("alice", "pref_a!b", "x", actor="alice")

    def test_a_viewer_still_cannot_touch_another(self):
        with self.assertRaises(ValueError):
            self.m.do_user_config_set("alice", "pref_말투", "x", actor="val")


if __name__ == "__main__":
    unittest.main()
