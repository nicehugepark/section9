"""P5 실측 — 다섯 장면을 **진짜 두 컴퓨터**로 밟는다 (REQ-20260902-037-62x6).

`tests/test_p5_field.py` 는 한 컴퓨터 안에서 머신 이름 둘(alpha·beta)로 위장해
같은 다섯 장면을 매번 밟는다(P0 픽스처, 회귀 게이트). 이 파일은 그 마지막 한
칸을 메운다 — **B 를 실제 두 번째 컴퓨터에 둔다.** 흉내 내는 것이 하나도 없다:

    A  이 컴퓨터 (WSL, hostname 그대로)        <tmp>/alpha
    B  두 번째 컴퓨터 (외부 비밀로 닿는 리눅스)  ~/s9field/beta
    origin  B 쪽의 bare 리포 + `git daemon` — A 는 ssh 포트 전달로 닿는다

A 의 `s9 sync` 는 진짜 네트워크(ssh 터널 위의 git://)로 밀고 당긴다. 두 머신의
`current_machine()` 은 각자의 hostname 을 낸다 — 리스·워처·목록이 보는 이름이
위장이 아니라 사실이다.

**이것은 회귀 게이트가 아니라 사람이 부르는 실측 도구다.** 두 번째 컴퓨터가
없는 자리에서 붉어질 것을 게이트로 세우지 않는다 — 게이트는 test_p5_field.py 고,
이 파일의 얼굴(tests/test_p5_live.py)은 사람이 `p5_live` 라고 지목한 실행에서만
깨어난다. 전체 스위트도, 샤드 자식도 그 낱말을 넘기지 않으므로 조용히 건너뛴다.

    실행:  python3 tests/ p5_live               (비밀 이름은 기억된 원격 state/test-remote·S9_TEST_REMOTE)
           python3 tests/p5_live.py --key <비밀이름> [--port 29418] [--keep]

비밀 값은 읽지 않는다 — `s9 secret run` 의 `{{secret:KEY}}` 치환으로만 쓴다
(tests/remote_run.py 와 같은 길). `--keep` 이 없으면 양쪽 임시 자리를 지운다.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
S9 = os.path.join(REPO, "bin", "s9")

# 부모 환경에서 새어 들면 판정을 바꾼다 — 매 호출마다 걷는다(twomachine 과 같은 표).
_SCRUB = ("S9_SESSION", "S9_USER", "S9_AUTO_RESUME", "S9_AUTO_RESUME_DISABLE",
          "S9_SYNC", "S9_JOB_REQ", "S9_ROOT", "S9_MACHINE")

SYNC_REMOTE_MARKER = ("remote — 문서 이벤트마다 commit→pull→push "
                      "(여럿이 쓰는 자리)\n")
GITATTRIBUTES = ("vault/**/*.md merge=s9doc\n"
                 "users/*/profile.md merge=s9doc\n"
                 "users/*/machines.json merge=s9doc\n")

ALICE, BOB, CAROL, ROOT = "alice", "bob", "carol", "root"
A_SESS, B_SESS = "aaaa1111", "bbbb2222"
RC_MARK = "__S9_LIVE_RC="


def shq(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ---------------------------------------------------------------- 판정 기록
class Report:
    def __init__(self):
        self.rows = []

    def check(self, scene, label, ok, detail=""):
        self.rows.append((scene, label, bool(ok), detail))
        mark = "✓" if ok else "✗"
        print(f"  {mark} [{scene}] {label}" + (f"\n      {detail}" if not ok and detail else ""),
              flush=True)
        return ok

    def mark(self):
        return len(self.rows)

    def failed_since(self, n):
        return [r for r in self.rows[n:] if not r[2]]

    @property
    def failed(self):
        return [r for r in self.rows if not r[2]]

    def summary(self):
        n, bad = len(self.rows), len(self.failed)
        print(f"\n판정 {n - bad}/{n}" + ("" if not bad else " — 어긋난 자리:"))
        for scene, label, _ok, detail in self.failed:
            print(f"  ✗ [{scene}] {label}: {detail}")
        return bad


REPORT = Report()


# ---------------------------------------------------------------- 두 머신
def default_key():
    """두 번째 컴퓨터의 비밀 이름 — 기억된 원격(state/test-remote)·S9_TEST_REMOTE 에서.

    특정 머신의 이름을 코드에 박지 않는다 — 그것은 한 사람의 비밀로 만든 장치라
    저장소를 이어받는 다른 사람은 그 개념 자체를 몰라야 한다(REQ-20260906-011).
    """
    import remote_run
    key = remote_run.remote_key([])
    if not key:
        raise SystemExit("두 번째 컴퓨터의 비밀 이름이 없다 — --key <이름> 또는 "
                         "`python3 tests/ --remote <이름> --remember`")
    return key


class Live:
    """A = 이 컴퓨터의 임시 루트, B = 원격 컴퓨터의 ~/s9field/beta."""

    def __init__(self, key=None, port=29418, keep=False):
        self.key, self.port, self.keep = key or default_key(), port, keep
        self.alpha = tempfile.mkdtemp(prefix="s9live-")
        self.lport = port          # 이 컴퓨터에서 터널이 서는 자리 (막혔으면 옮긴다)
        self.url = f"git://127.0.0.1:{self.lport}/origin.git"
        self.mod = None
        self.tunnel_pid = None     # 내가 세운 터널만 내가 거둔다
        self.a_machine = socket.gethostname()
        self.b_machine = None
        self.b_home = None
        self.b_s9 = None

    # ------------------------------------------------------------ 원격 셸
    def sh_b(self, cmd, timeout=180, check=True):
        """원격에서 한 줄 — 반환 (rc, 출력). 비밀은 치환으로만 지나간다."""
        marked = f"({cmd}); echo {RC_MARK}$?"
        script = "{{secret:%s}} %s" % (self.key, shq(marked))
        p = subprocess.run([S9, "secret", "run", "--", "sh", "-c", script],
                           capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        rc, lines = p.returncode, []
        for line in out.splitlines():
            if line.startswith(RC_MARK):
                try:
                    rc = int(line[len(RC_MARK):].strip())
                except ValueError:
                    rc = 1
                continue
            lines.append(line)
        text = "\n".join(lines).strip()
        if check and rc != 0:
            raise AssertionError(f"원격 실패(rc={rc}): {cmd}\n{text}")
        return rc, text

    def b(self, *argv, sess=None, user=None, check=True):
        """B 의 `s9 <argv>` — 그 컴퓨터의 자기 bin/s9 로 돈다."""
        env = f"S9_ROOT={self.b_home}/s9field/beta S9_REWORK_WATCH=off"
        if sess:
            env += f" S9_SESSION={sess}"
        if user:
            env += f" S9_USER={user}"
        cmd = (f"cd {self.b_home}/s9field/beta && {env} python3 {self.b_s9} "
               + " ".join(shq(a) for a in argv))
        rc, out = self.sh_b(cmd, check=check)
        self.last_rc = rc
        return out

    def bgit(self, *argv, check=True):
        cmd = f"git -C {self.b_home}/s9field/beta " + " ".join(shq(a) for a in argv)
        return self.sh_b(cmd, check=check)[1]

    def b_doc(self, doc_id):
        """B 디스크의 문서 — 원문을 그대로 받아 이 자리에서 파싱한다."""
        year, month = doc_id.split("-")[1][:4], doc_id.split("-")[1][4:6]
        path = f"{self.b_home}/s9field/beta/vault/requests/{year}/{month}/{doc_id}.md"
        rc, text = self.sh_b(f"cat {shq(path)}")
        return self.mod.fm_parse(text)

    # ------------------------------------------------------------ 이 컴퓨터
    def a(self, *argv, sess=None, user=None, check=True):
        env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
        env["S9_ROOT"] = self.alpha
        env["S9_REWORK_WATCH"] = "off"
        if sess:
            env["S9_SESSION"] = sess
        if user:
            env["S9_USER"] = user
        r = subprocess.run([S9, *argv], capture_output=True, text=True, env=env,
                           timeout=180)
        self.last_rc = r.returncode
        out = (r.stdout + r.stderr).strip()
        if check and r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)} @A: rc={r.returncode}\n{out}")
        return out

    def agit(self, *argv, check=True):
        r = subprocess.run(["git", "-C", self.alpha, *argv], capture_output=True,
                           text=True, timeout=120)
        if check and r.returncode != 0:
            raise AssertionError(f"git {' '.join(argv)} @A: {r.stdout}{r.stderr}")
        return (r.stdout + r.stderr).strip()

    def a_doc(self, doc_id):
        path = os.path.join(self.alpha, "vault", "requests", doc_id.split("-")[1][:4],
                            doc_id.split("-")[1][4:6], f"{doc_id}.md")
        return self.mod.read_doc(path)

    def new_req(self, title, sess=None, user=None, parent=None):
        argv = ["new", "request", "--title", title, "--summary", "s", "--size", "S",
                "--goal", "g", "--body", "b"]
        if parent:
            argv += ["--parent", parent]
        out = self.a(*argv, sess=sess, user=user)
        head = out.split()[0] if out.split() else ""
        if not head.startswith("REQ-"):
            raise AssertionError(f"s9 new 가 id 를 내지 않았다: {out}")
        return head

    def a_sync(self):
        out = self.a("sync")
        if "sync: ok" not in out:
            raise AssertionError(f"A 의 sync 가 ok 가 아니다: {out}")
        return out

    def a_pull(self):
        self.agit("pull", "--rebase", "--autostash", "-q")
        self.a("index", "rebuild")

    def b_pull(self):
        self.bgit("pull", "--rebase", "--autostash", "-q")
        self.b("index", "rebuild")

    # ------------------------------------------------------------ 세우기
    def load_mod(self):
        prev = {k: os.environ.get(k) for k in _SCRUB}
        os.environ["S9_ROOT"] = self.alpha
        for k in _SCRUB:
            if k != "S9_ROOT":
                os.environ.pop(k, None)
        try:
            spec = importlib.util.spec_from_loader(
                "s9_live", importlib.machinery.SourceFileLoader("s9_live", S9))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.mod = mod
        return mod

    def build(self):
        print("■ 준비 — 두 컴퓨터와 그 사이의 origin", flush=True)
        self.load_mod()
        # B 쪽 사실 확인: 어디에 사는가, 제 bin/s9 는 어디인가.
        _, info = self.sh_b("hostname; echo $HOME; ls -d $HOME/section9/bin/s9")
        self.b_machine, self.b_home, self.b_s9 = [x.strip() for x in info.splitlines()[:3]]
        print(f"  A = {self.a_machine} ({self.alpha})")
        print(f"  B = {self.b_machine} ({self.b_home}/s9field/beta, s9={self.b_s9})",
              flush=True)
        if self.b_machine == self.a_machine:
            raise AssertionError("두 이름이 같다 — 두 번째 컴퓨터가 아니다")

        # ① B 에 bare origin 과 git daemon (A 가 네트워크로 닿을 자리)
        self.sh_b(
            f"pkill -F $HOME/s9field/daemon.pid 2>/dev/null; sleep 0.3; "
            f"rm -rf $HOME/s9field; mkdir -p $HOME/s9field; "
            f"git init -q --bare -b main $HOME/s9field/origin.git; "
            f"git daemon --base-path=$HOME/s9field --export-all --enable=receive-pack "
            f"--listen=127.0.0.1 --port={self.port} --detach "
            f"--pid-file=$HOME/s9field/daemon.pid; sleep 1; "
            f"test -s $HOME/s9field/daemon.pid")
        self.ensure_tunnel()

        # ② A 를 인스턴스로 세운다 — 절차서의 `s9 instance init` 이 만드는 모양
        #    (.gitignore·.s9-sync·.gitattributes)을 그대로 손으로 세운다.
        self.agit("init", "-q", "-b", "main")
        self.agit("config", "user.name", f"s9-{self.a_machine}")
        self.agit("config", "user.email", "a@s9.test")
        self.agit("config", "pull.rebase", "true")
        for name, text in ((".gitignore", self.mod.INSTANCE_TRACK_GITIGNORE),
                           (".s9-sync", SYNC_REMOTE_MARKER),
                           (".gitattributes", GITATTRIBUTES)):
            with open(os.path.join(self.alpha, name), "w", encoding="utf-8") as f:
                f.write(text)
        self.a("init")
        self.register_driver_a()
        self.agit("add", "-A")
        self.agit("commit", "-q", "-m", "instance init (p5 live)")
        self.agit("remote", "add", "origin", self.url)
        self.agit("push", "-q", "-u", "origin", "main")

        # ③ B 는 clone 하고 `bin/s9-install` 이 하는 일(병합 드라이버 등록)을 한다
        self.sh_b(f"git clone -q $HOME/s9field/origin.git $HOME/s9field/beta")
        self.bgit("config", "user.name", f"s9-{self.b_machine}")
        self.bgit("config", "user.email", "b@s9.test")
        self.bgit("config", "pull.rebase", "true")
        self.register_driver_b()
        self.b("init")
        print("  준비 완료 — A→origin 은 ssh 터널 위의 git://, B→origin 은 그 컴퓨터 안",
              flush=True)

    def ensure_tunnel(self):
        """A 에서 B 의 git daemon 으로 가는 ssh 포트 전달.

        `-4` 와 `127.0.0.1:` 명시는 실측으로 얻은 것이다 — 생략하면 WSL 에서
        [::1] 로만 서서 연결이 거절된다(DOC-20260906-001).

        **살아 있는지는 포트가 아니라 대화로 묻는다.** 죽은 터널의 로컬 포트도
        accept 는 한다 — 앞선 실행이 남긴 껍데기를 「서 있다」로 읽고 push 에서
        「Could not read from remote repository」로 넘어졌다(실측). 그래서
        판정은 `git ls-remote` 한 번이고, 어긋나면 터널을 새로 세운다.
        """
        if self._talks():
            return
        if self._port_taken(self.lport):
            # 앞선 실행의 껍데기가 그 자리를 잡고 있다 — 남의 것일 수도 있으니
            # 죽이지 않고 옆으로 비킨다(pkill 은 제 셸부터 잡는다, PROTOCOL 19조).
            self.lport = self._free_port()
            self.url = f"git://127.0.0.1:{self.lport}/origin.git"
        # `nohup … & echo $!` — setsid 를 끼우지 않는 이유는 그것이 한 번 더
        # 갈라져 `$!` 가 곧 사라질 껍데기를 가리키기 때문이다. 여기서 받는 pid 로
        # 끝날 때 제 터널만 거둔다(pkill 로 이름을 훑지 않는다, PROTOCOL 19조).
        script = ("nohup {{secret:%s}} -4 -N -L 127.0.0.1:%d:127.0.0.1:%d "
                  "> /tmp/s9live-tunnel.log 2>&1 & echo $!"
                  % (self.key, self.lport, self.port))
        r = subprocess.run([S9, "secret", "run", "--", "sh", "-c", script],
                           capture_output=True, text=True, timeout=60)
        for tok in (r.stdout or "").split():
            if tok.isdigit():
                self.tunnel_pid = int(tok)
        for _ in range(30):
            time.sleep(0.5)
            if self._talks():
                return
        raise AssertionError(f"터널이 서지 않았다 — {self.url}")

    def _talks(self):
        """origin 과 실제로 말이 오가나 — TCP 가 아니라 git 대화로 묻는다."""
        r = subprocess.run(["git", "ls-remote", self.url], capture_output=True,
                           text=True, timeout=30)
        return r.returncode == 0

    @staticmethod
    def _port_taken(port):
        try:
            with socket.create_connection(("127.0.0.1", port), 2):
                return True
        except OSError:
            return False

    @staticmethod
    def _free_port():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def register_driver_a(self):
        self.agit("config", "merge.s9doc.driver", f"{S9} merge-doc %O %A %B")
        self.agit("config", "merge.s9doc.name", "section9 document merge")

    def register_driver_b(self):
        self.bgit("config", "merge.s9doc.driver", f"{self.b_s9} merge-doc %O %A %B")
        self.bgit("config", "merge.s9doc.name", "section9 document merge")

    def unregister_driver_b(self):
        self.bgit("config", "--unset", "merge.s9doc.driver", check=False)
        self.bgit("config", "--unset", "merge.s9doc.name", check=False)

    def cast(self):
        """네 계정 — admin 을 맨 먼저(등록된 admin 이 없을 때만 첫 admin 이 선다)."""
        self.a("user", "add", ROOT, "--role", "admin")
        self.a("user", "add", ALICE, user=ROOT)
        self.a("user", "add", BOB, user=ROOT)
        self.a("user", "add", CAROL, "--role", "viewer", user=ROOT)
        self.a_sync()
        self.b_pull()

    def close(self):
        if self.keep:
            print(f"\n(--keep) A={self.alpha} · B={self.b_home}/s9field "
                  f"· 터널 pid {self.tunnel_pid}")
            return
        shutil.rmtree(self.alpha, ignore_errors=True)
        if self.b_home:
            self.sh_b("pkill -F $HOME/s9field/daemon.pid 2>/dev/null; "
                      "rm -rf $HOME/s9field; true", check=False)
        if self.tunnel_pid:
            try:
                os.kill(self.tunnel_pid, 15)
            except OSError:
                pass                # 이미 갔으면 그만이다


# ---------------------------------------------------------------- 다섯 장면
def scene1_assign(fx):
    """장면 1 · 할당 — A 가 만든 일을 B 의 사람에게 넘긴다."""
    print("\n■ 장면 1 · 할당", flush=True)
    X = fx.new_req("인계할 일", sess=A_SESS, user=ALICE)
    out = fx.a("assign", X, BOB, "--why", "인계", user=ALICE)
    REPORT.check("S1-a", "A 화면이 「담당 alice → bob」을 말한다",
                 f"담당 {ALICE} → {BOB}" in out, out)
    meta, body = fx.a_doc(X)
    REPORT.check("S1-a", "담당은 bob, 만든 사람은 alice 로 남는다",
                 meta.get("user") == BOB and meta.get("creator") == ALICE, str(meta.get("user")))
    REPORT.check("S1-a", "History 에 인계 한 줄", f"assignee: {ALICE} -> {BOB}" in body)

    fx.a_sync()
    fx.b_pull()
    ls_bob, ls_alice = fx.b("ls", "--user", BOB), fx.b("ls", "--user", ALICE)
    REPORT.check("S1-b", "B 컴퓨터의 `s9 ls --user bob` 에 그 카드가 뜬다", X in ls_bob, ls_bob)
    REPORT.check("S1-b", "`--user alice` 에는 없다", X not in ls_alice, ls_alice)
    bmeta = fx.b_doc(X)[0]
    REPORT.check("S1-b", "B 가 읽은 문서도 담당 bob · 만든 사람 alice",
                 bmeta.get("user") == BOB and bmeta.get("creator") == ALICE, str(bmeta))
    nxt_b, nxt_a = fx.b("next", "--json", user=BOB), fx.a("next", "--json", user=ALICE)
    REPORT.check("S1-c", "착수 전 카드는 어느 쪽 `s9 next` 도 권하지 않는다",
                 X not in nxt_b and X not in nxt_a, f"B:{nxt_b[:120]} A:{nxt_a[:120]}")
    return X


def scene2_two_machines(fx):
    """장면 2 · 두 대 — 같은 사람이 A·B 두 컴퓨터에 앉는다."""
    print("\n■ 장면 2 · 두 대", flush=True)
    Y = fx.new_req("두 대에서 볼 일", sess=A_SESS, user=ALICE)
    fx.a("status", Y, "in-progress", "--note", "착수", sess=A_SESS, user=ALICE)
    fx.a_sync()
    fx.b_pull()
    lease = fx.b_doc(Y)[0].get("lease") or {}
    REPORT.check("S2-a", f"A 의 리스가 문서에 실려 B 로 건너간다 (machine={fx.a_machine})",
                 lease.get("machine") == fx.a_machine and lease.get("user") == ALICE
                 and lease.get("session") == A_SESS, str(lease))
    binding = fx.sh_b(f"ls {fx.b_home}/s9field/beta/state/sessions 2>/dev/null | wc -l",
                      check=False)[1]
    REPORT.check("S2-a", "세션 바인딩(state/)은 건너오지 않는다", binding.strip() in ("0", ""),
                 binding)

    out = fx.b("claim", Y, sess=B_SESS, user=ALICE)
    REPORT.check("S2-b", "B 의 맨 `s9 claim` 이 busy-elsewhere 로 막힌다",
                 "busy-elsewhere" in out and fx.a_machine in out, out)
    REPORT.check("S2-b", "막으면서 `--takeover` 를 함께 말한다", "--takeover" in out, out)
    REPORT.check("S2-b", "막았으면 리스는 그대로 A 다",
                 (fx.b_doc(Y)[0].get("lease") or {}).get("machine") == fx.a_machine)

    fx.b("claim", Y, "--takeover", sess=B_SESS, user=ALICE)
    bmeta, bbody = fx.b_doc(Y)
    REPORT.check("S2-c", f"`--takeover` 뒤 리스가 B 로 온다 (machine={fx.b_machine})",
                 (bmeta.get("lease") or {}).get("machine") == fx.b_machine, str(bmeta.get("lease")))
    REPORT.check("S2-c", "History 에 이관 한 줄", "lease: takeover" in bbody)
    fx.b("sync")
    fx.a_pull()
    ameta = fx.a_doc(Y)[0]
    REPORT.check("S2-c", "A 도 그 사실을 읽는다 — A 의 워처가 겹쳐 띄우지 않을 근거",
                 (ameta.get("lease") or {}).get("machine") == fx.b_machine,
                 str(ameta.get("lease")))
    back = fx.a("claim", Y, sess=A_SESS, user=ALICE)
    REPORT.check("S2-c", "이제 A 의 맨 claim 이 거꾸로 막힌다(대칭)",
                 "busy-elsewhere" in back and fx.b_machine in back, back)
    return Y


def scene3_derived(fx):
    """장면 3 · 파생 — A 의 에이전트 세션이 일하다 곁가지를 만든다."""
    print("\n■ 장면 3 · 파생", flush=True)
    X = fx.new_req("본줄기 일", sess=A_SESS, user=ALICE)
    Z = fx.new_req("파생된 일", sess=A_SESS, user=ALICE, parent=X)
    fx.a_sync()
    fx.b_pull()
    meta = fx.b_doc(Z)[0]
    REPORT.check("S3-a", "카드가 「만든 사람 alice · 기원: <본줄기> 를 처리하다(lead)」를 그릴 원재료",
                 meta.get("origin") == "derived" and meta.get("origin_req") == X
                 and meta.get("origin_actor") == "lead" and meta.get("creator") == ALICE
                 and meta.get("parent") == X, str(meta))
    REPORT.check("S3-a", f"만든 자리는 A 다 (machine={fx.a_machine})",
                 meta.get("machine") == fx.a_machine, str(meta.get("machine")))
    nxt = fx.b("next", "--json", user=ALICE)
    reo = fx.b("reopened", user=BOB)
    REPORT.check("S3-b", "B 는 그 파생 카드를 next 에서 집지 않는다", Z not in nxt, nxt[:200])
    REPORT.check("S3-b", "reopened 에서도 집지 않는다", Z not in reo, reo[:200])
    return Z


def scene4_viewer(fx, X):
    """장면 4 · 관찰자 — 읽기만 하는 계정. B 컴퓨터에서 확인한다."""
    print("\n■ 장면 4 · 관찰자", flush=True)
    for argv in (("new", "request", "--title", "뷰어의 일", "--summary", "s",
                  "--size", "S", "--goal", "g", "--body", "b"),
                 ("status", X, "in-progress", "--note", "n"),
                 ("note", X, "메모")):
        out = fx.b(*argv, user=CAROL, check=False)
        REPORT.check("S4-a", f"관찰 계정의 `s9 {argv[0]}` 가 거부된다",
                     fx.last_rc != 0 and fx.mod.VIEWER_DENIED_MSG in out, out[:200])
    out = fx.b("assign", X, CAROL, "--why", "w", user=ALICE, check=False)
    REPORT.check("S4-b", "담당은 관찰 계정에 넘어가지 않는다",
                 fx.last_rc != 0 and "관찰 계정" in out, out[:200])
    show = fx.b("show", X, user=CAROL)
    ls = fx.b("ls", user=CAROL)
    REPORT.check("S4-c", "조회(show)는 된다", X in show, show[:200])
    REPORT.check("S4-c", "목록(ls)도 된다", X in ls, ls[:200])
    self_grant = fx.b("user", "config", CAROL, "observe", "all", user=CAROL, check=False)
    REPORT.check("S4-d", "관찰 범위를 본인이 넓히지 못한다", fx.last_rc != 0, self_grant[:200])
    fx.b("user", "config", CAROL, "observe", "all", user=ROOT)
    scope = fx.b("user", "config", CAROL, user=ROOT, check=False)
    REPORT.check("S4-d", "admin 이 주면 선다", "observe" in scope and "all" in scope, scope[:300])
    fx.mod.rebuild_index(quiet=True)
    row = [r for r in fx.mod.load_catalog() if r["id"] == X]
    if not REPORT.check("S4-e", "A 의 카탈로그에 그 문서가 있다", bool(row)):
        return
    stranger = fx.mod.doc_visible(row[0], "stranger")
    holder = fx.mod.doc_visible(row[0], BOB)        # 지금 담당
    maker = fx.mod.doc_visible(row[0], ALICE)       # 만든 사람 (장면 1 에서 넘겼다)
    REPORT.check("S4-e", "여럿이 쓰는 자리에서 미등록 열람자는 화면이 거부한다",
                 not stranger, f"sync_mode={fx.mod.sync_mode()!r}")
    REPORT.check("S4-e", "담당은 그 문서를 본다", holder)
    # 실측으로 드러난 것 — doc_visible 의 마지막 줄은 **담당(user)** 만 본다.
    # 그래서 project 가 없는 문서는 인계하는 순간 **만든 사람의 화면에서 사라진다**
    # (함수 설명은 "작성자 본인만" 이라 적혀 있어 둘이 어긋난다). 여기서는 고치지
    # 않고 사실대로 못박는다 — 고칠 자리는 bin/ 이고, 제안은 REQ 노트에 남겼다.
    REPORT.check("S4-e", "인계하면 만든 사람의 화면에서는 사라진다 (제안 노트 참조)",
                 not maker, f"alice={maker}")


def scene5_sync_failure(fx, X):
    """장면 5 · 동기화 실패 — 바깥이 끊긴 채 일해도 잃지 않는다."""
    print("\n■ 장면 5 · 동기화 실패", flush=True)
    bad = f"{fx.b_home}/s9field/nope.git"
    good = f"{fx.b_home}/s9field/origin.git"
    fx.bgit("remote", "set-url", "origin", bad)
    try:
        fx.b("note", X, "끊긴 채 남긴 메모", user=BOB, check=False)
        line = fx.b("sync", "--status")
        REPORT.check("S5-a", "판이 「대기 n건 · 마지막 보냄 …」을 센다",
                     "대기 " in line and "마지막 보냄" in line, line[:300])
    finally:
        fx.bgit("remote", "set-url", "origin", good)
        # 네트워크 실패 뒤 60초 백오프는 **기다리면 풀린다** — 시험은 그 1분을
        # 자는 대신 시계 파일을 지운다(기다림의 흉내이지 게이트를 끄는 것이 아니다).
        fx.sh_b(f"rm -f {fx.b_home}/s9field/beta/state/.sync-fail.ts; true", check=False)
    out = fx.b("sync")
    REPORT.check("S5-a", "복구 뒤 한 번의 `s9 sync` 로 밀린 것이 나간다", "sync: ok" in out, out[:300])
    fx.a_pull()
    REPORT.check("S5-a", "그 메모가 A 컴퓨터로 건너온다",
                 "끊긴 채 남긴 메모" in fx.a_doc(X)[1])

    stats = fx.b("sync", "--stats")
    REPORT.check("S5-b", "`s9 sync --stats` 가 단계별 영수증을 남긴다",
                 "이벤트 " in stats and ("push 거부율" in stats or "push 기록 없음" in stats),
                 stats[:300])

    # 5-c 같은 문서를 두 컴퓨터가 동시에 — s9-install 을 돌린 자리
    fx.b("sync", check=False)
    fx.a_pull()
    fx.a("note", X, "A 가 같은 시각에 적은 줄", user=ALICE, check=False)
    fx.b("note", X, "B 가 같은 시각에 적은 줄", user=BOB, check=False)
    fx.a("sync", check=False)
    out = fx.b("sync", check=False)
    REPORT.check("S5-c", "병합 드라이버가 있는 자리에서는 사람 손이 필요 없다",
                 "sync: ok" in out, out[:300])
    body = fx.b_doc(X)[1]
    REPORT.check("S5-c", "두 줄이 모두 남는다",
                 "A 가 같은 시각에 적은 줄" in body and "B 가 같은 시각에 적은 줄" in body)

    # 5-d s9-install 을 건너뛴 자리 — 손이 하나 들되 잃지 않는다
    fx.unregister_driver_b()
    try:
        fx.b("sync", check=False)
        fx.a_pull()
        fx.a("note", X, "A 가 드라이버 없이 적은 줄", user=ALICE, check=False)
        fx.b("note", X, "B 가 드라이버 없이 적은 줄", user=BOB, check=False)
        fx.a("sync", check=False)
        out = fx.b("sync", check=False)
        REPORT.check("S5-d", "드라이버가 없으면 「sync: pull-conflict」로 선다",
                     "conflict" in out, out[:300])
        REPORT.check("S5-d", "막히면서도 내 줄이 사라지지 않는다",
                     "B 가 드라이버 없이 적은 줄" in fx.b_doc(X)[1])
        res = fx.b("sync", "resolve", X, "--take", "mine", check=False)
        saved = fx.sh_b(f"ls {fx.b_home}/s9field/beta/state/sync-conflict 2>/dev/null",
                        check=False)[1]
        REPORT.check("S5-d", "`s9 sync resolve --take mine` 이 확정하고 밀어낸다",
                     "확정" in res and "push: ok" in res, res[:300])
        REPORT.check("S5-d", "양쪽 본이 state/sync-conflict/ 에 보존된다",
                     f"{X}.mine.md" in saved and f"{X}.theirs.md" in saved, saved[:300])
    finally:
        fx.register_driver_b()


def main(argv):
    key, port, keep = None, 29418, False
    if "--key" in argv:
        key = argv[argv.index("--key") + 1]
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    keep = "--keep" in argv
    fx = Live(key=key, port=port, keep=keep)
    t0 = time.time()
    try:
        fx.build()
        fx.cast()
        X = scene1_assign(fx)
        scene2_two_machines(fx)
        scene3_derived(fx)
        scene4_viewer(fx, X)
        scene5_sync_failure(fx, X)
    finally:
        bad = REPORT.summary()
        print(f"({time.time() - t0:.0f}초)")
        fx.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
