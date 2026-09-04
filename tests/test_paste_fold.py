"""긴 붙여넣기를 한 줄로 접는다 (REQ-20260827-040-62x6).

로컬 터미널의 Claude Code 는 대량 텍스트를 붙이면 `[Pasted text #5 +17 lines]`
한 줄로 접고, 같은 것을 다시 붙이면 그 자리를 펼친다. 대시보드 입력줄은 붙인
것이 전부 그대로 펼쳐져 있었다.

이 테스트가 지키는 계약 — 가장 중요한 것부터:

  ① **전송되는 것은 원문이다.** 화면에만 접히고, 서버로 가는 텍스트에는 접힌
     자리에 원문이 그대로 들어간다. 이게 깨지면 사용자가 붙인 내용이 조용히
     사라진다 — 이 저장소에서 가장 나쁜 실패 모양이다.
  ② 칩 글자를 손으로 고치면 매핑이 끊긴다(유령 매핑 금지). 남은 글자는 글자
     그대로 나가고 원문은 새어나가지 않는다.
  ③ 원문 안에 다른 칩과 똑같은 문자열이 들어 있어도 그 안쪽은 다시 펼쳐지지
     않는다 — 왼→오 1패스 치환(치환 결과 재스캔 금지).
  ④ 접는 기준은 줄 수 **또는** 글자 수다. 줄바꿈 없는 긴 한 줄도 접는다.
  ⑤ 번호는 탭 안에서 누적된다 — 전송해도 초기화되지 않는다.
  ⑥ 원문 보관은 셸(DOM)보다 오래 산다 — 탭을 떠났다 와도 칩이 원문을 잃지
     않는다. 그래서 보관을 지우는 코드가 있어서는 안 된다.

접기/펼치기의 순수 로직은 index.html 안에 `paste-fold core (pure)` 마커로
묶여 있다. 이 테스트는 그 블록을 **그대로 떼어 node 로 실행**한다 — 정규식으로
"그렇게 생겼다"를 보는 대신 실제로 돌려 본다. node 가 없는 환경에서는 실행
검증만 건너뛰고, 소스 계약(아래 SourceContract)은 언제나 검사한다.

실행: python3 tests/ paste_fold
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()

CORE_RE = re.compile(
    r"/\* ==== paste-fold core \(pure\).*?\*/\n(.*?)\n\s*/\* ==== /paste-fold core",
    re.S)


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    # WSL/컨테이너에 node 가 없어도 VS Code 서버가 하나 들고 있는 경우가 많다
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()


def read_src():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


class PasteFoldCore(unittest.TestCase):
    """순수 로직을 실제로 실행해 본다."""

    @classmethod
    def setUpClass(cls):
        cls.src = read_src()
        m = CORE_RE.search(cls.src)
        assert m, "paste-fold core (pure) 블록을 못 찾았다"
        cls.core = m.group(1)

    def run_js(self, body):
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략 (소스 계약은 별도 검사)")
        script = self.core + "\n" + body
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0,
                         f"node 실행 실패:\n{p.stderr[-2000:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])

    # S1 — 여러 줄 붙여넣기는 접힌다, 라벨이 줄 수를 말한다
    def test_paste_fold_core(self):
        """순수 로직을 실제로 실행해 본다."""
        with self.subTest("s1_multiline_folds"):
                r = self.run_js("""
                  const s = Array.from({length:20}, (_,i)=>"line"+i).join("\\n");
                  console.log(JSON.stringify({
                    fold: pasteFoldNeeded(s), label: pasteFoldLabel(1, s)}));
                """)
                self.assertTrue(r["fold"])
                self.assertEqual(r["label"], "[Pasted text #1 +20 lines]")

            # S3 — 임계 미만은 접지 않는다 (기본 붙여넣기 그대로)
        with self.subTest("s3_short_paste_not_folded"):
                r = self.run_js("""
                  console.log(JSON.stringify({
                    five: pasteFoldNeeded("a\\nb\\nc\\nd\\ne"),
                    six: pasteFoldNeeded("a\\nb\\nc\\nd\\ne\\nf"),
                    c799: pasteFoldNeeded("x".repeat(799)),
                    c800: pasteFoldNeeded("x".repeat(800)),
                    empty: pasteFoldNeeded(""), nul: pasteFoldNeeded(null)}));
                """)
                self.assertFalse(r["five"], "5줄은 접지 않는다")
                self.assertTrue(r["six"], "6줄부터 접는다 (입력줄 120px 를 넘는 지점)")
                self.assertFalse(r["c799"])
                self.assertTrue(r["c800"])
                self.assertFalse(r["empty"])
                self.assertFalse(r["nul"])

            # S4 — 줄바꿈 없는 긴 한 줄도 접는다. 라벨은 글자 수로 말한다
        with self.subTest("s4_single_long_line"):
                r = self.run_js("""
                  const s = "y".repeat(1200);
                  console.log(JSON.stringify({
                    fold: pasteFoldNeeded(s), label: pasteFoldLabel(3, s)}));
                """)
                self.assertTrue(r["fold"])
                self.assertEqual(r["label"], "[Pasted text #3 +1200 chars]")

            # ① S2/S13 — 전송 확장: 칩 자리에 원문이 그대로 들어간다
        with self.subTest("s2_expand_restores_original"):
                r = self.run_js("""
                  const orig = "가\\n나\\n다\\n라\\n마\\n바";
                  const e = {n:1, label: pasteFoldLabel(1, orig), text: orig};
                  console.log(JSON.stringify({
                    only: pasteFoldExpand(e.label, [e]),
                    wrapped: pasteFoldExpand("앞 " + e.label + " 뒤", [e]),
                    none: pasteFoldExpand("칩 없는 평범한 입력", [e]),
                    noEntries: pasteFoldExpand("그냥 글", [])}));
                """)
                self.assertEqual(r["only"], "가\n나\n다\n라\n마\n바")
                self.assertEqual(r["wrapped"], "앞 가\n나\n다\n라\n마\n바 뒤")
                self.assertEqual(r["none"], "칩 없는 평범한 입력")
                self.assertEqual(r["noEntries"], "그냥 글")

            # S12 — 칩이 둘이면 각각 제 원문으로
        with self.subTest("s12_two_chips"):
                r = self.run_js("""
                  const a = "A".repeat(900), b = "B".repeat(900);
                  const ea = {n:1, label: pasteFoldLabel(1, a), text: a};
                  const eb = {n:2, label: pasteFoldLabel(2, b), text: b};
                  const out = pasteFoldExpand(ea.label + "\\n사이\\n" + eb.label,
                                              [ea, eb]);
                  console.log(JSON.stringify({ok: out === a + "\\n사이\\n" + b,
                                              len: out.length}));
                """)
                self.assertTrue(r["ok"], r)

            # ② S7 — 칩을 손으로 고치면 매핑이 끊긴다 (원문 유출 금지)
        with self.subTest("s7_edited_chip_is_literal"):
                r = self.run_js("""
                  const orig = "비밀\\n원문\\n1\\n2\\n3\\n4";
                  const e = {n:1, label: pasteFoldLabel(1, orig), text: orig};
                  const broken = e.label.slice(0, -1);            // 닫는 ] 를 지웠다
                  const inner = e.label.replace("lines", "line"); // 가운데를 고쳤다
                  console.log(JSON.stringify({
                    broken: pasteFoldExpand(broken, [e]),
                    inner: pasteFoldExpand(inner, [e])}));
                """)
                self.assertNotIn("비밀", r["broken"], "지운 칩에서 원문이 새어나갔다")
                self.assertNotIn("비밀", r["inner"], "고친 칩에서 원문이 새어나갔다")

            # ③ S8 — 원문 안의 칩 문자열은 다시 펼치지 않는다 (1패스)
        with self.subTest("s8_no_nested_reexpansion"):
                r = self.run_js("""
                  const inner = "안쪽\\n1\\n2\\n3\\n4\\n5";
                  const e1 = {n:1, label: pasteFoldLabel(1, inner), text: inner};
                  // #2 의 원문이 #1 의 라벨을 글자로 품고 있다
                  const outer = "머리\\n" + e1.label + "\\n꼬리\\n1\\n2\\n3";
                  const e2 = {n:2, label: pasteFoldLabel(2, outer), text: outer};
                  const out = pasteFoldExpand(e2.label, [e1, e2]);
                  console.log(JSON.stringify({out, ok: out === outer}));
                """)
                self.assertTrue(r["ok"],
                                f"치환 결과가 다시 펼쳐졌다(주입 경로): {r['out']!r}")

            # 라벨은 서로의 접두사가 되지 않는다 (#1 vs #12)
        with self.subTest("label_prefix_safety"):
            r = self.run_js("""
              const s = "z".repeat(900);
              const e1 = {n:1, label: pasteFoldLabel(1, s), text: "ONE"};
              const e12 = {n:12, label: pasteFoldLabel(12, s), text: "TWELVE"};
              console.log(JSON.stringify({
                a: pasteFoldExpand(e1.label, [e1, e12]),
                b: pasteFoldExpand(e12.label, [e1, e12])}));
            """)
            self.assertEqual(r["a"], "ONE")
            self.assertEqual(r["b"], "TWELVE")

class SourceContract(unittest.TestCase):
    """실행으로 못 보는 부분 — 글루 코드가 계약을 지키는지 소스로 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls.src = read_src()

    def fn(self, name):
        m = re.search(r"(?:async )?function " + name + r"\([^)]*\)\{(.*?)\n\}\n",
                      self.src, re.S)
        self.assertIsNotNone(m, f"{name}() 을 못 찾았다")
        return m.group(1)

    # ① 전송은 언제나 확장한 원문으로 — ta.value 를 그대로 보내면 안 된다
    def test_source_contract(self):
        """실행으로 못 보는 부분 — 글루 코드가 계약을 지키는지 소스로 확인한다."""
        with self.subTest("send_expands"):
                body = self.fn("sendChat")
                self.assertIn("termPasteExpandAll", body,
                              "sendChat 이 접힌 칩을 펼치지 않는다 — 원문이 사라진다")
                m = re.search(r"body: JSON\.stringify\(\{text", body)
                self.assertIsNotNone(m, "전송 payload 를 못 찾았다")
                # 확장 결과(raw)가 text 로 나가고, 화면 에코/히스토리는 접힌 표시(disp)
                self.assertRegex(body, r"const raw = termPasteExpandAll\(disp\)")
                self.assertRegex(body, r"T\.hist\.push\(disp\)")
                self.assertRegex(body, r"ta\.value = disp",
                                 "전송 실패 시 원문이 아니라 접힌 표시로 복원해야 한다")

            # ⑥ 원문 보관은 셸보다 오래 산다 + 지우지 않는다
        with self.subTest("store_outlives_shell"):
                m = re.search(r"\nlet termPastes = .*", self.src)
                self.assertIsNotNone(m, "termPastes 보관소가 최상위에 없다 "
                                        "— 탭을 떠나면 원문이 사라진다")
                # renderTerminal 안에서 초기화하면 탭 재진입 때 원문을 잃는다
                rt = self.fn("renderTerminal")
                self.assertNotIn("termPastes = {", rt,
                                 "탭 재진입 때 보관소를 비우면 접힌 칩이 껍데기가 된다")
                for bad in ("termPastes.list = []", "termPastes.list.splice",
                            "delete termPastes"):
                    self.assertNotIn(bad, self.src,
                                     f"보관소를 지우는 코드({bad})는 원문을 잃는다")

            # S5 — 같은 내용을 다시 붙이면 펼친다
        with self.subTest("paste_again_expands"):
                # **터미널 입력줄의** paste 핸들러를 본다. 판정 창도 그림을 받게 되면서
                # (REQ-20260829-015) 파일 안에 `ta.addEventListener("paste"` 가 둘이 됐다 —
                # 앞엣것을 집으면 이 계약이 엉뚱한 핸들러를 검사한다.
                h = self.fn("termBindInput")
                m = re.search(r'ta\.addEventListener\("paste", e => \{(.*?)\n  \}\);',
                              h, re.S)
                self.assertIsNotNone(m, "터미널 입력줄의 paste 핸들러를 못 찾았다")
                h = m.group(1)
                self.assertIn("termPasteFindChip", h,
                              "같은 내용을 다시 붙였는지 보지 않는다")
                self.assertIn("same.text", h, "펼치기 경로가 원문을 쓰지 않는다")
                # S11 — 이미지 첨부 경로가 살아 있다
                self.assertIn("termUpload", h, "이미지 붙여넣기 첨부가 사라졌다")
                self.assertIn("getData", h, "클립보드 텍스트를 읽지 않는다")

            # S11 — 접기가 다른 입력줄 기능을 밀어내지 않았다
        with self.subTest("regressions_intact"):
                for probe, why in [
                    ('root.addEventListener("drop"', "드래그&드롭 첨부"),
                    ("termPalUpdate(T)", "/ 명령 팔레트"),
                    ("T.histIdx = T.histIdx === null", "↑ 히스토리 탐색"),
                    ('e.key === "Escape"', "Escape 지우기"),
                    ('e.key === "Enter" && e.ctrlKey', "Ctrl+Enter 줄바꿈"),
                    ("termKeep.draft", "탭 이탈 초안 복원"),
                ]:
                    self.assertIn(probe, self.src, f"{why} 가 깨졌다")

            # 접힌 칩이 있는 동안 안내 한 줄이 뜬다 (한국어)
        with self.subTest("hint_line"):
                self.assertIn('id="cc-paste"', self.src, "안내 줄 요소가 없다")
                m = re.search(r'id="cc-paste"[^>]*>([^<]*)<', self.src)
                self.assertIsNotNone(m)
                self.assertIn("다시 붙여넣으면", m.group(1), m.group(1))
                self.assertIn("function termPasteHint", self.src)
                # 색면 하이라이트 금지 — 안내 줄에 배경을 깔지 않는다
                css = re.search(r"\n\.ccpaste\{([^}]*)\}", self.src)
                self.assertIsNotNone(css, ".ccpaste 스타일이 없다")
                self.assertNotIn("background", css.group(1),
                                 "색면 하이라이트 금지 — 글자색으로만")

            # 접기 상태가 바뀌는 자리마다 안내 줄을 다시 계산한다
        with self.subTest("hint_updated_everywhere"):
            self.assertGreaterEqual(self.src.count("termPasteHint()"), 4,
                                    "안내 줄 갱신이 일부 경로에서 빠졌다")
            self.assertIn("termPasteHint", self.fn("termInputSync"))

if __name__ == "__main__":
    unittest.main()
