"""윈도우에서 `bin/s9` 를 부를 수 있게 하는 문 (REQ-20260903-005).

**윈도우는 shebang 을 모른다.** 리눅스·맥에서 `subprocess.run([S9, "ls"])` 이
도는 것은 커널이 `#!/usr/bin/env python3` 를 읽어 인터프리터를 얹어 주기
때문이고, 윈도우의 `CreateProcess` 에는 그 단계가 아예 없다. 확장자 없는
스크립트를 그대로 넘기면 이렇게 끝난다 — 네이티브 윈도우 실측:

    OSError: [WinError 193] %1은(는) 올바른 Win32 응용 프로그램이 아닙니다

시험 116 파일이 `S9 = .../bin/s9` 를 그 형태로 부르므로, 그 판에서는 스위트가
**첫 setUpClass 에서 통째로 선다**. 즉 「무엇이 깨지는지」조차 잴 수 없다.

### 왜 시험 파일 116개를 고치지 않는가

그 파일들의 `S9` 는 **두 가지로 쓰인다** — `subprocess` 의 argv[0] 이면서,
동시에 `SourceFileLoader(..., S9)` 의 소스 경로다. 후자는 반드시 파이썬
원문 파일이어야 하므로 이름 하나를 `.cmd` 로 바꾸면 그쪽이 깨진다. 이름을
둘로 쪼개 116 파일을 고치는 것은 **판 하나 때문에 모든 시험을 건드리는**
일이고, 갈래는 그렇게 흩는 것이 아니라 한 자리에 모으는 것이다
(DOC-20260903-003 「판을 가르는 자리의 규율」).

그래서 여기 한 자리에서, 커널이 POSIX 에서 하는 일을 그대로 대신한다:
argv[0] 이 이 저장소의 확장자 없는 `bin/` 도구이면 앞에 인터프리터를 얹는다.
**윈도우에서만** 얹는다 — 리눅스·맥에서는 이 모듈이 아무것도 하지 않으므로
기준선의 동작이 한 글자도 달라지지 않는다.

`.cmd` 래퍼(사용자가 실제로 쓰는 진입점)를 대신 얹지 않는 것은, 시험이
`bin/s9` 라는 **그 파일**의 동작을 재야 하기 때문이다. 래퍼 자신의 계약
(한 번만 실행 · 스토어 스텁 회피 · UTF-8 · 종료코드)은 그 래퍼를 직접 부르는
시험이 따로 잰다 (tests/test_windows_entry.py).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BIN = os.path.join(REPO, "bin")

_installed = [False]


def is_s9_script(path):
    """이 경로가 `bin/` 아래의 확장자 없는 파이썬 도구인가."""
    try:
        p = os.path.abspath(str(path))
    except (TypeError, ValueError):
        return False
    if os.path.dirname(p) != BIN:
        return False
    return not os.path.splitext(p)[1] and os.path.isfile(p)


def shebang_argv(argv):
    """POSIX 커널이 shebang 으로 하는 일 — 윈도우에서는 우리가 한다."""
    if os.name != "nt" or not argv:
        return argv
    first = argv[0]
    if isinstance(first, (str, os.PathLike)) and is_s9_script(first):
        return [sys.executable, os.fspath(first), *argv[1:]]
    return argv


def install():
    """`subprocess` 의 진입점 셋에 위 규칙을 얹는다 (윈도우에서만, 한 번만).

    감싸는 것은 `Popen` 하나다 — `run`·`call`·`check_output` 이 전부 그 위에
    서 있으므로, 넷을 따로 감싸면 같은 규칙이 네 벌이 되고 그중 하나가
    갈라진다.
    """
    if os.name != "nt" or _installed[0]:
        return False
    import subprocess
    orig = subprocess.Popen

    class _Popen(orig):
        def __init__(self, args, *a, **kw):
            if isinstance(args, (list, tuple)):
                args = shebang_argv(list(args))
            super().__init__(args, *a, **kw)

    subprocess.Popen = _Popen
    _installed[0] = True
    return True
