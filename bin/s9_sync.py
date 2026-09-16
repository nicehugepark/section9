"""동기화가 저 혼자 쓰는 것들 — 가르기 조각 2 (REQ-20260916-019-62x6).

**이 파일은 혼자 올라가지 않는다.** `bin/s9.py` 가 마지막에 제 globals 로
`exec` 한다 — 그래서 여기 함수들의 `__globals__` 가 부모의 사전 **그 자체**다.
import 줄도 없다(부모의 것을 그대로 쓴다).

왜 이 모양인가 — 세 길을 재 보고 골랐다:
  ㉮ 옮기고 이름을 `g("ROOT")` 로 바꾸기 → 듣지만 304줄의 읽기를 영구히 버린다.
  ㉯ 옮기고 이름을 사본으로 꽂기 → **못 쓴다.** 시험 30개 이름 중 12개를 갈아
     끼우고(ROOT 20개 파일 · current_machine 19개), 사본은 그것을 못 본다.
     실제로 담았다가 test_machine_recv · test_index_catch_up 이 져서 되돌렸다.
  ㉰ 부모의 globals 로 exec → **갈아 끼우기가 그대로 듣고 코드도 안 바뀐다.**
     추적(traceback)도 이 파일을 가리킨다(`compile(..., 이 경로, "exec")`).

대가는 하나다: 이 파일만 따로 읽는 도구에게는 이름들이 정의돼 있지 않아 보인다.
그것을 알고 고른 것이고, 그래서 이 설명이 맨 위에 있다.

배운 규칙(값이 여기 있다): 「이름이 갈아 끼워지나」가 아니라 **「옮긴 코드가
갈아 끼워지는 이름을 부르나」**다. 조각 1 은 부모가 이름만 재수출해 무사했고,
조각 2 는 옮긴 코드가 직접 불러서 졌다.
"""

def _ago_word(epoch, now):
    if not epoch:
        return "없음"
    s = max(0, int(now - epoch))
    if s < 60:
        return f"{s}초 전"
    if s < 3600:
        return f"{s // 60}분 전"
    if s < 86400:
        return f"{s // 3600}시간 전"
    return f"{s // 86400}일 전"


def _commit_mark_pid(path):
    """「pid N 시각」 꼴 표식의 pid — 모르면 0."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.readline().split()
    except OSError:
        return 0
    if len(head) >= 2 and head[0] == "pid":
        try:
            return int(head[1])
        except ValueError:
            return 0
    return 0


def _conflict_label(rel):
    """충돌한 자리를 사람이 부르는 이름 — 문서는 id, 그 밖은 경로 그대로."""
    base = os.path.basename(rel)
    if rel.startswith("vault/") and base.endswith(".md"):
        return base[:-3]
    return rel


def _read_epoch_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return 0.0


def _rebase_in_progress():
    gd = os.path.join(ROOT, ".git")
    return (os.path.exists(os.path.join(gd, "rebase-merge"))
            or os.path.exists(os.path.join(gd, "rebase-apply")))


def _serve_owner_alive():
    """**이 저장소의** 대시보드 서버가 떠 있는가 — 전송의 주인이 있는가
    (REQ-20260902-023). 포트를 두드리면 다른 루트(시험용 임시 루트)에서도 실서버가
    답해 버린다 — 서버가 기동 시 남기는 지문(state/serve-code.json)의 pid 를 본다."""
    try:
        with open(os.path.join(ROOT, "state", "serve-code.json"), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return False
    pid = int((info or {}).get("pid") or 0)
    return bool(pid) and pid_alive(pid)


def _session_docs():
    """vault 의 세션 문서 전부 — (경로, meta, body)."""
    base = os.path.join(VAULT, "sessions")
    for dirpath, _dirs, files in os.walk(base):
        for fn in sorted(files):
            if not (fn.startswith("SES-") and fn.endswith(".md")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                meta, body = read_doc(path)
            except (OSError, ValueError):
                continue
            yield path, meta, body


def _stash_already_in_tree(ref):
    """그 보관함의 내용이 이미 작업 트리에 서 있는가 (REQ-20260915-060-62x6).

    판정은 git 에게 맡긴다 — 그 patch 를 **거꾸로** 적용해 보아 깨끗이 맞으면
    지금 트리에 그 내용이 이미 있다는 뜻이다(적용하지 않는다: `--check`).
    못 읽거나 판정이 안 서면 False — 모르는 것을 「담겼다」로 세면 사람이
    되돌리지 못한 작업을 조용히 잃는다."""
    if not ref:
        return False
    try:
        p = _sync_git("stash", "show", "-p", "--include-untracked", ref, timeout=30)
        if p.returncode != 0 or not (p.stdout or "").strip():
            return False
        r = subprocess.run(["git", "apply", "--reverse", "--check", "-"],
                           input=p.stdout, capture_output=True, encoding="utf-8",
                           errors="replace", cwd=ROOT, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def commit_module():
    """bin/s9_commit.py — 한 working tree 에서 여럿이 commit 하는 정식 길 (REQ-20260913-022-62x6).
    잠금(_sync_lock_take)·표식(_S9_COMMIT_MARK)·pid 판정은 이 이름공간의 것을 bind 로 받아
    두 벌이 되지 않는다. 한 번만 싣는다."""
    m = globals().get("_COMMIT_MODULE")
    if m is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "s9_commit", os.path.join(os.path.dirname(os.path.realpath(__file__)), "s9_commit.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.bind(globals())
        globals()["_COMMIT_MODULE"] = m
    return m


def git_run(argv, timeout=25):
    """이 화면이 git 에게 시킬 수 있는 전부 — **목록 밖은 부르기 전에 막는다.**

    셋을 함께 잰다: ① 하위명령이 읽기·네트워크 목록 안인가 ② 어느 토막에도
    금지 낱말이 없는가 ③ 네트워크 셋은 **모양까지** 정확한가. ③ 이 있는 이유는
    `pull` 이 허용 목록에 있다는 것만으로는 `pull --rebase` 를 못 막기
    때문이다 — 합치는 방식을 고르는 것은 화면의 일이 아니다(제약 ④)."""
    import subprocess as _sp
    argv = [str(a) for a in argv]
    if not argv:
        raise ValueError("빈 git 명령")
    verb = argv[0]
    for tok in argv:
        if tok in GIT_FORBIDDEN:
            raise ValueError("화면이 부를 수 없는 git 명령이다: %s (%s)"
                             % (tok, " ".join(argv)))
    if verb in GIT_NET_VERBS:
        shape = tuple(argv)
        if verb == "pull" and shape != ("pull", "--ff-only"):
            raise ValueError("pull 은 앞으로만 붙이는 방식뿐이다: %s"
                             % " ".join(argv))
        if verb == "push" and shape != ("push",):
            raise ValueError("push 에는 아무 옵션도 붙이지 않는다: %s"
                             % " ".join(argv))
        if verb == "fetch" and (len(argv) != 3 or argv[1] != "--quiet"):
            raise ValueError("fetch 는 한 곳에만 조용히 묻는다: %s"
                             % " ".join(argv))
    elif verb not in GIT_READ_VERBS:
        raise ValueError("화면이 부를 수 없는 git 명령이다: %s" % verb)
    return _sp.run(["git", "-C", ROOT, *argv],
                   capture_output=True,
                       encoding="utf-8", errors="replace", timeout=timeout)


def harness_id_from_transcript(path, tail=262144):
    """transcript 에 하네스가 적어 둔 이 세션의 바깥 이름표.

    표식(`claude.ai/code/session_…`)은 턴마다 들어오므로 꼬리만 읽는다 —
    프롬프트마다 수십 MB 를 다시 읽지 않기 위해서다.
    """
    if not path:
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail))
            blob = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    ids = _HARNESS_ID_RE.findall(blob)
    return "bridge:" + ids[-1] if ids else ""


def index_catch_up(quiet=True):
    """HEAD 가 표와 다르면 그 사이만 반영한다 — **어느 경로로 움직였든**.

    사고 2026-09-08 (REQ-20260908-017): 맥이 지운 문서의 삭제가 pull 로 들어왔는데
    목록에는 그대로 남아 「문서를 찾을 수 없습니다」가 떴다. 색인 쪽은 지운 문서를
    다룰 줄 안다(`index_upsert` 가 묘비를 세운다) — 빠진 것은 **그 길을 타지 않는
    pull** 이었다. HEAD 를 움직이는 자리는 넷인데(수신 폴 · `_pull_if_stale` ·
    전송 루프의 rebase · 사람이 손으로 친 `git pull`) 색인을 부르는 것은 앞의
    둘뿐이었다. 그래서 부르는 자리마다 잇는 대신, **표와 HEAD 를 견주는 자리**를
    하나 두고 서버 루프가 매 틱 묻는다.

    반환: 반영한 문서 수 · 전량으로 물러났으면 -1 · 할 일이 없으면 0.
    """
    head = repo_head_sha()
    if not head:
        return 0
    mark = _index_head_read()
    if mark == head:
        return 0
    n = index_sync_range(mark, head, quiet=quiet) if mark else -1
    if not mark:
        rebuild_index(quiet=quiet)
    index_head_stamp(head)
    return n


def machine_recv_beat(push=False, now=None, name=None):
    """이 컴퓨터가 마지막으로 받은 때를 등록부의 제 줄에 적는다.

    받은 때의 원천은 로컬의 폴 도장(_SYNC_PULL_TS) 하나다 — 여기서 시계를 따로
    만들지 않는다. push=True 면 적은 뒤 스스로 한 번 민다(조용한 컴퓨터의 길).
    돌려주는 값: 적었으면 True, 최소 간격에 걸렸거나 적을 자리가 없으면 False.

    등록부에 이 컴퓨터 줄이 없으면 **만들지 않는다** — 계정 이력은 세션이 적는
    것이고, 받았다는 사실 하나로 「이 사람이 여기서 일했다」를 지어내면 그 표가
    거짓이 된다."""
    import time as _time
    now = now or _time.time()
    if sync_mode() != "remote":
        return False
    got = _read_epoch_file(_SYNC_PULL_TS)
    if not got:
        return False                     # 아직 한 번도 받은 적이 없다
    name = name or _fp_user()
    if not name:
        return False
    ppath = os.path.join(USERS, name, "profile.md")
    if not os.path.isfile(ppath):
        return False
    machine, acct = current_machine(), getpass.getuser()
    try:
        with open(ppath, encoding="utf-8") as f:
            meta, body = fm_parse(f.read())
    except OSError:
        return False
    rows = meta.get("machine_accounts") or []
    row = next((r for r in rows if isinstance(r, dict)
                and r.get("machine") == machine and r.get("account") == acct), None)
    if row is None:
        return False
    prev = _epoch(row.get("last_recv"))
    if prev and now - prev < MACHINE_RECV_BEAT_SEC:
        return False                     # 최소 간격 — 폴이 commit 이 되지 않게
    if prev and prev >= got:
        return False                     # 적힌 것이 더 새것이다 (되돌려 적지 않는다)
    row["last_recv"] = datetime.datetime.fromtimestamp(got).astimezone().isoformat(
        timespec="seconds")
    # 담기지 않은 일도 같은 줄에 싣는다 (REQ-20260911-001) — 받은 때와 같은
    # 규칙이다: 나가는 것은 **사실 한 줄**이고 적는 것은 언제나 제 줄뿐이다.
    # 0 은 적지 않는다 — 깨끗한 것이 보통이라, 적으면 표가 0 으로 뒤덮인다.
    _un = machine_uncommitted()
    if _un > 0:
        row["uncommitted"] = _un
    else:
        row.pop("uncommitted", None)
    meta["machine_accounts"] = rows
    write_doc(ppath, meta, body)
    if push:
        try:
            sync_run("recv-beat")
        except Exception:
            pass
    return True


def machine_recv_lines(user=None, now=None):
    """컴퓨터마다 「이름 — 마지막 받음 N분 전」 한 줄씩 (CLI 표시용).

    임계를 넘은 줄만 사유를 덧붙인다 — 다 괜찮은데 다 떠드는 목록은 아무것도
    말하지 않는 것과 같다."""
    import time as _time
    now = now or _time.time()
    out = []
    for mv, v in sorted(machine_table(user).items()):
        lr = v.get("last_recv") or ""
        if not lr:
            continue
        lvl = machine_recv_level(lr, now)
        line = f"{machine_phrase(mv, user)} — 마지막 받음 {_ago_word(_epoch(lr), now)}"
        if lvl:
            line += "  [사고 — 오래 못 받고 있다]" if lvl == "stale" else "  [주의]"
        out.append(line)
    return out


def note_call_name(src, name):
    """관측한 (보낸 쪽 id → 부르는 이름) 을 그 id 를 적어 둔 문서에 적는다.

    적을 문서를 못 찾으면 버리지 않고 대기에 남긴다 — 상대가 제 이름표를 적어
    동기화되는 순간 채워진다. 채운 문서 id 를 돌려준다(못 찾으면 빈 문자열).
    """
    name = clean_call_name(name)
    if not src or not name:
        return ""
    for path, meta, body in _session_docs():
        if meta.get("harness_session") != src:
            continue
        if meta.get("call_name") != name:
            meta["call_name"] = name
            meta["updated"] = now_iso()
            write_doc(path, meta, body)
        pend = read_call_pending()
        if pend.pop(src, None) is not None:
            write_call_pending(pend)
        return meta.get("id", "")
    pend = read_call_pending()
    if pend.get(src, {}).get("name") != name:
        pend[src] = {"name": name, "seen": now_iso()}
        write_call_pending(pend)
    return ""


def parse_cross_session(text):
    """프롬프트 **머리**의 하네스 표식에서 (보낸 쪽 id, 부르는 이름).

    머리에서만 읽는다 — 본문에 인용된 같은 글자는 하네스가 붙인 것이 아니라
    사람이 적은 글자다. 그것으로 이름을 적으면 지어낸 이름이 된다.
    """
    m = CROSS_TAG_RE.match(text or "")
    if not m:
        return None
    at = dict(_ATTR_RE.findall(m.group(1)))
    src = (at.get("from") or "").strip()
    name = clean_call_name(at.get("from-name") or "")
    if not src or not name:
        return None
    return src, name


def resolve_call_names():
    """대기 중인 관측을 다시 짝지어 본다 — 채운 문서 id 목록."""
    pend = read_call_pending()
    if not pend:
        return []
    filled = []
    for src, v in list(pend.items()):
        did = note_call_name(src, (v or {}).get("name", ""))
        if did:
            filled.append(did)
    return filled