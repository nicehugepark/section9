"""새 요청은 parent 나 root 를 갖는다 (REQ-20260909-073).

주인 2026-09-09: 「명백하게 children 문서인데 parent 가 없거나 parent 인데 children 이
없는 문서들이 꽤 많다 … 재발되지 않게 근원을 해결해」. 프론트매터 parent↔children
은 양방향으로 맞았지만(불일치 0), **뜻으로는** 자식인데 parent 없는 요청이 9월에만
204건이었다. 2026-09-09 까지의 것은 backfill 로 채우는 중이라, 강제는 다음 날부터다:
created >= 2026-09-10 인 요청은 parent 또는 root 가 있어야 한다(cancelled 제외).
이 vault 를 그대로 걷는다(test_no_projectless 와 같은 꼴). 걸리면 `s9 link <id>
--parent <REQ>` 나 `s9 set <id> --root` 로 고친다 — 시험을 늦추는 것이 아니다.

실행: python3 tests/ no_orphan_requests
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENFORCE_FROM = "2026-09-10"


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
                if fm_field(fm, "status") == "cancelled":
                    continue
                if fm_field(fm, "parent") or fm_field(fm, "root").lower() in ("true", "1", "yes"):
                    continue
                bare.append(fm_field(fm, "id") or os.path.relpath(os.path.join(dp, fn), ROOT))
        self.assertEqual(bare, [], "parent 도 root 도 없는 요청 (REQ-20260909-073) — "
                         "`s9 link <id> --parent <REQ>` 또는 `s9 set <id> --root`: "
                         + ", ".join(bare[:10]))


if __name__ == "__main__":
    unittest.main()
