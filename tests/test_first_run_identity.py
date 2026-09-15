"""첫 실행의 신원 잇기 — 이미 있는 이름이면 attach, 없으면 add (REQ-20260906-075).

두 번째 기계의 첫 `s9 code` 가 이름을 묻고 무조건 user add 를 돌려, 다른 기계에서
등록한 내 이름을 치면 「이미 있다」로 실패하고 계정이 미등록으로 남았다(맥미니 실제 발생
2026-09-06). 주인 지적: s9 code 가 사용자를 입력받으니 attach 를 따로 할 필요가 없어야 한다.

실행: python3 tests/ first_run_identity
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class FirstRunIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader("s9_fri", importlib.machinery.SourceFileLoader("s9_fri", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    # F1. 이미 있는 이름을 치면 attach — 물음에 등록된 이름이 보인다
    def test_f1_existing_name_attaches(self):
        asked = []
        verb, name = self.m.first_run_identity("seongjinpark", ["nicehugepark", "bob"],
                                               lambda q: asked.append(q) or "nicehugepark")
        self.assertEqual((verb, name), ("attach", "nicehugepark"))
        self.assertIn("nicehugepark", asked[0]); self.assertIn("bob", asked[0])

    # F2. 없는 이름이면 add
    def test_f2_new_name_adds(self):
        self.assertEqual(self.m.first_run_identity("me", ["nicehugepark"], lambda q: "carol"),
                         ("add", "carol"))

    # F3. Enter 는 OS 계정 이름의 새 사람 — 그 이름이 이미 있으면 attach
    def test_f3_enter_means_the_os_account(self):
        self.assertEqual(self.m.first_run_identity("me", ["nicehugepark"], lambda q: ""), ("add", "me"))
        self.assertEqual(self.m.first_run_identity("nicehugepark", ["nicehugepark"], lambda q: "  "),
                         ("attach", "nicehugepark"))

    # ── 못 쓸 이름을 기본값으로 내밀지 않는다 (REQ-20260915-013-62x6) ────────────
    #
    # 실제 사고 2026-09-15: 한글 OS 계정(박성진)에서 그냥 Enter 를 쳤더니 그 이름이
    # 그대로 등록으로 가 「한글은 안 된다」는 오류만 남기고 화면은 다음 걸음(Claude
    # 로그인)으로 넘어갔다 — 사람은 왜 막혔는지도 무엇을 쳐야 하는지도 모른 채
    # 미등록으로 남았다. 주인 물음: 「한글을 못 쓰는게 맞는건가?」
    def test_f4_a_korean_os_account_is_not_offered_as_the_default(self):
        """F4. 기본값은 쓸 수 있는 이름일 때만 — 없으면 git 이메일의 앞부분."""
        asked = []
        verb, name = self.m.first_run_identity(
            "박성진", [], lambda q: asked.append(q) or "",
            email="nicehugepark@example.com")
        self.assertEqual((verb, name), ("add", "nicehugepark"))
        self.assertIn("Enter=nicehugepark", asked[0])
        self.assertNotIn("Enter=박성진", asked[0])

    def test_f5_no_english_anywhere_means_the_rule_is_shown_and_asked_again(self):
        """F5. 이메일도 한글 계정이면 기본값이 없다 — 규칙을 보이고 다시 묻는다."""
        asked, said = [], []
        verb, name = self.m.first_run_identity(
            "박성진", [], lambda q: asked.append(q) or (["", "sjpark"][len(asked) - 1]),
            email="", out=said.append)
        self.assertEqual((verb, name), ("add", "sjpark"))
        self.assertEqual(len(asked), 2, "빈 Enter 뒤에 다시 묻지 않았다")
        self.assertIn(self.m.USER_NAME_RULE, asked[0])
        self.assertTrue(any("표시 이름" in s for s in said),
                        "한글 이름이 어디로 가는지 말하지 않았다")

    def test_f6_it_never_hands_back_a_name_that_cannot_be_registered(self):
        """F6. 끝내 못 정하면 skip — 못 쓸 이름을 등록으로 넘기지 않는다."""
        verb, name = self.m.first_run_identity("박성진", [], lambda q: "김철수",
                                               email="", out=lambda s: None)
        self.assertEqual((verb, name), ("skip", ""))

    def test_f7_the_rule_lives_in_one_place(self):
        """F7. 판정은 한 곳(user_name_ok)이고 등록도 그것을 쓴다."""
        self.assertTrue(self.m.user_name_ok("nice.hugepark-1_2"))
        for bad in ("박성진", "", "  ", "nice hugepark", "a/b", "a@b"):
            self.assertFalse(self.m.user_name_ok(bad), bad)
        self.assertEqual(self.m.user_name_from("박성진", "nicehugepark@x.com"), "nicehugepark")
        self.assertEqual(self.m.user_name_from("박성진", "박성진@x.com"), "")
        self.assertEqual(self.m.user_name_from("bob", "other@x.com"), "bob")
        with self.assertRaises(ValueError) as e:
            self.m.do_user_add("박성진")
        self.assertIn("display", str(e.exception), "한글 이름이 갈 자리를 말하지 않는다")


if __name__ == "__main__":
    unittest.main()
