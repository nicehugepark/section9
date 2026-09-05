"""문서 관계 무결성 (REQ-20260825-059).

parent/children/relates/derived_from가 깨지면 "연관 요청이 없다"가 된다 —
전수 검사(link_audit)로 검출하고 --fix로 복구한다. 복구는 멱등이어야
한다(왕복 수정 금지). 채팅 카드는 지목한 문서·선행 카드와 자동 연결된다.

실행: python3 tests/ link_integrity
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
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)

TMP = tempfile.mkdtemp(prefix="s9link-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE", "S9_USER")}
os.environ.update({"S9_ROOT": TMP, "S9_MACHINE": "testbox", "S9_USER": "tester"})
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_link", importlib.machinery.SourceFileLoader("s9_mod_link", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestLinkAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = {**os.environ, "S9_ROOT": TMP, "S9_MACHINE": "testbox",
                   "S9_USER": "tester"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")

    @classmethod
    def cli(cls, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=cls.env, timeout=20, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout

    def new(self, title):
        return self.cli("new", "request", "--title", title, "--summary", "s",
                        "--size", "S", "--goal", "g", "--body", "b").split()[0]

    def _path(self, rid):
        import glob
        return glob.glob(os.path.join(TMP, "vault", "**", rid + ".md"),
                         recursive=True)[0]

    def _meta(self, rid):
        with open(self._path(rid), encoding="utf-8") as f:
            fm = f.read().split("---")[1]
        out = {}
        for ln in fm.splitlines():
            if ": " in ln:
                k, v = ln.split(": ", 1)
                try:
                    out[k] = json.loads(v)
                except Exception:
                    out[k] = v.strip()
        return out

    def _write_meta(self, rid, key, value):
        p = self._path(rid)
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        head, fm, body = txt.split("---", 2)
        lines = [l for l in fm.splitlines() if not l.startswith(key + ":")]
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}"
                     if isinstance(value, list) else f"{key}: {value}")
        with open(p, "w", encoding="utf-8") as f:
            f.write(head + "---" + "\n".join(lines) + "\n---" + body)
        self.cli("index", "rebuild")

    # L1. 정상 상태에서는 문제 0건
    def test_test_link_audit(self):
        """TestLinkAudit 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("l1_clean"):
                a, b = self.new("부모"), self.new("자식")
                self.cli("link", b, "--parent", a)
                issues, _ = mod.link_audit()
                self.assertEqual([i for i in issues if a in i or b in i], [])

            # L2. relates는 양방향으로 기록된다 (단방향이 "연관 누락"의 원인)
        with self.subTest("l2_relates_symmetric"):
                a, b = self.new("A"), self.new("B")
                # --why 는 필수다 (REQ-20260827-030) — 여기서 보는 것은 대칭이지
                # 이유가 아니므로 픽스처용 한 줄이면 된다.
                self.cli("link", a, "--relates", b, "--why", "대칭 검사용 픽스처")
                self.assertIn(a, self._meta(b).get("relates") or [])

            # L3. 깨진 관계 검출 + 복구, 복구는 멱등(재실행 시 문제 0)
        with self.subTest("l3_detect_and_fix"):
                a, b = self.new("고아 부모"), self.new("고아 자식")
                self._write_meta(b, "parent", a)          # 역참조 없는 부모 지정
                self._write_meta(a, "relates", ["REQ-90000000-999"])  # 미존재 참조
                issues, _ = mod.link_audit()
                self.assertTrue(any("역참조 누락" in i for i in issues), issues)
                self.assertTrue(any("미존재" in i for i in issues), issues)
                _i2, fixed = mod.link_audit(fix=True)
                self.assertGreater(fixed, 0)
                again, _ = mod.link_audit()
                self.assertEqual(again, [], f"복구가 멱등하지 않다: {again}")

            # L4. 자기참조·순환 검출
        with self.subTest("l4_cycles"):
            a, b = self.new("순환1"), self.new("순환2")
            self._write_meta(a, "parent", b)
            self._write_meta(b, "parent", a)
            issues, _ = mod.link_audit()
            self.assertTrue(any("순환" in i for i in issues), issues)
            mod.link_audit(fix=True)
            self.assertEqual([i for i in mod.link_audit()[0] if "순환" in i], [])

class TestAutoRepairEntrypoint(unittest.TestCase):
    """자동화 계약 (REQ-20260825-061): 관계 복구가 사람의 명령 기억에
    의존하지 않는다 — 서버 기동 경로에 자동 복구가 걸려 있고, 규약에
    3층 관계 규칙이 명시돼 있다."""
    def test_serve_auto_repairs(self):
        """serve 기동 경로에 자동 복구가 있다.

        검사 범위를 **함수 전체**로 잡는다. 앞서 2500자 창으로 잘랐더니,
        cmd_serve 에 감시자 분기(REQ-20260825-096)가 들어오면서 link_audit 이
        창 밖으로 밀려 코드가 멀쩡한데 테스트만 빨개졌다. 고정할 성질은
        "기동 경로에 있다"이지 "앞에서 2500자 안에 있다"가 아니다.
        """
        import re
        with open(S9_SRC, encoding="utf-8") as f:
            src = f.read()
        i = src.index("def cmd_serve(")
        m = re.compile(r"^def \w+\(", re.M).search(src, i + 1)
        body = src[i:m.start() if m else len(src)]
        self.assertIn("link_audit(fix=True)", body,
                      "serve 기동 경로에 자동 복구가 없다")

    def test_protocol_documents_model(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(S9)))
        with open(os.path.join(root, "CLAUDE.md"), encoding="utf-8") as f:
            proto = f.read()
        self.assertIn("derived_from", proto)
        self.assertIn("다중 부모는 쓰지 않는다", proto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
