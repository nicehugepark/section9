"""사용량 칩은 못 받았다고 지워지지 않는다 (REQ-20260907-068).

한 번(`tries: 1`) 실패하면 칩을 비우고 마지막 값까지 버렸다 — WSL 중계의 간헐
리셋 한 번에 계정 줄이 아무 말 없이 사라졌다. 이제 마지막 값이 있으면 ⏳ 를
달고 남고, 받은 적이 없으면 「사용량을 받지 못했습니다」가 선다.

`renderUsageChip` 과 실패 갈래를 node 로 **실행**해 잰다(소스 글자 대조 아님).
실행: python3 tests/ usage_chip_keeps
"""
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 준비 삼아 한 번만 읽는다 (DOC-20260907-002)
USAGE_SRC = open(os.path.join(HERE, "..", "web", "app", "usage.js"), encoding="utf-8").read()
import glob
import shutil


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node",
                "/mnt/c/Temp/s9-webkit/node-*/node.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()

STUBS = r"""
const esc = s => String(s);
const usageTitle = () => "사용량";
function mkEl(){ const a = {}; return {textContent: "", innerHTML: "",
  setAttribute(k, v){ a[k] = v; }, removeAttribute(k){ delete a[k]; }, attrs: a}; }
"""


def _fn(src, name):
    i = src.index(f"function {name}(")
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{": depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0: return src[i:j + 1]
    raise AssertionError(name)


def _fail_branch(src):
    """refreshUsage 안의 실패 갈래만 — `if (!d || ...){` 부터 `usageLast = d;` 앞까지."""
    body = _fn(src, "refreshUsage")
    a = body.index("if (!d || (!d.ok && !d.stale)){")
    b = body.index("usageLast = d;")
    return body[a:b]


@unittest.skipUnless(NODE, "node 가 없다")
class Chip(unittest.TestCase):
    def _run(self, driver):
        src = USAGE_SRC
        prog = STUBS + _fn(src, "renderUsageChip") + "\n" + driver
        r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_a_good_value_is_drawn(self):
        out = self._run(r"""
const el = mkEl();
renderUsageChip(el, {email: "a@b", limits: [{kind: "session", percent: 29}, {kind: "weekly_all", percent: 22}]});
console.log(el.innerHTML);""")
        self.assertIn("a@b", out); self.assertIn("5h", out); self.assertIn("29%", out)
        self.assertNotIn("⏳", out)

    def test_a_stale_value_carries_the_mark(self):
        out = self._run(r"""
const el = mkEl();
renderUsageChip(el, {email: "a@b", stale: true, limits: []});
console.log(el.innerHTML);""")
        self.assertIn("⏳", out)

    def test_failure_after_a_value_keeps_it_with_the_mark(self):
        """핵심 — 실패해도 마지막 값이 ⏳ 를 달고 남는다. 칩이 비지 않는다."""
        src = USAGE_SRC
        driver = STUBS + _fn(src, "renderUsageChip") + r"""
let usageLast = {email: "a@b", limits: [{kind: "session", percent: 29}]};
const el = mkEl(); el.setAttribute("tabindex", "0");
const d = null;                                   // 이번 폴은 못 받았다
(function(){ """ + _fail_branch(src) + r""" })();
console.log(JSON.stringify({html: el.innerHTML, text: el.textContent, last: !!usageLast}));"""
        r = subprocess.run([NODE, "-e", driver], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = __import__("json").loads(r.stdout.strip())
        self.assertIn("a@b", got["html"], "마지막 값이 지워졌다 — 계정 줄이 사라진다")
        self.assertIn("⏳", got["html"], "못 받은 것을 표시하지 않는다")
        self.assertTrue(got["last"], "usageLast 를 버렸다 — 다음 실패에 빈 칸이 된다")

    def test_failure_with_no_value_says_so(self):
        """받은 적이 없으면 빈 칸이 아니라 그 사실을 말한다."""
        src = USAGE_SRC
        driver = STUBS + _fn(src, "renderUsageChip") + r"""
let usageLast = null;
const el = mkEl(); el.setAttribute("tabindex", "0");
const d = null;
(function(){ """ + _fail_branch(src) + r""" })();
console.log(JSON.stringify({text: el.textContent, tab: "tabindex" in el.attrs}));"""
        r = subprocess.run([NODE, "-e", driver], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = __import__("json").loads(r.stdout.strip())
        self.assertIn("받지 못했습니다", got["text"], "빈 칸이다 — 아무 문제 없음으로 읽힌다")
        self.assertFalse(got["tab"], "글자만 있는 칩이 tab 순서에 남았다")


if __name__ == "__main__":
    unittest.main()
