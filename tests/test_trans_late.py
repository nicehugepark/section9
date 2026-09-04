"""전이표가 늦거나 안 와도 버튼 줄이 비지 않는다 (REQ-20260828-027-62x6).

`http://127.0.0.1:9909/#docs/REQ-…` 로 곧장 들어가거나 그 자리에서 F5 하면,
문서의 상태 옮기기 버튼이 통째로 비고 `이어 말하기` 만 남는 때가 있었다. 세 번
재현됐고, 같은 문서를 목록에서 눌러 열면 정상이었다.

**원인은 재현해서 확인했다.** 화면이 뜨는 순간 여덟 개 남짓한 API 를 한꺼번에
부르는데, 이 환경(WSL 로컬 중계)에서 그 폭주 중 일부 연결이 실제로 끊긴다 —
측정: 120 요청 중 30건이 `Connection reset by peer`, `/api/transitions` 만
따로 세면 15번 중 2번. 그런데 부트는 그 실패를 이렇게 삼켰다:

    try{ TRANS = await (await fetch("/api/transitions")).json(); }catch(e){}

한 번 놓치면 `TRANS` 는 **그 세션 내내 빈 채로 남는다.** 다시 받는 자리가
어디에도 없었다. 그러면 `TRANS[m.status] || []` 가 빈 배열이 되고, 화면은 아무
말 없이 버튼을 안 그린다 — 사용자는 "이 문서는 옮길 수 없구나"로 읽는다.
**없는 것과 아직 안 온 것이 화면에서 같아 보이는 것**이 이 결함의 나쁜 점이다.

계약은 넷이다.

  ① 전이표는 한 번 실패로 끝나지 않는다 — `loadTrans()` 가 물러서며 다시 받는다.
  ② 표를 받는 자리는 하나다. 부트도, 다시 받기도, 배경 갱신도 그 함수를 지난다.
  ③ **없는 것과 안 온 것을 가른다.** `done` 처럼 갈 곳이 없는 상태는 원래
     버튼이 없다(정상). 표 자체가 안 온 것은 그렇게 말하고, 다시 받는 길을 준다.
  ④ 조용히 실패하지 않는다 — 못 받은 동안 그 자리에 무슨 일인지가 적혀 있다.

`?transfail` / `?transfail=once` 로 이 상황을 손 없이 만들 수 있다(진단·헤드리스
캡처용 — 이 화면의 다른 진단 스위치와 같은 어휘).

실행: python3 tests/ trans_late
"""
import os
import re
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()


def grab(src, name):
    m = re.search(r"(?:async )?function %s\([^)]*\)\{[\s\S]*?\n\}" % name, src)
    assert m, name
    return m.group(0)


class TransLate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()
        cls.boot = grab(cls.src, "boot")
        cls.load = grab(cls.src, "loadTrans")
        cls.doc = grab(cls.src, "loadDoc")

    # T1. 다시 받는 자리가 있다 — 한 번의 실패가 세션을 못 쓰게 만들지 않는다.
    #     REQ-20260828-039 에서 **그 자리가 공통 문(loadSupply)으로 옮겨졌다**:
    #     전이표만이 아니라 부트가 받는 값 전부가 같은 재시도를 탄다. 계약의
    #     세기는 그대로다 — 전이표는 여전히 물러섰다 다시 받아야 하고, 여기서는
    #     그 규칙이 실제로 걸린 자리를 짚는다.
    def test_trans_late(self):
        """TransLate 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("t1_retries"):
                self.assertIn("fetch", self.load)
                self.assertIn("loadSupply", self.load, "전이표가 공통 문을 안 지난다")
                door = grab(self.src, "loadSupply")
                self.assertTrue(re.search(r"for\s*\(", door) or "retry" in door,
                                "공통 문이 한 번만 받고 만다")
                self.assertIn("setTimeout", door, "물러섰다 다시 받지 않는다")

            # T2. 부트가 표를 직접 받지 않는다 — 받는 자리는 하나다
        with self.subTest("t2_boot_uses_one_door"):
                self.assertIn("loadTrans", self.boot)
                self.assertNotIn('fetch("/api/transitions")', self.boot,
                                 "부트가 전이표를 직접 받는다 — 재시도를 못 탄다")
                # 표를 받는 fetch 는 온 파일에서 loadTrans 안의 한 줄뿐이어야 한다
                self.assertEqual(self.src.count('fetch("/api/transitions")'), 1,
                                 "전이표를 받는 자리가 둘 이상이다")
                self.assertIn('fetch("/api/transitions")', self.load)

            # T3. 빈 표와 '갈 곳 없음'을 가른다
        with self.subTest("t3_missing_is_not_empty"):
                self.assertIn("transReady", self.src,
                              "표가 왔는지 묻는 자리가 없다 — targets.length 로는 구분이 안 된다")
                m = re.search(r"const transLost\s*=([^\n;]*)", self.doc)
                self.assertTrue(m, "문서 화면이 '표가 안 왔다'를 판정하지 않는다")
                self.assertNotIn("targets.length", m.group(1),
                                 "갈 곳 없는 done 문서를 '표가 안 왔다'로 읽는다")

            # T4. 못 받은 동안 그 자리가 조용하지 않다 + 다시 받는 길이 있다
        with self.subTest("t4_says_and_offers"):
                self.assertIn("transLost", self.doc)
                # 전이 단추 무리가 transBtns 로 갈라졌다 (REQ-20260830-046 — 행동 띠가
                # 벨트·전이·말하기를 한 곳에 모으며). '못 받은 경우'는 그 무리가 다룬다.
                i = self.doc.index("const transBtns")
                seg = self.doc[i:i + 900]
                self.assertIn("transLost", seg, "버튼 줄이 못 받은 경우를 다루지 않는다")
                self.assertIn("data-retrans", self.src, "다시 받는 버튼이 없다")
                self.assertIn("dataset.retrans", self.src, "다시 받기 버튼에 핸들러가 없다")

            # T5. 표가 오면 보고 있던 문서를 다시 그린다 — 사람이 새로고침하게 두지 않는다
        with self.subTest("t5_redraws_when_it_arrives"):
                refill = grab(self.src, "transRefill")
                self.assertIn("loadTrans", refill)
                self.assertIn("loadDoc(", refill,
                              "표가 와도 열려 있는 문서를 다시 그리지 않는다")
                self.assertIn("dataset.showing", refill,
                              "그 사이 다른 문서로 옮겨 갔는지 보지 않는다")
                self.assertIn("transRefill", self.doc,
                              "문서 화면이 표를 다시 받으러 가지 않는다")

            # T6. 배경 갱신이 빈 표를 메운다 — 보드의 드래그 대상 표시도 이 표를 쓴다
        with self.subTest("t6_background_heals"):
                rc = grab(self.src, "refreshCatalog")
                self.assertIn("transRefill", rc, "배경 갱신이 빈 전이표를 그대로 둔다")
                self.assertIn("transReady", rc, "이미 받은 표를 매 주기 다시 받는다")

            # T7. 손 없이 이 상황을 만들 수 있다 (진단·헤드리스 캡처용)
        with self.subTest("t7_diagnostic_switch"):
            self.assertIn("transfail", self.src, "재현 스위치가 없다")
            self.assertIn("transfail=once", self.src,
                          "한 번만 실패시키는 경로가 없다 — 회복을 못 찍는다")

if __name__ == "__main__":
    unittest.main()
