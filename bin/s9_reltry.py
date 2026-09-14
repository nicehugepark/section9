"""s9 release try — 배포판을 만들어 풀고 첫 실행까지 스스로 시험한다 (REQ-20260913-020).

맥의 백그라운드 작업자는 `bin/s9 …` 와 `python3 tests/ …` 만 실행할 수 있어 tar·
python3·bin/s9-release 를 직접 못 부른다 — 배포판 실측이 「사람이 맥 앞에 앉을
때까지」 막혀 있었다. 이 명령 하나가 그 절차 전부다:
  ① bin/s9-release 로 tar.gz·zip·SHA256SUMS 를 만든다(코드만 — vault·users·projects 없음)
  ② tar.gz 를 scratchpad/release-try/ 아래에 푼다(tarfile — 바깥 tar 불필요)
  ③ 그 자리에서 `bin/s9 code --no-open` 을 claude 실행 직전까지(S9_CODE_DRYRUN=1) 돌린다 —
     HOME·CLAUDE_CONFIG_DIR 은 임시 폴더라 사람의 설정을 건드리지 않는다
  ④ 확인: .git(main, commit 1) · .s9-sync local · 훅이 임시 설정에 · 대시보드가 그 자리에서 답한다
  ⑤ 이름을 등록하고 기본 프로젝트를 세운다 — 사람이라면 첫 실행의 이름 물음이 하는 일인데
     여기는 비대화형이라 그 물음이 뜨지 않으므로 `s9 user add` · `s9 init` 으로 같은 함수를
     지난다 — 그리고 general 에 사용법 안내(onboarding) 요청이 open 으로 섰는지 센다
     (REQ-20260914-011-62x6; 배포판에 harness/common/onboarding/*.md 가 있을 때만 N≥1 을 요구)
  ⑥ 서버를 내리고 폴더를 지운다(--keep 이면 남긴다)
출력은 사람이 읽는 보고다 — 가이드의 「예상 출력」과 맞춰 보는 자리.
"""
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

TRY_DIR = os.path.join("scratchpad", "release-try")
CODE_TIMEOUT = 240
PORT_LO, PORT_HI = 9960, 9990


def free_port(lo=PORT_LO, hi=PORT_HI):
    for p in range(lo, hi):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return 0


def clean_env(base):
    """러너·훅이 실은 S9_*·GIT_* 를 걷어 사람의 셸에 가깝게."""
    return {k: v for k, v in base.items()
            if not k.startswith(("S9_", "GIT_")) and k not in ("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME")}


def os_account():
    try:
        return getpass.getuser() or "user"
    except Exception:          # 계정 정보가 없는 컨테이너 — getpass 가 KeyError 를 낸다
        return "user"


def s9_run(site, env, *argv, timeout=120):
    """푼 자리의 bin/s9 한 번 — (exit, 출력)."""
    r = subprocess.run([sys.executable, os.path.join(site, "bin", "s9"), *argv],
                       cwd=site, env=env, capture_output=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def onboarding_count(site, env, log):
    """(배포판의 안내 파일 수, general 에 open 으로 선 onboarding 요청 수, 기본 프로젝트가 섰나).

    사람의 첫 실행은 이름 물음 뒤에 기본 프로젝트를 세우고 그 자리에서 안내를 심는다
    (bin/s9.py ensure_default_project). 비대화형에서는 물음이 뜨지 않으므로 그 안내
    줄이 시키는 대로 `s9 user add <계정>` 뒤 `s9 init` 으로 같은 함수를 지난다."""
    try:
        n_files = len([f for f in os.listdir(os.path.join(site, "harness", "common", "onboarding"))
                       if f.endswith(".md") and not f.startswith(".")])
    except OSError:
        n_files = 0
    for argv in (("user", "add", os_account()), ("init",)):
        _rc, out = s9_run(site, env, *argv)
        for line in out.splitlines():
            log("  │ " + line)
    _rc, cat = s9_run(site, env, "index", "cat")
    n_open, has_project = 0, False
    for line in cat.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") == "project" and r.get("slug") == "general":
            has_project = True
        if (r.get("type") == "request" and r.get("status") == "open"
                and r.get("project") == "general" and "onboarding" in (r.get("tags") or [])):
            n_open += 1
    return n_files, n_open, has_project


def build(root, ref, out, log):
    r = subprocess.run([sys.executable, os.path.join(root, "bin", "s9-release"),
                        "--ref", ref, "--out", out],
                       capture_output=True, encoding="utf-8", errors="replace", cwd=root)
    for line in (r.stdout or "").splitlines():
        log("  " + line)
    if r.returncode != 0:
        log((r.stderr or "").strip())
        return None
    tars = [f for f in os.listdir(out) if f.endswith(".tar.gz")]
    return os.path.join(out, tars[0]) if tars else None


def wait_http(url, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            time.sleep(0.5)
    return None


def release_try(root, ref="HEAD", keep=False, log=print):
    """(전부 통과했나, 확인 목록) — 확인은 (이름, 통과 여부, 근거) 셋."""
    base = os.path.join(root, TRY_DIR)
    shutil.rmtree(base, ignore_errors=True)
    dist, unpacked = os.path.join(base, "dist"), os.path.join(base, "unpacked")
    home, cfg = os.path.join(base, "home"), os.path.join(base, "claude")
    for d in (dist, unpacked, home, cfg):
        os.makedirs(d, exist_ok=True)
    checks = []

    def check(name, ok, why=""):
        checks.append((name, bool(ok), why))
        log(("✓ " if ok else "✗ ") + name + (f" — {why}" if why else ""))

    log(f"① 배포판 만들기 (ref {ref})")
    tar_path = build(root, ref, dist, log)
    check("tar.gz 가 만들어졌다", tar_path, tar_path or "bin/s9-release 실패")
    if not tar_path:
        return False, checks
    with tarfile.open(tar_path) as tf:
        names = tf.getnames()
        data = [n for n in names if n.split("/")[1:2] and n.split("/")[1] in
                ("vault", "users", "projects", "state", "scratchpad", ".s9-sync")]
        check("배포판에 문서·사용자·상태가 없다", not data, ", ".join(data[:3]))
        log(f"② 풀기 → {unpacked}")
        tf.extractall(unpacked)
    site = os.path.join(unpacked, "section9")
    check("최상위 폴더가 section9/ 이다", os.path.isdir(os.path.join(site, "bin")))
    port = free_port()
    env = clean_env(os.environ)
    env.update({"HOME": home, "CLAUDE_CONFIG_DIR": cfg, "S9_PORT": str(port),
                "S9_CODE_DRYRUN": "1", "S9_REWORK_WATCH": "off", "S9_PORT_GUARD": "off",
                "PYTHONUTF8": "1"})
    log(f"③ 그 자리에서 bin/s9 code --no-open (포트 {port}, claude 실행 직전까지)")
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.join(site, "bin", "s9"), "code", "--no-open"],
                           cwd=site, env=env, capture_output=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=CODE_TIMEOUT)
        out = (r.stdout or "") + (r.stderr or "")
        rc = r.returncode
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        rc = -1
    for line in out.splitlines():
        log("  │ " + line)
    check(f"첫 실행이 끝났다 ({time.time() - t0:.0f}초)", rc == 0, f"exit {rc}")
    check("저장소를 새로 세웠다는 줄이 있다", "저장소를 새로 세웠다" in out)
    git_dir = os.path.join(site, ".git")
    check(".git 이 생겼다", os.path.isdir(git_dir))
    head = ""
    try:
        head = open(os.path.join(git_dir, "HEAD"), encoding="utf-8").read().strip()
    except OSError:
        pass
    check("가지가 main 이다", head.endswith("refs/heads/main"), head)
    marker = ""
    try:
        marker = open(os.path.join(site, ".s9-sync"), encoding="utf-8").read()
    except OSError:
        pass
    check(".s9-sync 가 local(혼자 쓰는 상태)이다", marker.startswith("local"), marker.splitlines()[0] if marker else "없음")
    settings = os.path.join(cfg, "settings.json")
    hooked = False
    try:
        hooked = site in open(settings, encoding="utf-8").read()
    except OSError:
        pass
    check("Claude 훅이 임시 설정에 이 자리의 경로로 들어갔다", hooked, settings)
    who = wait_http(f"http://127.0.0.1:{port}/api/whoami", timeout=30)
    root_ok = bool(who) and os.path.realpath(str(who.get("root") or "")) == os.path.realpath(site)
    check("대시보드가 그 자리에서 답한다", root_ok,
          f"root={who.get('root')}" if who else "응답 없음")
    log("⑤ 이름 등록 → 기본 프로젝트 → 사용법 안내 (비대화형이라 s9 user add · s9 init 으로)")
    n_files, n_open, has_project = onboarding_count(site, env, log)
    check("기본 프로젝트 general 이 섰다", has_project)
    check(f"general 에 onboarding 요청 {n_open}건이 open",
          n_open >= 1 if n_files else True,
          f"배포판의 안내 파일 {n_files}건" if n_files
          else "배포판에 안내 파일이 없다(harness/common/onboarding) — 0건이 맞다")
    log("⑥ 서버 내리기")
    subprocess.run([sys.executable, os.path.join(site, "bin", "s9"), "serve", "--stop"],
                   cwd=site, env=env, capture_output=True, encoding="utf-8", errors="replace",
                   stdin=subprocess.DEVNULL, timeout=120)
    ok = all(c[1] for c in checks)
    if keep:
        log(f"남겨 둠: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    log(("전부 통과 — " if ok else "실패 — ") + f"{sum(1 for c in checks if c[1])}/{len(checks)}")
    return ok, checks
