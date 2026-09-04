"""uid 발번 체계 테스트 (REQ-20260825-031 — REQ-006 D-정밀판 승인 구현).

uid = PREFIX-YYYYMMDD-NNN-<머신지문4>: 순번은 머신 로컬, 지문이 달라 통신
없이 전역 유일. 짧은 지칭은 prefix resolve(유일할 때만), rm은 tombstone.

격리: S9_ROOT=mktemp. 실행: python3 tests/ uid
"""
import glob
import json
import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class TestUid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9uid-")
        cls.base = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                    "S9_USER": "tester"}
        cls.base.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")

    @classmethod
    def cli(cls, *argv, origin=None, expect=0):
        env = dict(cls.base)
        if origin:
            env["S9_ORIGIN"] = origin
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=env, timeout=15, stdin=subprocess.DEVNULL)
        if expect is not None and r.returncode != expect:
            raise AssertionError(f"s9 {' '.join(argv)}: rc={r.returncode}\n"
                                 f"{r.stdout}{r.stderr}")
        return r

    def new_req(self, title, origin):
        r = self.cli("new", "request", "--title", title, "--summary", "s",
                     "--size", "S", "--body", "b", origin=origin)
        return r.stdout.split()[0]

    # U1. uid 형식: PREFIX-YYYYMMDD-NNN-<지문4>
    def test_test_uid(self):
        """TestUid 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("u1_uid_format"):
                rid = self.new_req("형식 검증", "aaaa")
                self.assertRegex(rid, r"^REQ-\d{8}-\d{3}-aaaa$")

            # U2. 두 머신(지문 상이)이 같은 날 발번 — 순번이 겹쳐도 별개 uid로 공존
        with self.subTest("u2_two_machines_coexist"):
                a = self.new_req("머신A 문서", "m1m1")
                b = self.new_req("머신B 문서", "m2m2")
                na = re.search(r"-(\d{3})-m1m1$", a).group(1)
                nb = re.search(r"-(\d{3})-m2m2$", b).group(1)
                self.assertEqual(na, nb)                 # 각자 로컬 순번 — 같은 NNN
                files = glob.glob(os.path.join(self.tmp, "vault", "requests", "**",
                                               f"REQ-*-{na}-*.md"), recursive=True)
                self.assertGreaterEqual(len(files), 2)   # 파일 충돌 없이 둘 다 존재

            # U3. 짧은 지칭 resolve: 유일 순번이면 show 성공, 겹친 순번(001)은
            #     후보 나열 실패. (모든 지문의 첫 문서가 001이라 001은 항상 모호 —
            #     u1/u2가 만든 상태를 그대로 이용한다)
        with self.subTest("u3_short_resolve"):
                first = self.new_req("solo 1호", "solo")      # 001-solo (모호 대상)
                second = self.new_req("solo 2호", "solo")     # 002-solo — 이 시점 유일
                short = second.rsplit("-", 1)[0]
                r = self.cli("show", short, "--meta")
                self.assertIn(second, r.stdout)
                amb = first.rsplit("-", 1)[0]                 # …-001: aaaa·m1m1 등과 겹침
                r = self.cli("show", amb, expect=None)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("모호", r.stdout + r.stderr)
                self.assertIn("-solo", r.stdout + r.stderr)   # 후보에 지문 노출

            # U4. normalize: note 속 지문 없는 date형 지칭이 유일 후보면 uid로 확장
            #     (norm 지문으로 003까지 만들어 이 스위트에서 003이 유일하게 한다)
        with self.subTest("u4_note_normalizes_to_uid"):
                self.new_req("정규화 채움1", "norm")           # 001-norm
                self.new_req("정규화 채움2", "norm")           # 002-norm (002-solo와 겹침)
                rid = self.new_req("정규화 대상", "norm")      # 003-norm — 유일 순번
                short = rid.rsplit("-", 1)[0]
                self.cli("note", rid, f"관련: {short} 참조", "--label", "x",
                         origin="norm")
                p = glob.glob(os.path.join(self.tmp, "vault", "requests", "**",
                                           rid + ".md"), recursive=True)[0]
                with open(p, encoding="utf-8") as f:
                    self.assertIn(f"관련: {rid} 참조", f.read())

            # U5. rm tombstone: .trash 이동·카탈로그 제외·번호 재발급 금지
        with self.subTest("u5_rm_tombstone_no_reissue"):
            rid = self.new_req("삭제될 문서", "tomb")
            num = int(re.search(r"-(\d{3})-tomb$", rid).group(1))
            self.cli("rm", rid, "--reason", "test", origin="tomb")
            # 파일은 .trash로 이동
            trashed = glob.glob(os.path.join(self.tmp, "vault", "requests", "**",
                                             ".trash", rid + ".md"),
                                recursive=True)
            self.assertEqual(len(trashed), 1)
            # 카탈로그에서는 제외
            with open(os.path.join(self.tmp, "index", "catalog.jsonl"),
                      encoding="utf-8") as f:
                self.assertNotIn(rid, f.read())
            # 다음 발번은 삭제 번호를 건너뛴다 (재발번 사고 방지)
            nxt = self.new_req("후속 문서", "tomb")
            self.assertEqual(int(re.search(r"-(\d{3})-tomb$", nxt).group(1)),
                             num + 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
