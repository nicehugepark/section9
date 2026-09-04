"""두 머신 위장 시험 (REQ-20260902-015-62x6 · 설계 DOC-20260902-001-62x6 §1·§5).

두 컴퓨터가 리포 하나를 나눠 쓸 때 **남의 반려 문서가 pull 돼 오면 내 쪽의
훅 목록·`s9 next`·워처·의존 재개·채팅 대상이 그것을 집는다** — deep-diver 의
격리 재현(projects/section9/assets/014-sync-design/)이 exit 0 으로 확인한
현행 결함이다. 이 파일은 그 재현을 회귀 시험으로 고정한다.

**이 파일의 S4~S7 은 지금 코드에서 빨강이어야 옳다.** P0 의 목적이 빨간
시험이다 — 초록으로 만드는 것은 후속 REQ 의 몫이고, 각 시험의 docstring 에
어느 REQ 가 그것을 초록으로 만드는지 적었다:

    016  귀속 게이트 단일화 (exec_verdict 하나 — 잠정 키 machine)
    017  세션 바인딩 불가침 (남의 바인딩은 판정에 쓰지 않고 고쳐 쓰지 않는다)
    020  리스 프로토콜 (담당자 + 문서 리스, 다른 머신은 벽시계만)

픽스처 자체의 시험(S1·S2)과 회귀 고정(S3)은 지금도 통과해야 한다.

실행: python3 tests/ two_machine
픽스처: tests/twomachine.py (`--changed` 가 그 파일의 변경을 이 시험에 잇는다)
"""
import os
import subprocess
import unittest

from twomachine import (A_SESS, B_SESS, TwoMachine, reject_on,
                        seed_alpha_review)


class TestFixtureRoundTrip(unittest.TestCase):
    """S1·S2 — 픽스처가 진짜로 왕복하는가 (통과해야 옳다)."""

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cls.fx.cli("alpha", "user", "add", "alice")
        cls.fx.cli("alpha", "user", "switch", "alice", sess=A_SESS)
        cls.X = cls.fx.new_request("alpha", "왕복 문서", sess=A_SESS)

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_s1_document_crosses_and_returns(self):
        """alpha 의 문서가 beta 에 pull 되고, beta 의 전이가 alpha 로 돌아온다."""
        fx, X = self.fx, self.X
        fx.sync("alpha")
        fx.pull("beta")
        out = fx.cli("beta", "show", X)
        self.assertIn("왕복 문서", out)
        self.assertEqual(fx.doc("beta", X)[0].get("machine"), "alpha")
        # beta 에서 전이 — CLI 의 문서 이벤트가 maybe_sync 로 실제 push 까지 간다
        fx.cli("beta", "status", X, "in-progress", "--note", "beta 착수",
               sess=B_SESS, user="alice")
        fx.sync("beta")
        fx.pull("alpha")
        meta, body = fx.doc("alpha", X)
        self.assertEqual(meta.get("status"), "in-progress")
        self.assertIn("open -> in-progress", body)
        self.assertEqual(fx.head("alpha"), fx.head("beta"))
        self.assertEqual(fx.head("alpha"), fx.head())

    def test_s2_bindings_stay_home_and_claude_is_never_spawned(self):
        """state/sessions 는 track 해제(REQ-20260902-026) — alpha 의 바인딩은
        sync→pull 뒤에도 beta 에 오지 않는다. fake_spawn 은 claude 만 삼킨다."""
        fx = self.fx
        fx.sync("alpha")
        fx.pull("beta")
        self.assertFalse(os.path.isfile(fx.binding_file("beta", "alpha", A_SESS)),
                         "alpha 의 세션 바인딩이 beta 의 state/sessions 에 실려 왔다 "
                         "— track 해제가 풀렸다 (.gitignore 또는 SYNC_DATA_PATHS)")
        with fx.fake_spawn():
            r = subprocess.run(["git", "--version"], capture_output=True,
                               text=True)
            self.assertIn("git version", r.stdout)     # git 은 진짜로 돈다
            p = subprocess.Popen(["claude", "-p", "hello"])
            self.assertEqual(p.pid, 4242)               # claude 는 삼킨다
        self.assertEqual(len(fx.claude_spawns()), 1)
        self.assertEqual(fx.claude_spawns()[0]["argv"][:2], ["claude", "-p"])


class TestReworkWatcherAcrossMachines(unittest.TestCase):
    """S3·S4 — 반려 워처. alpha 의 alice 문서를 beta 대시보드에서 반려한 장면."""

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cls.X = seed_alpha_review(cls.fx)
        cls.fx.sync("alpha")
        cls.fx.pull("beta")
        reject_on(cls.fx, "beta", cls.X)
        cls.fx.sync("beta")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_s3_beta_watcher_does_not_spawn_for_alpha_doc(self):
        """(a) 회귀 고정 — beta 워처는 alpha 의 문서를 띄우지 않는다.

        현행도 통과한다(machine 가드 'elsewhere'). 016 이 게이트를 한 함수로
        모은 뒤에도, 020 이 키를 리스로 바꾼 뒤에도(alpha 세션 A 의 리스가
        신선하다) 0 이어야 한다."""
        fx = self.fx
        self.assertEqual(fx.doc("beta", self.X)[0].get("status"), "in-progress")
        spawned, calls = fx.tick("beta", grace=0)
        self.assertEqual(spawned, [], "beta 워처가 alpha 의 문서를 띄웠다")
        self.assertEqual(calls, [])

    def test_s4_alpha_watcher_respects_beta_claim(self):
        """(b) 빨강 — beta 세션이 `s9 claim` 으로 이어받았는데 alpha 워처가 겹쳐 띄운다.

        현행: alpha 의 `rework_claimed` 는 beta 바인딩을 보지만 생존 신호
        (pid·transcript·inbox tail)가 전부 alpha 에 없어 '죽은 세션'으로 읽고
        스폰한다(repro_reassign [1], Popen 2회). 초록으로 만드는 것: 016(게이트
        단일화 — 다른 머신의 클레임은 로컬 생존 신호로 판정하지 않는다) →
        020(리스: 다른 머신은 벽시계만)."""
        fx, X = self.fx, self.X
        fx.pull("beta")
        fx.cli("beta", "user", "switch", "alice", sess=B_SESS)
        # alpha 세션 A 의 리스가 아직 신선하다 — 다른 컴퓨터에서 이어가는 길은
        # 명시 이관(--takeover)이다 (D1 조건, REQ-20260902-020)
        fx.cli("beta", "claim", X, "--takeover", sess=B_SESS)
        b = fx.read_binding_file("beta", "beta", B_SESS)
        self.assertIn(X, b.get("active_reqs") or [])
        fx.sync("beta")
        fx.pull("alpha")
        # 바인딩은 오지 않는다(REQ-20260902-026) — alpha 가 아는 것은 문서뿐이다
        self.assertFalse(os.path.isfile(fx.binding_file("alpha", "beta", B_SESS)))
        self.assertEqual(fx.doc("alpha", X)[0].get("session"), B_SESS)
        fx.clear_spawn_marks("alpha")
        spawned, calls = fx.tick("alpha", grace=0)
        self.assertEqual(
            spawned, [],
            f"beta 세션 {B_SESS} 가 클레임한 {X} 에 alpha 워처가 겹쳐 띄웠다 "
            f"(claude argv {len(calls)}건)")


class TestLeaseCasAcrossMachines(unittest.TestCase):
    """S8 (REQ-20260902-020) — 스폰은 리스를 push 한 뒤에만, 남은 쪽은 물러난다."""

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cls.X = seed_alpha_review(cls.fx)
        cls.fx.sync("alpha")
        cls.fx.pull("beta")
        reject_on(cls.fx, "beta", cls.X)
        cls.fx.sync("beta")
        cls.fx.pull("alpha")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_s8_first_spawner_holds_the_lease_and_the_other_yields(self):
        fx, X = self.fx, self.X
        fx.clear_spawn_marks("alpha")
        spawned, calls = fx.tick("alpha", grace=0)
        self.assertEqual(spawned, [X], f"alpha 워처가 담당자의 반려 문서를 띄우지 않았다: {calls}")
        meta = fx.doc("alpha", X)[0]
        lease = meta.get("lease") or {}
        self.assertEqual(lease.get("machine"), "alpha")
        self.assertEqual(lease.get("user"), "alice")
        # 리스는 이미 origin 에 있다 — beta 가 당기면 물러난다
        fx.pull("beta")
        self.assertEqual((fx.doc("beta", X)[0].get("lease") or {}).get("machine"), "alpha")
        fx.clear_spawn_marks("beta")
        spawned, calls = fx.tick("beta", grace=0)
        self.assertEqual(spawned, [], f"beta 워처가 alpha 의 리스를 무시하고 띄웠다: {calls}")


class TestHookListsAcrossMachines(unittest.TestCase):
    """S5 — 훅이 매 턴 주입하는 목록·`s9 next` 가 남의 문서를 싣는가."""

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cls.X = seed_alpha_review(cls.fx)
        cls.fx.sync("alpha")
        cls.fx.pull("beta")
        reject_on(cls.fx, "beta", cls.X)
        cls.fx.cli("beta", "user", "add", "bob")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_s5a_reopened_list_of_bob_at_beta_excludes_alice_doc(self):
        """(c) 빨강 — bob@beta 의 `s9 reopened` 에 alice 의 반려 문서가 오른다.

        `reopened_requests` 에는 user·machine 필터가 없다(deep-diver [b]). 훅
        (s9-audit-prompt)이 이 목록을 "이번 턴에서 우선 이어서" 로 주입하므로
        bob 의 리드 세션이 워처보다 먼저 남의 일을 받는다. 초록: 016 (목록
        4곳이 exec_verdict 를 쓴다)."""
        fx, X = self.fx, self.X
        out = fx.cli("beta", "reopened", user="bob")
        self.assertNotIn(X, out, f"bob@beta 의 reopened 에 alice 의 {X} 가 올랐다")
        # bob 의 `s9 next` 는 user 필터로 지금도 비어 있다 — 회귀 고정
        nxt = fx.cli("beta", "next", "--json", user="bob")
        self.assertNotIn(X, nxt)

    def test_s5b_next_of_alice_at_beta_does_not_offer_alpha_doc(self):
        """(c) 빨강 — alice@beta 의 `s9 next` 가 alpha 에서 alice 가 하던 문서를 준다.

        `next_pickup` 은 user 만 보고 machine 을 안 본다. 같은 사람이라도
        문서의 리스는 alpha 세션 A 에 있으니 beta 가 집으면 두 머신이 같은
        문서를 동시에 만진다. 초록: 016 (잠정 키 machine) / 020 (신선한 리스는
        다른 머신에 not-mine)."""
        fx, X = self.fx, self.X
        nxt = fx.cli("beta", "next", "--json", user="alice")
        self.assertNotIn(X, nxt, f"alice@beta 의 next 가 alpha 의 {X} 를 권했다")


class TestDependentsAcrossMachines(unittest.TestCase):
    """S6 — 의존 해제 자동 재개가 남의 blocked 문서를 내 머신에서 되살린다."""

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        fx = cls.fx
        cls.X = seed_alpha_review(fx)
        cls.Y = fx.new_request("alpha", "알파의 후속", sess=A_SESS)
        fx.cli("alpha", "status", cls.Y, "in-progress", "--note", "착수",
               sess=A_SESS)
        fx.cli("alpha", "link", cls.Y, "--blocked-by", cls.X, sess=A_SESS)
        fx.cli("alpha", "status", cls.Y, "blocked", "--note",
               f"{cls.X} 완료 대기", sess=A_SESS)
        fx.sync("alpha")
        fx.pull("beta")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_s6_beta_does_not_resume_alpha_blocked_doc(self):
        """(d) 빨강 — beta 에서 X 를 닫으면 alpha 의 Y 가 beta 에서 in-progress 로 살아난다.

        `trigger_dependents` 는 카탈로그 전수를 돌며 blocked_by 에 done id 가
        있으면 `do_transition(in-progress, auto=True)` 한다 — 문서가 누구의
        것이든(deep-diver [e]). Y 는 alice 가 alpha 세션 A 에서 막아 둔 문서다.
        초록: 016 (trigger_dependents 가 exec_verdict 를 쓴다)."""
        fx, X, Y = self.fx, self.X, self.Y
        mod = fx.load_mod("beta")
        self.assertEqual(fx.doc("beta", Y)[0].get("status"), "blocked")
        with fx.fake_spawn():
            mod.do_transition(X, "done", note="승인: 끝", judge=True,
                              via="dashboard")
            freed = mod.trigger_dependents(X)
        self.assertNotIn(Y, freed, f"beta 가 alpha 의 {Y} 를 재개했다: {freed}")
        self.assertEqual(fx.doc("beta", Y)[0].get("status"), "blocked")


class TestBindingCollisionAcrossMachines(unittest.TestCase):
    """S7 — 남의 바인딩의 attach_pid 가 내 머신의 산 pid 와 겹칠 때."""

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        fx = cls.fx
        cls.X = seed_alpha_review(fx)
        # alpha 세션 A 의 바인딩: X 를 잡고 있고 attach_pid 는 alpha 의 claude.
        # 그 번호가 beta 에서는 (우연히) 이 시험 프로세스다 — 실리포 바인딩
        # 159건 중 131건이 attach_pid 를 가진다(DOC-20260902-001 §1).
        b = fx.read_binding_file("alpha", "alpha", A_SESS)
        b["active_reqs"] = [cls.X]
        b["attach_pid"] = os.getpid()
        fx.write_binding_file("alpha", b)
        fx.sync("alpha")
        fx.pull("beta")
        # track 해제(REQ-20260902-026) 뒤로 바인딩은 git 으로 오지 않는다. 그래도
        # 해제 전에 실려 온 잔재가 beta 디스크에 남아 있을 수 있다 — 그 잔재를
        # 그대로 놓아 017(남의 바인딩은 판정에 쓰지 않는다)의 회귀를 지킨다.
        fx.write_binding_file("beta", b)

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_s7_chat_target_at_beta_ignores_alpha_binding(self):
        """(e) 빨강 — beta 의 `chat_target()` 이 alpha/aaaa1111 을 고른다.

        `chat_live` 는 `pid_alive(attach_pid)` 를 보고, pid 는 그 머신에서만
        뜻이 있다(deep-diver [f]). 고르면 사용자의 채팅이 아무도 읽지 않는
        수신함으로 간다. 초록: 017 (남의 바인딩은 판정에 쓰지 않는다 — D7 ㉠
        track 해제까지 가면 파일 자체가 오지 않는다)."""
        fx = self.fx
        mod = fx.load_mod("beta")
        b = fx.read_binding_file("beta", "alpha", A_SESS)
        self.assertEqual(b.get("attach_pid"), os.getpid())
        t = mod.chat_target(None)
        self.assertFalse(
            t and t.get("machine") == "alpha",
            f"beta 의 chat_target 이 남의 바인딩을 골랐다: "
            f"{(t or {}).get('machine')}/{(t or {}).get('session')}")


if __name__ == "__main__":
    unittest.main()
