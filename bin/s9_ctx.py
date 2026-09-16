"""s9.py 를 가르기 위한 **이음매** — 부모의 이름공간을 사전으로 받는다.

`bin/s9.py` 는 41,564줄이고 여럿이 동시에 고친다. 가르고 싶은데 못 가른 까닭은
의존이 양방향이기 때문이다 — 동기화 계열 77개가 밖에서 27번 불리고 밖의 것을
37개 끌어 쓴다(리드 실측 2026-09-16). 그냥 옮기면 순환 import 가 된다.

**옮기기로는 못 푼다. 이음매를 뒤집어 푼다** (DOC-20260916-003-62x6):
자식이 부모를 import 하지 않고, 부모가 제 이름공간을 `bind(globals())` 로
건네준다. 그러면 `chat_send` 가 `ROOT` 와 함수 다섯에 기대도 그 다섯이 `_S9`
안에 있으므로 **엉킨 채로 옮겨진다**.

이 장치는 새로 짓는 것이 아니다 — `bin/s9_commit.py` 가 이미 같은 꼴로 산다.

**왜 평범한 import 가 아닌가** (둘 다 실측에 걸린다):
- 시험 345개가 `SourceFileLoader` 로 `bin/s9.py` 를 올린다. 그 모듈의 globals 를
  직접 부른다(`s9.now_iso()`) — s9.py 의 globals 가 사실상 공개 API 다.
- `ROOT` 는 import 때 한 번 정해지고, 시험은 `S9_ROOT` 를 바꿔 **다시 올리는
  것**으로 격리한다. 자식을 `sys.modules` 에 캐시하면 그 격리가 무너진다.
"""
import datetime
import os
import socket
import sys

_S9 = {}                      # bind() 가 채운다 — s9.py 의 이름공간
_PARENT = [None]              # 그 사전 **자체** (복사본이 아니다)


def bind(ns):
    """부모(s9.py)의 globals 를 받는다.

    사전을 **복사만 하지 않고 그 자체를 쥔다**: `SERVE_STARTED` 처럼 나중에
    값이 정해지는 이름이 있어서, 복사본만 들면 bind 시점의 빈 값이 굳는다.
    `_S9` 도 함께 채워 둔다 — `bin/s9_commit.py` 가 쓰는 꼴과 같게.
    """
    _PARENT[0] = ns
    _S9.update(ns)


def g(name):
    """부모의 이름 하나. **없으면 KeyError** — 모르는 값을 지어내지 않는다.

    bind 전에 읽으면 여기서 바로 진다. 조용히 기본값을 돌려주면 그 값으로 도는
    코드가 어디까지 갔는지 아무도 모른다.
    """
    src = _PARENT[0]
    if src is not None and name in src:
        return src[name]
    return _S9[name]


# ── 혼자 서는 것들 ────────────────────────────────────────────────────────
def die(msg):
    print(f"s9: error: {msg}", file=sys.stderr)
    sys.exit(1)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def current_machine():
    return os.environ.get("S9_MACHINE") or socket.gethostname()


def _iso_epoch(v):
    try:
        return datetime.datetime.fromisoformat(str(v)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _notice_sig(*parts):
    import hashlib
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


# ── 부모의 이름에 기대는 것 — 이 장치가 있어야 옮겨진다 ──────────────────
def _notice_epoch():
    """시작 시각을 따로 적어 두지 않은 조건(미등록 계정 등)의 since — 서버가 뜬
    때. 같은 서버가 도는 동안은 값이 바뀌지 않아 「N일째」가 폴마다 바뀌지 않는다.

    `SERVE_STARTED`·`_NOTICE_EPOCH` 는 부모의 전역이다 — 이 함수가 이 모듈에
    설 수 있는 유일한 까닭이 `bind` 다. 옮기기만으로는 여기 못 온다.
    """
    return g("SERVE_STARTED") or g("_NOTICE_EPOCH")
