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


# 이 판에는 파일이 없는 표준 모듈 (REQ-20260915-003-2n7g, 맥 실측 2026-09-15).
# 표준 라이브러리는 판마다 구성이 다르다 — `winreg` 는 윈도우에만 깔리고 `pwd` 는
# POSIX 에만 깔린다. 3.10+ 의 `sys.stdlib_module_names` 는 **판과 무관한** 목록이라
# 둘 다 알지만, 아래 폴백은 이 판에 실제로 깔린 파일만 훑으므로 남의 판 전용
# 모듈을 서드파티로 본다. 맥에서 `bin/s9_firstrun.py` 의 `import winreg`
# (윈도우에서만 부르는 자리다)가 그렇게 잡혀 맥의 모든 code 커밋이 막혔다.
# 여기 적는 것은 **어느 판에서든 표준인 이름**뿐이라, 3.10+ 에서 합치면 무연산이다.
OTHER_PLATFORM_STDLIB = {
    # Windows 전용
    "winreg", "winsound", "msvcrt", "_winapi", "nt",
    # POSIX 전용
    "posix", "pwd", "grp", "termios", "fcntl", "tty", "pty",
    "resource", "syslog", "crypt", "spwd", "nis", "ossaudiodev",
}


def stdlib_names():
    """표준 라이브러리 최상위 모듈 이름 집합.

    `sys.stdlib_module_names` 는 3.10 에서 생겼다 — 맥의 기본 python3 는 3.9
    (CommandLineTools) 라 그 속성이 없어 이 스모크 시험이 AttributeError 로 오류나고
    커밋 검사가 모든 code 커밋을 막았다 (REQ-20260906-011-2n7g, 맥 실측 2026-09-06).
    3.9 이하에서는 같은 답을 파일 시스템에서 만든다: 내장 모듈 ∪ stdlib 디렉터리의
    .py/패키지 ∪ lib-dynload 의 확장 모듈 ∪ 남의 판 전용 표준 모듈.
    """
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names) | OTHER_PLATFORM_STDLIB
    import sysconfig
    out = set(sys.builtin_module_names)
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
    return out | OTHER_PLATFORM_STDLIB


class TestStdlibOnly(unittest.TestCase):
    def test_stdlib_names_are_known_on_this_python(self):
        # 3.9 의 폴백도 3.10+ 의 목록과 같은 핵심을 알아야 한다 — 비면 헛통과다
        names = stdlib_names()
        for m in ("os", "sys", "json", "ast", "sqlite3", "ssl", "unittest"):
            self.assertIn(m, names, m)
        self.assertNotIn("site-packages", names)

    def test_other_platforms_modules_are_not_third_party(self):
        """남의 판 전용 표준 모듈은 서드파티가 아니다 (REQ-20260915-003-2n7g).

        맥에서 윈도우 전용 `winreg` 가 서드파티로 잡혀 모든 code 커밋이 막혔다.
        목록이 그만큼 헐거워지지 않았는지도 함께 본다 — 진짜 서드파티는 밖이다.
        """
        names = stdlib_names()
        for m in ("winreg", "msvcrt", "pwd", "fcntl"):
            self.assertIn(m, names, "%s 가 표준 밖으로 보인다 — 이 판에 파일이 "
                                    "없을 뿐 표준 모듈이다" % m)
        for m in ("requests", "numpy", "flask", "pytest"):
            self.assertNotIn(m, names, "%s 가 표준으로 보인다 — 가드가 헐거워졌다" % m)

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

    def test_sources_found(self):
        # 가드가 빈 목록을 검사하며 헛통과하지 않는지
        srcs = py_sources()
        self.assertGreaterEqual(len(srcs), 5, srcs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
