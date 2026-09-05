"""긴 잡 가시화 — 러너가 선언하고 서버가 검증한다 (REQ-20260830-022).

사용자(2026-08-30 15:03): "test 같은 프로그램이 돌 때는 완전히 가려져 있어서
진행 여부를 알 수가 없다 … 모든 것이 멈춰 있는 것처럼 보이기만 한다."

계약 (다각 검토 v1 합의):
  J1 러너 모듈이 잡 파일을 쓰고 거둔다 · 안쪽 실행(S9_TESTS_NESTED)은 안 쓴다
  J2 죽은 pid·명령줄 불일치 잡은 안 보인다 (급사한 러너의 파일은 거짓말 못 한다)
  J3 시작 60분 상한 — 행·고아가 진행으로 못 굳는다
  J4 세션 선언이 있고 그 바인딩이 클레임 중일 때만 카드 귀속(attached),
     무명 잡은 전역(serveinfo)까지만
  J5 잡 디렉토리가 없으면 현행과 동일
  J7 화면은 서버 필드(jobs)를 소비만 한다

실행: python3 tests/ jobfile
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def _load(name="s9jb"):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _jobfile():
    spec = importlib.util.spec_from_file_location(
        "jobfile_t", os.path.join(HERE, "jobfile.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Base(unittest.TestCase):
    def setUp(self):
        # 걷어야 하는 것을 **하나라도 빠뜨리면** 이 파일은 홀로 초록이면서
        # 스위트에서만 붉어진다 (REQ-20260903-012). 실제로 `S9_USER` 가 빠져
        # 있었고, 앞서 돈 파일이 두고 간 그 값 하나에 J4 가 넘어갔다 —
        # 문서를 만든 사람과 상태를 옮기는 사람이 갈리면 클레임이 안 서고,
        # 클레임이 없으면 잡이 카드에 붙지 않는다.
        #
        # 뿌리는 여기가 아니라 `os.environ` 이 프로세스 전체의 것이라는 사실에
        # 있다 — 그 구조를 고치는 일은 따로 세웠다. 이 파일이 할 수 있는 것은
        # **자기 격리를 완결하는 것**이고, 그러면 누가 무엇을 두고 가든 흔들리지
        # 않는다.
        self._saved = {k: os.environ.get(k)
                       for k in ("S9_ROOT", "S9_MACHINE", "S9_SESSION",
                                 "S9_TESTS_NESTED", "S9_USER", "S9_JOB_REQ",
                                 "S9_AUTO_RESUME")}
        self.root = tempfile.mkdtemp(prefix="s9jb-")
        os.environ["S9_ROOT"] = self.root
        os.environ["S9_MACHINE"] = "testbox"
        os.environ.pop("S9_SESSION", None)
        for _k in ("S9_USER", "S9_JOB_REQ", "S9_AUTO_RESUME"):
            os.environ.pop(_k, None)
        # 병렬 러너의 직렬 꼬리는 S9_TESTS_NESTED=1 환경에서 돈다 — 이 스위트가
        # 검사하는 것이 바로 그 스위치라, 물려받은 값을 걷어야 한다(안 걷으면
        # start() 가 전부 무음이 되어 다섯 건이 한꺼번에 빨개진다 — 실측).
        os.environ.pop("S9_TESTS_NESTED", None)
        self.env = {**os.environ}
        subprocess.run([S9, "init"], capture_output=True, env=self.env,
                       timeout=30)
        self.m = _load()
        self.jdir = os.path.join(self.root, "state", "jobs")

    def tearDown(self):
        import shutil
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def put_job(self, pid=None, started=None, hint="python", session="",
                name="테스트"):
        os.makedirs(self.jdir, exist_ok=True)
        j = {"name": name, "hint": hint,
             "pid": os.getpid() if pid is None else pid,
             "started": time.time() if started is None else started,
             "session": session, "total": 100, "done": 42}
        with open(os.path.join(self.jdir, "tests.json"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps(j))
        return j


class TheWriter(Base):
    """J1 — 러너 모듈의 쓰기·거두기·안쪽 실행 침묵."""

    def test_j1_start_writes_bump_updates_clear_removes(self):
        jf = _jobfile()
        bump, clear = jf.start(100, root=self.root)
        p = os.path.join(self.jdir, f"tests-{os.getpid()}.json")
        self.assertTrue(os.path.exists(p), "시작이 잡 파일을 안 썼다")
        j = json.load(open(p, encoding="utf-8"))
        self.assertEqual(j["pid"], os.getpid())
        self.assertEqual(j["total"], 100)
        time.sleep(1.05)
        bump(37)
        j = json.load(open(p, encoding="utf-8"))
        self.assertEqual(j["done"], 37, "진행 수가 갱신되지 않았다")
        clear()
        self.assertFalse(os.path.exists(p), "끝났는데 잡 파일이 남았다")

    def test_c1_concurrent_runs_coexist(self):
        # 반려가 찾은 결함: 이름이 하나면 동시 실행이 서로 덮어쓴다.
        jf = _jobfile()
        bump, clear = jf.start(100, root=self.root)
        self.put_job()          # 다른 실행의 잡 (put_job 은 tests.json 에 쓴다)
        rows = self.m.jobs_running()
        self.assertEqual(len(rows), 2,
                         "동시 실행 둘이 잡 하나로 뭉개졌다")
        clear()

    def test_c2_clear_removes_only_its_own(self):
        jf = _jobfile()
        bump, clear = jf.start(100, root=self.root)
        other = self.put_job()   # 다른 실행
        clear()                  # 내 것만 거둔다
        rows = self.m.jobs_running()
        self.assertEqual(len(rows), 1,
                         "한 실행의 정리가 다른 실행의 표시를 지웠다")
        self.assertEqual(rows[0]["pid"], other["pid"])

    def test_c3_week_old_leftovers_are_swept_on_start(self):
        # kill -9 는 clear 를 못 만나고 읽는 쪽은 무시만 한다 — pid 파일명이
        # 된 뒤로 고아가 이름을 바꿔 가며 쌓이므로, 다음 시작이 거둬야 한다.
        os.makedirs(self.jdir, exist_ok=True)
        old = os.path.join(self.jdir, "tests-424242.json")
        with open(old, "w", encoding="utf-8") as f:
            f.write("{}")
        week_ago = time.time() - 8 * 86400
        os.utime(old, (week_ago, week_ago))
        fresh = os.path.join(self.jdir, "tests.json")
        self.put_job()                    # 신선한 동시 실행은 남아야 한다
        jf = _jobfile()
        bump, clear = jf.start(10, root=self.root)
        self.assertFalse(os.path.exists(old), "7일 넘은 고아 잡이 안 거둬졌다")
        self.assertTrue(os.path.exists(fresh), "신선한 형제 잡까지 지웠다")
        clear()

    def test_c4_args_reach_the_server(self):
        jf = _jobfile()
        bump, clear = jf.start(30, root=self.root, args="wake stall")
        rows = self.m.jobs_running()
        mine = [r for r in rows if r["pid"] == os.getpid()]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["args"], "wake stall",
                         "실행 범위가 서버 응답에 안 실린다")
        clear()

    def test_c5_writer_sweeps_week_old_orphans(self):
        # kill -9 로 죽은 실행의 잔재 — atexit 이 못 돈다. 쓰기 쪽 안전망과
        # 워처 sweep(bin/s9, heartbeat 와 같은 루프) 두 겹이 거둔다.
        os.makedirs(self.jdir, exist_ok=True)
        orphan = os.path.join(self.jdir, "tests-424242.json")
        with open(orphan, "w") as f:
            f.write("{}")
        t = time.time() - 8 * 86400
        os.utime(orphan, (t, t))
        jf = _jobfile()
        bump, clear = jf.start(10, root=self.root)
        self.assertFalse(os.path.exists(orphan),
                         "7일 넘은 고아 잡 파일이 안 거둬졌다")
        clear()

    def test_c5b_watcher_sweep_covers_jobs_dir(self):
        # 문서가 약속한 sweep 이 실재하는가 — 코드 계약 검사 (재검증이 찾은
        # "주장은 있는데 코드가 없다" 재발 방지).
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("def rework_watch_tick(")
        j = src.index("\ndef ", i + 10)
        self.assertIn('"jobs"', src[i:j],
                      "워처 틱의 7일 sweep 이 state/jobs 를 안 돈다")

    def test_j1b_nested_run_writes_nothing(self):
        os.environ["S9_TESTS_NESTED"] = "1"
        jf = _jobfile()
        jf.start(100, root=self.root)
        self.assertFalse(os.path.exists(self.jdir),
                         "안쪽 실행이 잡을 썼다 — 바깥 화면이 이중으로 센다")


class TheReader(Base):
    """J2·J3·J5 — 서버는 선언을 검증해서만 믿는다."""

    def test_j2_dead_pid_is_invisible(self):
        self.put_job(pid=999999983)
        self.assertEqual(self.m.jobs_running(), [],
                         "죽은 pid 의 잡이 진행으로 보인다")

    def test_j2b_wrong_cmdline_is_invisible(self):
        # 내 pid 는 살아 있지만 명령줄에 이 힌트는 없다 — pid 재사용의 모형.
        self.put_job(hint="definitely-not-in-cmdline-zz9")
        self.assertEqual(self.m.jobs_running(), [],
                         "명령줄 불일치 잡이 보인다 — pid 재사용 방어 구멍")

    def test_j2c_live_matching_job_is_visible(self):
        self.put_job()          # 내 pid + 'python' 힌트 = 살아 있는 잡
        rows = self.m.jobs_running()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["done"], 42)
        self.assertEqual(rows[0]["name"], "테스트")

    def test_j3_hour_cap(self):
        self.put_job(started=time.time() - 3700)
        self.assertEqual(self.m.jobs_running(), [],
                         "한 시간 넘은 잡이 진행으로 굳어 있다")

    def test_j5_no_dir_no_signal(self):
        self.assertEqual(self.m.jobs_running(), [])


class TheAttribution(Base):
    """J4 — 세션 선언이 있을 때만 카드로 간다."""

    def mkreq(self, sess):
        env = dict(self.env)
        env["S9_SESSION"] = sess
        r = subprocess.run([S9, "new", "request", "--title", "잡 붙는 곳",
                            "--summary", "s", "--size", "S", "--user",
                            "nicehugepark", "--goal", "g", "--body", "x"],
                           capture_output=True, text=True, env=env, timeout=30)
        rid = r.stdout.split()[0]
        subprocess.run([S9, "status", rid, "in-progress", "--note", "t"],
                       capture_output=True, env=env, timeout=30)
        return rid

    def test_j4_declared_session_reaches_the_card(self):
        subprocess.run([S9, "user", "add", "nicehugepark"],
                       capture_output=True, env=self.env, timeout=30)
        rid = self.mkreq("cafe9999")
        self.put_job(session="cafe9999")
        row = next(r for r in self.m.catalog_with_live() if r["id"] == rid)
        self.assertTrue(row.get("jobs"), "선언된 잡이 카드에 안 실렸다")
        self.assertEqual(row.get("stall_state"), "attached", row)
        self.assertIsNone(row.get("stalled_mins"),
                          "잡이 도는데 깨우기 손잡이가 선다")

    def test_j4c_last_req_alone_does_not_attach(self):
        """REQ-20260830-040 실측: 훅이 매 프롬프트 회전시키는 last_req 를 잡
        귀속이 믿어, 한 테스트 런이 대화만 스친 카드에도 「테스트 4분째」로
        섰다(스크린샷: 037·039 두 카드 동시). 클레임(active_reqs)만 귀속 근거다."""
        subprocess.run([S9, "user", "add", "nicehugepark"],
                       capture_output=True, env=self.env, timeout=30)
        mine = self.mkreq("cafe9999")            # cafe9999 의 클레임
        other = self.mkreq("beef8888")           # 남의 클레임 — 대화만 스친 카드
        env = dict(self.env)
        env["S9_SESSION"] = "cafe9999"
        subprocess.run([S9, "last", other], capture_output=True, env=env,
                       timeout=30)               # 훅 회전 흉내: last_req 만 other
        self.put_job(session="cafe9999")
        rows = {r["id"]: r for r in self.m.catalog_with_live()}
        self.assertTrue(rows[mine].get("jobs"), "클레임 카드에서 잡이 사라졌다")
        self.assertFalse(rows[other].get("jobs"),
                         "last_req 만으로 잡이 남의 카드에 붙었다 — 오귀속")

    def test_j4b_anonymous_job_stays_global(self):
        subprocess.run([S9, "user", "add", "nicehugepark"],
                       capture_output=True, env=self.env, timeout=30)
        rid = self.mkreq("cafe9999")
        self.put_job(session="")                 # 무명 잡
        row = next(r for r in self.m.catalog_with_live() if r["id"] == rid)
        self.assertFalse(row.get("jobs"),
                         "무명 잡이 카드에 귀속됐다 — 추측 귀속(근원 B)")
        self.assertEqual(len(self.m.jobs_running()), 1,
                         "무명 잡은 전역에는 보여야 한다")


class TheWorkerDeclaration(Base):
    """W1~W5 (REQ-20260830-026) — 워커의 잡은 S9_JOB_REQ 로 선언 귀속된다."""

    def put_req_job(self, req):
        os.makedirs(self.jdir, exist_ok=True)
        j = {"name": "테스트", "hint": "python", "pid": os.getpid(),
             "started": time.time(), "session": "", "req": req,
             "total": 10, "done": 3}
        with open(os.path.join(self.jdir, "tests-w.json"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps(j))

    def mkreq(self):
        subprocess.run([S9, "user", "add", "alice"], capture_output=True,
                       env=self.env, timeout=30)
        r = subprocess.run([S9, "new", "request", "--title", "워커 잡",
                            "--summary", "s", "--size", "S", "--user", "alice",
                            "--goal", "g", "--body", "x"],
                           capture_output=True, text=True, env=self.env,
                           timeout=30)
        rid = r.stdout.split()[0]
        subprocess.run([S9, "status", rid, "in-progress", "--note", "t"],
                       capture_output=True, env=self.env, timeout=30)
        return rid

    def test_w1_spawn_env_carries_job_req(self):
        # 스폰 봉투 계약 — env 조립부에 선언이 실재하는가 (모든 reason 공통 자리).
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("def _spawn_worker(")
        j = src.index("\ndef ", i + 10)
        self.assertIn('env["S9_JOB_REQ"] = canon_id(doc_id)', src[i:j],
                      "워커 봉투에 잡 선언이 없다 — 워커 테스트가 전역에만 뜬다")

    def test_w2_jobfile_records_the_declaration(self):
        os.environ["S9_JOB_REQ"] = "REQ-20260830-999-zzzz"
        try:
            jf = _jobfile()
            bump, clear = jf.start(5, root=self.root)
            p = os.path.join(self.jdir, f"tests-{os.getpid()}.json")
            j = json.load(open(p, encoding="utf-8"))
            self.assertEqual(j["req"], "REQ-20260830-999-zzzz")
            clear()
        finally:
            os.environ.pop("S9_JOB_REQ", None)

    def test_w3_declared_req_reaches_the_card_without_session(self):
        rid = self.mkreq()
        self.put_req_job(rid)
        row = next(r for r in self.m.catalog_with_live() if r["id"] == rid)
        self.assertTrue(row.get("jobs"), "req 선언 잡이 카드에 안 붙었다")
        self.assertEqual(row.get("stall_state"), "attached", row)

    def test_w5_unknown_req_stays_global(self):
        rid = self.mkreq()
        self.put_req_job("REQ-20200101-777-none")   # 실재하지 않는 문서
        row = next(r for r in self.m.catalog_with_live() if r["id"] == rid)
        self.assertFalse(row.get("jobs"),
                         "없는 id 선언이 남의 카드에 붙었다")
        self.assertEqual(len(self.m.jobs_running()), 1,
                         "전역 표시까지 사라졌다 — 선언 실패는 전역 강등이어야")


class TheScreen(Base):
    """J7 — 화면은 서버 필드를 소비만 한다."""

    def test_j7_screen_consumes_server_fields(self):
        notice = open(os.path.join(HERE, "..", "web", "app", "notice.js"),
                      encoding="utf-8").read()
        card = open(os.path.join(HERE, "..", "web", "app", "card.js"),
                    encoding="utf-8").read()
        self.assertIn("ocInfo.jobs", notice, "칩이 서버 잡 필드를 안 읽는다")
        self.assertIn("잠잠", notice, "잠잠(신호 침묵) 낱말이 없다")
        self.assertIn("r.jobs", card, "카드가 잡 필드를 안 읽는다")
        for js in (notice, card):
            self.assertNotIn("state/jobs", js,
                             "화면이 잡 파일을 직접 읽으려 한다 — 서버 검증 우회")


if __name__ == "__main__":
    unittest.main(verbosity=2)
