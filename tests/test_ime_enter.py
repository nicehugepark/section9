"""한글 조합 중의 Enter 는 전송이 아니다 (REQ-20260911-001-2n7g).

맥 실측 2026-09-11 10:06: 대시보드 터미널에 「스스로 판단해」를 치고 바로 Enter 를
누르자 「스스로 판단해」와 「해」가 따로 도착했다. 마지막 글자가 아직 입력기 안에서
조합 중일 때 keydown(Enter, keyCode 229, isComposing) 이 먼저 오고, 그 자리에서
전송하면 입력기가 조합을 끝내며 그 글자를 빈 칸에 다시 넣기 때문이다.

termKeydown 을 node 로 **실행**해 잰다(소스 글자 대조 아님).
실행: python3 tests/ ime_enter
"""
import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, "..", "web", "app", "input.js"), encoding="utf-8").read()
NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(src, name):
    i = src.index(f"function {name}(")
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{": depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0: return src[i:j + 1]
    raise AssertionError(name)


STUBS = r"""
const calls = {send: 0, pick: 0, prevent: 0};
function sendChat(){ calls.send++; }
function termPalPick(){ calls.pick++; }
function termPalClose(){}
function termPalRender(){}
function termAttRender(){}
function termPasteHint(){}
function termInterrupt(){}
function mkTa(v){ return {value: v, selectionStart: v.length, selectionEnd: v.length, style: {}, scrollHeight: 20}; }
function ev(ta, extra){ return Object.assign({key: "Enter", target: ta, shiftKey: false, ctrlKey: false,
  altKey: false, metaKey: false, isComposing: false, keyCode: 13, preventDefault(){ calls.prevent++; }}, extra); }
const T = {pal: {open: false, items: [], idx: 0}, atts: [], hist: [], histIdx: null, waitOn: false};
"""


@unittest.skipUnless(NODE, "node 가 없다")
class ImeEnter(unittest.TestCase):
    def _run(self, driver):
        prog = STUBS + _fn(SRC, "termKeydown") + "\n" + driver
        r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip())

    def test_i1_enter_while_composing_does_not_send(self):
        """핵심 — 조합 중(isComposing)의 Enter 는 보내지 않고 입력기에 맡긴다."""
        got = self._run(r"""
const ta = mkTa("스스로 판단해");
termKeydown(T, ev(ta, {isComposing: true, keyCode: 229}));
console.log(JSON.stringify(calls));""")
        self.assertEqual(got["send"], 0, "조합 중인 마지막 글자가 따로 한 번 더 간다")
        self.assertEqual(got["prevent"], 0, "입력기의 키를 가로챘다")

    def test_i2_keycode_229_alone_is_also_composition(self):
        """경계 — isComposing 을 안 주는 판(옛 WebKit)은 keyCode 229 가 그 표시다."""
        got = self._run(r"""
const ta = mkTa("해");
termKeydown(T, ev(ta, {keyCode: 229}));
console.log(JSON.stringify(calls));""")
        self.assertEqual(got["send"], 0)

    def test_i3_plain_enter_still_sends(self):
        """회귀 — 조합이 끝난 뒤의 Enter 는 종전대로 보낸다."""
        got = self._run(r"""
const ta = mkTa("스스로 판단해");
termKeydown(T, ev(ta, {}));
console.log(JSON.stringify(calls));""")
        self.assertEqual(got["send"], 1)
        self.assertEqual(got["prevent"], 1)

    def test_i4_palette_ignores_composing_keys_too(self):
        """경계 — 팔레트가 열려 있어도 조합 중의 Enter 는 고르기가 아니다."""
        got = self._run(r"""
T.pal.open = true; T.pal.items = [{name: "x"}];
const ta = mkTa("/ㅎ");
termKeydown(T, ev(ta, {isComposing: true, keyCode: 229}));
console.log(JSON.stringify(calls));""")
        self.assertEqual(got["pick"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
