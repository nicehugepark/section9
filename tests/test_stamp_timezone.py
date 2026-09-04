"""시각 표시는 개인 설정 타임존을 따른다 (REQ-20260828-024-62x6).

사용자: "시각 표시에 KST로, 그리고 KST라고 출력이 되고 있는데 내가 지시를 그렇게
했었지만, settings의 개인설정 타임존을 따라가게 하는게 맞다."

훅이 매 턴 주입하는 `◈ 이 턴이 도착한 시각 …` 이 KST 로 못박혀 있었다(`now_kst()` 가
UTC+9 를 상수로 들고 있었다). 설정에 `timezone` 이 이미 있고 대시보드는 그것을
따르는데(`display_tz()`), 이 한 줄만 따로 놀았다 — 같은 물음에 두 답이 있으면
언젠가 갈린다.

라벨도 함께 따라가야 한다. 시각만 바꾸고 "KST" 를 그대로 두면 **틀린 시각을
확신 있게 적는 것**이 되어, 안 고친 것보다 나쁘다.

격리: 임시 S9_ROOT + 사용자 설정. 실행: python3 tests/ stamp_timezone
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
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class StampTimezone(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9tz-")
        subprocess.run([S9, "init"], capture_output=True,
                       env={**os.environ, "S9_ROOT": self.root})
        subprocess.run([S9, "user", "add", "tz-user"], capture_output=True,
                       env={**os.environ, "S9_ROOT": self.root},
                       stdin=subprocess.DEVNULL)
        self.m = _load("s9hook_tz", HOOK)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _cfg(self, **kv):
        d = os.path.join(self.root, "users", "tz-user", "config")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(kv, f)

    def _stamp(self):
        env = {**os.environ, "S9_ROOT": self.root}
        env.pop("S9_TZ", None)
        return self.m.stamp_context(env=env, who="tz-user")

    def test_n1_follows_configured_zone(self):
        self._cfg(timezone="Asia/Seoul")
        s = self._stamp()
        self.assertIn(" KST ", s, "설정이 서울인데 KST 로 안 적힌다")

    def test_n2_other_zone_is_not_kst(self):
        self._cfg(timezone="America/New_York")
        s = self._stamp()
        self.assertNotIn("KST", s, "설정을 바꿨는데 KST 가 그대로다")
        self.assertRegex(s, r"◈ 이 턴이 도착한 시각 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} E[SD]T",
                         "뉴욕 시간대 라벨이 아니다")

    def test_n3_time_and_label_agree(self):
        """라벨만 바꾸고 시각을 안 바꾸면 틀린 시각을 확신 있게 적는 꼴이다."""
        import datetime
        import zoneinfo
        self._cfg(timezone="America/New_York")
        s = self._stamp()
        m = re.search(r"◈ 이 턴이 도착한 시각 (\d{4}-\d{2}-\d{2} \d{2}:\d{2}):\d{2}", s)
        self.assertIsNotNone(m, s[:120])
        want = datetime.datetime.now(
            zoneinfo.ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
        self.assertEqual(m.group(1), want, "라벨만 바뀌고 시각이 안 따라왔다")

    def test_b1_no_setting_uses_system_local(self):
        self._cfg()
        s = self._stamp()
        self.assertRegex(s, r"◈ 이 턴이 도착한 시각 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+ —",
                         "설정이 없을 때 라벨이 비었다")

    def test_b2_bad_zone_falls_back_quietly(self):
        self._cfg(timezone="Mars/Olympus")
        s = self._stamp()          # 예외 없이 서야 한다
        self.assertIn("◈ 이 턴이 도착한 시각", s)

    def test_b3_two_lines_agree(self):
        """주입 문구는 시각을 두 번 적는다 — 둘이 다르면 모델이 어느 쪽을 쓸지 모른다."""
        self._cfg(timezone="Asia/Seoul")
        s = self._stamp()
        stamps = re.findall(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+?)(?: —| -)", s)
        self.assertGreaterEqual(len(stamps), 2, s[:160])
        self.assertEqual(stamps[0], stamps[1], "두 자리의 시각·라벨이 다르다")


class ProtocolText(unittest.TestCase):
    """B4 — 규약 문서의 폴백 명령도 KST 고정이면 안 된다."""

    def test_b4_docs_do_not_hardcode_kst_fallback(self):
        for p in ("CLAUDE.md", "harness/common/PROTOCOL.md"):
            txt = open(os.path.join(HERE, "..", p), encoding="utf-8").read()
            self.assertNotIn("%H:%M:%S KST", txt,
                             f"{p}: 폴백 명령이 KST 를 박아 넣는다")


if __name__ == "__main__":
    unittest.main()
