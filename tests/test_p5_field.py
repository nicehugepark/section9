"""P5 실측 절차서 — 다섯 장면을 기계가 매번 밟는다
(REQ-20260902-037-62x6 · 설계 DOC-20260902-001-62x6 §5 P5. 선행 P1~P4 done).

**이 파일이 곧 절차서다.** 사람이 두 컴퓨터를 놓고 따라 할 다섯 장면 —
할당 · 두 대 · 파생 · 관찰자 · 동기화 실패 — 을 순서 그대로 담고, 각 시험의
docstring 에 **사람이 칠 명령**과 **보여야 할 화면**을 적었다. 사람의 실측은
한 번이고 기계의 실측은 매번이다: 절차서만 문서에 두면 코드가 바뀌는 날
조용히 낡지만, 여기 두면 낡는 순간 빨강으로 선다.

픽스처는 P0 이 세운 것을 그대로 쓴다(tests/twomachine.py): 임시 디렉토리
하나에 bare origin 하나 + S9_ROOT 둘(alpha·beta), `.s9-sync` 는 remote —
git 전송층은 진짜고 흉내 내는 것은 머신 이름뿐이다. 사람이 두 번째 컴퓨터에서
할 일과 다른 것은 그 한 가지뿐이라, 여기서 초록인 절차는 두 컴퓨터에서도
같은 자리를 지난다(같다고 **증명**하지는 못한다 — 그래서 사람의 한 번이 남는다).

    실행: python3 tests/ p5_field
"""
import os
import unittest

from twomachine import S9, A_SESS, B_SESS, TwoMachine

# 사람이 쓸 이름 — alice 가 A 의 담당, bob 이 B 의 담당, carol 이 관찰 계정,
# root 는 관찰 범위를 주는 admin.
ALICE, BOB, CAROL, ROOT = "alice", "bob", "carol", "root"


def cast(fx):
    """네 계정을 세운다. admin 은 **맨 먼저** — 등록된 admin 이 하나도 없을 때만
    첫 admin 을 세울 길이 열린다(_write_gate 부트스트랩 예외)."""
    fx.cli("alpha", "user", "add", ROOT, "--role", "admin")
    fx.cli("alpha", "user", "add", ALICE, user=ROOT)
    fx.cli("alpha", "user", "add", BOB, user=ROOT)
    fx.cli("alpha", "user", "add", CAROL, "--role", "viewer", user=ROOT)
    fx.sync("alpha")
    fx.pull("beta")


# `.gitattributes` 는 리포에 실려 오고(track), 드라이버 등록은 머신마다
# `bin/s9-install` 이 한다 — 절차서가 B 에서 s9-install 을 먼저 시키는 이유다.
# 픽스처는 s9-install 을 돌리지 않으므로 그 두 줄만 여기서 세운다.
GITATTRIBUTES = ("vault/**/*.md merge=s9doc\n"
                 "users/*/profile.md merge=s9doc\n"
                 "users/*/machines.json merge=s9doc\n")


def ship_gitattributes(fx, machine):
    """리포에 실려 오는 쪽 — clone 하면 누구에게나 있다."""
    with open(os.path.join(fx.roots[machine], ".gitattributes"), "w",
              encoding="utf-8") as f:
        f.write(GITATTRIBUTES)


def register_driver(fx, machine):
    """머신마다 s9-install 이 하는 쪽 — clone 만으로는 생기지 않는다."""
    fx.git(machine, "config", "merge.s9doc.driver", f"{S9} merge-doc %O %A %B")
    fx.git(machine, "config", "merge.s9doc.name", "section9 document merge")


def unregister_driver(fx, machine):
    fx.git(machine, "config", "--unset", "merge.s9doc.driver", check=False)
    fx.git(machine, "config", "--unset", "merge.s9doc.name", check=False)


class TestS1Assign(unittest.TestCase):
    """장면 1 · 할당 — A 가 만든 일을 B 에게 넘긴다.

    A 에서:
        s9 new request --title 인계할 일 --summary s --size S --goal g \\
                       --origin human --body b
        s9 assign <id> bob --why 인계
        s9 sync
    B 에서:
        git pull --rebase   (또는 그냥 기다린다 — serve 가 60초 안에 당긴다)
        s9 ls --user bob
    """

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cast(cls.fx)
        cls.X = cls.fx.new_request("alpha", "인계할 일", sess=A_SESS, user=ALICE)

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_assign_says_who_hands_to_whom(self):
        """A 화면: 「<id>: 담당 alice → bob」 한 줄. 만든 사람은 그대로 alice 다."""
        out = self.fx.cli("alpha", "assign", self.X, BOB, "--why", "인계",
                          user=ALICE)
        self.assertIn(f"담당 {ALICE} → {BOB}", out)
        meta = self.fx.doc("alpha", self.X)[0]
        self.assertEqual(meta.get("user"), BOB, "담당이 안 옮겨졌다")
        self.assertEqual(meta.get("creator"), ALICE, "만든 사람이 함께 옮겨졌다")
        self.assertIn(f"assignee: {ALICE} -> {BOB}", self.fx.doc("alpha", self.X)[1],
                      "History 에 인계 한 줄이 없다")

    def test_card_lands_on_bob_at_beta_and_leaves_alice(self):
        """B 화면: `s9 ls --user bob` 에 그 카드가 뜨고, `--user alice` 에는 없다.
        대시보드 카드의 「담당」도 같은 행(catalog user)을 읽는다."""
        fx, X = self.fx, self.X
        fx.cli("alpha", "assign", X, BOB, "--why", "인계", user=ALICE)
        fx.sync("alpha")
        fx.pull("beta")
        self.assertIn(X, fx.cli("beta", "ls", "--user", BOB))
        self.assertNotIn(X, fx.cli("beta", "ls", "--user", ALICE))
        row = [r for r in fx.load_mod("beta").load_catalog() if r["id"] == X]
        self.assertTrue(row, f"{X} 가 beta 카탈로그에 없다")
        self.assertEqual(row[0]["user"], BOB)
        self.assertEqual(row[0]["creator"], ALICE)

    def test_neither_machine_offers_an_unstarted_card(self):
        """`s9 next` 는 **아직 아무도 착수하지 않은 카드를 권하지 않는다** —
        멈춘 in-progress 만 고른다(next_pickup→stalled_requests). 인계 직후
        B 가 볼 자리는 `s9 next` 가 아니라 `s9 ls --user bob` 이다.
        (초안이 여기서 틀렸다: "B 의 `s9 next` 가 그 문서를 권한다".)"""
        fx, X = self.fx, self.X
        fx.cli("alpha", "assign", X, BOB, "--why", "인계", user=ALICE)
        fx.sync("alpha")
        fx.pull("beta")
        self.assertNotIn(X, fx.cli("beta", "next", "--json", user=BOB))
        self.assertNotIn(X, fx.cli("alpha", "next", "--json", user=ALICE))


class TestS2TwoMachinesOnePerson(unittest.TestCase):
    """장면 2 · 두 대 — 같은 사람이 A·B 두 대에 앉는다.

    A 에서:  s9 status <id> in-progress --note 착수   (세션이 리스를 쥔다)
             s9 sync
    B 에서:  git pull --rebase
             s9 claim <id>              ← 막힌다
             s9 claim <id> --takeover   ← 이어받는다
    """

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cast(cls.fx)
        cls.Y = cls.fx.new_request("alpha", "두 대에서 볼 일", sess=A_SESS,
                                   user=ALICE)
        cls.fx.cli("alpha", "status", cls.Y, "in-progress", "--note", "착수",
                   sess=A_SESS, user=ALICE)
        cls.fx.sync("alpha")
        cls.fx.pull("beta")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_lease_travels_with_the_document(self):
        """A 가 착수하면 문서에 리스가 박히고 그것이 B 로 건너간다 —
        B 의 카드가 「alice@alpha 가 …부터 쥐고 있다」를 말할 근거다.
        세션 바인딩은 건너오지 않는다(state/ 는 track 하지 않는다)."""
        lease = self.fx.doc("beta", self.Y)[0].get("lease") or {}
        self.assertEqual(lease.get("machine"), "alpha")
        self.assertEqual(lease.get("user"), ALICE)
        self.assertEqual(lease.get("session"), A_SESS)

    def test_plain_claim_is_refused_and_names_the_way_out(self):
        """B 화면: 「◌ 리스 busy-elsewhere: alice@alpha 가 HH:MM 부터 쥐고 있다
        — 이어받으려면 `s9 claim <id> --takeover`」. 막고 끝내지 않고 다음
        손동작을 함께 말한다."""
        out = self.fx.cli("beta", "claim", self.Y, sess=B_SESS, user=ALICE)
        self.assertIn("busy-elsewhere", out)
        self.assertIn("alpha", out)
        self.assertIn("--takeover", out)
        self.assertEqual(self.fx.doc("beta", self.Y)[0]["lease"]["machine"],
                         "alpha", "막았다면서 리스가 넘어왔다")

    def test_takeover_moves_the_lease_and_leaves_a_line(self):
        """`--takeover` 뒤 리스가 beta 로 오고 History 에 이관 한 줄이 남는다.
        A 로 sync 하면 A 의 워처는 그 문서를 더 띄우지 않는다."""
        fx, Y = self.fx, self.Y
        fx.cli("beta", "claim", Y, "--takeover", sess=B_SESS, user=ALICE)
        meta, body = fx.doc("beta", Y)
        self.assertEqual(meta["lease"]["machine"], "beta")
        self.assertIn("lease: takeover", body)
        fx.sync("beta")
        fx.pull("alpha")
        fx.clear_spawn_marks("alpha")
        spawned, calls = fx.tick("alpha", grace=0)
        self.assertEqual(spawned, [],
                         f"beta 가 이어받은 {Y} 를 alpha 워처가 겹쳐 띄웠다 "
                         f"(claude argv {len(calls)}건)")


class TestS3Derived(unittest.TestCase):
    """장면 3 · 파생 — A 의 에이전트 세션이 일하다 곁가지 요청을 만든다.

    A 에서:  s9 new request --parent <id> --title 파생된 일 …
    B 에서:  git pull --rebase && s9 next / s9 reopened   ← 집지 않는다
    """

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cast(cls.fx)
        cls.X = cls.fx.new_request("alpha", "본줄기 일", sess=A_SESS, user=ALICE)
        out = cls.fx.cli("alpha", "new", "request", "--title", "파생된 일",
                         "--summary", "s", "--size", "S", "--goal", "g",
                         "--parent", cls.X, "--body", "b",
                         sess=A_SESS, user=ALICE)
        cls.Z = out.split()[0]
        cls.fx.sync("alpha")
        cls.fx.pull("beta")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def test_card_says_who_made_it_and_out_of_what(self):
        """카드가 「만든 사람 alice · 기원: <본줄기 id> 를 처리하다(lead)」를
        그릴 원재료가 문서에 있다 — origin=derived · origin_req · origin_actor."""
        meta = self.fx.doc("beta", self.Z)[0]
        self.assertEqual(meta.get("origin"), "derived")
        self.assertEqual(meta.get("origin_req"), self.X)
        self.assertEqual(meta.get("origin_actor"), "lead")
        self.assertEqual(meta.get("creator"), ALICE)
        self.assertEqual(meta.get("parent"), self.X)

    def test_beta_does_not_pick_up_the_derived_card(self):
        """B 는 그 파생 카드를 집지 않는다 — 만든 자리는 alpha 다."""
        fx, Z = self.fx, self.Z
        self.assertEqual(fx.doc("beta", Z)[0].get("machine"), "alpha")
        self.assertNotIn(Z, fx.cli("beta", "next", "--json", user=BOB))
        self.assertNotIn(Z, fx.cli("beta", "next", "--json", user=ALICE))
        self.assertNotIn(Z, fx.cli("beta", "reopened", user=BOB))


class TestS4Viewer(unittest.TestCase):
    """장면 4 · 관찰자 — 읽기만 하는 계정.

    A 에서:  s9 user add carol --role viewer
    carol 로:  s9 new / status / note / assign  ← 전부 거부
               s9 show / ls / search            ← 전부 됨
    admin 이 범위를 줄 때만 남의 문서가 화면에 보인다:
               s9 user config carol observe all
    """

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cast(cls.fx)
        cls.X = cls.fx.new_request("alpha", "관찰당할 일", sess=A_SESS, user=ALICE)

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def _denied(self, *argv):
        out = self.fx.cli("alpha", *argv, user=CAROL, check=False)
        self.assertNotEqual(self.fx.last.returncode, 0,
                            f"관찰 계정이 `s9 {' '.join(argv)}` 를 해냈다:\n{out}")
        self.assertIn("관찰 계정은 쓰지 못합니다", out)
        return out

    def test_viewer_cannot_write_documents(self):
        """만들기·전이·노트가 전부 같은 문장으로 막힌다 — 문은 write_doc 한 곳이다."""
        self._denied("new", "request", "--title", "뷰어의 일", "--summary", "s",
                     "--size", "S", "--goal", "g", "--body", "b")
        self._denied("status", self.X, "in-progress", "--note", "n")
        self._denied("note", self.X, "메모")

    def test_viewer_cannot_be_handed_a_card(self):
        """담당은 관찰 계정에 넘어가지 않는다 — 맡을 수 없는 사람에게 맡기면
        그 카드는 아무도 안 하는 카드가 된다."""
        out = self.fx.cli("alpha", "assign", self.X, CAROL, "--why", "w",
                          user=ALICE, check=False)
        self.assertNotEqual(self.fx.last.returncode, 0)
        self.assertIn("관찰 계정", out)
        self.assertEqual(self.fx.doc("alpha", self.X)[0]["user"], ALICE)

    def test_viewer_can_read(self):
        """조회·검색·이력은 전부 된다 — 막는 것은 쓰기뿐이다."""
        out = self.fx.cli("alpha", "show", self.X, user=CAROL)
        self.assertIn("관찰당할 일", out)
        self.assertIn(self.X, self.fx.cli("alpha", "ls", user=CAROL))

    def test_observe_scope_is_granted_by_admin_only(self):
        """관찰 범위는 admin 이 준다. 본인이 스스로 넓히지 못한다."""
        fx = self.fx
        out = fx.cli("alpha", "user", "config", CAROL, "observe", "all",
                     user=CAROL, check=False)
        self.assertNotEqual(fx.last.returncode, 0, "관찰 계정이 스스로 범위를 넓혔다")
        mod = fx.load_mod("alpha")
        self.assertIsNone(mod.observe_scope(CAROL))
        fx.cli("alpha", "user", "config", CAROL, "observe", "all", user=ROOT)
        mod._OBSERVE_CACHE.clear()
        self.assertEqual(mod.observe_scope(CAROL), "all")

    def test_unregistered_viewer_is_denied_on_a_shared_instance(self):
        """여럿이 쓰는 자리(remote)에서 미등록은 부트스트랩이 아니라 모르는 사람이다
        — 화면(doc_visible)이 거부로 뒤집힌다."""
        mod = self.fx.load_mod("alpha")
        row = [r for r in mod.load_catalog() if r["id"] == self.X][0]
        self.assertFalse(mod.doc_visible(row, "stranger"))
        self.assertTrue(mod.doc_visible(row, ALICE))


class TestS5SyncFailure(unittest.TestCase):
    """장면 5 · 동기화 실패 — 바깥이 끊긴 채 일해도 잃지 않는다.

    B 에서:  git remote set-url origin <틀린 주소>   (끊김을 흉내)
             s9 note <id> '끊긴 채 남긴 메모'
             s9 sync --status        ← 「대기 n건」이 선다
             git remote set-url origin <원래 주소>
             s9 sync                 ← 밀린 것이 한 번에 나간다
             s9 sync --stats         ← 단계별 건수·실패가 남는다
    """

    @classmethod
    def setUpClass(cls):
        cls.fx = TwoMachine()
        cast(cls.fx)
        cls.X = cls.fx.new_request("alpha", "끊김을 겪을 일", sess=A_SESS,
                                   user=ALICE)
        cls.fx.sync("alpha")
        cls.fx.pull("beta")

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def _cut(self):
        self.fx.git("beta", "remote", "set-url", "origin",
                    os.path.join(self.fx.tmp, "nope.git"))

    def _heal(self):
        """주소를 되돌리고 **백오프가 풀리기를 기다린다**.

        네트워크 실패 뒤 60초 동안은 `s9 sync` 조차 전송을 건너뛰고 「sync: local」
        을 낸다(_sync_net_backoff). 사람의 절차서에서는 "1분쯤 뒤 다시" 한 줄이고,
        시험에서는 그 1분을 자는 대신 시계 파일(state/.sync-fail.ts)을 지운다 —
        기다림을 흉내 내는 것이지 게이트를 끄는 것이 아니다.
        """
        self.fx.git("beta", "remote", "set-url", "origin", self.fx.origin)
        try:
            os.remove(os.path.join(self.fx.roots["beta"], "state",
                                   ".sync-fail.ts"))
        except OSError:
            pass

    def test_offline_edits_queue_and_are_visible(self):
        """끊긴 채 남긴 메모는 로컬 commit 으로 남고, 판이 「대기 n건」으로 센다.
        복구하면 한 번의 `s9 sync` 로 전부 나간다."""
        fx, X = self.fx, self.X
        self._cut()
        try:
            fx.cli("beta", "note", X, "끊긴 채 남긴 메모", user=BOB, check=False)
            st = fx.load_mod("beta").sync_status()
            self.assertGreaterEqual(st["pending"], 1, "미전송 commit 이 세어지지 않는다")
            line = fx.cli("beta", "sync", "--status")
            self.assertIn("대기 ", line)
            self.assertIn("마지막 보냄", line)
        finally:
            self._heal()
        self.assertIn("sync: ok", fx.cli("beta", "sync"))
        self.assertEqual(fx.load_mod("beta").sync_status()["pending"], 0)
        fx.pull("alpha")
        self.assertIn("끊긴 채 남긴 메모", fx.doc("alpha", X)[1],
                      "복구 뒤에도 그 메모가 A 로 건너오지 않았다")

    def test_stats_keep_the_receipts(self):
        """`s9 sync --stats` 가 단계별 건수·실패·거부율을 말한다 — 「밀렸다」를
        사람이 느낌이 아니라 수로 확인하는 자리."""
        fx = self.fx
        self._heal()
        fx.cli("beta", "note", self.X, "기록을 남길 메모", user=BOB, check=False)
        fx.cli("beta", "sync", check=False)
        out = fx.cli("beta", "sync", "--stats")
        self.assertIn("이벤트 ", out)
        self.assertTrue("push 거부율" in out or "push 기록 없음" in out)
        st = fx.load_mod("beta").sync_stats()
        self.assertIn("push", st["stages"])

    def _clash(self, doc_id, a_line, b_line):
        """A 가 먼저 적어 밀고, B 는 그것을 못 본 채 자기 줄을 적는다 —
        두 대가 같은 문서에 겹치는 장면. 반환: B 의 `s9 sync` 출력."""
        fx = self.fx
        self._heal()
        fx.sync("beta")
        fx.pull("alpha")
        fx.cli("alpha", "note", doc_id, a_line, user=ALICE, check=False)
        fx.cli("beta", "note", doc_id, b_line, user=BOB, check=False)
        fx.cli("alpha", "sync", check=False)
        return fx.cli("beta", "sync", check=False)

    def test_two_machines_editing_one_document_merge_by_meaning(self):
        """**B 가 `bin/s9-install` 을 돌린 자리**(= 절차서가 시키는 자리)에서는
        두 대의 노트가 사람 손 없이 합쳐진다 — 문서 병합 드라이버(merge=s9doc)가
        노트를 시각순으로 잇는다. 화면: `s9 sync` 가 「sync: ok」, 문서에 두 줄이
        모두 있다."""
        fx, X = self.fx, self.X
        for m in ("alpha", "beta"):
            ship_gitattributes(fx, m)
            register_driver(fx, m)
        try:
            out = self._clash(X, "A 가 같은 시각에 적은 줄", "B 가 같은 시각에 적은 줄")
            self.assertIn("sync: ok", out,
                          f"드라이버가 있는데 손이 필요했다:\n{out}")
            body = fx.doc("beta", X)[1]
            self.assertIn("A 가 같은 시각에 적은 줄", body)
            self.assertIn("B 가 같은 시각에 적은 줄", body)
            fx.pull("alpha")
            self.assertEqual(fx.head("alpha"), fx.head("beta"))
        finally:
            for m in ("alpha", "beta"):
                unregister_driver(fx, m)

    def test_skipping_s9_install_costs_a_hand_but_loses_nothing(self):
        """**B 가 `bin/s9-install` 을 건너뛰면 손이 하나 든다.**

        `.gitattributes` 는 리포에 실려 오지만 `merge.s9doc.driver` 등록은
        머신마다 s9-install 이 한다. 등록이 없으면 git 은 그 이름을 모르는 것으로
        보고 평범한 텍스트 병합으로 물러선다 — 같은 문서를 두 대가 고치면 충돌이
        서고 `s9 sync` 가 「sync: pull-conflict」를 낸다.

        그래도 **한쪽이 조용히 사라지지 않는다**: 내 줄은 로컬 commit 에 남아
        대기로 세어지고, `s9 sync resolve <id> --take mine|theirs` 가 한쪽을
        확정하되 양쪽 본을 state/sync-conflict/ 에 남긴다. 드는 손을 없애는 법은
        하나 — 그 머신에서 `bin/s9-install` 을 돌린다(위 시험이 그 자리다)."""
        fx, X = self.fx, self.X
        for m in ("alpha", "beta"):
            ship_gitattributes(fx, m)      # clone 하면 있다
            unregister_driver(fx, m)       # s9-install 을 건너뛴 자리
        out = self._clash(X, "A 가 드라이버 없이 적은 줄", "B 가 드라이버 없이 적은 줄")
        self.assertIn("conflict", out, f"충돌이 서지 않았다: {out}")
        mod = fx.load_mod("beta")
        self.assertGreaterEqual(mod.sync_status()["pending"], 1,
                                "막혔는데 내 commit 이 대기로 세어지지 않는다")
        self.assertIn("B 가 드라이버 없이 적은 줄", fx.doc("beta", X)[1],
                      "막히면서 내 줄이 사라졌다")
        res = mod.sync_resolve([X], "mine")
        self.assertTrue(res.get("ok"), res)
        self.assertIn(X, res["resolved"])
        self.assertEqual({os.path.basename(p) for p in res["saved"]},
                         {f"{X}.mine.md", f"{X}.theirs.md"}, "진 쪽 본이 남지 않았다")
        with open([p for p in res["saved"] if p.endswith("theirs.md")][0],
                  encoding="utf-8") as f:
            self.assertIn("A 가 드라이버 없이 적은 줄", f.read())


if __name__ == "__main__":
    unittest.main()
