"""가이드가 이름을 대는 시작 파일은 그 판의 배포판에 들어 있다 (REQ-20260918-006-62x6).

실제 사고 2026-09-18: 주인이 GitHub 릴리스의 `section9-0.9.1-windows.zip` 을 받아
풀었는데 `section9.cmd` 가 없었다. 사라진 것이 아니라 **그 판에 없던 것**이다 —
태그 v0.9.1 은 2026-09-14 에 땄고, 탐색기에서 두 번 눌러 시작하는 파일 셋
(section9.cmd · section9-dashboard.cmd · section9-stop.cmd)은 그 다음 날인
2026-09-15 에 들어왔다(REQ-20260915-006-62x6). 그 사이 나흘 동안 코드 commit 이
147 개 쌓이는 동안 VERSION 은 0.9.1 그대로였고, 가이드는 머리에 「기준 버전 0.9.1」을
달고 A-3 에서 「폴더 맨 위의 section9.cmd 를 두 번 누릅니다」라고 적었다.

받은 사람에게는 이것이 「파일이 사라졌다」로 보인다. 아무도 보지 않던 것은 하나다 —
**가이드가 이름을 대는 파일이 그 판의 배포판에 실제로 들어 있는가.**

이 시험이 그것을 본다. `tests/test_release_archive.py` 는 *지금 HEAD* 로 지은
배포판의 내용을 보고, 이 시험은 *이미 나간 판*(VERSION 과 같은 이름의 태그)과
가이드가 맞는지를 본다. 둘은 다른 자리다.

실행: python3 tests/ release_guide_match
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUIDE = os.path.join(ROOT, "docs", "guide-windows.md")
VERSION_RE = re.compile(r"기준 버전\s+v?(\d+\.\d+\.\d+)")


def read_version():
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def guide_text():
    with open(GUIDE, encoding="utf-8") as f:
        return f.read()


def guide_version(text):
    """가이드 머리의 「기준 버전 X」 — 없으면 None."""
    m = VERSION_RE.search(text)
    return m.group(1) if m else None


def launchers_named(text, present):
    """가이드가 이름을 대는 최상위 실행 파일 — `present` 에 실제로 있는 것만.

    작업 트리에 없는 이름은 세지 않는다: 가이드가 앞으로 만들 파일을 먼저 적었을 수
    있고, 없는 파일을 배포판에서 찾는 것은 뜻이 없다(경계 ④)."""
    return sorted(n for n in present if n in text)


def top_level_cmds():
    """작업 트리 맨 위의 *.cmd — 탐색기에서 두 번 누르는 것들."""
    return sorted(n for n in os.listdir(ROOT) if n.endswith(".cmd"))


def tag_exists(tag):
    r = subprocess.run(["git", "-C", ROOT, "tag", "-l", tag], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == tag


def missing_in_tag(tag, names):
    """그 태그의 트리에 없는 이름들."""
    out = []
    for n in names:
        r = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", f"{tag}:{n}"], capture_output=True)
        if r.returncode != 0:
            out.append(n)
    return out


class TheGuideMatchesTheReleasedVersion(unittest.TestCase):

    def setUp(self):
        self.ver = read_version()
        self.text = guide_text()

    def test_a1_the_named_launchers_are_in_that_release(self):
        """정상 ① / 실패 ⑤ — 가이드가 두 번 누르라고 이름을 댄 파일이 그 판에 있다.

        나간 판(v<VERSION>)이 아직 없으면 건너뛴다(경계 ③): 판을 올린 commit 과
        태그를 따는 순간 사이가 그 자리다 — 그 사이를 막으면 판을 못 올린다."""
        tag = f"v{self.ver}"
        if not tag_exists(tag):
            self.skipTest(f"{tag} 를 아직 따지 않았다 — 판을 올리고 태그를 따기 전의 자리")
        named = launchers_named(self.text, top_level_cmds())
        self.assertTrue(named, "가이드가 최상위 실행 파일을 하나도 이름으로 대지 않는다")
        missing = missing_in_tag(tag, named)
        self.assertEqual(missing, [], (
            f"가이드는 {', '.join(missing)} 를 두 번 누르라고 하는데 {tag} 배포판에는 없다 — "
            f"VERSION 을 올리고 새 판을 내라 (받은 사람에게는 「파일이 사라졌다」로 보인다)"))

    def test_a2_the_guide_version_matches_the_version_file(self):
        """정상 ② — 가이드 머리의 「기준 버전」 과 VERSION 이 같다."""
        gv = guide_version(self.text)
        self.assertIsNotNone(gv, "guide-windows.md 머리에 「기준 버전 X」 가 없다")
        self.assertEqual(gv, self.ver,
                         f"가이드는 기준 버전 {gv} 라고 적는데 VERSION 은 {self.ver} 다")


class TheHelpersReadWhatTheyClaim(unittest.TestCase):
    """경계 — git 없이 함수만으로 재는 것들."""

    def test_b1_only_files_that_exist_are_counted(self):
        """경계 ④ — 가이드가 이름을 대도 작업 트리에 없으면 세지 않는다."""
        text = "폴더 맨 위의 `section9.cmd` 와 `section9-future.cmd` 를 두 번 누릅니다"
        self.assertEqual(launchers_named(text, ["section9.cmd", "section9-stop.cmd"]),
                         ["section9.cmd"])

    def test_b2_unnamed_launchers_are_not_demanded(self):
        """가이드가 말하지 않는 파일은 이 시험의 몫이 아니다."""
        self.assertEqual(launchers_named("아무 이름도 없다", ["section9.cmd"]), [])

    def test_b3_the_version_line_is_read_with_or_without_v(self):
        self.assertEqual(guide_version("verified 2026-09-18 · 기준 버전 0.9.2 (`s9 --version`)"), "0.9.2")
        self.assertEqual(guide_version("기준 버전 v1.0.0 ·"), "1.0.0")
        self.assertIsNone(guide_version("버전 이야기가 없는 줄"))

    def test_b4_the_tag_lookup_is_exact(self):
        """`git tag -l v0.9` 가 v0.9.1 을 집어 오면 엉뚱한 판을 본다."""
        self.assertFalse(tag_exists("v0.0.0-없는태그"))


if __name__ == "__main__":
    unittest.main()
