#!/usr/bin/env python3
"""bin/s9_commit.py — 한 working tree 에서 여럿이 commit 하는 정식 길 (REQ-20260913-022-62x6).

    s9 commit [-m 메시지 | -F 파일] [--hunks <patch>] [--wait 초] -- <경로…>

무엇을 담나. **HEAD 대비 지정한 경로의 변경만.** 공유 index(.git/index)는 읽지도
쓰지도 않는다 — 임시 index 에 HEAD 를 읽고(read-tree) 거기에 경로를 add 하므로,
남이 공유 index 에 담아 둔 것은 이 commit 에 실리지 않고 그대로 남는다.
`--hunks <patch>` 는 그 patch 의 hunk 만 담는다(apply --cached): 남이 고치는 중인
공유 파일(bin/s9.py)에서 내 hunk 만 가를 때. patch 가 건드리는 경로는 지정한
경로 안에 있어야 한다.

언제 담나. sync 회차(commit→pull→push)와 겹치지 않는 창에서. 실측 2026-09-13
(devops-engineer, REQ-20260913-006-62x6): 임시 index 로 commit 하면 `.git/index.lock`
이 안 잡혀 sync 가 진행 중인 commit 을 못 보고, 훅(검사 40초)이 도는 사이 sync
commit 이 HEAD 를 옮겨 `cannot lock ref HEAD` 로 두 번 실패했다. 그래서 셋을 한다:
① `state/.sync.lock` 을 잡는다 — 이미 도는 회차는 끝날 때까지 기다리고, 잡은 뒤에는
   새 회차가 서지 않는다(sync_run 은 30초 안의 잠금을 보면 회차를 미룬다).
② `state/s9-commit-in-progress` 표식(pid)을 둔다 — `_sync_commit_busy` 가 이것을
   셋째 항목으로 본다(REQ-20260906-030 의 계약을 넓힌 자리). pid 가 죽은 표식은
   남은 파일로 보고 무시한다.
③ commit 동안 잠금의 mtime 을 5초마다 갱신한다 — 검사가 30초를 넘겨도 잠금이
   낡은 것으로 판정돼 sync 에 제거되지 않게.

commit 뒤. 공유 index 의 그 경로가 옛 HEAD blob 그대로면(아무도 담지 않았으면) 새
HEAD blob 으로 맞춘다. 맞추지 않으면 `git diff --cached` 가 내 변경의 **역방향**을
「담긴 것」으로 보이고, 다음 사람의 pathspec 없는 `git commit` 이 내 변경을 되돌린다
(scratch 저장소 실측 2026-09-13 — DOC-20260913-004-62x6 의 절차에 없던 자리). 남이
담아 둔 항목(index blob ≠ 옛 HEAD)은 그대로 둔다: 그 사람의 `git add` 는 그 사람의 것이다.

동시 작업 표(S9_ALLOW_CONCURRENT)는 같은 임시 index 로 `s9-guard --concurrent` 를
한 번 불러 그 목록을 화면에 보이고, 같은 실행의 `git commit` 에 그대로 쓴다 —
공유 index 로는 남의 add 가 섞일 때마다 표가 바뀌어 사람이 두세 번 다시 걸어야
했다(실측 2026-09-13 ④). 임시 index 는 이 실행 안에서 바뀌지 않으므로 표도 안 바뀐다.

s9.py 의 헬퍼(ROOT · _sync_lock_take · _sync_commit_busy · pid_alive)는 bind() 로
받는다 — 잠금과 표식의 정의를 두 벌로 두지 않는다. 훅(pre-commit=s9-guard ·
commit-msg · post-commit)은 그대로 돈다: `--no-verify` 는 어디에도 없다.

종료 코드: 0 성공 · 1 git/훅 거부 · 2 인자·내용 거부(경로 없음·변경 없음·메시지 없음·
patch 범위 밖) · 3 기다림 초과(sync 회차 또는 다른 commit 이 --wait 안에 안 끝남).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

_S9 = {}                      # bind() 가 채운다 — s9.py 의 이름공간
LOCK_TOUCH_SEC = 5            # 잠금 mtime 갱신 간격 — sync 의 30초 낡음 판정보다 충분히 짧다
WAIT_POLL_SEC = 0.25
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_INDEX_VERSION",
                "GIT_QUARANTINE_PATH")
_TOKEN_RE = re.compile(r"S9_ALLOW_CONCURRENT=([0-9a-f]{4,})")

USAGE = ("usage: s9 commit [-m 메시지 | -F 파일] [--hunks <patch>] [--wait 초] -- <경로…>\n"
         "  지정한 경로의 HEAD 대비 변경만 임시 index 로 commit 한다 — 공유 index 의\n"
         "  남의 항목은 실리지 않고 그대로 남는다. sync 회차·다른 commit 이 끝나기를\n"
         "  기다렸다가(--wait, 기본 90초) 그 잠금 아래에서 commit 하므로 훅이 도는 동안\n"
         "  HEAD 가 옮겨지지 않는다. 훅(s9-guard·commit-msg·post-commit)은 그대로 돈다.\n"
         "  --hunks <patch>: 그 patch 의 hunk 만 담는다 (patch 의 경로는 <경로…> 안이어야 한다)\n"
         "  -F -: 메시지를 stdin 에서 읽는다")


def bind(g):
    """s9.py 의 이름공간을 받는다 — ROOT·잠금·표식·pid 판정을 한 벌로 쓴다."""
    _S9.update(g)


def root():
    return _S9["ROOT"]


def mark_path():
    return _S9.get("_S9_COMMIT_MARK") or os.path.join(root(), "state", "s9-commit-in-progress")


def code_root():
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def clean_env(**extra):
    """git 훅 아래에서 물려받았을 GIT_* 를 벗긴 환경 + 덧붙일 것."""
    e = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    e.update(extra)
    return e


def git(*argv, env=None, timeout=120, input=None):
    return subprocess.run(["git", "-C", root(), *argv], env=env or clean_env(),
                          capture_output=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=input)


def parse_argv(argv):
    """옵션은 `--` 앞뒤 어디에 와도 받는다 — argparse 는 `--` 뒤를 전부 위치 인자로
    읽어 `s9 commit -- <경로…> -m …` 을 못 받는다. 반환: (opts, paths) 또는 usage 오류
    문자열."""
    opts = {"message": [], "msg_file": None, "hunks": None, "wait": 90.0, "help": False}
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            i += 1
            continue
        if a in ("-h", "--help"):
            opts["help"] = True
            i += 1
            continue
        if a in ("-m", "--message", "-F", "--file", "--hunks", "--wait"):
            if i + 1 >= len(argv):
                return f"{a} 에 값이 없다", None
            v = argv[i + 1]
            if a in ("-m", "--message"):
                opts["message"].append(v)
            elif a in ("-F", "--file"):
                opts["msg_file"] = v
            elif a == "--hunks":
                opts["hunks"] = v
            else:
                try:
                    opts["wait"] = float(v)
                except ValueError:
                    return f"--wait 는 초 단위 숫자다: {v}", None
            i += 2
            continue
        if a.startswith("-m") and len(a) > 2:      # -m"메시지" 붙여 쓴 꼴
            opts["message"].append(a[2:])
            i += 1
            continue
        if a.startswith("-") and not os.path.exists(os.path.join(root(), a)):
            return f"모르는 옵션: {a}", None
        paths.append(a)
        i += 1
    return opts, paths


def rel_paths(paths):
    """저장소 루트 기준 경로로 — 절대 경로·cwd 기준 상대 경로 둘 다 받는다."""
    out = []
    rt = os.path.realpath(root())
    for p in paths:
        cand = p
        if os.path.isabs(p):
            cand = os.path.relpath(os.path.realpath(p), rt)
        elif not os.path.lexists(os.path.join(rt, p)) and os.path.lexists(p):
            cand = os.path.relpath(os.path.realpath(p), rt)
        cand = cand.replace(os.sep, "/").rstrip("/")
        if cand.startswith("../"):
            return None, f"저장소 밖의 경로: {p}"
        out.append(cand)
    return out, ""


def read_message(opts):
    if opts["message"] and opts["msg_file"]:
        return None, "-m 과 -F 는 함께 쓰지 않는다"
    if opts["message"]:
        return "\n\n".join(opts["message"]).rstrip() + "\n", ""
    if opts["msg_file"]:
        try:
            if opts["msg_file"] == "-":
                body = sys.stdin.read()
            else:
                with open(opts["msg_file"], encoding="utf-8") as f:
                    body = f.read()
        except OSError as e:
            return None, f"메시지 파일을 읽지 못했다: {e}"
        if body.strip():
            return body.rstrip() + "\n", ""
    return None, "commit 메시지가 없다 — -m '…' 또는 -F <파일>"


def patch_paths(patch):
    """patch 가 건드리는 경로 — `git apply --numstat` 의 셋째 칸 (index 를 안 건드린다)."""
    r = git("apply", "--numstat", "-z", "--", patch)
    if r.returncode != 0:
        return None, r.stderr.strip()
    names = []
    for rec in r.stdout.split("\0"):
        if not rec.strip():
            continue
        parts = rec.split("\t", 2)
        if len(parts) == 3:
            names.append(parts[2])
    return names, ""


# ------------------------------------------------------------ 잠금·표식

def mark_write():
    p = mark_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"pid {os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
    except OSError:
        pass


def mark_clear():
    try:
        os.remove(mark_path())
    except OSError:
        pass


def mark_pid_alive(path):
    """표식의 pid 가 살아 있는가 — 파일이 사라졌으면 False, 형식을 모르면 True(나이로만 판정)."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.readline().split()
    except OSError:
        return False
    if len(head) >= 2 and head[0] == "pid":
        alive = _S9.get("pid_alive")
        if alive is not None:
            return bool(alive(head[1]))
    return True


def take_sync_window(wait_sec, err):
    """sync 잠금을 잡고 다른 commit 이 없는 창을 만든다. 반환: 잠금 경로 또는 ''(초과).

    잠금을 먼저 잡는다 — 잡은 뒤로는 새 sync 회차가 서지 않으니, 그 다음
    「다른 commit 이 진행 중」이 풀리기를 잠금을 쥔 채 기다린다(사이에 회차가
    끼어들 수 없게)."""
    deadline = time.time() + max(0.0, float(wait_sec))
    lock = ""
    said = set()
    while True:
        if not lock:
            lock = _S9["_sync_lock_take"](30)
            if not lock:
                if "sync" not in said:
                    print("동기화 회차가 실행 중 — 끝나기를 기다린다 (state/.sync.lock)", file=err)
                    said.add("sync")
        if lock:
            busy = _S9["_sync_commit_busy"]()
            if not busy:
                return lock
            if busy not in said:
                print(f"다른 commit 이 진행 중({busy}) — 끝나기를 기다린다", file=err)
                said.add(busy)
        if time.time() >= deadline:
            if lock:
                try:
                    os.remove(lock)
                except OSError:
                    pass
            return ""
        time.sleep(WAIT_POLL_SEC)


class LockToucher:
    """commit 이 도는 동안 잠금 파일의 mtime 을 갱신한다 — 훅의 검사가 30초를 넘겨도
    sync 가 잠금을 낡은 것으로 보고 제거하지 않게."""

    def __init__(self, path):
        self.path = path
        self.stop = threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop.wait(LOCK_TOUCH_SEC):
            try:
                os.utime(self.path, None)
            except OSError:
                return

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.t.join(timeout=1.0)


# ------------------------------------------------------------ 공유 index 맞추기

def _tree_entries(rev, paths):
    """{경로: (mode, sha)} — 그 rev 의 트리에서."""
    r = git("ls-tree", "-r", "-z", rev, "--", *paths)
    out = {}
    if r.returncode != 0:
        return out
    for rec in r.stdout.split("\0"):
        if not rec:
            continue
        meta, _, name = rec.partition("\t")
        parts = meta.split()
        if len(parts) >= 3:
            out[name] = (parts[0], parts[2])
    return out


def _index_entries(paths):
    """{경로: (mode, sha)} — 공유 index 에서 (stage 0 만)."""
    r = git("ls-files", "-s", "-z", "--", *paths)
    out = {}
    if r.returncode != 0:
        return out
    for rec in r.stdout.split("\0"):
        if not rec:
            continue
        meta, _, name = rec.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[2] == "0":
            out[name] = (parts[0], parts[1])
    return out


def reconcile_shared_index(old, new, paths, err):
    """commit 뒤 공유 index 의 그 경로를 새 HEAD 에 맞춘다 — **옛 HEAD 와 같은
    항목만**(아무도 담지 않은 것). 남이 담아 둔 항목(index ≠ 옛 HEAD)은 그대로.
    반환: 맞춘 경로 목록."""
    if not paths:
        return []
    before = _tree_entries(old, paths)
    after = _tree_entries(new, paths)
    idx = _index_entries(paths)
    lines = []
    fixed = []
    for p in paths:
        o = before.get(p)
        n = after.get(p)
        i = idx.get(p)
        if (i[1] if i else None) != (o[1] if o else None):
            continue                    # 남의 add 다 — 건드리지 않는다
        if (i[1] if i else None) == (n[1] if n else None):
            continue                    # 이미 같다
        if n:
            lines.append(f"{n[0]} {n[1]}\t{p}")
        else:
            lines.append(f"0 {'0' * 40}\t{p}")      # 삭제된 경로 — index 에서도 뺀다
        fixed.append(p)
    if not lines:
        return []
    payload = "\0".join(lines) + "\0"
    for attempt in range(5):
        r = git("update-index", "-z", "--index-info", input=payload)
        if r.returncode == 0:
            return fixed
        if "index.lock" not in (r.stderr or "") or attempt == 4:
            print(f"경고: 공유 index 를 새 HEAD 에 맞추지 못했다 — {r.stderr.strip()[:160]}\n"
                  f"  `git diff --cached` 에 이 경로의 역방향이 담긴 것으로 보일 수 있다: "
                  f"{' '.join(fixed)}", file=err)
            return []
        time.sleep(0.2)                 # 남의 git add 가 index.lock 을 잠깐 쥐고 있다
    return []


# ------------------------------------------------------------ 본체

def do_commit(paths, message, hunks=None, wait=90.0, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    rt = root()
    r = git("rev-parse", "--verify", "-q", "HEAD")
    if r.returncode != 0:
        print("HEAD 가 없다 — 첫 commit 은 git commit 으로", file=err)
        return 2
    old = r.stdout.strip()
    patched = []
    if hunks:
        if not os.path.isfile(hunks):
            print(f"--hunks: patch 파일이 없다: {hunks}", file=err)
            return 2
        patched, why = patch_paths(hunks)
        if patched is None:
            print(f"--hunks: patch 를 읽지 못했다 — {why}", file=err)
            return 2
        outside = sorted(set(patched) - set(paths))
        if outside:
            print("--hunks: patch 가 지정하지 않은 경로를 건드린다 — 그 경로도 <경로…> 에 적어라: "
                  + " ".join(outside), file=err)
            return 2
    lock = take_sync_window(wait, err)
    if not lock:
        print(f"{wait:.0f}초 안에 조용한 창이 안 났다 — 잠시 뒤 다시 하거나 --wait 를 늘려라",
              file=err)
        return 3
    tmp = tempfile.mkdtemp(prefix="s9commit-")
    idx = os.path.join(tmp, "index")
    env = clean_env(GIT_INDEX_FILE=idx, S9_ROOT=rt)
    try:
        with LockToucher(lock):
            mark_write()
            r = git("read-tree", "HEAD", env=env)
            if r.returncode != 0:
                print(f"임시 index 를 만들지 못했다 — {r.stderr.strip()[:200]}", file=err)
                return 1
            if hunks:
                r = git("apply", "--cached", "--", hunks, env=env)
                if r.returncode != 0:
                    print(f"--hunks: patch 가 HEAD 에 맞지 않는다 — {r.stderr.strip()[:300]}",
                          file=err)
                    return 2
            rest = [p for p in paths if p not in set(patched)]
            if rest:
                r = git("add", "--", *rest, env=env)
                if r.returncode != 0:
                    print(f"경로를 담지 못했다 — {r.stderr.strip()[:300]}", file=err)
                    return 2
            r = git("diff", "--cached", "--name-only", "-z", env=env)
            staged = [n for n in r.stdout.split("\0") if n]
            if not staged:
                print("HEAD 대비 변경이 없다: " + " ".join(paths), file=err)
                return 2
            print("담는 것 (HEAD 대비): " + " ".join(staged), file=out)
            # 동시 작업 표 — 같은 임시 index 로 한 번 계산해 이 실행에 쓴다.
            guard = os.path.join(code_root(), "bin", "s9-guard")
            if os.path.isfile(guard):
                g = subprocess.run([sys.executable, guard, "--concurrent"], env=env,
                                   cwd=rt, capture_output=True, encoding="utf-8",
                                   errors="replace", timeout=60)
                text = (g.stdout or "") + (g.stderr or "")
                m = _TOKEN_RE.search(text)
                if m:
                    print(text.rstrip(), file=out)
                    env["S9_ALLOW_CONCURRENT"] = m.group(1)
            msg_path = os.path.join(tmp, "msg")
            with open(msg_path, "w", encoding="utf-8") as f:
                f.write(message)
            # 훅의 출력은 그대로 흘려 보낸다 — 검사가 왜 막았는지 사람이 읽어야 한다.
            p = subprocess.Popen(["git", "-C", rt, "commit", "-q", "-F", msg_path],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding="utf-8", errors="replace")
            collected = []
            for line in p.stdout:
                err.write(line)
                collected.append(line)
            rc = p.wait()
            if rc != 0:
                text = "".join(collected)
                if "cannot lock ref" in text:
                    print("HEAD 가 그 사이 옮겨졌다 — 잠금 밖에서 누군가 commit/pull 했다. 다시 실행",
                          file=err)
                else:
                    print(f"git commit 이 거부됐다 (exit {rc})", file=err)
                return 1
            new = git("rev-parse", "HEAD").stdout.strip()
            parent = git("rev-parse", "HEAD~1").stdout.strip()
            if parent != old:
                print(f"경고: 새 commit {new[:9]} 의 부모가 시작 때의 HEAD({old[:9]})가 아니다 — "
                      f"{parent[:9]}", file=err)
            r = git("diff-tree", "-r", "--no-commit-id", "--name-only", "-z", new)
            committed = [n for n in r.stdout.split("\0") if n]
            fixed = reconcile_shared_index(old, new, committed, err)
            print(f"commit {new[:9]} — {len(committed)}개 파일: " + " ".join(committed), file=out)
            if fixed:
                print("공유 index 를 새 HEAD 에 맞췄다: " + " ".join(fixed), file=out)
            return 0
    finally:
        mark_clear()
        try:
            os.remove(lock)
        except OSError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    opts, paths = parse_argv(list(argv or []))
    if paths is None:
        print(opts, file=err)
        print(USAGE, file=err)
        return 2
    if opts["help"]:
        print(USAGE, file=out)
        return 0
    if not paths:
        print("담을 경로가 없다", file=err)
        print(USAGE, file=err)
        return 2
    rel, why = rel_paths(paths)
    if rel is None:
        print(why, file=err)
        return 2
    message, why = read_message(opts)
    if message is None:
        print(why, file=err)
        return 2
    return do_commit(rel, message, hunks=opts["hunks"], wait=opts["wait"], out=out, err=err)


if __name__ == "__main__":       # 단독 실행은 지원하지 않는다 — s9 의 이름공간이 필요하다
    print("이 모듈은 `s9 commit` 이 싣는다 — bin/s9 commit … 으로 실행하라", file=sys.stderr)
    sys.exit(2)
