"""의존성 0 정책 가드 (REQ-20260824-003, pyproject.toml 참조).

bin/의 실행 파일과 tests/의 테스트가 표준 라이브러리 밖 모듈을 import하면 실패한다.
서드파티 도입은 pyproject.toml dependencies에 선언하는 결정과 함께만 허용.
실행: python3 tests/test_stdlib_only.py
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def py_sources():
    out = []
    for name in os.listdir(os.path.join(ROOT, "bin")):
        p = os.path.join(ROOT, "bin", name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    head = f.readline()
                if "python" in head:
                    out.append(p)
            except (OSError, UnicodeDecodeError):
                pass
    for name in os.listdir(HERE):
        if name.endswith(".py"):
            out.append(os.path.join(HERE, name))
    return out


def local_helpers():
    """tests/ 안의 우리 헬퍼 모듈 — 설치가 필요 없으니 서드파티가 아니다.

    (REQ-20260825-100: portpool 처럼 여러 테스트가 공유하는 규율 모듈.)
    """
    return {n[:-3] for n in os.listdir(HERE)
            if n.endswith(".py") and not n.startswith("test_")
            and n != "__main__.py"}


# 그 운영체제에만 설치되는 표준 라이브러리 — 파일이 없어도 표준이다.
# `sys.stdlib_module_names`(3.10+)는 플랫폼과 무관한 한 목록이라 이것들을 담지만,
# 아래 폴백은 디스크를 훑으므로 맥·리눅스에서는 이 이름들이 통째로 빠진다. 그러면
# Windows 갈래 안에서 import 하는 우리 파일이 서드파티로 잡힌다 (REQ-20260915-002-2n7g,
# 맥 실측 2026-09-15: bin/s9_firstrun.py 의 `import winreg` 하나로 전체 테스트가 실패).
PLATFORM_ONLY = {"winreg", "msvcrt", "winsound", "_winapi", "nt", "msilib"}


def stdlib_names():
    """표준 라이브러리 최상위 모듈 이름 집합.

    `sys.stdlib_module_names` 는 3.10 에서 생겼다 — 맥의 기본 python3 는 3.9
    (CommandLineTools) 라 그 속성이 없어 이 스모크 시험이 AttributeError 로 오류나고
    커밋 검사가 모든 code 커밋을 막았다 (REQ-20260906-011-2n7g, 맥 실측 2026-09-06).
    3.9 이하에서는 같은 답을 파일 시스템에서 만든다: 내장 모듈 ∪ stdlib 디렉터리의
    .py/패키지 ∪ lib-dynload 의 확장 모듈 ∪ 다른 운영체제 전용 모듈(PLATFORM_ONLY).
    """
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    import sysconfig
    out = set(sys.builtin_module_names) | PLATFORM_ONLY
    for key in ("stdlib", "platstdlib"):
        d = sysconfig.get_paths().get(key)
        if not d or not os.path.isdir(d):
            continue
        for sub in (d, os.path.join(d, "lib-dynload")):
            try:
                entries = os.listdir(sub)
            except OSError:
                continue
            for n in entries:
                if n.startswith("__"):          # __pycache__, __phello__ …
                    continue
                if n.endswith(".py"):
                    out.add(n[:-3])
                elif ".so" in n or n.endswith(".pyd"):
                    out.add(n.split(".")[0])
                elif os.path.isdir(os.path.join(sub, n)) and n != "site-packages":
                    out.add(n)
    return out


class TestStdlibOnly(unittest.TestCase):
    def test_stdlib_names_are_known_on_this_python(self):
        # 3.9 의 폴백도 3.10+ 의 목록과 같은 핵심을 알아야 한다 — 비면 헛통과다
        names = stdlib_names()
        for m in ("os", "sys", "json", "ast", "sqlite3", "ssl", "unittest"):
            self.assertIn(m, names, m)
        self.assertNotIn("site-packages", names)

    def test_no_third_party_imports(self):
        allowed = stdlib_names() | local_helpers()
        bad = []
        for path in py_sources():
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 \
                        and node.module:
                    mods = [node.module.split(".")[0]]
                for m in mods:
                    if m not in allowed:
                        bad.append(f"{os.path.relpath(path, ROOT)}: import {m}")
        self.assertFalse(bad, "표준 라이브러리 밖 import 발견 — pyproject.toml에 "
                              "의존성 선언 + 정책 결정 없이 금지:\n" + "\n".join(bad))

    def test_fallback_knows_other_platforms_stdlib(self):
        """3.9 폴백도 다른 운영체제 전용 표준 모듈을 안다 (REQ-20260915-002-2n7g).

        디스크를 훑는 폴백은 맥·리눅스에 파일이 없는 winreg 를 못 본다. 3.10+ 에서도
        그 갈래를 강제로 태워 본다 — 이 머신이 3.10 으로 올라가도 검사가 남아야 한다."""
        had = hasattr(sys, "stdlib_module_names")
        saved = getattr(sys, "stdlib_module_names", None)
        if had:
            del sys.stdlib_module_names
        try:
            names = stdlib_names()
        finally:
            if had:
                sys.stdlib_module_names = saved
        for m in ("winreg", "msvcrt", "winsound"):
            self.assertIn(m, names, m)
        self.assertIn("os", names)     # 폴백이 통째로 비어 헛통과하지 않는지

    def test_sources_found(self):
        # 가드가 빈 목록을 검사하며 헛통과하지 않는지
        srcs = py_sources()
        self.assertGreaterEqual(len(srcs), 5, srcs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
