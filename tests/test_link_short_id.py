"""짧은 부모 id 는 지우지 않고 정식 id 로, 서버 기동은 문서를 고쳐 쓰지 않는다 (REQ-20260906-048).

실제 사고 2026-09-06: 자동 등록된 후속 요청의 parent 가 짧은 id(REQ-20260906-009)였고,
서버 기동의 관계 복구가 「미존재」로 보고 지웠다 — 원격 머신의 기동이 같은 일을 하며
동기화로 오갔다.

실행: python3 tests/ link_short_id
"""
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")


class LinkShortId(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9lsi-")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("S9_")}
        self.env["S9_ROOT"] = self.root
        subprocess.run([S9, "init"], env=self.env, capture_output=True, check=True)
        subprocess.run([S9, "user", "add", "t"], env=self.env, capture_output=True)
        self.a = self._new("a")
        self.b = self._new("b")
        old = os.environ.get("S9_ROOT"); os.environ["S9_ROOT"] = self.root
        try:
            spec = importlib.util.spec_from_loader(
                "s9_lsi", importlib.machinery.SourceFileLoader("s9_lsi", S9))
            self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        finally:
            if old is None:
                os.environ.pop("S9_ROOT", None)
            else:
                os.environ["S9_ROOT"] = old

    def _new(self, t, *extra):
        r = subprocess.run([S9, "new", "request", "--title", t, "--summary", "s", "--size", "S",
                            "--goal", "g", "--body", "b", *extra], env=self.env, capture_output=True, text=True)
        return [x for x in r.stdout.split() if x.startswith("REQ-")][0]

    def _path(self, doc):
        return subprocess.run(["find", os.path.join(self.root, "vault"), "-name", doc + ".md"],
                              capture_output=True, text=True).stdout.strip()

    def test_l1_short_parent_is_resolved_not_removed(self):
        """L1. parent 가 짧은 id 면 정식 id 로 고치고 부모의 children 에 넣는다 — 지우지 않는다."""
        short = self.a.rsplit("-", 1)[0]
        pb = self._path(self.b)
        text = open(pb, encoding="utf-8").read()
        text = re.sub(r"(?m)^parent:.*$", "", text).replace("\nid: ", f"\nparent: {short}\nid: ", 1)
        open(pb, "w", encoding="utf-8").write(text)
        issues, fixed = self.m.link_audit(fix=True)
        self.assertGreaterEqual(fixed, 1, issues)
        self.assertIn(f"parent: {self.a}\n", open(pb, encoding="utf-8").read())
        self.assertIn(self.b, open(self._path(self.a), encoding="utf-8").read())

    def test_l2_new_stores_the_full_parent_id(self):
        """L2. `s9 new --parent <짧은 id>` 는 정식 id 로 적는다."""
        short = self.a.rsplit("-", 1)[0]
        c = self._new("c", "--parent", short)
        self.assertIn(f"parent: {self.a}\n", open(self._path(c), encoding="utf-8").read())

    def test_l3_serve_start_does_not_fix_links(self):
        """L3. 서버 기동은 관계를 읽기만 한다 — fix=True 호출이 cmd_serve 안에 없다."""
        src = open(os.path.join(REPO, "bin", "s9.py"), encoding="utf-8").read()
        i = src.index("def cmd_serve(args):"); j = src.index("\ndef ", i + 10)
        body = src[i:j]
        self.assertNotIn("link_audit(fix=True)", body)
        self.assertIn("link_audit(fix=False)", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
