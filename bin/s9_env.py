"""기존 환경의 승계·정리·백업 (REQ-20260905-025) — s9 와 s9-install 이 함께 쓰는 모듈.

원칙(product-owner·architect·security-engineer 판정): 남이 쓴 것은 지우지 않는다 ·
우리가 쓰는 것만 다시 쓴다 · 자격증명은 읽지도 백업하지도 않는다 · 백업은 검증 없이는
백업이 아니다 · 승계는 사람이 고른 줄만.

1차 판: ① 설치 때 조용한 백업(복사, KB 급 항목만) + `s9 env restore` ② 설치 표식
(state/installed_at) 이전이고 바인딩 없는 transcript 는 후보에서 뺀다 ③ `s9 env inherit`
로 옛 CLAUDE.md·메모리 항목을 골라 `pref_승계` 로. 옛 파일의 이동·정리는 2차(파생 REQ).
"""
import datetime
import hashlib
import json
import os
import shutil
import stat

# 백업할 것 — 우리가 만지거나(settings.json) 승계 후보로 읽는(CLAUDE.md·메모리) 작은 파일만.
# 자격증명(.credentials.json·~/.claude.json)은 목록에 **없다** — 만지지 않으니 백업할 이유가
# 없고, 넣는 순간 백업이 토큰이 된다(security). transcript(GB 급)는 2차의 이동 몫.
BACKUP_ITEMS = ("settings.json", "CLAUDE.md", "projects/*/memory")
NEVER = (".credentials.json",)
MAX_COPY_BYTES = 50 * 1024 * 1024        # 이보다 크면 오분류다 — 멈춘다


def config_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def backups_root(config=None):
    """저장소 밖·~/.claude 밖 — 재설치의 `rm -rf ~/section9` 가 백업을 같이 지우지 않는다."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    tag = os.path.basename(os.path.realpath(config or config_home())).lstrip(".") or "claude"
    return os.path.join(base, "section9", "backups", tag)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_items(home):
    """(상대경로, 절대경로) — BACKUP_ITEMS 를 펼친다. 심링크는 따라가지 않는다."""
    import glob as _glob
    out = []
    for pat in BACKUP_ITEMS:
        for p in sorted(_glob.glob(os.path.join(home, pat))):
            if os.path.islink(p):
                continue
            if os.path.isdir(p):
                for dp, _dn, fns in os.walk(p):
                    for fn in fns:
                        fp = os.path.join(dp, fn)
                        if not os.path.islink(fp) and os.path.isfile(fp):
                            out.append((os.path.relpath(fp, home), fp))
            elif os.path.isfile(p):
                out.append((os.path.relpath(p, home), p))
    return [(r, a) for r, a in out if os.path.basename(r) not in NEVER]


def backup(home=None, root=None, now=None, reason="install"):
    """조용한 백업. 반환 dict(dir, entries, bytes) — 옮길 것이 없으면 dir 없이 entries=[].

    쓰기 순서: <ts>.partial 에 복사 → 전수 sha256 재검증 → manifest.json → rename → LATEST.
    권한은 0700/0600(umask 077) 뒤 stat 로 확인. 절대 덮어쓰지 않는다(매번 새 ts).
    """
    home = home or config_home()
    root = root or backups_root(home)
    items = _walk_items(home)
    if not items:
        return {"dir": "", "entries": [], "bytes": 0}
    total = sum(os.path.getsize(a) for _r, a in items)
    if total > MAX_COPY_BYTES:
        raise RuntimeError(f"백업 대상이 {total // (1 << 20)}MB — 오분류다, 멈춘다")
    ts = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    final = os.path.join(root, ts)
    if os.path.exists(final):
        raise RuntimeError(f"같은 시각의 백업이 있다: {final}")
    partial = final + ".partial"
    old_umask = os.umask(0o077)
    try:
        os.makedirs(partial, exist_ok=False)
        entries = []
        for rel, src in items:
            dst = os.path.join(partial, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            os.chmod(dst, 0o600)
            with open(dst, "rb") as f:
                os.fsync(f.fileno())
            entries.append({"rel": rel, "op": "copy", "bytes": os.path.getsize(src),
                            "mtime": os.path.getmtime(src), "sha256": _sha256(src)})
        for e in entries:                      # 읽어 확인하지 않은 백업은 백업이 아니다
            if _sha256(os.path.join(partial, e["rel"])) != e["sha256"]:
                raise RuntimeError(f"백업 검증 실패: {e['rel']}")
        manifest = {"at": ts, "home": home, "reason": reason, "entries": entries,
                    "total_bytes": total, "version": 1}
        with open(os.path.join(partial, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.flush(); os.fsync(f.fileno())
        os.chmod(partial, 0o700)
        os.rename(partial, final)
        with open(os.path.join(root, "LATEST"), "w", encoding="utf-8") as f:
            f.write(ts + "\n")
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    finally:
        os.umask(old_umask)
    if stat.S_IMODE(os.stat(final).st_mode) & 0o077:
        raise RuntimeError(f"권한을 지키지 못하는 파일시스템이다: {final}")
    return {"dir": final, "entries": entries, "bytes": total}


def list_backups(root=None):
    root = root or backups_root()
    try:
        return sorted(n for n in os.listdir(root)
                      if os.path.isfile(os.path.join(root, n, "manifest.json")))
    except OSError:
        return []


def restore(which="latest", home=None, root=None, dry_run=False):
    """manifest 대로 원위치에 되돌린다. 원위치에 **다른** 파일이 있으면 덮지 않고
    `.s9-conflict-<ts>` 로 비켜 세운다. 반환 dict(restored, skipped, conflicts)."""
    home = home or config_home()
    root = root or backups_root(home)
    if which == "latest":
        try:
            with open(os.path.join(root, "LATEST"), encoding="utf-8") as f:
                which = f.read().strip()
        except OSError:
            raise RuntimeError("되돌릴 백업이 없다")
    bdir = os.path.join(root, which)
    with open(os.path.join(bdir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    res = {"at": which, "restored": [], "skipped": [], "conflicts": [], "dry_run": dry_run}
    for e in manifest["entries"]:
        src = os.path.join(bdir, e["rel"])
        dst = os.path.join(home, e["rel"])
        if _sha256(src) != e["sha256"]:
            raise RuntimeError(f"백업이 손상됐다: {e['rel']}")
        if os.path.exists(dst) and _sha256(dst) == e["sha256"]:
            res["skipped"].append(e["rel"])            # 이미 같다
            continue
        if os.path.exists(dst):
            aside = dst + f".s9-conflict-{manifest['at']}"
            res["conflicts"].append((e["rel"], aside))
            if not dry_run:
                os.rename(dst, aside)
        res["restored"].append(e["rel"])
        if not dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    return res


INHERIT_SOURCES = ("CLAUDE.md", "projects/*/memory/MEMORY.md")


def inherit_candidates(bdir):
    """백업본의 CLAUDE.md·MEMORY.md 에서 목록 항목(- · *)만 뽑는다 — 데이터로 보여줄 뿐
    실행하지 않는다. 반환 [(출처 상대경로, 줄)]."""
    import glob as _glob
    out = []
    for pat in INHERIT_SOURCES:
        for p in sorted(_glob.glob(os.path.join(bdir, pat))):
            rel = os.path.relpath(p, bdir)
            try:
                lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
            except OSError:
                continue
            for ln in lines:
                s = ln.strip()
                if s.startswith(("- ", "* ")) and len(s) > 4:
                    out.append((rel, s[2:].strip()[:300]))
    return out


RESET_DIRS = ("state", "index")   # 기계 상태 — 문서(vault·users·projects)는 아니다


def reset_root(root):
    """저장소의 기계 상태 백업 자리 — ~/.claude 백업과 같은 지붕, 다른 방."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    tag = os.path.basename(os.path.realpath(root)) or "section9"
    return os.path.join(base, "section9", "reset", tag)


def reset_backup(root, now=None):
    """state/·index/ 를 통째로 복사해 둔다 (REQ-20260905-028). 반환 백업 디렉토리(없으면 "")."""
    import shutil as _sh
    ts = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(reset_root(root), ts)
    n = 1
    while os.path.exists(dest):          # 같은 초에 두 번 — 덮어쓰지도 섞지도 않는다
        n += 1
        dest = os.path.join(reset_root(root), f"{ts}-{n}")
    any_ = False
    for d in RESET_DIRS:
        src = os.path.join(root, d)
        if os.path.isdir(src) and os.listdir(src):
            _sh.copytree(src, os.path.join(dest, d), symlinks=True,
                         ignore_dangling_symlinks=True, dirs_exist_ok=True)
            any_ = True
    if not any_:
        return ""
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"root": os.path.realpath(root), "at": ts, "dirs": list(RESET_DIRS)}, f)
    return dest


def reset_backups(root):
    r = reset_root(root)
    try:
        return sorted(n for n in os.listdir(r) if os.path.isfile(os.path.join(r, n, "manifest.json")))
    except OSError:
        return []


def reset_clear(root, dry_run=False):
    """state/·index/ 의 내용물만 비운다 — 디렉토리는 남긴다. 반환 지운 항목 경로들."""
    import shutil as _sh
    gone = []
    for d in RESET_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name)
            gone.append(p)
            if dry_run:
                continue
            if os.path.islink(p) or os.path.isfile(p):
                os.remove(p)
            else:
                _sh.rmtree(p, ignore_errors=True)
    return gone


def reset_restore(root, which, dry_run=False):
    """reset 백업을 되돌린다 — 지금 state/·index/ 는 먼저 비운다(그 전에 다시 백업)."""
    import shutil as _sh
    src = os.path.join(reset_root(root), which)
    if not os.path.isfile(os.path.join(src, "manifest.json")):
        raise FileNotFoundError(f"reset 백업이 없다: {src}")
    if dry_run:
        return {"from": src, "dirs": [d for d in RESET_DIRS if os.path.isdir(os.path.join(src, d))]}
    pre = reset_backup(root)
    reset_clear(root)
    for d in RESET_DIRS:
        sd = os.path.join(src, d)
        if os.path.isdir(sd):
            _sh.copytree(sd, os.path.join(root, d), symlinks=True, dirs_exist_ok=True)
    return {"from": src, "pre": pre}


def installed_at_path(root):
    return os.path.join(root, "state", "installed_at")


def mark_installed(root, now=None):
    """설치 표식 — 이미 있으면 바꾸지 않는다(첫 설치 시각이 판정 기준)."""
    p = installed_at_path(root)
    if os.path.exists(p):
        return False
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(str(int((now or datetime.datetime.now()).timestamp())) + "\n")
    return True


def installed_at(root):
    try:
        with open(installed_at_path(root), encoding="utf-8") as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return 0.0


def predates_install(path, root):
    """이 transcript 가 설치 전의 것인가 — 설치 표식이 없으면 False(모르면 안 뺀다)."""
    at = installed_at(root)
    if not at:
        return False
    try:
        return os.path.getmtime(path) < at
    except OSError:
        return False
