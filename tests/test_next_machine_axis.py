"""`s9 next` 도 담당 컴퓨터를 본다 (REQ-20260915-011-2n7g).

실측 2026-09-15 22:51: 맥의 세션 기동에서 `s9 next` 가 DESKTOP-1A2B3C 에 묶인
요청을 「이어받기」로 권했다. 그 자리(`next_pickup`)가 보던 것은 담당자와 문서
리스뿐이었는데, 리스는 CLAIM_GRACE(30분)가 지나면 저절로 풀린다 — 저쪽 세션이
30분 조용하기만 하면 남의 컴퓨터의 일이 이 컴퓨터의 후보로 올라왔다. 기동
프롬프트는 그 줄을 보고 claim 하라고 지시하므로, 문서를 열어 보지 않았다면 두
컴퓨터가 같은 요청을 잡는다(2026-09-11 과 같은 사고).

같은 판정을 하는 다른 두 자리(`here_requests`·무인 스폰 검사)는 이미 이 축을
갖고 있었다. 여기서 고정하는 것은 **셋이 한 술어를 쓴다**는 것이다.

실행: python3 tests/ next_machine_axis
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def load_s9():
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = os.path.abspath(os.path.join(HERE, ".."))
    try:
        spec = importlib.util.spec_from_loader(
            "s9axis", importlib.machinery.SourceFileLoader("s9axis", S9))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


MAC, OTHER = "MAC-A", "DESKTOP-B"


def req(rid, **kw):
    r = {"id": rid, "type": "request", "status": "in-progress",
         "title": rid, "user": "alice", "machine": MAC,
         "needs_machine": "", "needs_os": "", "priority": 50,
         "updated": "2026-09-15T22:00:00+09:00",
         "created": "2026-09-15T21:00:00+09:00", "tags": []}
    r.update(kw)
    return r


class MachineAxisPredicate(unittest.TestCase):
    """술어 하나 — 담당자는 보지 않고 컴퓨터·판만 본다."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()

    def test_1_needs_machine_here_passes(self):
        """1. 담당 컴퓨터가 이 컴퓨터면 지나간다."""
        self.assertTrue(self.m.machine_axis_ok(
            req("R1", needs_machine=MAC), MAC, "macOS"))

    def test_2_no_pin_passes(self):
        """2. 담당 컴퓨터가 비어 있으면(어느 컴퓨터에서나) 지나간다."""
        self.assertTrue(self.m.machine_axis_ok(req("R2"), MAC, "macOS"))

    def test_3_needs_os_match_passes(self):
        """3. needs_os 가 이 판이면 지나간다."""
        self.assertTrue(self.m.machine_axis_ok(
            req("R3", needs_os="macOS"), MAC, "macOS"))

    def test_4_needs_machine_elsewhere_blocked(self):
        """4. 담당 컴퓨터가 다른 컴퓨터면 막는다 — 이번 사고의 자리."""
        self.assertFalse(self.m.machine_axis_ok(
            req("R4", needs_machine=OTHER), MAC, "macOS"))

    def test_5_needs_os_mismatch_blocked(self):
        """5. needs_os 가 다른 판이면 막는다."""
        self.assertFalse(self.m.machine_axis_ok(
            req("R5", needs_os="Windows"), MAC, "macOS"))

    def test_5b_pin_beats_os(self):
        """담당 컴퓨터가 적혀 있으면 needs_os 는 보지 않는다 (here_requests 와 같은 순서)."""
        self.assertTrue(self.m.machine_axis_ok(
            req("R5b", needs_machine=MAC, needs_os="Windows"), MAC, "macOS"))


class NextPickupUsesTheAxis(unittest.TestCase):
    """next_pickup 이 그 술어를 지난다 — 이 파일이 세우려는 계약."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()

    def pickup(self, catalog, incoming=(), all_users=False):
        m = self.m
        keep = {k: getattr(m, k) for k in
                ("stalled_requests", "rework_claimed", "handoff_rows",
                 "_mine_rows", "load_catalog", "current_machine",
                 "os_platform", "locate", "local_facts")}
        stall = [{"id": c["id"], "title": c["title"], "user": c["user"],
                  "machine": c["machine"], "assignee": "", "mins": 40,
                  "state": "stalled", "why": "", "reason": ""}
                 for c in catalog]
        try:
            m.stalled_requests = lambda win=None, states=("stalled",): list(stall)
            m.rework_claimed = lambda rid, win=120: False
            m.handoff_rows = lambda local=None, session=None: {
                "incoming": [dict(r) for r in incoming], "outgoing": []}
            m._mine_rows = lambda rows, local=None, want="list", lease_gate=True: rows
            m.load_catalog = lambda *a, **k: [dict(c) for c in catalog]
            m.current_machine = lambda: MAC
            m.os_platform = lambda: "macOS"
            m.locate = lambda rid, *a, **k: None
            m.local_facts = lambda *a, **k: {"user": "alice", "machine": MAC,
                                             "role": "member"}
            got = m.next_pickup(all_users=all_users)
        finally:
            for k, v in keep.items():
                setattr(m, k, v)
        return (got or {}).get("id")

    def test_4_elsewhere_not_offered(self):
        """4. 담당 컴퓨터가 다른 컴퓨터인 멈춘 요청은 리스가 만료됐어도 후보가 아니다."""
        self.assertIsNone(self.pickup([req("R-ELSE", needs_machine=OTHER)]))

    def test_1_here_offered(self):
        """1. 담당 컴퓨터가 이 컴퓨터면 종전대로 낸다."""
        self.assertEqual(self.pickup([req("R-HERE", needs_machine=MAC)]),
                         "R-HERE")

    def test_2_unpinned_offered(self):
        """2. 못이 안 박힌 것도 종전대로 낸다."""
        self.assertEqual(self.pickup([req("R-FREE")]), "R-FREE")

    def test_5_os_mismatch_not_offered(self):
        """5. needs_os 가 다른 판이면 후보가 아니다."""
        self.assertIsNone(self.pickup([req("R-WIN", needs_os="Windows")]))

    def test_6_all_users_still_gated(self):
        """6. `--all`(남의 것까지)에서도 담당 컴퓨터 축은 그대로 선다."""
        self.assertIsNone(self.pickup([req("R-ELSE2", user="bob",
                                           needs_machine=OTHER)],
                                      all_users=True))

    def test_7_handoff_passes_the_pin(self):
        """7. 이관으로 이 컴퓨터에 온 것은 담당 컴퓨터가 달라도 낸다 — 사람이 누른 자리다."""
        c = req("R-MOVED", needs_machine=OTHER)
        inc = [{"id": c["id"], "title": c["title"], "user": c["user"],
                "machine": c["machine"], "assignee": "", "mins": 0,
                "state": "handoff", "why": "", "reason": "이 컴퓨터로 옮겨짐"}]
        self.assertEqual(self.pickup([c], incoming=inc), "R-MOVED")

    def test_pick_order_keeps_the_allowed_one(self):
        """막힌 것이 먼저 와도 허용된 것이 후보로 남는다 — 거르고 고른다."""
        self.assertEqual(
            self.pickup([req("R-ELSE3", needs_machine=OTHER, priority=90),
                         req("R-OK", priority=50)]),
            "R-OK")


class HereRequestsUnchanged(unittest.TestCase):
    """9. here_requests 의 세 갈래가 종전 그대로 — 담당자 검사 포함."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_s9()

    def here(self, rows):
        return [r["id"] for r in self.m.here_requests(
            platform="macOS", rows=rows, machine=MAC, user="alice")]

    def test_pinned_here_and_mine(self):
        self.assertEqual(self.here([req("H1", needs_machine=MAC)]), ["H1"])

    def test_pinned_here_but_not_mine(self):
        """담당 컴퓨터가 맞아도 담당자가 다르면 안 낸다."""
        self.assertEqual(self.here([req("H2", needs_machine=MAC,
                                        user="bob")]), [])

    def test_pinned_elsewhere(self):
        self.assertEqual(self.here([req("H3", needs_machine=OTHER)]), [])

    def test_needs_os_ignores_owner(self):
        """needs_os 갈래는 담당자를 보지 않는다 — 「이 판이면 아무나」인 옛 축."""
        self.assertEqual(self.here([req("H4", needs_os="macOS",
                                        user="bob")]), ["H4"])

    def test_needs_os_mismatch(self):
        self.assertEqual(self.here([req("H5", needs_os="Windows")]), [])

    def test_unpinned_needs_owner(self):
        self.assertEqual(self.here([req("H6"), req("H7", user="bob")]), ["H6"])


if __name__ == "__main__":
    unittest.main()
