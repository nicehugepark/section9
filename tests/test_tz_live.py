"""시간대를 바꾸면 서버를 다시 띄우지 않아도 따라온다 (REQ-20260828-030-62x6).

ux-writer 가 REQ-20260828-029 설계 중 실측했다: `TZ = display_tz()` 가
`cmd_serve` 안에서 **한 번** 계산된다. 그래서 개인 설정 timezone 을 바꿔도
Stream·터미널의 타임스탬프는 서버를 다시 띄우기 전까지 옛 시간대로 남는다.

이것을 문구로 덮으면 안 된다 — "서버를 다시 시작하면 반영됩니다" 는 결함에
자막을 다는 것이다. 설정을 바꾼 사람은 화면이 따라올 것이라 믿고, 안 따라오면
설정이 안 먹었다고 읽는다. REQ-20260828-029 가 저장 알림에서 "화면 시각이
따라갑니다" 라고 넓게 약속하지 못한 이유가 이것이다.

캐시를 지우는 것이 아니라 **매번 해석한다.** 이 값은 설정 파일 한 줄을 읽는
것이고(zoneinfo 는 자체 캐시가 있다), 그 비용은 "재기동 전까지 틀린 시각을
보여 준다" 는 대가보다 훨씬 싸다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ tz_live
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class TzLive(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9tzl-")
        self.env = {**os.environ, "S9_ROOT": self.root}
        self.env.pop("S9_TZ", None)
        subprocess.run([S9, "init"], capture_output=True, env=self.env)
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=self.env, stdin=subprocess.DEVNULL)
        os.environ["S9_ROOT"] = self.root
        os.environ.pop("S9_TZ", None)
        spec = importlib.util.spec_from_loader(
            "s9_tzl", importlib.machinery.SourceFileLoader("s9_tzl", S9))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def _set_tz(self, name):
        d = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"timezone": name}, f)

    # N1. 해석은 부를 때마다 지금 설정을 본다.
    def test_n1_resolves_each_call(self):
        self.assertTrue(hasattr(self.m, "display_tz"),
                        "display_tz 가 모듈 수준에 없다 — serve 안에 갇혀 있으면 "
                        "요청마다 다시 해석할 수 없다")
        self._set_tz("Asia/Seoul")
        a = self.m.display_tz("alice")
        self._set_tz("America/New_York")
        b = self.m.display_tz("alice")
        self.assertNotEqual(str(a), str(b),
                            "설정을 바꿨는데 같은 시간대를 준다 — "
                            "재기동 전까지 옛 시간대로 남는다")
        self.assertIn("New_York", str(b))

    # N2. 그 시간대로 실제 시각이 변환된다.
    def test_n2_stamp_follows(self):
        self._set_tz("Asia/Seoul")
        seoul = self.m.local_ts("2026-08-28T00:00:00+00:00", "alice")
        self._set_tz("America/New_York")
        ny = self.m.local_ts("2026-08-28T00:00:00+00:00", "alice")
        self.assertRegex(seoul, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertNotEqual(seoul, ny, "같은 UTC 를 같은 벽시계로 그린다")
        self.assertTrue(seoul.startswith("2026-08-28 09:"), seoul)
        self.assertTrue(ny.startswith("2026-08-27 20:"), ny)

    # B1. $S9_TZ 가 설정보다 앞선다 (기존 계약).
    def test_b1_env_wins(self):
        self._set_tz("Asia/Seoul")
        os.environ["S9_TZ"] = "Europe/Berlin"
        try:
            self.assertIn("Berlin", str(self.m.display_tz("alice")))
        finally:
            os.environ.pop("S9_TZ", None)

    # B2. 설정이 없거나 이름이 틀리면 시스템 로컬 — 조용히 물러선다.
    def test_b2_bad_or_missing_falls_back(self):
        self.assertIsNone(self.m.display_tz("alice"))
        self._set_tz("Mars/Olympus")
        self.assertIsNone(self.m.display_tz("alice"))

    # B3. 서버 코드가 기동 시 1회 계산한 값을 붙들지 않는다.
    def test_b3_serve_does_not_freeze_it(self):
        src = open(os.path.join(HERE, "..", "bin", "s9.py"),
                   encoding="utf-8").read()
        self.assertNotRegex(
            src, r"\n    TZ = display_tz\(\)",
            "cmd_serve 가 기동 시 1회 계산한 값을 들고 돈다 — "
            "설정을 바꿔도 재기동 전까지 안 따라온다")


if __name__ == "__main__":
    unittest.main()
