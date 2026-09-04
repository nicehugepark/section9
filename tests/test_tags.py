"""태그 자동 부여 테스트 (REQ-20260825-052).

태그가 기계 태그(auto-audit)뿐이면 태그 필터·주제 검색이 죽는다 — 생성
시점에 통제 어휘로 자동 부여하고, 사람이 붙인 태그는 건드리지 않는다.

실행: python3 tests/ tags
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
TMP = tempfile.mkdtemp(prefix="s9tag-")
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_tag", importlib.machinery.SourceFileLoader("s9_mod_tag", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestDeriveTags(unittest.TestCase):
    # G1. 도메인 어휘 → 통제 태그
    def test_test_derive_tags(self):
        """TestDeriveTags 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g1_domain_vocab"):
                self.assertIn("terminal", mod.derive_tags(
                    "웨이팅 스피너 정리", "대시보드 터미널의 스피너 글리프", ""))
                self.assertIn("sync", mod.derive_tags(
                    "깃 동기화 주기", "리모트 구성과 푸시 디바운스", ""))
                self.assertIn("assets", mod.derive_tags(
                    "첨부 저장 위치", "업로드 이미지 경로 재설계", ""))

            # G2. 최대 3개 · 매칭 많은 순
        with self.subTest("g2_limit"):
                t = mod.derive_tags("대시보드 터미널 세션 첨부 카탈로그 권한 테스트",
                                    "보드 채팅 모델 이미지 인덱스 격리 검증", "")
                self.assertLessEqual(len(t), 3)

            # G3. 매칭 없으면 빈 목록 (억지 태깅 금지)
        with self.subTest("g3_no_match"):
            self.assertEqual(mod.derive_tags("점심 메뉴", "김치찌개", ""), [])

class TestTagOnCreate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9tagcli-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")

    @classmethod
    def cli(cls, *argv):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def tags_of(self, rid):
        import glob
        p = glob.glob(os.path.join(self.tmp, "vault", "**", rid + ".md"),
                      recursive=True)[0]
        with open(p, encoding="utf-8") as f:
            meta = f.read().split("---")[1]
        for ln in meta.splitlines():
            if ln.startswith("tags:"):
                return json.loads(ln.split(":", 1)[1].strip())
        return []

    # G4. auto-audit 카드에도 의미 태그가 붙는다
    def test_test_tag_on_create(self):
        """TestTagOnCreate 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("g4_auto_card_gets_tags"):
                rid = self.cli("new", "request", "--title", "터미널 스피너 정리",
                               "--summary", "대시보드 터미널 웨이팅 표시", "--size", "S",
                               "--tag", "auto-audit", "--body", "채팅 수신함 관련").split()[0]
                tags = self.tags_of(rid)
                self.assertIn("auto-audit", tags)
                self.assertTrue([t for t in tags if t != "auto-audit"], tags)

            # G5. 사람이 붙인 태그가 있으면 자동 보강하지 않는다
        with self.subTest("g5_human_tags_respected"):
                rid = self.cli("new", "request", "--title", "터미널 스피너 정리",
                               "--summary", "대시보드 터미널", "--size", "S",
                               "--tag", "myown", "--body", "x").split()[0]
                self.assertEqual(self.tags_of(rid), ["myown"])

            # G6. backfill: 기계 태그뿐인 기존 문서를 보강
        with self.subTest("g6_backfill"):
            rid = self.cli("new", "request", "--title", "무의미", "--summary", "",
                           "--size", "S", "--tag", "auto-audit",
                           "--body", "깃 동기화와 커밋 푸시 리모트 구성").split()[0]
            before = self.tags_of(rid)
            if [t for t in before if t != "auto-audit"]:
                self.skipTest("생성 시점에 이미 태깅됨")
            self.cli("tag", "backfill")
            self.assertIn("sync", self.tags_of(rid))

if __name__ == "__main__":
    unittest.main(verbosity=2)
