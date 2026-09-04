"""병행 REQ live 표시 테스트 (REQ-20260823-079 → 080 → 082에서 정밀화).

live(녹색 점멸) = 세션의 명시 실행 등록만: last_req 포인터 또는 active_reqs
(in-progress 전이 시 자동 등록), 그 세션의 스트림이 2분 내 갱신일 때.
스트림에 id가 언급만 되거나(대화 ≠ 작업) 문서 파일이 갱신됐다는 것(반려 전이 등)은
직접 증거가 아니다 (REQ-20260823-082). 세션만 활발하면 live_kind=session (간접).
격리: S9_ROOT=mktemp. 실행: python3 tests/test_live_catalog.py
"""
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


# 임시 포트를 뽑지 않는다 — 고정 풀에서 돌려쓴다 (REQ-20260825-100, portpool 참조)
from portpool import free_port, wait_server  # noqa: E402


class TestLiveCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9live-")
        cls.claude_dir = os.path.join(cls.tmp, "claude-projects")
        os.makedirs(os.path.join(cls.claude_dir, "proj"), exist_ok=True)
        base = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                "S9_CLAUDE_PROJECTS": cls.claude_dir,
                # 이 판의 문서는 alice 의 것이고, 전이도 alice 가 한다.
                # 소유 게이트(REQ-20260902-016)가 들어온 뒤로 **남의 문서를
                # 전이한 세션은 그 문서를 클레임하지 않는다** — 짓는 이와 집는
                # 이가 갈리면 D6·D7 이 "등록이 안 됐다"로 넘어진다. 그것은 이
                # 시험이 재려던 것이 아니다.
                "S9_USER": "alice"}
        # 바깥 세션의 자취를 들이지 않는다 — 무인 재작업 세션 안에서 스위트를
        # 돌리면 그 봉투(S9_AUTO_RESUME·S9_ORIGIN·S9_JOB_REQ)가 새로 짓는
        # 문서에 origin_actor=worker:auto-resume 로 새겨진다. 시험은 제 판에서만
        # 서야 한다.
        for leak in ("S9_SESSION", "S9_AUTO_RESUME", "S9_ORIGIN",
                     "S9_JOB_REQ", "S9_REWORK_WATCH"):
            base.pop(leak, None)

        def cli(sess, *argv):
            env = dict(base)
            if sess:
                env["S9_SESSION"] = sess
            r = subprocess.run([S9, *argv], capture_output=True, text=True,
                               env=env, timeout=15)
            if r.returncode != 0:
                raise AssertionError(f"s9 {' '.join(argv)}: {r.stdout}{r.stderr}")
            return r.stdout

        cli(None, "init")
        cli(None, "user", "add", "alice")
        mk = lambda sess, title: cli(
            sess, "new", "request", "--title", title, "--summary", "t", "--goal", "t",
            "--size", "S", "--user", "alice", "--body", "x").split()[0]
        # A: 세션 aaaa1111이 last_req로 붙잡음 (기존 경로)
        cls.A = mk("aaaa1111", "pointed")
        cli("aaaa1111", "status", cls.A, "in-progress", "--note", "t")
        cli("aaaa1111", "last", cls.A)
        # B: 같은 세션 소속, 포인터·active 등록 없음 — 스트림 언급만으로 direct
        cls.B = mk("aaaa1111", "parallel")
        cli(None, "status", cls.B, "in-progress", "--note", "t")
        # C: 세션 bbbb2222 — 스트림이 오래됨 (좀비)
        cls.C = mk("bbbb2222", "stale")
        cli("bbbb2222", "status", cls.C, "in-progress", "--note", "t")
        cli("bbbb2222", "last", cls.C)
        # D: 같은 활발 세션이지만 done
        cls.D = mk("aaaa1111", "finished")
        cli("aaaa1111", "status", cls.D, "in-progress", "--note", "t")
        cli("aaaa1111", "status", cls.D, "done", "--note", "t")
        # E: 스트림/바인딩 없는 세션의 in-progress
        cls.E = mk("cccc3333", "orphan")
        cli("cccc3333", "status", cls.E, "in-progress", "--note", "t")
        # F: 세션이 직접 in-progress 전이 → binding.active_reqs 자동 등록 (직접)
        cls.F = mk("aaaa1111", "activereq")
        cli("aaaa1111", "status", cls.F, "in-progress", "--note", "t")
        # G: 같은 세션 소속이지만 전이는 세션 없이 — 간접(session)만
        cls.G = mk("aaaa1111", "indirect")
        cli(None, "status", cls.G, "in-progress", "--note", "t")
        # H: in-progress 등록 후 done — active_reqs에서 자동 제거(prune) 확인
        cls.H = mk("aaaa1111", "pruned")
        cli("aaaa1111", "status", cls.H, "in-progress", "--note", "t")
        cli("aaaa1111", "status", cls.H, "done", "--note", "t")
        # I: 세션 신호 없음 — 문서 파일이 방금 갱신되면 직접 증거
        cls.I = mk("dddd4444", "docfresh")
        cli(None, "status", cls.I, "in-progress", "--note", "t")
        # J: last --add로 병행 실행 등록 (last_req 교체 없이) → 직접
        cls.J = mk("aaaa1111", "added")
        cli(None, "status", cls.J, "in-progress", "--note", "t")
        cli("aaaa1111", "last", cls.J, "--add")

        # K: 세션 신호 없음 + 무인 스폰 기록만 있음 → spawned 표시
        cls.K = mk("ffff6666", "spawnedcase")
        cli(None, "status", cls.K, "in-progress", "--note", "t")
        ar_dir = os.path.join(cls.tmp, "state", "auto_resume")
        os.makedirs(ar_dir, exist_ok=True)
        with open(os.path.join(ar_dir, cls.K + ".json"), "w") as f:
            json.dump({"last": time.time() - 60, "count": 1}, f)

        # N: 무인 스폰형 세션 — 바인딩에 transcript 없음, 클레임(--add) 시
        # native transcript 자동 발견 → 즉시 direct (REQ-20260824-013)
        cls.N = mk("gggg7777", "workerclaim")
        cli(None, "status", cls.N, "in-progress", "--note", "t")
        with open(os.path.join(cls.claude_dir, "proj",
                               "gggg7777-aaaa-bbbb-cccc-dddddddddddd.jsonl"), "w") as f:
            f.write("{}\n")
        cli("gggg7777", "last", cls.N, "--add")

        # M: blocked + 사유 note → 카탈로그 block_reason (REQ-20260824-011)
        cls.M = mk("aaaa1111", "blockedcase")
        cli(None, "status", cls.M, "in-progress", "--note", "t")
        cli(None, "status", cls.M, "blocked", "--note", "패치 적용 대기(리드) — P1 적용 필요")

        # 모든 vault 문서 mtime을 10분 전으로 — 문서 갱신 증거는 I만 남긴다
        import glob as g
        old = time.time() - 600
        docs = g.glob(os.path.join(cls.tmp, "vault", "requests", "**", "*.md"),
                      recursive=True)
        for p in docs:
            os.utime(p, (old, old))
        ipath = [p for p in docs if p.endswith(cls.I + ".md")][0]
        os.utime(ipath, None)  # I 문서만 방금 갱신된 것으로

        # 스트림 파일: aaaa1111=방금 갱신(B id 언급 포함), bbbb2222=10분 전
        streams = os.path.join(cls.tmp, "streams")
        os.makedirs(streams, exist_ok=True)
        fresh = os.path.join(streams, "aaaa1111.jsonl")
        stale = os.path.join(streams, "bbbb2222.jsonl")
        with open(fresh, "w") as f:
            f.write(json.dumps({"role": "assistant",
                                "text": f"s9 note {cls.B} 작업 진행"}) + "\n")
        with open(stale, "w") as f:
            f.write(json.dumps({"role": "assistant",
                                "text": f"{cls.C} 작업"}) + "\n")
        old = time.time() - 600
        os.utime(stale, (old, old))

        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=base, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)   # WSL 포트 공개 지연 대비 (REQ-099) — 백오프 대기
        with urllib.request.urlopen(
                f"http://127.0.0.1:{cls.port}/api/catalog", timeout=5) as r:
            cls.rows = {x["id"]: x for x in json.loads(r.read().decode())}

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    # D1. 포인터 직접 증거
    def test_test_live_catalog(self):
        """TestLiveCatalog 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("d1_pointer_live"):
                r = self.rows[self.A]
                self.assertTrue(r["live"], r)

            # D2(082 개정): 스트림 tail 언급은 대화일 뿐 — 직접 증거 아님, 간접까지만
        with self.subTest("d2_mention_is_not_direct"):
                r = self.rows[self.B]
                self.assertFalse(r["live"], r)
                self.assertEqual(r.get("live_kind"), "session", r)

            # D3. 세션만 활발 = 간접 — live 아님, live_kind=session
        with self.subTest("d3_unmentioned_session_indirect"):
                r = self.rows[self.G]
                self.assertFalse(r["live"], r)
                self.assertEqual(r.get("live_kind"), "session", r)

            # D6. 세션이 in-progress로 전이한 REQ = binding.active_reqs 자동 등록 → 직접
        with self.subTest("d6_active_req_direct"):
                r = self.rows[self.F]
                self.assertTrue(r["live"], r)

            # D7. done 전이 시 모든 바인딩의 active_reqs에서 제거
        with self.subTest("d7_done_prunes_active"):
                bp = os.path.join(self.tmp, "state", "sessions", "testbox__aaaa1111.json")
                with open(bp) as f:
                    b = json.load(f)
                self.assertIn(self.F, b.get("active_reqs", []), b)
                self.assertNotIn(self.H, b.get("active_reqs", []), b)

            # D10. 무인 스폰 직후(클레임 전) → live_kind=spawned (REQ-20260824-008)
        with self.subTest("d10_spawned_pending_visible"):
                r = self.rows[self.K]
                self.assertFalse(r["live"], r)
                self.assertEqual(r.get("live_kind"), "spawned", r)

            # D11 (REQ-20260824-013). 클레임 시 transcript 자동 발견 → 무인 세션도 direct
        with self.subTest("d11_worker_claim_direct"):
                r = self.rows[self.N]
                self.assertTrue(r["live"], r)
                self.assertEqual(r.get("live_kind"), "direct", r)

            # B1 (REQ-20260824-011). blocked 문서는 마지막 blocked 전이 note가 사유로 노출
        with self.subTest("b1_block_reason_exposed"):
                r = self.rows[self.M]
                self.assertEqual(r.get("block_reason"), "패치 적용 대기(리드) — P1 적용 필요", r)

            # D9. last --add 병행 등록 → 직접 (last_req는 A 그대로)
        with self.subTest("d9_last_add_direct"):
                self.assertTrue(self.rows[self.J]["live"], self.rows[self.J])
                self.assertTrue(self.rows[self.A]["live"])  # last_req 교체 안 됨

            # D8(082 개정): 문서 갱신(반려 전이 등)만으로는 live 아님 — 실행 등록 필요
        with self.subTest("d8_doc_write_alone_not_live"):
                r = self.rows[self.I]
                self.assertFalse(r["live"], r)
                self.assertFalse(r.get("live_kind"), r)

            # D4. 오래된 세션 = 무신호 (스트림에 id가 있어도 스트림 자체가 stale)
        with self.subTest("d4_stale_session_no_signal"):
                r = self.rows[self.C]
                self.assertFalse(r["live"], r)
                self.assertFalse(r.get("live_kind"), r)

            # D5. done은 신호 무관 live 아님
        with self.subTest("d5_done_not_live"):
            self.assertFalse(self.rows[self.D]["live"], self.rows[self.D])
        with self.subTest("d5b_unrelated_not_live"):
            r = self.rows[self.E]
            self.assertFalse(r["live"], r)
            self.assertFalse(r.get("live_kind"), r)

if __name__ == "__main__":
    unittest.main(verbosity=2)
