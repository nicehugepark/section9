"""두 머신 위장 픽스처 — 한 컴퓨터에서 S9_MACHINE 둘 + bare origin 하나
(REQ-20260902-015-62x6 · 설계 DOC-20260902-001-62x6 §5 P0).

무엇을 흉내 내나. 실제 배치는 「사람 둘, 컴퓨터 둘, GitHub 리포 하나」다.
여기서는 그것을 임시 디렉토리 하나 아래에 세운다:

    <tmp>/origin.git     bare — 네트워크 없는 origin
    <tmp>/alpha          S9_ROOT 하나 (S9_MACHINE=alpha)
    <tmp>/beta           S9_ROOT 둘  (S9_MACHINE=beta)

두 루트 다 `.s9-sync` 마커를 remote 모드로 두어 `s9 sync`(와 문서 이벤트의
maybe_sync)가 **실제로** commit → pull --rebase → push 를 돈다. 흉내 내는 것은
머신 이름뿐이고 git 전송층은 진짜다 — 그래야 "남의 문서가 pull 돼 왔을 때
내 훅·워처·목록이 그것을 집는가"를 코드 그대로 묻는다.

워커는 절대 실스폰하지 않는다. `fake_spawn()` 안에서는 `subprocess.Popen` 이
가짜로 바뀌어 `claude` argv 를 기록만 하고, `git` 은 진짜 Popen 으로 넘긴다
(sync 는 그 안에서도 실제로 돌아야 하므로).

씨앗: projects/section9/assets/014-sync-design/repro_cross_machine.py ·
repro_reassign.py (deep-diver 격리 재현). 격리 관행은 tests/test_switch_residue.py
(S9_ROOT=mktemp + 모듈 로드) · tests/test_access_isolation.py(S9_MACHINE 고정).

쓰는 법:

    from twomachine import TwoMachine
    fx = TwoMachine()
    fx.cli("alpha", "user", "add", "alice")
    X = fx.new_request("alpha", "알파의 일", sess="aaaa1111")
    fx.sync("alpha"); fx.pull("beta")
    mod = fx.load_mod("beta")            # current_machine() == "beta" 로 고정
    with fx.fake_spawn():
        mod.rework_watch_tick(grace=0)
    fx.claude_spawns()                   # 기록된 claude argv 들
    fx.close()
"""
import contextlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.abspath(os.path.join(HERE, "..", "bin", "s9"))
MACHINES = ("alpha", "beta")

# 이 셋은 부모 환경에서 새어 들어오면 판정을 바꾼다 — 매 호출마다 걷는다.
_SCRUB = ("S9_SESSION", "S9_USER", "S9_AUTO_RESUME", "S9_AUTO_RESUME_DISABLE",
          "S9_SYNC", "S9_JOB_REQ")

SYNC_REMOTE_MARKER = ("remote — 문서 이벤트마다 commit→pull→push "
                      "(여럿이 쓰는 자리)\n")


class FakePopen:
    """`claude` 스폰을 삼키고 기록한다. `git` 은 진짜 Popen 으로 넘긴다.

    `subprocess.run` 도 모듈 전역 `Popen` 을 쓰므로 여기가 그 길목이다 —
    워처 틱 안의 git(자리 판정·sync)이 실제로 돌게 하면서 claude 만 막는다.
    subprocess.run 이 기대하는 얼굴(with·communicate·poll·wait·kill)을 갖춘다.
    """
    real = subprocess.Popen
    log = []            # 인스턴스가 바꿔 단다 — 클래스 속성은 기본값일 뿐

    def __new__(cls, args, *a, **kw):
        argv = list(args) if isinstance(args, (list, tuple)) else [str(args)]
        if argv and os.path.basename(str(argv[0])) == "git":
            return cls.real(args, *a, **kw)
        return super().__new__(cls)

    def __init__(self, args, *a, **kw):
        argv = list(args) if isinstance(args, (list, tuple)) else [str(args)]
        self.args = argv
        self.pid = 4242
        self.returncode = 0
        self.stdout = self.stderr = self.stdin = None
        type(self).log.append({"argv": argv, "cwd": kw.get("cwd"),
                               "env": kw.get("env")})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def communicate(self, *a, **k):
        return ("", "")

    def poll(self):
        return None

    def wait(self, *a, **k):
        return 0

    def kill(self):
        pass

    terminate = kill


class TwoMachine:
    def __init__(self, prefix="s9two-"):
        self.tmp = tempfile.mkdtemp(prefix=prefix)
        self.origin = os.path.join(self.tmp, "origin.git")
        self.roots = {m: os.path.join(self.tmp, m) for m in MACHINES}
        self.mods = {}
        self.spawn_log = []
        self._build()

    # ------------------------------------------------------------ 세우기
    def git(self, machine, *argv, check=True, cwd=None):
        cwd = cwd or (self.roots[machine] if machine else self.tmp)
        r = subprocess.run(["git", "-C", cwd, *argv], capture_output=True,
                           text=True, timeout=30)
        if check and r.returncode != 0:
            raise AssertionError(
                f"git {' '.join(argv)} @{machine or cwd}: rc={r.returncode}\n"
                f"{r.stdout}{r.stderr}")
        return r

    def _identity(self, machine):
        self.git(machine, "config", "user.name", f"s9-{machine}")
        self.git(machine, "config", "user.email", f"{machine}@s9.test")
        # 시험 상자에는 전역 pull 설정이 없을 수 있다 — 갈림 경고를 끈다
        self.git(machine, "config", "pull.rebase", "true")

    def _build(self):
        self.git(None, "init", "-q", "--bare", "-b", "main", self.origin)
        alpha = self.roots["alpha"]
        os.makedirs(alpha)
        self.git("alpha", "init", "-q", "-b", "main")
        self._identity("alpha")
        # .gitignore 는 인스턴스 리포와 같은 것을 쓴다 — 무엇이 track 되는지
        # (vault/users 는 되고 index/·state/* — 세션 바인딩 포함 — 는 안 되는 것)가
        # 곧 시험 대상이다 (REQ-20260902-026).
        mod = self.load_mod("alpha")
        with open(os.path.join(alpha, ".gitignore"), "w", encoding="utf-8") as f:
            f.write(mod.INSTANCE_TRACK_GITIGNORE)
        with open(os.path.join(alpha, ".s9-sync"), "w", encoding="utf-8") as f:
            f.write(SYNC_REMOTE_MARKER)
        self.cli("alpha", "init")
        self.git("alpha", "add", "-A")
        self.git("alpha", "commit", "-q", "-m", "instance init (twomachine)")
        self.git("alpha", "remote", "add", "origin", self.origin)
        self.git("alpha", "push", "-q", "-u", "origin", "main")
        self.git(None, "clone", "-q", self.origin, self.roots["beta"])
        self._identity("beta")
        self.cli("beta", "init")
        self.load_mod("beta")

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ CLI
    def env(self, machine, sess=None, user=None):
        env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
        env["S9_ROOT"] = self.roots[machine]
        env["S9_MACHINE"] = machine
        env["S9_REWORK_WATCH"] = "off"
        if sess:
            env["S9_SESSION"] = sess
        if user:
            env["S9_USER"] = user
        return env

    def cli(self, machine, *argv, sess=None, user=None, check=True):
        """`s9 <argv>` 를 그 머신의 S9_ROOT·S9_MACHINE 으로 돌린다. stdout+stderr."""
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env(machine, sess, user), timeout=60)
        self.last = r
        if check and r.returncode != 0:
            raise AssertionError(
                f"s9 {' '.join(argv)} @{machine}: rc={r.returncode}\n"
                f"{r.stdout}{r.stderr}")
        return (r.stdout + r.stderr).strip()

    def new_request(self, machine, title, sess=None, user=None, **kw):
        """REQ 하나를 만들고 id 를 돌려준다 (goal·size 등 필수 필드는 채워 둔다)."""
        args = ["new", "request", "--title", title, "--summary", "s",
                "--size", kw.get("size", "S"), "--goal", kw.get("goal", "g"),
                "--body", kw.get("body", "orig")]
        if kw.get("priority"):
            args += ["--priority", kw["priority"]]
        out = self.cli(machine, *args, sess=sess, user=user)
        head = out.split()[0] if out.split() else ""
        if not head.startswith("REQ-"):
            r = self.last
            vault = os.path.join(self.roots[machine], "vault", "requests")
            files = sorted(os.path.relpath(os.path.join(d, f), vault)
                           for d, _s, fs in os.walk(vault) for f in fs)
            raise AssertionError(
                f"s9 new @{machine} 가 id 를 내지 않았다: rc={r.returncode} "
                f"stdout={r.stdout!r} stderr={r.stderr!r}\n"
                f"vault/requests: {files}\nsync.log: {self._sync_log(machine)}")
        return head

    # ------------------------------------------------------------ 모듈
    def load_mod(self, machine):
        """bin/s9 를 그 머신의 루트로 모듈 로드 — 워처·판정 함수를 직접 부른다.

        ROOT 는 import 시점의 S9_ROOT 로 박히고, `current_machine()` 은 호출
        시점의 환경을 읽으므로 그 함수만 고정한다. 모듈 이름을 머신마다 다르게
        해서 한 프로세스에 두 루트가 공존한다. Popen 은 여기서 바꾸지 않는다 —
        `fake_spawn()` 이 감싼 구간에서만 가짜다(CLI 왕복은 진짜 Popen 이 필요).
        """
        if machine in self.mods:
            return self.mods[machine]
        prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE", *_SCRUB)}
        os.environ["S9_ROOT"] = self.roots[machine]
        os.environ["S9_MACHINE"] = machine
        for k in _SCRUB:
            os.environ.pop(k, None)
        try:
            name = f"s9_two_{machine}"
            spec = importlib.util.spec_from_loader(
                name, importlib.machinery.SourceFileLoader(name, S9))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        mod.current_machine = lambda: machine
        self.mods[machine] = mod
        return mod

    @contextlib.contextmanager
    def fake_spawn(self):
        """이 구간의 `subprocess.Popen` 은 claude 를 삼키고 git 만 통과시킨다."""
        real = subprocess.Popen
        fake = type("FakePopen", (FakePopen,), {"real": real,
                                                "log": self.spawn_log})
        subprocess.Popen = fake
        try:
            yield self.spawn_log
        finally:
            subprocess.Popen = real

    def claude_spawns(self):
        return [s for s in self.spawn_log
                if s["argv"] and os.path.basename(str(s["argv"][0])) == "claude"]

    @contextlib.contextmanager
    def session_env(self, sess=None, user=None):
        """모듈 함수 호출에 세션·사용자를 실어 줄 때 — 끝나면 원래대로."""
        prev = {k: os.environ.get(k) for k in ("S9_SESSION", "S9_USER")}
        for k in prev:
            os.environ.pop(k, None)
        if sess:
            os.environ["S9_SESSION"] = sess
        if user:
            os.environ["S9_USER"] = user
        try:
            yield
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def tick(self, machine, grace=0):
        """그 머신의 워처 1틱 — 반환 (스폰한 id 목록, 이 틱의 claude 스폰 기록)."""
        mod = self.load_mod(machine)
        n0 = len(self.claude_spawns())
        with self.fake_spawn():
            spawned = mod.rework_watch_tick(grace=grace)
        return spawned, self.claude_spawns()[n0:]

    def clear_spawn_marks(self, machine):
        """스폰 마커(state/auto_resume)를 지운다 — 남으면 다음 판정(worker_running)
        이 가짜 pid 를 도는 워커로 읽는다."""
        shutil.rmtree(os.path.join(self.roots[machine], "state", "auto_resume"),
                      ignore_errors=True)

    # ------------------------------------------------------------ 동기화
    def sync(self, machine):
        """`s9 sync` — commit → pull --rebase → push. 'ok' 가 아니면 실패로 올린다
        (조용한 미동기화가 이 설계가 고치려는 병이다 — 시험에서는 숨기지 않는다)."""
        out = self.cli(machine, "sync")
        if "sync: ok" not in out:
            raise AssertionError(f"sync @{machine} 가 ok 가 아니다: {out}\n"
                                 f"{self._sync_log(machine)}")
        return out

    def pull(self, machine):
        """받기만 — fetch + rebase(autostash). 받은 뒤 색인을 다시 세운다:
        카탈로그는 track 되지 않으므로 pull 만으로는 CLI 가 새 문서를 못 본다."""
        self.git(machine, "pull", "--rebase", "--autostash", "-q")
        self.load_mod(machine).rebuild_index(quiet=True)

    def head(self, machine=None):
        cwd = self.origin if machine is None else self.roots[machine]
        return self.git(None, "rev-parse", "HEAD", cwd=cwd).stdout.strip()

    def _sync_log(self, machine):
        try:
            with open(os.path.join(self.roots[machine], "state", "sync.log"),
                      encoding="utf-8") as f:
                return f.read()[-800:]
        except OSError:
            return "(sync.log 없음)"

    # ------------------------------------------------------------ 문서·바인딩
    def doc(self, machine, doc_id):
        """(meta, body) — 그 머신 디스크의 문서."""
        mod = self.load_mod(machine)
        path = mod.locate(doc_id)
        if not path:
            raise AssertionError(f"{doc_id} 가 {machine} 에 없다")
        return mod.read_doc(path)

    def binding_file(self, machine_root, binding_machine, sess):
        """<machine_root> 의 state/sessions 에 있는 <binding_machine>__<sess>.json 경로."""
        mod = self.load_mod(machine_root)
        return mod.binding_path(binding_machine, sess)

    def read_binding_file(self, machine_root, binding_machine, sess):
        with open(self.binding_file(machine_root, binding_machine, sess),
                  encoding="utf-8") as f:
            return json.load(f)

    def write_binding_file(self, machine_root, b):
        p = self.binding_file(machine_root, b["machine"], b["session"])
        with open(p, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False, indent=1)
        return p


# ---------------------------------------------------------------- 씨앗 장면
A_SESS, B_SESS = "aaaa1111", "bbbb2222"


def enable_worker(fx, machine, user):
    """그 사용자의 백그라운드 작업을 켜고 캡·쿨다운을 시험용으로 푼다."""
    for kv in (("auto_resume", "on"), ("auto_resume_cooldown_sec", "0"),
               ("auto_resume_global_per_hour", "50"),
               ("auto_resume_global_per_day", "100"),
               ("auto_resume_grace_sec", "0")):
        fx.cli(machine, "user", "config", user, *kv)


def seed_alpha_review(fx, title="알파의 일", priority=None):
    """alpha 의 alice(세션 A)가 REQ 를 만들어 review 까지 올린다. 반환: id.

    alice 의 워커 옵트인은 켜 둔다 — 그래야 워처가 '옵트인 꺼짐'이 아니라
    귀속 가드에서 판정한다."""
    fx.cli("alpha", "user", "add", "alice", check=False)
    enable_worker(fx, "alpha", "alice")
    fx.cli("alpha", "user", "switch", "alice", sess=A_SESS)
    x = fx.new_request("alpha", title, sess=A_SESS, priority=priority)
    fx.cli("alpha", "status", x, "in-progress", "--note", "착수", sess=A_SESS)
    fx.cli("alpha", "status", x, "review", "--note", "확인해 주세요", sess=A_SESS)
    return x


def reject_on(fx, machine, doc_id, note="반려: 다시"):
    """그 머신의 대시보드에서 반려(review→in-progress [via dashboard])."""
    mod = fx.load_mod(machine)
    with fx.fake_spawn():          # 긴급 우선순위면 전이 자리에서 즉시 스폰한다
        old = mod.do_transition(doc_id, "in-progress", note=note, judge=True,
                                via="dashboard")
    return old
