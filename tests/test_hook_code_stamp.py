"""낡은 코드 배너가 훅 파일까지 본다 (REQ-20260828-025-62x6).

부모 REQ-20260826-034-62x6 에서 실제로 물린 자리다. 첨부 분류 고침은
`bin/s9-audit-prompt` 에 들어갔는데, 채팅을 받던 서버는 1시간 반 전에 뜬
프로세스라 **옛 판정자를 메모리에 들고 있었다.** 그래서 질문이 요청 카드가
되어 반려가 났다.

배너(REQ-20260826-011)는 바로 그런 어긋남을 알리라고 있는 장치인데, 지문을
`bin/s9` 하나만 떴다. 채팅 판정자는 `bin/s9-audit-prompt` 에 있고 서버가 첫
채팅 때 한 번 로드해 `_chat_classifier` 로 **캐시한다** — 즉 훅만 고치면
배너는 침묵한다. 그때 배너가 떴던 것은 우연히 `bin/s9` 도 같이 만져지던
덕이었다.

서버가 메모리에 들고 도는 것이 그 둘이니, 지문도 그 둘이어야 한다.

읽을 수 없으면 낡았다고 단정하지 않는다 — 기존 규율 그대로다(code_is_stale).

실행: python3 tests/ hook_code_stamp
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from s9src import serve_tail     # 소스 구간은 한 곳에서 (s9src 참조)
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"   # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HookStamp(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9hookstamp-")
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)
        self.m = _load("s9_hookstamp_" + os.path.basename(self.root), S9)
        self.m.ROOT = self.root

    def stamp(self, d):
        with open(os.path.join(self.root, "state", "serve-code.json"), "w",
                  encoding="utf-8") as f:
            json.dump(d, f)

    # H1. 지문이 서버가 들고 도는 것 **둘 다**를 담는다
    def test_h1_stamp_covers_both_files(self):
        st = self.m.running_code_stamp()
        self.assertTrue(st.get("s9", {}).get("size"), st)
        self.assertTrue(st.get("hook", {}).get("size"), st)
        self.assertNotEqual(st["s9"], st["hook"],
                            "같은 파일을 두 번 떴다")

    # H2. **핵심** — 훅만 바뀌어도 낡음이다 (이 결함이 놓치던 그 경우)
    def test_h2_hook_change_alone_is_stale(self):
        a = {"s9": {"mtime": 1.0, "size": 10},
             "hook": {"mtime": 2.0, "size": 20}}
        b = {"s9": {"mtime": 1.0, "size": 10},
             "hook": {"mtime": 9.0, "size": 20}}
        self.assertTrue(self.m.stamp_is_stale(a, b))
        self.assertEqual(self.m.stale_parts(a, b), ["bin/s9-audit-prompt"])

    # H3. bin/s9 만 바뀌어도 여전히 낡음 (기존 행동 보존)
    def test_h3_s9_change_still_stale(self):
        a = {"s9": {"mtime": 1.0, "size": 10},
             "hook": {"mtime": 2.0, "size": 20}}
        b = {"s9": {"mtime": 1.0, "size": 11},
             "hook": {"mtime": 2.0, "size": 20}}
        self.assertTrue(self.m.stamp_is_stale(a, b))
        self.assertEqual(self.m.stale_parts(a, b), ["bin/s9"])

    # H4. 둘 다 그대로면 조용하다 — 상시 경고는 곧 안 읽힌다
    def test_h4_unchanged_is_silent(self):
        st = self.m.running_code_stamp()
        self.assertFalse(self.m.stamp_is_stale(st, dict(st)))
        self.assertEqual(self.m.stale_parts(st, st), [])

    # H5. 옛 단일 지문(이 고침 이전 서버가 남긴 것)도 깨지지 않는다.
    #     그 서버는 훅 지문을 애초에 뜬 적이 없으니 훅으로는 판정할 수 없다 —
    #     비교할 수 있는 bin/s9 만 본다. 근거 없는 단정을 하지 않는 규율이다.
    def test_h5_legacy_flat_stamp_still_compared(self):
        legacy = {"mtime": 1.0, "size": 10}
        cur = {"s9": {"mtime": 1.0, "size": 10},
               "hook": {"mtime": 2.0, "size": 20}}
        self.assertFalse(self.m.stamp_is_stale(legacy, cur))
        cur2 = {"s9": {"mtime": 5.0, "size": 10},
                "hook": {"mtime": 2.0, "size": 20}}
        self.assertTrue(self.m.stamp_is_stale(legacy, cur2))

    # H6. 읽을 수 없으면 낡았다고 단정하지 않는다
    def test_h6_unknown_is_not_stale(self):
        cur = self.m.running_code_stamp()
        self.assertFalse(self.m.stamp_is_stale({}, cur))
        self.assertFalse(self.m.stamp_is_stale(cur, {}))
        self.assertFalse(self.m.stamp_is_stale(None, None))
        # 한쪽 파일만 읽히지 않은 경우도 그 파일로는 단정하지 않는다
        half = {"s9": cur["s9"], "hook": {}}
        self.assertFalse(self.m.stamp_is_stale(cur, half))

    # H7. serve_stale() 이 **어떤 파일이 바뀌었는지** 말한다 — "코드가 바뀌었다"
    #     만으로는 무엇이 안 도는지 사람이 짚을 수 없다
    def test_h7_message_names_the_changed_file(self):
        cur = self.m.running_code_stamp()
        old = {"s9": cur["s9"], "hook": {"mtime": 1.0, "size": 10}}
        self.stamp({"stamp": old, "pid": os.getpid(),
                    "started": "2026-08-28T15:00:00+09:00"})
        msg = self.m.serve_stale()
        self.assertIn("bin/s9-audit-prompt", msg)
        self.assertIn("--restart", msg, "무엇을 하라는지 말하지 않는다")

    # H8. 훅만 바뀐 서버에 대해 serve_stale 이 침묵하지 않는다 (H7의 판정 부분)
    def test_h8_hook_only_server_is_reported(self):
        cur = self.m.running_code_stamp()
        fresh = {"stamp": cur, "pid": os.getpid()}
        self.stamp(fresh)
        self.assertEqual(self.m.serve_stale(), "")
        self.stamp({"stamp": {"s9": cur["s9"],
                              "hook": {"mtime": 1.0, "size": 10}},
                    "pid": os.getpid()})
        self.assertIn("옛 코드", self.m.serve_stale())

    # H9. serve 기동이 **둘 다**를 지문으로 남긴다 — 남기지 않으면 물어볼 데가 없다
    def test_h9_serve_stamps_both(self):
        src = open(S9_SRC, encoding="utf-8").read()
        self.assertIn("SERVE_CODE_STAMP = running_code_stamp()", src)
        self.assertIn("serve-code.json", serve_tail(src))

    # H10. /api/serveinfo 도 같은 지문으로 판정한다 — 화면과 CLI 가 갈리면
    #      둘 중 어느 쪽을 믿어야 하는지가 또 하나의 문제가 된다
    def test_h10_serveinfo_uses_same_stamp(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index('parsed.path == "/api/serveinfo"')
        seg = src[i:i + 900]
        self.assertIn("running_code_stamp()", seg)
        self.assertIn("stamp_is_stale(SERVE_CODE_STAMP", seg)

    # H11. 훅 경로는 채팅 판정자를 **실제로 로드하는 그 경로**여야 한다.
    #      지문과 로드가 다른 파일을 가리키면 배너는 또 엉뚱한 것을 본다.
    def test_h11_hook_path_matches_the_loaded_one(self):
        src = open(S9_SRC, encoding="utf-8").read()
        i = src.index("_chat_classifier = mod.classify")
        seg = src[max(0, i - 900):i]
        self.assertIn("hook_path()", seg,
                      "채팅 판정자 로드가 hook_path() 를 쓰지 않는다 — "
                      "지문과 로드가 갈릴 수 있다")
        self.assertTrue(os.path.exists(self.m.hook_path()), self.m.hook_path())


class Banner(unittest.TestCase):
    """화면도 바뀐 파일을 서버가 말한 대로 말한다 — 문구가 `bin/s9` 로 못
    박혀 있으면 훅만 바뀐 경우에 거짓말이 된다."""

    def test_h12_banner_names_reported_files(self):
        body = open(index_path(),
                    encoding="utf-8").read()
        i = body.index("서버가 옛 코드로 돌고 있습니다")
        seg = body[max(0, i - 700):i + 700]
        self.assertIn("d.changed", seg,
                      "서버가 알려준 바뀐 파일을 쓰지 않는다")
        self.assertNotIn("<code>bin/s9</code> 가 바뀌었습니다", seg,
                         "파일 이름이 문구에 못 박혀 있다")


if __name__ == "__main__":
    unittest.main()
