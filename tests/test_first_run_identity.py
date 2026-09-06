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


if __name__ == "__main__":
    unittest.main()
