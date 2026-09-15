"""새 요청은 parent 나 root 를 갖는다 (REQ-20260909-073).

주인 2026-09-09: 「명백하게 children 문서인데 parent 가 없거나 parent 인데 children 이
없는 문서들이 꽤 많다 … 재발되지 않게 근원을 해결해」. 프론트매터 parent↔children
은 양방향으로 맞았지만(불일치 0), **뜻으로는** 자식인데 parent 없는 요청이 9월에만
204건이었다. 2026-09-09 까지의 것은 backfill 로 채우는 중이라, 강제는 다음 날부터다:
created >= 2026-09-10 인 요청은 parent 또는 root 가 있어야 한다(cancelled 제외).
이 vault 를 그대로 걷는다(test_no_projectless 와 같은 꼴). 걸리면 `s9 link <id>
--parent <REQ>` 나 `s9 set <id> --root` 로 고친다 — 시험을 늦추는 것이 아니다.

**판정은 제 것을 짓지 않고 `bin/s9.py` 의 `_parentless_row` 를 부른다**
(REQ-20260916-002, 실제 사고 2026-09-16): 전에는 이 시험이 제 판정을 다시 짰고,
그 사이 `_parentless_row` 는 `origin == "human"` 만 세고 있었다. 그래서 무인
작업자가 세운 parent 없는 요청 하나가 **이 시험을 실패시키면서 화면의 어느
목록에도 안 떴다** — 두 목록의 교집합이 0이었다. 판정이 둘이면 사람은 아무
목록도 믿지 않는다. 시행일도 그쪽의 `PARENT_ENFORCE_FROM` 을 읽는다.

실행: python3 tests/ no_orphan_requests
"""
import importlib.machinery
import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _s9():
    path = os.path.join(ROOT, "bin", "s9.py")
    spec = importlib.util.spec_from_loader(
        "s9_orphan", importlib.machinery.SourceFileLoader("s9_orphan", path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S9 = _s9()
ENFORCE_FROM = S9.PARENT_ENFORCE_FROM


def fm_field(fm, key):
    mm = re.search(r"^%s:\s*(.*)$" % key, fm, re.M)
    return (mm.group(1).strip().strip('"\'') if mm else "")


class EveryNewRequestHasAParentOrIsARoot(unittest.TestCase):

    def test_o1_requests_created_from_enforce_date_have_parent_or_root(self):
        bare = []
        base = os.path.join(ROOT, "vault", "requests")
        for dp, _dn, fns in os.walk(base):
            if ".trash" in dp:
                continue
            for fn in fns:
                if not fn.endswith(".md"):
                    continue
                with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                    head = f.read()
                if not head.startswith("---"):
                    continue
                fm = head.split("\n---", 1)[0]
                if fm_field(fm, "type") != "request":
                    continue
                if fm_field(fm, "created")[:10] < ENFORCE_FROM:
                    continue
                row = {"type": "request",
                       "status": fm_field(fm, "status"),
                       "parent": fm_field(fm, "parent"),
                       "root": fm_field(fm, "root").lower() in ("true", "1", "yes")}
                if not S9._parentless_row(row):
                    continue
                bare.append(fm_field(fm, "id") or os.path.relpath(os.path.join(dp, fn), ROOT))
        self.assertEqual(bare, [], "parent 도 root 도 없는 요청 (REQ-20260909-073) — "
                         "`s9 link <id> --parent <REQ>` 또는 `s9 set <id> --root`: "
                         + ", ".join(bare[:10]))


class TheJudgmentIsOne(unittest.TestCase):
    """짚는 목록과 막는 시험이 **같은 판정**을 읽는다 (REQ-20260916-002)."""

    def row(self, **kw):
        r = {"type": "request", "status": "done", "parent": "", "root": False}
        r.update(kw)
        return r

    # 실패 — 입구로 가르지 않는다 (2026-09-16 그 자리)
    def test_an_agent_made_orphan_counts_too(self):
        self.assertTrue(S9._parentless_row(
            self.row(origin="derived", origin_actor="worker:auto-resume",
                     origin_req="REQ-20260916-019-2n7g")),
            "무인 작업자가 세운 parent 없는 요청을 안 센다 — 시험만 실패하고 "
            "화면의 어느 목록에도 안 뜨던 그 자리")

    def test_a_human_made_orphan_still_counts(self):
        self.assertTrue(S9._parentless_row(self.row(origin="human")))

    # 정상 — parent 나 root 가 있으면 결함이 아니다
    def test_a_request_with_a_parent_is_not_an_orphan(self):
        self.assertFalse(S9._parentless_row(self.row(parent="REQ-1")))

    def test_a_root_request_is_not_an_orphan(self):
        self.assertFalse(S9._parentless_row(self.row(root=True)))

    # 경계 — 취소된 것과 요청이 아닌 것은 세지 않는다
    def test_cancelled_and_non_requests_are_skipped(self):
        self.assertFalse(S9._parentless_row(self.row(status="cancelled")))
        self.assertFalse(S9._parentless_row(self.row(type="knowledge")))


if __name__ == "__main__":
    unittest.main()
