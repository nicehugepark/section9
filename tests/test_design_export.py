"""디자인 시스템 미리보기 내보내기 (REQ-20260913-015-62x6).

bin/s9-design-export 가 web/css/tokens.css 와 부품 규칙(실제 선택자)에서 Claude Design
카드용 미리보기 HTML 네 장을 만든다. 시험은 임시 디렉터리로 내보내 결과만 본다 —
소스는 tokens.css 를 한 번 제 손으로 읽어 값을 대조한다(시험 예산 기준선: 소스 글자
계약 파일을 늘리지 않는다). 역할 정의·스킬에 규율이 있는지는 test_ux_agents U4 가 본다.

실행: python3 tests/ design_export
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPORT = os.path.join(ROOT, "bin", "s9-design-export")
TOKENS = os.path.join(ROOT, "web", "css", "tokens.css")
CARDS = {"colors.html": "Colors", "type.html": "Type",
         "spacing.html": "Spacing", "components.html": "Components"}
MARK = re.compile(r'^<!-- @dsCard group="([A-Za-z]+)" -->$')
EXTERNAL = re.compile(r"<link\b|<script\s[^>]*\bsrc=|@import\b|https?://")
DECL = re.compile(r"--([a-zA-Z0-9-]+)\s*:\s*([^;]+);")


def _run(out, root=ROOT):
    return subprocess.run([sys.executable, EXPORT, "--root", root, "--out", out],
                          capture_output=True, text=True, encoding="utf-8")


def _files(out):
    got = {}
    for name in CARDS:
        with open(os.path.join(out, name), encoding="utf-8") as f:
            got[name] = f.read()
    return got


def _blocks(css):
    """tokens.css 를 시험이 제 손으로 읽은 (라이트, 다크 재정의) 선언."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    light = re.search(r":root\s*\{([^}]*)\}", css).group(1)
    dark = re.search(r':root\[data-theme="carbon"\]\s*\{([^}]*)\}', css).group(1)
    return ({k: v.strip() for k, v in DECL.findall(light)},
            {k: v.strip() for k, v in DECL.findall(dark)})


class DesignExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="s9ds-")
        cls.res = _run(cls.out)

    def test_t1_four_cards_with_dscard_marker_first_line(self):
        """T1. 카드 네 장 + README, 첫 줄이 @dsCard 표지이고 group 이 파일과 맞는다."""
        self.assertEqual(self.res.returncode, 0, self.res.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.out, "README.md")))
        for name, body in _files(self.out).items():
            first = body.split("\n", 1)[0]
            m = MARK.match(first)
            self.assertIsNotNone(m, f"{name}: 첫 줄이 @dsCard 표지가 아니다 — {first!r}")
            self.assertEqual(m.group(1), CARDS[name], name)
            self.assertIn("<!doctype html>", body.split("\n", 2)[1], name)

    def test_t2_no_external_resources(self):
        """T2. 외부 자원 0건 — CSS 는 전부 인라인, 링크·스크립트·@import·http 없음."""
        for name, body in _files(self.out).items():
            hit = EXTERNAL.search(body)
            self.assertIsNone(hit, f"{name}: 외부 자원 참조 — {hit and hit.group(0)!r}")
            self.assertIn("<style>", body, name)

    def test_t3_token_values_match_tokens_css_light_and_dark(self):
        """T3. 라이트·다크 토큰이 tokens.css 의 이름·값 그대로 네 장 모두에 있다."""
        with open(TOKENS, encoding="utf-8") as f:
            light, dark_only = _blocks(f.read())
        self.assertGreater(len(light), 20)
        self.assertGreater(len(dark_only), 5)
        for name, body in _files(self.out).items():
            tl = re.search(r"\.tone-light\{([^}]*)\}", body).group(1)
            td = re.search(r"\.tone-dark\{([^}]*)\}", body).group(1)
            for k, v in light.items():
                self.assertIn(f"--{k}:{v};", tl, f"{name}: 라이트 --{k}")
            for k, v in light.items():
                want = dark_only.get(k, v)     # 다크가 안 덮은 토큰은 라이트 값 그대로
                self.assertIn(f"--{k}:{want};", td, f"{name}: 다크 --{k}")
            self.assertNotIn(f"--bg:{light['bg']};", td, f"{name}: 다크 판이 라이트 바탕색을 쓴다")
        colors = _files(self.out)["colors.html"]
        for v in (light["bg"], dark_only["bg"], light["text"], dark_only["text"]):
            self.assertIn(f'>{v}<', colors, f"colors.html 표에 {v} 가 글자로 안 보인다")

    def test_t4_idempotent_bytes(self):
        """T4. 같은 입력으로 두 번 실행하면 바이트가 같다."""
        out2 = tempfile.mkdtemp(prefix="s9ds2-")
        self.assertEqual(_run(out2).returncode, 0)
        for name in CARDS:
            with open(os.path.join(self.out, name), "rb") as a, \
                    open(os.path.join(out2, name), "rb") as b:
                self.assertEqual(a.read(), b.read(), name)

    def test_t5_missing_tokens_fails_loudly(self):
        """T5. tokens.css 가 없거나 `:root{` 블록이 없으면 종료 2 + stderr 사유."""
        empty = tempfile.mkdtemp(prefix="s9ds-empty-")
        r = _run(os.path.join(empty, "out"), root=empty)
        self.assertEqual(r.returncode, 2)
        self.assertIn("tokens.css", r.stderr)
        broken = tempfile.mkdtemp(prefix="s9ds-broken-")
        os.makedirs(os.path.join(broken, "web", "css"))
        with open(os.path.join(broken, "web", "css", "tokens.css"), "w", encoding="utf-8") as f:
            f.write("*{box-sizing:border-box}\n")
        r = _run(os.path.join(broken, "out"), root=broken)
        self.assertEqual(r.returncode, 2)
        self.assertIn(":root", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
