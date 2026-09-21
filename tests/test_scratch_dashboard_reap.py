"""임시 작업 자리의 대시보드는 거둔다 (REQ-20260921-023-62x6).

주인 물음 2026-09-21: 「대시보드 포트가 9909에서 왜 자꾸 증가하는거야」.

실측: 9909 는 비어 있는데 9910~9913 을 임시 작업 자리 셋(scratchpad/ident-v2 ·
final-check · umbrella)과 형제 폴더의 클론 하나가 잡고 있었다. 코드를 풀어
확인하는 자리에서 `s9 code` 를 돌리면 감시자까지 서고, 그 자리를 버려도 감시자는
남는다 — 회수는 시험 포트 구간(18800~18863)만 보므로 9910~9949 의 임시
대시보드는 아무도 거두지 않았다. 본 저장소는 다시 뜰 때마다 빈 포트를 찾아 한
칸씩 올라갔다.

가르는 선이 이 파일의 전부다: **scratchpad/ 아래는 버리는 자리, 그 밖은 남의
작업 자리.** 남의 것을 거두면 그 사람의 화면이 말없이 꺼진다.

실행: python3 tests/ scratch_dashboard_reap
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROOT = "/repo"


def _doctor():
    loader = importlib.machinery.SourceFileLoader(
        "s9doctor_reap", os.path.join(REPO, "bin", "s9-doctor"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def row(pid, cmd, age=9999, ppid=1):
    return (pid, ppid, age, cmd)


def serve(path, port=9911):
    return f"/usr/bin/python3 {path}/bin/s9 serve --host 127.0.0.1 --port {port}"


class ScratchDashboardsAreReaped(unittest.TestCase):
    def setUp(self):
        self.m = _doctor()

    def found(self, rows, **kw):
        return [ws for _pid, _age, ws in
                self.m.scratch_dashboards(rows, root=ROOT, **kw)]

    # ── 정상 ───────────────────────────────────────────────────────────
    def test_n1_a_scratchpad_dashboard_is_found(self):
        """scratchpad/<이름> 에서 도는 대시보드는 거둘 것으로 잡힌다."""
        rows = [row(11, serve(ROOT + "/scratchpad/ident-v2"))]
        self.assertEqual(self.found(rows), [ROOT + "/scratchpad/ident-v2"])

    def test_n2_the_supervisor_counts_too(self):
        """감시자도 같은 자리의 같은 물건이다 — pid 하나만 내리면 되살아난다."""
        rows = [row(11, f"/usr/bin/python3 {ROOT}/scratchpad/umbrella/bin/s9"
                        " serve --supervise --port-auto --port 9912")]
        self.assertEqual(self.found(rows), [ROOT + "/scratchpad/umbrella"])

    # ── 경계 ───────────────────────────────────────────────────────────
    def test_b1_the_main_repos_dashboard_is_left_alone(self):
        """본 저장소의 대시보드는 사람이 보고 있는 화면이다."""
        self.assertEqual(self.found([row(11, serve(ROOT, 9909))]), [])

    def test_b2_a_sibling_clone_is_left_alone(self):
        """형제 폴더의 클론은 남의 작업 자리다 — 이 저장소가 흘린 것이 아니다."""
        rows = [row(11, serve("/home/x/section9-cloit", 9913)),
                row(12, serve(ROOT + "-other/scratchpad/a", 9914))]
        self.assertEqual(self.found(rows), [])

    def test_b3_a_fresh_one_is_left_alone(self):
        """갓 뜬 것은 지금 확인 중일 수 있다 — 끊으면 그 확인이 거짓으로 끝난다."""
        rows = [row(11, serve(ROOT + "/scratchpad/now"), age=10)]
        self.assertEqual(self.found(rows), [])
        self.assertEqual(self.found(rows, older_than=1),
                         [ROOT + "/scratchpad/now"])

    def test_b4_a_non_serve_process_there_is_left_alone(self):
        """그 자리의 다른 명령은 대시보드가 아니다."""
        rows = [row(11, f"/usr/bin/python3 {ROOT}/scratchpad/a/bin/s9 shot x")]
        self.assertEqual(self.found(rows), [])

    # ── 회귀 ───────────────────────────────────────────────────────────
    def test_r1_the_test_pool_orphan_rule_is_unchanged(self):
        """시험 포트 구간의 고아 판정은 그대로다 — 이 조항이 덮지 않는다."""
        cmd = f"/usr/bin/python3 /tmp/s9run-1-x/bin/s9 serve --port {self.m.POOL_LO}"
        _serves, orphans, _ch = self.m.scan([row(11, cmd, ppid=1)], live_runs=[])
        self.assertEqual([p for p, _a, _c in orphans], [11])


if __name__ == "__main__":
    unittest.main()
