"""동기화 멈춤 표시와 복구 (REQ-20260902-025-62x6).

실패는 state/sync.log 한 줄뿐이었다 — 화면·digest·훅에는 아무것도 없었다.
sync_status() 한 함수가 사실을 내고 표면 셋이 그것을 본다; resolve 는 드라이버가
못 푼 충돌 문서를 한쪽으로 확정하고 rebase 를 잇는다; rescue 는 미전송 커밋을
patch 로 뽑는다. **갈래·충돌은 흉내 내지 않는다** — bare origin + 클론 둘로
실제로 만든 뒤 잰다.

실행: python3 tests/ sync_status
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
HOOK = os.path.join(HERE, "..", "bin", "s9-audit-prompt")
WEB = os.path.join(HERE, "..", "web")

DOC = "vault/requests/2026/09/{id}.md"


def sh(*argv, cwd=None, env=None, check=False):
    r = subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True,
                       text=True, timeout=60, stdin=subprocess.DEVNULL)
    if check and r.returncode != 0:
        raise AssertionError("%s 실패: %s%s" % (" ".join(argv), r.stdout, r.stderr))
    return r


def doc_text(doc_id, body):
    return (f"---\nid: {doc_id}\ntype: request\ntitle: t\nstatus: open\n"
            f"user: tester\nupdated: 2026-09-02T10:00:00+09:00\n---\n\n"
            f"## Original\n\n{body}\n\n## Notes\n\n## History\n")


class SyncStatusRepo(unittest.TestCase):
    """bare origin + 클론 A(S9_ROOT) + 클론 B. 모듈은 한 번만 싣는다."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="s9ss-")
        cls.bare = os.path.join(cls.base, "origin.git")
        sh("git", "init", "-q", "--bare", "-b", "main", cls.bare, check=True)
        cls.a = os.path.join(cls.base, "a")
        cls.b = os.path.join(cls.base, "b")
        for d in (cls.a, cls.b):
            os.makedirs(d)
            for c in (["git", "init", "-q", "-b", "main"],
                      ["git", "config", "user.name", "t"],
                      ["git", "config", "user.email", "t@t"],
                      ["git", "remote", "add", "origin", cls.bare]):
                sh(*c, cwd=d, check=True)
        os.makedirs(os.path.join(cls.a, "state"), exist_ok=True)
        with open(os.path.join(cls.a, ".s9-sync"), "w") as f:
            f.write("remote\n")
        cls.put(cls.a, "seed.txt", "seed\n")
        sh("git", "add", "-A", cwd=cls.a, check=True)
        sh("git", "commit", "-q", "-m", "seed", cwd=cls.a, check=True)
        sh("git", "push", "-q", "-u", "origin", "main", cwd=cls.a, check=True)
        sh("git", "pull", "-q", "origin", "main", cwd=cls.b, check=True)
        sh("git", "branch", "-q", "--set-upstream-to=origin/main", "main",
           cwd=cls.b, check=True)
        os.environ["S9_ROOT"] = cls.a
        os.environ.setdefault("S9_USER", "tester")
        spec = importlib.util.spec_from_loader(
            "s9_ss", importlib.machinery.SourceFileLoader("s9_ss", S9))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.base, ignore_errors=True)

    @staticmethod
    def put(root, rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def commit(self, root, msg, author_epoch=None):
        env = dict(os.environ)
        if author_epoch:
            env["GIT_AUTHOR_DATE"] = f"{int(author_epoch)} +0900"
            env["GIT_COMMITTER_DATE"] = f"{int(author_epoch)} +0900"
        sh("git", "add", "-A", cwd=root, check=True)
        sh("git", "commit", "-q", "-m", msg, cwd=root, env=env, check=True)

    def sync_to_origin(self):
        """A 를 origin 과 맞춘다 — 시험 사이의 바닥."""
        sh("git", "fetch", "-q", cwd=self.a)
        sh("git", "rebase", "-q", "@{upstream}", cwd=self.a)
        sh("git", "push", "-q", cwd=self.a)
        sh("git", "pull", "-q", "--rebase", cwd=self.b)
        for n in (".sync-stall-seen", "sync.jsonl", ".sync-pull.ts",
                  ".sync-fail.ts", ".sync-queue"):
            try:
                os.remove(os.path.join(self.a, "state", n))
            except OSError:
                pass
        with open(os.path.join(self.a, ".s9-sync"), "w") as f:
            f.write("remote\n")

    def setUp(self):
        self.sync_to_origin()

    # S1. 밀린 것 없음
    def test_s1_clean(self):
        st = self.m.sync_status()
        self.assertEqual(st["mode"], "remote")
        self.assertEqual(st["pending"], 0)
        self.assertEqual(st["stalled_sec"], 0)
        self.assertEqual(st["level"], "")
        self.assertFalse(st["diverged"])
        self.assertEqual(st["kind"], "")

    # S2. 미전송 커밋의 나이가 곧 밀림 — 작성 시각 기준
    def test_s2_pending_and_stall_levels(self):
        """밀림의 등급 — **시계를 고정하고** 잰다 (REQ-20260904-003).

        예전엔 `sync_status()` 가 진짜 시계를 읽게 뒀다. 그러면 이 시험은
        「방금 만든 커밋은 밀린 것이 아니다」가 아니라 **「이 기계가 60초 안에
        여기까지 온다」**를 재게 된다. 부하가 걸린 병렬 실행에서 커밋과 판정
        사이가 77초로 벌어져 붉어졌다(실측 2026-09-04, 커밋 게이트).

        `sync_status(now=…)` 는 처음부터 시계를 받게 돼 있었다 — 그걸 쓰면
        판정 논리만 남고 기계 속도는 빠진다.
        """
        now = time.time()
        self.put(self.a, "old.txt", "x\n")
        self.commit(self.a, "old", author_epoch=now - 600)
        st = self.m.sync_status(now=now)
        self.assertEqual(st["pending"], 1)
        self.assertGreaterEqual(st["stalled_sec"], 600)
        self.assertEqual(st["level"], "stale")
        self.assertEqual(len(st["oldest"]), 12)
        # 방금 만든 커밋만 있으면 밀림이 아니다
        self.sync_to_origin()
        self.put(self.a, "new.txt", "y\n")
        self.commit(self.a, "new", author_epoch=now)
        st = self.m.sync_status(now=now)
        self.assertEqual(st["pending"], 1)
        self.assertLess(st["stalled_sec"], 60)
        self.assertEqual(st["level"], "")
        # 60초 ~ 5분 사이는 late
        self.sync_to_origin()
        self.put(self.a, "mid.txt", "z\n")
        self.commit(self.a, "mid", author_epoch=now - 120)
        self.assertEqual(self.m.sync_status(now=now)["level"], "late")

    # S3·S4. 보냄/받음 시각과 마지막 실패 종류
    def test_s3_s4_last_sent_received_kind(self):
        st = self.m.sync_status()
        self.assertEqual(st["last_sent"], 0.0)
        self.assertEqual(st["last_received"], 0.0)
        ev = os.path.join(self.a, "state", "sync.jsonl")
        with open(ev, "w") as f:
            f.write('{"ts":"2026-09-02T10:00:00+09:00","stage":"push","rc":0}\n'
                    '{"ts":"2026-09-02T10:00:05+09:00","stage":"pull","rc":1,'
                    '"kind":"conflict"}\n')
        with open(os.path.join(self.a, "state", ".sync-pull.ts"), "w") as f:
            f.write("1700000000")
        st = self.m.sync_status()
        self.assertEqual(int(st["last_sent"]), int(self.m._iso_epoch(
            "2026-09-02T10:00:00+09:00")))
        self.assertEqual(int(st["last_received"]), 1700000000)
        self.assertEqual(st["kind"], "conflict")
        with open(ev, "a") as f:
            f.write('{"ts":"2026-09-02T10:00:09+09:00","stage":"push","rc":0}\n')
        self.assertEqual(self.m.sync_status()["kind"], "")

    # S5. 갈라짐 — A 로컬 커밋 + B 의 push 를 fetch 한 뒤
    def test_s5_diverged(self):
        self.put(self.a, "a.txt", "a\n")
        self.commit(self.a, "a")
        self.put(self.b, "b.txt", "b\n")
        self.commit(self.b, "b")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.assertFalse(self.m.sync_status()["diverged"])
        sh("git", "fetch", "-q", cwd=self.a, check=True)
        self.assertTrue(self.m.sync_status()["diverged"])

    # S6. local 모드 — 나갈 일이 없으면 멈춤도 없다
    def test_s6_local_mode_never_stalls(self):
        with open(os.path.join(self.a, ".s9-sync"), "w") as f:
            f.write("local\n")
        self.put(self.a, "l.txt", "l\n")
        self.commit(self.a, "l", author_epoch=time.time() - 900)
        st = self.m.sync_status()
        self.assertEqual(st["mode"], "local")
        self.assertEqual(st["pending"], 1)
        self.assertEqual(st["stalled_sec"], 0)
        self.assertEqual(st["level"], "")

    # S7. 문구 고정점
    def test_s7_line_fixed_points(self):
        now = 1_000_000.0
        st = {"last_sent": now - 12, "last_received": now - 8, "pending": 3}
        self.assertEqual(self.m.sync_status_line(st, now),
                         "마지막 보냄 12초 전 · 받음 8초 전 · 대기 3건")
        st = {"last_sent": 0, "last_received": now - 3600 * 5, "pending": 0,
              "diverged": True, "kind": "conflict"}
        self.assertEqual(self.m.sync_status_line(st, now),
                         "마지막 보냄 없음 · 받음 5시간 전 · 대기 0건 · "
                         "갈래가 갈렸습니다 · 충돌 — s9 sync resolve 필요")
        self.assertIn("resolve", self.m.sync_status_hint({"kind": "conflict"}))
        self.assertIn("rescue", self.m.sync_status_hint({"kind": "net"}))

    # S8. git 판이 같은 함수를 싣는다
    def test_s8_git_state_carries_sync(self):
        self.put(self.a, "g.txt", "g\n")
        self.commit(self.a, "g", author_epoch=time.time() - 400)
        st = self.m.git_state()
        self.assertEqual(st["sync"]["pending"], 1)
        self.assertEqual(st["sync"]["level"], "stale")
        self.assertTrue(st["sync"]["line"].startswith("마지막 보냄"))
        self.assertEqual(st["ahead"], st["sync"]["pending"])
        # 캡처 갈래도 같은 문장을 쓴다
        d = self.m.git_state(demo="stale")
        self.assertEqual(d["sync"]["level"], "stale")
        self.assertIn("대기 3건", d["sync"]["line"])

    # S9. digest 머리 — 멈춤일 때만
    def test_s9_digest_head(self):
        import io
        import contextlib
        stale = {"mode": "remote", "level": "stale", "pending": 2,
                 "stalled_sec": 700, "last_sent": 0, "last_received": 0,
                 "kind": "net"}
        clean = dict(stale, level="", stalled_sec=0)

        def run_digest():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    self.m.cmd_digest(mock.Mock(user=None, budget=2500))
                except SystemExit:
                    pass
            return buf.getvalue()
        with mock.patch.object(self.m, "sync_status", lambda now=None: stale):
            out = run_digest()
        self.assertTrue(out.startswith("◈ 동기화 지연 — 마지막 보냄 없음"), out[:120])
        self.assertIn("rescue", out.splitlines()[0])
        with mock.patch.object(self.m, "sync_status", lambda now=None: clean):
            out = run_digest()
        self.assertNotIn("◈ 동기화 지연", out)

    # S10. 훅 주입 한 줄 — 같은 멈춤에 한 번만
    def test_s10_stall_once(self):
        self.assertEqual(self.m.sync_stall_once(), "")
        self.put(self.a, "s.txt", "s\n")
        self.commit(self.a, "s", author_epoch=time.time() - 120)
        self.assertEqual(self.m.sync_stall_once(), "")      # late 는 아직
        self.sync_to_origin()
        self.put(self.a, "s2.txt", "s\n")
        self.commit(self.a, "s2", author_epoch=time.time() - 900)
        first = self.m.sync_stall_once()
        self.assertTrue(first.startswith("마지막 보냄"), first)
        self.assertIn("대기 1건", first)
        self.assertEqual(self.m.sync_stall_once(), "")      # 같은 에피소드
        # 그것이 나가고 새 멈춤이 오면 다시 한 번
        sh("git", "push", "-q", cwd=self.a, check=True)
        self.put(self.a, "s3.txt", "s\n")
        self.commit(self.a, "s3", author_epoch=time.time() - 900)
        self.assertNotEqual(self.m.sync_stall_once(), "")
        # CLI 도 같은 문 — remote 가 아니면 조용히 0
        r = sh(S9, "sync", "--status", "--quiet", cwd=self.a,
               env=dict(os.environ, S9_ROOT=self.a))
        self.assertEqual(r.returncode, 0, r.stderr)

    def _conflict(self, doc_id):
        """A·B 가 같은 문서를 달리 고친 상태를 만든다 (B 가 먼저 밀었다)."""
        self.put(self.a, DOC.format(id=doc_id), doc_text(doc_id, "base"))
        self.commit(self.a, "doc base")
        sh("git", "push", "-q", cwd=self.a, check=True)
        sh("git", "pull", "-q", "--rebase", cwd=self.b, check=True)
        self.put(self.b, DOC.format(id=doc_id), doc_text(doc_id, "from B"))
        self.commit(self.b, "B edit")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.put(self.a, DOC.format(id=doc_id), doc_text(doc_id, "from A"))
        self.commit(self.a, "A edit")

    def _read(self, root, doc_id):
        with open(os.path.join(root, DOC.format(id=doc_id)), encoding="utf-8") as f:
            return f.read()

    # S11. resolve --take mine
    def test_s11_resolve_mine(self):
        did = "REQ-20260902-101-test"
        self._conflict(did)
        with mock.patch.object(self.m, "rebuild_index", lambda quiet=True: None):
            res = self.m.sync_resolve([did], "mine")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["resolved"], [did])
        self.assertIn("from A", self._read(self.a, did))
        cdir = os.path.join(self.a, "state", "sync-conflict")
        with open(os.path.join(cdir, f"{did}.mine.md"), encoding="utf-8") as f:
            self.assertIn("from A", f.read())
        with open(os.path.join(cdir, f"{did}.theirs.md"), encoding="utf-8") as f:
            self.assertIn("from B", f.read())
        self.assertFalse(self.m._rebase_in_progress())
        self.assertEqual(res["pushed"], "ok")
        st = self.m.sync_status()
        self.assertEqual(st["pending"], 0)
        self.assertFalse(st["diverged"])

    # S12. resolve --take theirs
    def test_s12_resolve_theirs(self):
        did = "REQ-20260902-102-test"
        self._conflict(did)
        with mock.patch.object(self.m, "rebuild_index", lambda quiet=True: None):
            res = self.m.sync_resolve([did], "theirs")
        self.assertTrue(res["ok"], res)
        self.assertIn("from B", self._read(self.a, did))
        self.assertEqual(self.m.sync_status()["pending"], 0)
        sh("git", "pull", "-q", "--rebase", cwd=self.b, check=True)
        self.assertIn("from B", self._read(self.b, did))

    # S13. 실패 경로 — 잘못된 take · 지목하지 않은 문서의 충돌
    def test_s13_resolve_refuses(self):
        with self.assertRaises(ValueError):
            self.m.sync_resolve(["REQ-x"], "ours")
        with self.assertRaises(ValueError):
            self.m.sync_resolve([], "mine")
        d1, d2 = "REQ-20260902-103-test", "REQ-20260902-104-test"
        self._conflict(d1)
        # 같은 커밋에 두 번째 문서의 충돌도 싣는다
        self.put(self.b, DOC.format(id=d2), doc_text(d2, "B2"))
        self.commit(self.b, "B2")
        sh("git", "push", "-q", cwd=self.b, check=True)
        self.put(self.a, DOC.format(id=d2), doc_text(d2, "A2"))
        self.commit(self.a, "A2")
        with mock.patch.object(self.m, "rebuild_index", lambda quiet=True: None):
            res = self.m.sync_resolve([d1], "mine")
        self.assertFalse(res["ok"])
        self.assertIn(d2, res.get("others", []))
        self.assertFalse(self.m._rebase_in_progress())
        self.assertIn("from A", self._read(self.a, d1))      # 아무것도 안 바꿨다
        with mock.patch.object(self.m, "rebuild_index", lambda quiet=True: None):
            res = self.m.sync_resolve([d1, d2], "mine")
        self.assertTrue(res["ok"], res)
        self.assertEqual(sorted(res["resolved"]), sorted([d1, d2]))

    # S14. rescue — patch 로 뽑고 git am 으로 되살린다
    def test_s14_rescue(self):
        res = self.m.sync_rescue()
        self.assertTrue(res["ok"])
        self.assertEqual(res["files"], [])
        self.put(self.a, "r1.txt", "one\n")
        self.commit(self.a, "r1")
        self.put(self.a, "r2.txt", "two\n")
        self.commit(self.a, "r2")
        res = self.m.sync_rescue()
        self.assertEqual(len(res["files"]), 2)
        for fp in res["files"]:
            self.assertTrue(fp.endswith(".patch") and os.path.exists(fp))
        sh("git", "am", "-q", *res["files"], cwd=self.b, check=True)
        with open(os.path.join(self.b, "r2.txt")) as f:
            self.assertEqual(f.read(), "two\n")
        again = self.m.sync_rescue()
        self.assertEqual(len(again["files"]), 2)
        self.assertFalse(set(again["files"]) & set(res["files"]))   # 덮지 않는다
        self.assertEqual(self.m.sync_status()["pending"], 2)        # 커밋은 그대로
        shutil.rmtree(os.path.join(self.a, "state", "sync-rescue"))


class SyncStatusSurface(unittest.TestCase):
    """S15~S17 — 표면 고정점과 게이트 회귀 (소스 검사)."""

    def test_sync_status_surface(self):
        """S15~S17 — 표면 고정점과 게이트 회귀 (소스 검사)."""
        with self.subTest("s15_no_tree_reverting_git"):
            with open(S9_SRC, encoding="utf-8") as f:
                src = f.read()
            a = src.index("멈춤 표시와 복구 (REQ-20260902-025)")
            b = src.index("# 문서 의미 병합 (REQ-20260902-024")
            zone = src[a:b]
            self.assertIn("def sync_resolve", zone)
            for bad in ('"--hard"', '"checkout"', '"stash"', '"restore"', '"clean"'):
                self.assertNotIn(bad, zone, bad)
        with self.subTest("s16_panel_paints_line_by_text_color_only"):
            with open(os.path.join(WEB, "app", "repo.js"), encoding="utf-8") as f:
                js = f.read()
            self.assertIn('id="g-sync"', js)
            self.assertIn("function gitSyncPaint", js)
            self.assertIn("sy.line", js)
            self.assertIn('"wfact gsync"', js)
            with open(os.path.join(WEB, "css", "density.css"), encoding="utf-8") as f:
                css = f.read()
            self.assertIn(".wfact.gsync.late{color:var(--c-review)}", css)
            self.assertIn(".wfact.gsync.stale{color:var(--c-blocked)", css)
            self.assertNotIn(".gsync.late{background", css)
        with self.subTest("s17_hook_injects_once_line"):
            with open(HOOK, encoding="utf-8") as f:
                src = f.read()
            self.assertIn('run(env, "sync", "--status", "--quiet")', src)
            self.assertIn("◈ 동기화 지연", src)
            self.assertIn("{sync_late}", src)

if __name__ == "__main__":
    unittest.main()
