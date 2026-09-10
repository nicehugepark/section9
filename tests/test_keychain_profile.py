"""맥에서 프로필 계정도 제 Keychain 항목으로 사용량을 본다 (REQ-20260910-014-2n7g).

주인 지적 2026-09-10 23:53: 「사용량이 안 나오는 건 결함이 아닌 것이 아니라
결함이다. 이유가 있다면 이유를 고쳐야지.」 이유는 이것이었다 — Claude Code 는
프로필마다 Keychain 항목을 따로 두는데(기본 자리 「Claude Code-credentials」,
프로필 「Claude Code-credentials-<sha256(경로)[:8]>」), 우리는 활성 자리의 접미
없는 항목만 읽어 프로필로 뜬 세션의 사용량이 늘 「—」였다. claude04 프로필
경로의 해시 앞 8자가 실제 Keychain 항목(71b3ff26)과 맞았다.

실행: python3 tests/ keychain_profile
"""
import hashlib
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
PLAIN = "Claude Code-credentials"


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_kc", importlib.machinery.SourceFileLoader("s9_kc", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _keychain(items):
    """항목 이름 → 자격증명 JSON 을 아는 가짜 `security`."""
    def run(argv, **kw):
        svc = argv[3]
        class R:
            returncode = 0 if svc in items else 44
            stdout = items.get(svc, "")
        return R()
    return run


class KeychainProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()
        cls.tmp = tempfile.mkdtemp(prefix="s9kc-")
        cls.prof = os.path.join(cls.tmp, "profiles", "who@x")
        os.makedirs(cls.prof)
        cls.suffix = hashlib.sha256(os.path.abspath(cls.prof).encode("utf-8")).hexdigest()[:8]

    def test_k1_profile_name_is_the_path_hash(self):
        """핵심 — 프로필의 항목 이름은 경로 sha256 앞 8자 접미, 기본 자리는 접미 없음."""
        self.assertEqual(self.m.keychain_service_names(self.prof)[0], f"{PLAIN}-{self.suffix}")
        self.assertEqual(self.m.keychain_service_names("~/.claude"), [PLAIN])

    def test_k2_profile_reads_its_own_item(self):
        """정상 — 활성 자리가 아니어도 제 항목이 있으면 자격증명이 온다."""
        run = _keychain({f"{PLAIN}-{self.suffix}":
                         '{"claudeAiOauth": {"accessToken": "t", "subscriptionType": "max"}}'})
        with mock.patch.object(self.m, "claude_home", lambda: os.path.join(self.tmp, "elsewhere")):
            got = self.m.read_claude_oauth(self.prof, platform="darwin", run=run)
        self.assertEqual((got or {}).get("subscriptionType"), "max",
                         "프로필로 뜬 세션의 사용량이 「—」로 남는 그 결함이다")

    def test_k3_profile_never_borrows_the_default_item(self):
        """경계 — 기본 자리의 항목만 있으면 프로필은 아무것도 받지 않는다(남의 사용량 금지)."""
        run = _keychain({PLAIN: '{"claudeAiOauth": {"accessToken": "t"}}'})
        with mock.patch.object(self.m, "claude_home", lambda: os.path.join(self.tmp, "elsewhere")):
            self.assertIsNone(self.m.read_claude_oauth(self.prof, platform="darwin", run=run))

    def test_k4_active_profile_still_falls_back_to_the_plain_name(self):
        """회귀 — 프로필이 활성 자리이기도 하면 접미 없는 옛 항목도 뒤에 본다."""
        run = _keychain({PLAIN: '{"claudeAiOauth": {"accessToken": "t", "subscriptionType": "pro"}}'})
        with mock.patch.object(self.m, "claude_home", lambda: self.prof):
            got = self.m.read_claude_oauth(self.prof, platform="darwin", run=run)
        self.assertEqual((got or {}).get("subscriptionType"), "pro")

    def test_k5_missing_item_says_how_to_log_in(self):
        """경계 — 항목이 없을 때의 문장은 로그인하는 길을 말한다."""
        src = open(S9 + ".py", encoding="utf-8").read()
        i = src.index("Keychain 에 이 프로필의 항목이 없다")
        self.assertIn("로그인", src[i:i + 200])


if __name__ == "__main__":
    unittest.main(verbosity=2)
