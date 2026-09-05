"""진행 신호(점멸등) 정합 테스트 (REQ-20260825-086).

세 가지 오판을 고정한다.
1. uid 접미 불일치: 바인딩 active_reqs에 접미 없는 짧은 id가 저장돼 있으면
   카탈로그 정식 id와 문자열 매칭이 깨져 직접 증거를 놓친다. 같은 원인이
   rework_claimed도 깨뜨려 워처가 이미 클레임된 REQ를 중복 스폰한다.
2. 위임 에이전트 미등록: 리드가 Agent 툴로 띄운 작업은 클레임도 transcript도
   없어 화면에 안 보인다.
3. 죽은 워커 앰버: 스폰 마커의 600초 창만 보고 "기동됨"을 계속 표시한다 —
   모델 한도로 즉사한 워커도 10분간 살아 있는 것처럼 보였다.
격리: S9_ROOT=mktemp. 실행: python3 tests/ live_signal
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def loopback_ok():
    """이 머신에서 새 리스닝 포트가 실제로 접속되는가.

    WSL virtioproxy 등으로 네트워크가 degraded면 새로 bind한 포트가 전부
    ECONNREFUSED가 된다. 그 상태에서 서버 테스트를 강행하면 접속에 실패한
    s9 serve 프로세스만 쌓여 머신을 더 망가뜨린다 — 띄우기 전에 확인하고
    스킵한다(2026-08-25 실측)."""
    try:
        srv = pool_socket()
    except (OSError, RuntimeError):
        return False
    try:
        # 새 포트는 호스트 공개까지 수 초 걸릴 수 있다(REQ-099) — 즉시 판정하면
        # 멀쩡한 환경에서도 서버 테스트가 통째로 스킵된다.
        deadline = time.time() + 20
        while True:
            try:
                socket.create_connection(srv.getsockname(), 0.5).close()
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.25)
        return True
    except OSError:
        return False
    finally:
        srv.close()


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, pool_socket, wait_server  # noqa: E402


def make_cli(tmp):
    base = {**os.environ, "S9_ROOT": tmp, "S9_MACHINE": "testbox"}
    base.pop("S9_SESSION", None)

    def cli(sess, *argv):
        env = dict(base)
        if sess:
            env["S9_SESSION"] = sess
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=20)
        if r.returncode != 0:
            raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
        return r.stdout
    return cli


def short_of(doc_id):
    """정식 id에서 uid 접미를 뗀 짧은 형태 (과거 바인딩이 저장하던 모양)."""
    return doc_id.rsplit("-", 1)[0]


class TestLiveSignal(unittest.TestCase):
    """/api/catalog 의 live/live_kind 판정."""

    @classmethod
    def setUpClass(cls):
        if not loopback_ok():
            raise unittest.SkipTest("루프백 접속 불가(네트워크 degraded) — "
                                    "서버 테스트를 띄우지 않는다")
        cls.tmp = tempfile.mkdtemp(prefix="s9livesig-")
        cls.cli = staticmethod(make_cli(cls.tmp))
        cls.procs = []
        cli = cls.cli
        cli(None, "init")
        cli(None, "user", "add", "alice")
        mk = lambda sess, t: cli(sess, "new", "request", "--title", t,
                                 "--summary", "t", "--goal", "t", "--size", "S",
                                 "--user", "alice", "--body", "x").split()[0]
        streams = os.path.join(cls.tmp, "streams")
        os.makedirs(streams, exist_ok=True)
        ar_dir = os.path.join(cls.tmp, "state", "auto_resume")
        os.makedirs(ar_dir, exist_ok=True)

        def binding(sess, **kw):
            p = os.path.join(cls.tmp, "state", "sessions", f"testbox__{sess}.json")
            b = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {
                "machine": "testbox", "session": sess, "user": "alice",
                "history": []}
            b.update(kw)
            json.dump(b, open(p, "w", encoding="utf-8"), ensure_ascii=False)

        # A: 바인딩이 '짧은 id'로 등록 — 과거 데이터 그대로 (L1)
        cls.A = mk("aaaa1111", "shortid")
        cli(None, "status", cls.A, "in-progress", "--note", "t")
        with open(os.path.join(streams, "aaaa1111.jsonl"), "w") as f:
            f.write("{}\n")
        binding("aaaa1111", active_reqs=[short_of(cls.A)], last_req="")

        # B: 위임 에이전트 등록 경로 (L2)
        cls.B = mk("bbbb2222", "delegated")
        cli(None, "status", cls.B, "in-progress", "--note", "t")
        cls.agent_tr = os.path.join(cls.tmp, "agent-run.jsonl")
        with open(cls.agent_tr, "w") as f:
            f.write("{}\n")
        cli("bbbb2222", "claim", cls.B, "--agent-transcript", cls.agent_tr)

        def spawn_marker(doc_id, **extra):
            with open(os.path.join(ar_dir, doc_id + ".json"), "w") as f:
                json.dump({"last": time.time() - 60, "count": 1, **extra}, f)

        # C: 스폰 마커 신선 + 죽은 pid → 앰버 금지 (L3)
        cls.C = mk("cccc3333", "deadworker")
        cli(None, "status", cls.C, "in-progress", "--note", "t")
        dead = subprocess.Popen(["sleep", "0"])
        dead.wait()
        spawn_marker(cls.C, pid=dead.pid)
        with open(os.path.join(ar_dir, cls.C + ".log"), "w") as f:
            f.write("You've reached your Fable 5 limit. Switch to another model.\n")

        # D: 스폰 마커 신선 + pid 없음(구 마커) → 기존대로 앰버 (L4)
        cls.D = mk("dddd4444", "legacymarker")
        cli(None, "status", cls.D, "in-progress", "--note", "t")
        spawn_marker(cls.D)

        # E: 살아있지만 claude가 아닌 pid (pid 재사용) → 앰버 금지 (L5)
        cls.E = mk("eeee5555", "reusedpid")
        cli(None, "status", cls.E, "in-progress", "--note", "t")
        alive = subprocess.Popen(["sleep", "60"])
        cls.procs.append(alive)
        cls.addClassCleanup(cls._reap)
        spawn_marker(cls.E, pid=alive.pid)

        # 문서 mtime을 과거로 — 문서 갱신이 직접 증거로 새지 않게
        import glob as g
        old = time.time() - 600
        for p in g.glob(os.path.join(cls.tmp, "vault", "requests", "**", "*.md"),
                        recursive=True):
            os.utime(p, (old, old))

        cls.port = free_port()
        base = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox"}
        base.pop("S9_SESSION", None)
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=base, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls._reap)   # 아래 단계가 실패해도 프로세스는 회수
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기
        with urllib.request.urlopen(
                f"http://127.0.0.1:{cls.port}/api/catalog", timeout=10) as r:
            cls.rows = {x["id"]: x for x in json.load(r)}

    @classmethod
    def _reap(cls):
        for p in [getattr(cls, "srv", None)] + list(cls.procs):
            if p is None:
                continue
            try:
                p.terminate()
                p.wait(timeout=10)
            except Exception:
                pass
        cls.procs = []

    # L1. 짧은 id로 저장된 과거 active_reqs도 정식 id 카드와 매칭된다
    def test_test_live_signal(self):
        """/api/catalog 의 live/live_kind 판정."""
        with self.subTest("l1_short_id_matches"):
                r = self.rows[self.A]
                self.assertTrue(r["live"], r)
                self.assertEqual(r.get("live_kind"), "direct", r)

            # L2. s9 claim 한 줄로 위임 에이전트 진행이 직접 증거가 된다
        with self.subTest("l2_claim_registers_agent"):
                r = self.rows[self.B]
                self.assertTrue(r["live"], r)
                self.assertEqual(r.get("live_kind"), "direct", r)

            # L3. 죽은 워커는 앰버가 아니라 실패로 구분된다 (사유 노출)
        with self.subTest("l3_dead_worker_not_amber"):
                r = self.rows[self.C]
                self.assertNotEqual(r.get("live_kind"), "spawned", r)
                self.assertEqual(r.get("live_kind"), "spawn_failed", r)
                self.assertIn("Fable", r.get("live_reason", ""), r)

            # L4. pid 없는 구 마커는 기존대로 앰버 (하위호환)
        with self.subTest("l4_legacy_marker_amber"):
                self.assertEqual(self.rows[self.D].get("live_kind"), "spawned",
                                 self.rows[self.D])

            # L5. pid가 살아 있어도 claude가 아니면 죽은 것으로 본다 (pid 재사용 방어)
        with self.subTest("l5_reused_pid_not_amber"):
            self.assertEqual(self.rows[self.E].get("live_kind"), "spawn_failed",
                             self.rows[self.E])

class TestClaimCli(unittest.TestCase):
    """클레임 저장 형식과 s9 claim 서브커맨드."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9claim-")
        cls.cli = staticmethod(make_cli(cls.tmp))
        cls.cli(None, "init")
        cls.cli(None, "user", "add", "alice")

    def mkreq(self, title, sess=None):
        return self.cli(sess, "new", "request", "--title", title, "--summary",
                        "t", "--goal", "t", "--size", "S", "--user", "alice",
                        "--body", "x").split()[0]

    def binding(self, sess):
        p = os.path.join(self.tmp, "state", "sessions", f"testbox__{sess}.json")
        return json.load(open(p, encoding="utf-8"))

    # L6. 짧은 id로 클레임해도 바인딩에는 정식 id로 저장된다
    def test_test_claim_cli(self):
        """클레임 저장 형식과 s9 claim 서브커맨드."""
        with self.subTest("l6_add_normalizes_id"):
                r = self.mkreq("normalize")
                self.cli("1111aaaa", "last", short_of(r), "--add")
                self.assertIn(r, self.binding("1111aaaa")["active_reqs"])

            # L7. claim은 agent_transcript_path를 리스트로 누적한다 (덮어쓰지 않는다)
        with self.subTest("l7_claim_appends_transcript"):
                r = self.mkreq("multiagent")
                p1 = os.path.join(self.tmp, "a1.jsonl")
                p2 = os.path.join(self.tmp, "a2.jsonl")
                for p in (p1, p2):
                    open(p, "w").write("{}\n")
                self.cli("2222bbbb", "claim", r, "--agent-transcript", p1)
                self.cli("2222bbbb", "claim", r, "--agent-transcript", p2)
                self.cli("2222bbbb", "claim", r, "--agent-transcript", p1)  # 중복
                b = self.binding("2222bbbb")
                self.assertEqual(b["agent_transcript_path"], [p1, p2], b)
                self.assertEqual(b["active_reqs"].count(r), 1, b)

            # L8. 짧은 id로 등록된 값도 떠나는 전이에서 제거된다
        with self.subTest("l8_leaving_prunes_short_id"):
                r = self.mkreq("prune", "3333cccc")
                self.cli("3333cccc", "status", r, "in-progress", "--note", "t")
                p = os.path.join(self.tmp, "state", "sessions", "testbox__3333cccc.json")
                b = json.load(open(p, encoding="utf-8"))
                b["active_reqs"] = [short_of(r)]          # 과거 형식으로 되돌린다
                json.dump(b, open(p, "w", encoding="utf-8"))
                self.cli("3333cccc", "status", r, "blocked", "--note", "t")
                self.assertEqual(self.binding("3333cccc")["active_reqs"], [])

            # L9. 클레임된 REQ는 워처가 중복 스폰하지 않는다 (짧은 id로 등록됐어도)
        with self.subTest("l9_claimed_short_id_blocks_respawn"):
            r = self.mkreq("claimed", "4444dddd")
            self.cli("4444dddd", "status", r, "in-progress", "--note", "t")
            streams = os.path.join(self.tmp, "streams")
            os.makedirs(streams, exist_ok=True)
            open(os.path.join(streams, "4444dddd.jsonl"), "w").write("{}\n")
            p = os.path.join(self.tmp, "state", "sessions", "testbox__4444dddd.json")
            b = json.load(open(p, encoding="utf-8"))
            b["active_reqs"] = [short_of(r)]
            json.dump(b, open(p, "w", encoding="utf-8"))
            spec = importlib.util.spec_from_loader(
                "s9mod_claim", importlib.machinery.SourceFileLoader("s9mod_claim", S9))
            mod = importlib.util.module_from_spec(spec)
            os.environ["S9_ROOT"] = self.tmp
            os.environ["S9_MACHINE"] = "testbox"
            spec.loader.exec_module(mod)
            self.assertTrue(mod.rework_claimed(r), "짧은 id 클레임이 인식되지 않았다")

class TestSpawnPidRecord(unittest.TestCase):
    """워커 pid 기록 계약 — 이게 없으면 생존 판정이 다시 눈을 잃는다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9pid-")
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        spec = importlib.util.spec_from_loader(
            "s9mod_pid", importlib.machinery.SourceFileLoader("s9mod_pid", S9))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    # L10. pid 기록이 기존 마커(쿨다운 카운터)를 덮어쓰지 않는다
    def test_test_spawn_pid_record(self):
        """워커 pid 기록 계약 — 이게 없으면 생존 판정이 다시 눈을 잃는다."""
        with self.subTest("l10_mark_pid_preserves_marker"):
                d = self.mod._auto_dir()
                path = os.path.join(d, "REQ-X.json")
                with open(path, "w") as f:
                    json.dump({"last": 1234.5, "count": 2}, f)

                class P:
                    pid = 4242
                self.mod._auto_mark_pid("REQ-X", P())
                got = json.load(open(path))
                self.assertEqual(got["pid"], 4242)
                self.assertEqual(got["last"], 1234.5)
                self.assertEqual(got["count"], 2)

            # L11. pid가 정수가 아니면(모킹 등) 조용히 건너뛴다 — 스폰을 깨뜨리지 않는다
        with self.subTest("l11_mark_pid_tolerates_mock"):
                class P:
                    pid = object()
                self.mod._auto_mark_pid("REQ-Y", P())   # 예외 없이 통과해야 한다

            # L12. 워커 스폰 지점은 하나뿐이고, 그 하나가 pid를 기록한다.
            # 원래는 "스폰 지점 수 == pid 기록 수"였다. REQ-20260825-090에서 스폰 경로를
            # _spawn_worker 하나로 합치면서(반려·후속·항목재개가 각자 Popen을 갖고 있었다)
            # 더 강한 불변식으로 바꾼다 — 경로가 하나면 누락될 경로가 없다.
        with self.subTest("l12_all_spawn_sites_record_pid"):
            with open(S9_SRC, encoding="utf-8") as f:
                src = f.read()
            spawns = src.count('wp = subprocess.Popen(argv,')
            self.assertEqual(spawns, 1, "워커 스폰 경로가 둘 이상으로 갈라졌다")
            self.assertEqual(src.count("_auto_mark_pid(doc_id, wp"), 1,
                             "스폰 후 pid를 기록하지 않는다")
            # 까닭도 함께 적는다 (REQ-20260831-025) — 마커가 그것을 버리던 동안,
            # 제 손으로 ▶ 를 누른 사람이 "저절로 떴다"는 문장을 읽었다.
            self.assertIn("_auto_mark_pid(doc_id, wp, reason)", src,
                          "스폰 까닭(사람 wake·워처)이 마커에 안 실린다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
