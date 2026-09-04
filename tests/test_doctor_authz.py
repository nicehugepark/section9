"""역할의 진실은 GitHub 권한, profile 은 캐시 (REQ-20260902-034).

실행: python3 tests/ doctor_authz
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, "..", "bin", "s9-doctor")


class DoctorAuthz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_loader(
            "s9_doctor_authz", importlib.machinery.SourceFileLoader("s9_doctor_authz", DOC))
        cls.d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.d)

    def gh(self, perms, private=False):
        def fake(path):
            if path.startswith("repos/") and "/collaborators/" not in path:
                return {"private": private}
            u = path.split("/collaborators/")[1].split("/")[0]
            return {"permission": perms[u]} if u in perms else None
        return fake

    # P1. 일치
    def test_doctor_authz(self):
        """DoctorAuthz 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("p1_match"):
                a = self.d.authz_info("o/r", {"root": {"role": "admin", "github": "root-gh"},
                                              "bob": {"role": "member", "github": "bob-gh"},
                                              "eve": {"role": "viewer", "github": "eve-gh"}},
                                      self.gh({"root-gh": "admin", "bob-gh": "write",
                                               "eve-gh": "read"}, private=True))
                self.assertEqual(a["mismatch"], [])
                self.assertEqual(len(a["checked"]), 3)
                v = self.d.authz_verdict(a)
                self.assertEqual(v["level"], "ok")

            # P2. 불일치 양방향
        with self.subTest("p2_mismatch_both_ways"):
                a = self.d.authz_info("o/r", {"root": {"role": "admin", "github": "root-gh"},
                                              "bob": {"role": "member", "github": "bob-gh"}},
                                      self.gh({"root-gh": "write", "bob-gh": "admin"}, private=True))
                self.assertEqual({m["user"] for m in a["mismatch"]}, {"root", "bob"})
                v = self.d.authz_verdict(a)
                self.assertEqual(v["level"], "warn")
                self.assertIn("역할 불일치", v["line"])
                self.assertIn("GitHub 권한", v["advice"])

            # P3. 건너뜀·확인 불가
        with self.subTest("p3_skips_and_unavailable"):
                a = self.d.authz_info("o/r", {"nogh": {"role": "member", "github": ""},
                                              "gone": {"role": "member", "github": "gone-gh"}},
                                      self.gh({}, private=True))
                self.assertEqual(sorted(a["skipped"]), ["gone", "nogh"])
                self.assertEqual(a["mismatch"], [])
                a2 = self.d.authz_info("", {}, self.gh({}))
                self.assertTrue(a2["unavailable"])
                self.assertEqual(self.d.authz_verdict(a2)["level"], "ok")
                a3 = self.d.authz_info("o/r", {}, lambda p: None)
                self.assertTrue(a3["unavailable"])

            # P4. public + vault track → 경고
        with self.subTest("p4_public_vault_warns"):
                a = self.d.authz_info("o/r", {}, self.gh({}, private=False))
                if a["vault_tracked"]:          # 이 리포는 실제로 그렇다
                    v = self.d.authz_verdict(a)
                    self.assertEqual(v["level"], "warn")
                    self.assertIn("public", v["line"])
                a["public"], a["vault_tracked"] = True, True
                self.assertIn("instance init", self.d.authz_verdict(a)["advice"])
                a["public"] = False
                self.assertEqual(self.d.authz_verdict(a)["level"], "ok")

            # slug 파싱
        with self.subTest("origin_slug_forms"):
            import re
            pat = r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$"
            for url in ("git@github.com:o/r.git", "https://github.com/o/r", "https://github.com/o/r.git"):
                m = re.search(pat, url)
                self.assertEqual((m.group(1), m.group(2)), ("o", "r"), url)

if __name__ == "__main__":
    unittest.main()
