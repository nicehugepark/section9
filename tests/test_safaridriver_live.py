"""실제 safaridriver 를 띄우고 거둬 본다 — 맥에서만 (REQ-20260916-019-2n7g).

test_safaridriver.py 는 판정 논리를 가짜 프로세스 표 위에서 잰다. 그 시험이 전부
통과해도 **실제로 띄우지 못하면 아무 값도 없다**: `ps` 의 나이 꼴이 이 맥에서
다를 수 있고(etimes 를 안 주는 판이 있다), 프로세스 표에서 실행 파일 이름을
읽는 자리도 실물로만 확인된다. 그래서 여기서 한 바퀴를 실제로 돈다 —
띄우고 · 목록에서 찾고 · 나이를 재고 · 거둔다.

`safaridriver -p <포트>` 는 **WebDriver 세션을 만들기 전까지 Safari 를 열지
않는다** — 이 시험은 창을 띄우지 않고 서버 프로세스만 오간다.

맥이 아니면 통째로 건너뛴다. 실행: python3 tests/ safaridriver_live
"""
import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import time
import unittest

import portpool

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load():
    spec = importlib.util.spec_from_loader(
        "s9_sdlive", importlib.machinery.SourceFileLoader("s9_sdlive", S9))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(sys.platform == "darwin", "safaridriver 는 맥에만 있다")
@unittest.skipUnless(shutil.which("safaridriver"), "이 맥에 safaridriver 가 없다")
class SafariDriverLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def setUp(self):
        # 기록만 임시 자리로 돌린다 — 프로세스 표는 진짜를 본다.
        self.tmp = tempfile.mkdtemp(prefix="s9-sdlive-")
        self._root, self.m.ROOT = self.m.ROOT, self.tmp
        self.pid = 0

    def tearDown(self):
        if self.pid:
            self.m._sd_kill(self.pid)
        self.m.ROOT = self._root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _free_port(self):
        """포트는 **스위트의 풀**에서 받는다 (portpool, REQ-20260825-100).

        손으로 고른 대역을 쓰면 샤드 둘이 같은 번호를 집어 간헐 실패가 된다 —
        `tests/test_port_pool.py` 가 그 규율을 파일 단위로 지킨다."""
        return portpool.free_port()

    def test_z1_spawn_list_age_and_reap(self):
        """정상 — 실제로 한 바퀴: 띄우고, 목록에서 찾고, 나이를 재고, 거둔다."""
        m = self.m
        port = self._free_port()
        self.pid = m._sd_spawn(port)
        self.assertTrue(self.pid, "safaridriver 를 띄우지 못했다")
        self.assertTrue(m._sd_ready(port),
                        "safaridriver 가 GET /status 로 답하지 않는다 — "
                        "Safari ▸ 설정 ▸ 고급 ▸ 개발자용의 「Allow Remote "
                        "Automation」이 꺼져 있을 수 있다")

        # 실제 프로세스 표에서 이 드라이버를 포트째로 찾아낸다.
        procs = m._sd_processes()
        self.assertIn(self.pid, procs, f"프로세스 표에 pid {self.pid} 가 없다")
        self.assertEqual(procs[self.pid], port)

        # 나이 — 이 맥의 ps 가 주는 꼴이 무엇이든 초로 읽힌다.
        time.sleep(1.2)
        age = m._sd_age(self.pid)
        self.assertGreaterEqual(age, 1, "나이를 못 쟀다 — --stale 의 하한이 무력해진다")
        self.assertLess(age, 600)

        # 주인을 적으면 이 세션 것으로 읽힌다.
        m._sd_write_reg({"port": port, "pid": self.pid, "session": "livetest",
                         "machine": m.current_machine(), "req": "",
                         "started": m.now_iso()})
        row = next(r for r in m._sd_rows("livetest") if r["pid"] == self.pid)
        self.assertEqual(row["verdict"], m.SD_MINE)
        self.assertEqual(row["port"], port)

        # 거둔다 — 프로세스도 기록도 남지 않는다.
        self.assertTrue(m._sd_kill(self.pid), "거두지 못했다")
        self.assertFalse(m.pid_alive(self.pid))
        self.assertFalse(m._sd_port_busy(port))
        m._sd_drop_reg(port)
        self.assertFalse(os.path.exists(m._sd_reg_path(port)))
        self.pid = 0


if __name__ == "__main__":
    unittest.main(verbosity=2)
