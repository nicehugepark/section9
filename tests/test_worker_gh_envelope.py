"""무인 작업자에게 gh 를 주는 스위치 (REQ-20260827-076-62x6).

사용자: "이 자동 세션에 gh 를 허용을 어떻게 하는거야? 그냥 해"

무인 작업자의 봉투는 기본이 **읽기 + s9** 다(DOC-20260823-003). 옵트인
`auto_resume_apply` 를 켜면 파일 편집과 검증 명령이 더해진다.

gh 는 **거기에 끼워 넣지 않는다.** `auto_resume_apply` 의 뜻은 "이 워크스페이스의
파일을 고쳐도 좋다"이고 gh 의 뜻은 "**바깥 서비스의 설정을 바꿔도 좋다**"다.
하나를 켰다고 다른 하나가 따라 켜지면 그 결정을 누구도 한 적이 없게 된다.

솔직히 적어 둔다: 이 봉투는 경계가 아니다. `gh api` 하나로 저장소 설정 대부분을
바꾸고 지울 수 있다. 켠다는 것은 **사람이 없는 자리에서 도는 작업자에게 깃헙 계정
권한을 준다**는 뜻이다. 그래서 기본은 꺼짐이고, 사용자가 알고 켜는 스위치다.

실행: python3 tests/ worker_gh_envelope
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class WorkerGhEnvelope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = open(S9, encoding="utf-8").read()
        i = src.index('perm = ["--allowedTools"')
        cls.seg = src[i:i + 1800]

    # N1. 스위치가 있고, 켜면 gh 가 봉투에 든다
    def test_worker_gh_envelope(self):
        """WorkerGhEnvelope 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_switch_exists"):
                self.assertIn('cfg.get("auto_resume_gh")', self.seg)
                m = re.search(r'cfg\.get\("auto_resume_gh"\):\s*\n\s*perm = perm \+ '
                              r'\[(.+?)\]', self.seg)
                self.assertIsNotNone(m, self.seg[-600:])
                self.assertIn("gh", m.group(1))

            # N2. 기본 봉투는 그대로 — 읽기 + s9
        with self.subTest("n2_default_envelope_unchanged"):
                head = self.seg[:self.seg.index("if cfg.get(")]
                for t in ("Read", "Glob", "Grep", "bin/s9"):
                    self.assertIn(t.replace("bin/s9", "s9bin"), head) \
                        if t == "bin/s9" else self.assertIn(t, head)
                self.assertNotIn("gh", head, "기본 봉투에 gh 가 들어 있다")

            # B1. 편집 스위치와 **섞이지 않는다** — 하나를 켰다고 다른 하나가 따라오면
            #     그 결정을 누구도 한 적이 없게 된다
        with self.subTest("b1_not_bundled_with_apply"):
                m = re.search(r'if cfg\.get\("auto_resume_apply"\):(.*?)\n\s*#',
                              self.seg, re.S)
                self.assertIsNotNone(m)
                self.assertNotIn("gh", m.group(1),
                                 "파일 편집 스위치에 gh 가 묶여 있다")

            # B2. 켜지 않은 사용자에게는 아무것도 달라지지 않는다
        with self.subTest("b2_off_by_default"):
                self.assertNotIn('cfg.get("auto_resume_gh", True)', self.seg)
                self.assertNotIn('cfg.get("auto_resume_gh") is not False', self.seg)

            # F1. 무엇을 켜는 것인지 코드가 말해 준다 — 조용한 권한 확장은 안 된다
        with self.subTest("f1_documented"):
            self.assertIn("경계가 아니다", self.seg,
                          "gh 봉투가 경계가 아니라는 사실이 코드에 없다")

if __name__ == "__main__":
    unittest.main()
