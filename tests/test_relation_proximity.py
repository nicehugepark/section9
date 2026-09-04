"""가까운 시각이 연관으로 기록되는가 (REQ-20260826-040-62x6).

사용자 지적: "038 요청의 연관성 요청으로 037이 등록되어있는데 무슨 연관성이
있는거지?? 전혀 관계없는것같은데."

맞다. 23:18 "문서가 낡았다"(037)와 23:23 "응답 시각이 부정확하다"(038)는 서로
아무 관계가 없다. 둘을 묶은 것은 **5분**뿐이었다 — chat_audit 이 직전 15분 안의
채팅이 만든 REQ 를 전부 relates 로 걸고 있었다.

원래 의도(REQ-20260825-059)는 다른 것이었다: 아직 문서가 없는 선행 대화가
맥락 없이 유실되는 것을 막는 것. 그건 이미 **body 에 통째로 접어 넣는 것**으로
해결돼 있다 — 그건 링크가 아니라 본문이라 따로 걸 것이 없다.

없는 관계를 보는 쪽이 있는 관계를 못 보는 것보다 나쁘다. 그래프가 거짓말을
하기 시작하면 그래프를 보는 이유가 없어진다.

실행: python3 tests/ relation_proximity
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class RelationProximity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9rel-")
        cls._prev = {k: os.environ.get(k)
                     for k in ("S9_ROOT", "S9_MACHINE", "S9_USER",
                               "S9_SESSION", "S9_REWORK_WATCH")}
        os.environ["S9_ROOT"] = cls.tmp
        os.environ["S9_MACHINE"] = "testbox"
        os.environ["S9_USER"] = "tester"
        os.environ["S9_REWORK_WATCH"] = "off"
        os.environ.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "tester")
        cls.s9 = _load("s9relmod", S9)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    @classmethod
    def cli(cls, *args):
        return subprocess.run([S9, *args], capture_output=True, text=True,
                              timeout=20, stdin=subprocess.DEVNULL)

    def relates(self, doc_id):
        out = self.cli("show", doc_id, "--meta").stdout
        for line in out.splitlines():
            if line.startswith("relates:"):
                return json.loads(line.split(":", 1)[1].strip())
        return []

    def test_relation_proximity(self):
        """RelationProximity 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("p1_unrelated_messages_are_not_linked"):
            a = self.s9.chat_audit(
                "대시보드 문서의 첫 줄이 낡았다. 읽기 전용이 아닌데 그렇게 적혀 "
                "있으니 지금 상태에 맞게 고쳐라.", "tester", "relsess")
            b = self.s9.chat_audit(
                "응답 머리에 찍히는 시각이 추정값이면 안 된다. 반드시 실제 시각이 "
                "찍히도록 고쳐라.", "tester", "relsess")
            self.assertTrue(a and b and a != b, (a, b))
            self.assertNotIn(b, self.relates(a), f"{a} 가 무관한 {b} 와 묶였다")
            self.assertNotIn(a, self.relates(b), f"{b} 가 무관한 {a} 와 묶였다")
        with self.subTest("p2_named_review_doc_is_still_linked"):
            target = self.cli(
                "new", "request", "--title", "확인 대상", "--summary", "t",
                "--goal", "t", "--size", "S", "--user", "tester",
                "--body", "x").stdout.split()[0]
            self.cli("status", target, "in-progress", "--note", "t")
            self.cli("status", target, "review", "--note", "t", "--force")
            # 짧은 메타 지시("반려해")는 분류상 문서를 만들지 않는다 — 여기서
            # 보려는 것은 그 경로가 아니라 '이름이 불린 문서가 묶이는가' 이므로
            # 요청으로 분류되기에 충분한 길이의 실제 지적문을 쓴다.
            msg = (f"{target} 화면에서 버튼을 눌러도 아무 반응이 없다. 콘솔에도 "
                   f"오류가 안 뜨는데 상태가 그대로다. 어디서 끊기는지 확인해서 "
                   f"눌리면 실제로 전이되도록 고쳐 달라.")
            doc = self.s9.chat_audit(msg, "tester", "relsess")
            self.assertTrue(doc, doc)
            self.assertIn(target, self.relates(doc),
                          "이름으로 지목한 판정 대기 문서가 안 묶였다")
        with self.subTest("p3_unrelate_removes_both_sides"):
            def mk(title):
                return self.cli("new", "request", "--title", title, "--summary",
                                "t", "--goal", "t", "--size", "S", "--user",
                                "tester", "--body", "x").stdout.split()[0]
            x, y = mk("한쪽"), mk("다른쪽")
            self.cli("link", x, "--relates", y, "--why", "거두기 검사용 픽스처")
            self.assertIn(y, self.relates(x))
            self.assertIn(x, self.relates(y))
            self.cli("link", x, "--unrelate", y)
            self.assertNotIn(y, self.relates(x))
            self.assertNotIn(x, self.relates(y), "반대편에 유령 관계가 남았다")
        with self.subTest("p4_backfill_prunes_only_proximity_edges"):
            a = self.s9.chat_audit(
                "보드 카드의 글자 크기가 너무 작아서 훑기가 어렵다. 한 단계 키우고 "
                "줄간격도 함께 손봐 달라.", "tester", "backfillsess")
            b = self.s9.chat_audit(
                "검색창에 한글을 넣으면 첫 글자가 씹힌다. 입력 조합 중에 필터가 "
                "도는 것 같으니 확인해서 고쳐 달라.", "tester", "backfillsess")
            self.assertTrue(a and b and a != b, (a, b))
            # 자동 연결이 걸던 그 간선을 손으로 재현한다 (지금 코드는 안 건다)
            self.cli("link", a, "--relates", b, "--why", "근접 백필 검사용 픽스처")
            self.assertIn(b, self.relates(a))

            # 손으로 건 연관(본문이 서로를 부르는 쪽)은 살아남아야 한다
            keep = self.cli("new", "request", "--title", "언급되는쪽", "--summary",
                            "t", "--goal", "t", "--size", "S", "--user", "tester",
                            "--body", "x").stdout.split()[0]
            self.cli("link", a, "--relates", keep, "--why", "남아야 하는 간선")

            hits = self.s9.proximity_relates(fix=True)
            pairs = {tuple(sorted((x, y))) for x, y, _ in hits}
            self.assertIn(tuple(sorted((a, b))), pairs,
                          f"근접 간선을 못 찾았다: {hits}")
            self.assertNotIn(b, self.relates(a), "거두고도 남아 있다")
            self.assertNotIn(a, self.relates(b), "반대편에 유령 관계가 남았다")
            self.assertIn(keep, self.relates(a),
                          "손으로 건 연관까지 지웠다 — 고침이 새 손실이 된다")

if __name__ == "__main__":
    unittest.main()
