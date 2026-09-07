"""Stream 행 제목은 그 세션에서 사람이 처음 친 말이다 (REQ-20260907-034).

여든 행이 전부 시각 하나로만 갈리면 「무슨 일을 하던 자리였나」를 못 고른다.
그런데 미러의 **첫 `user` 이벤트가 곧 사람의 말은 아니다** — 이 판에서 실측한
것 셋: ① `s9 code` 가 넣는 부트 문구가 늘 맨 앞에 선다 ② 도구 결과도 `user` 로
실린다 ③ 그림을 붙이면 글자가 블록 목록 안에 있다.

고정하는 계약 넷.
1. 훅이 넣은 프롬프트는 **통째로** 건너뛴다 — 줄 단위로 거르면 부트 문구의
   둘째 줄이 제목이 된다(실측: 여든 행 중 여럿이 같은 말로 시작했다).
2. 도구 결과·그림 설명은 사람의 말이 아니다.
3. 못 찾으면 빈 값 — 화면이 종전의 시각 제목으로 물러난다.
4. 미러를 통째로 읽지 않는다. 한 번 찾은 것은 다시 찾지 않는다.

실행: python3 tests/ stream_row_title
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

TMP = tempfile.mkdtemp(prefix="s9-strowtitle-")
_prev = {k: os.environ.get(k) for k in ("S9_ROOT", "S9_MACHINE")}
os.environ["S9_ROOT"] = TMP
os.environ["S9_MACHINE"] = "testbox"
try:
    spec = importlib.util.spec_from_loader(
        "s9_mod_srt", importlib.machinery.SourceFileLoader("s9_mod_srt", S9))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
finally:
    for k, v in _prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def user(content):
    return {"type": "user", "message": {"role": "user", "content": content}}


class FirstPrompt(unittest.TestCase):
    """서버가 내주는 값 — `stream_first_prompt` 를 직접 부른다."""

    _n = [0]

    def _mirror(self, events, name=None):
        # 이름이 겹치면 안 된다 — 서버가 파일마다 첫 말을 **기억하므로**(캐시)
        # 같은 이름이면 앞 시험의 답이 나온다. 실제로 그렇게 두 건이 어긋났다.
        self._n[0] += 1
        p = os.path.join(TMP, name or f"m{self._n[0]}.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return p

    def _fn(self):
        # streams_list 와 같은 껍데기 안에 산다 — 서버를 세우지 않고 꺼내 쓴다
        return mod.stream_first_prompt

    def test_a_plain_prompt(self):
        p = self._mirror([user("헤더 정렬 고쳐줘")])
        self.assertEqual(self._fn()(p), "헤더 정렬 고쳐줘")

    def test_the_boot_prompt_is_skipped_whole(self):
        """줄 단위로 거르면 부트 문구의 **둘째 줄**이 제목이 된다."""
        boot = "[section9 bootstrap] 세션 기동\n이 턴에서 할 일은 하나다: 수신함을 arm 하라"
        p = self._mirror([user(boot), user("진짜 물음이다")])
        self.assertEqual(self._fn()(p), "진짜 물음이다")

    def test_tool_results_are_not_a_persons_words(self):
        p = self._mirror([
            user([{"type": "tool_result", "tool_use_id": "t1", "content": "출력"}]),
            user("사람의 말"),
        ])
        self.assertEqual(self._fn()(p), "사람의 말")

    def test_text_inside_a_block_list_counts(self):
        # 그림을 붙이면 글자가 블록 목록 안에 있다
        p = self._mirror([user([{"type": "image", "source": {}},
                                {"type": "text", "text": "이거 왜 이러지"}])])
        self.assertEqual(self._fn()(p), "이거 왜 이러지")

    def test_image_metadata_is_skipped(self):
        p = self._mirror([user("[Image: original 1520x2430, displayed at 1251x2000"),
                          user("사람의 말")])
        self.assertEqual(self._fn()(p), "사람의 말")

    def test_only_the_first_line(self):
        p = self._mirror([user("첫 줄이다\n둘째 줄은 제목이 아니다")])
        self.assertEqual(self._fn()(p), "첫 줄이다")

    def test_blank_lines_are_stepped_over(self):
        p = self._mirror([user("\n\n   \n내용 있는 첫 줄")])
        self.assertEqual(self._fn()(p), "내용 있는 첫 줄")

    def test_a_long_prompt_is_cut(self):
        long = "가" * 200
        got = self._fn()(self._mirror([user(long)]))
        self.assertEqual(len(got), 60)
        self.assertTrue(got.endswith("…"))

    def test_nothing_human_falls_back_to_empty(self):
        """무인 작업자 세션 — 화면이 시각 제목으로 물러난다."""
        p = self._mirror([user("[section9 답 찾기] 질문 QST-1 에 답이 없다")])
        self.assertEqual(self._fn()(p), "")

    def test_a_missing_file_does_not_raise(self):
        self.assertEqual(self._fn()(os.path.join(TMP, "없다.jsonl")), "")

    def test_it_does_not_read_the_whole_mirror(self):
        """앞부분만 본다 — 여든 파일을 통째로 읽으면 목록 한 번이 수백 MB 다."""
        events = [user([{"type": "tool_result", "tool_use_id": "t", "content": "x"}])
                  ] * 5000 + [user("아주 뒤에 있는 말")]
        self.assertEqual(self._fn()(self._mirror(events, "big.jsonl")), "")


class TheScreenFallsBack(unittest.TestCase):
    def test_the_row_title_prefers_the_prompt_and_falls_back_to_the_time(self):
        src = open(os.path.join(HERE, "..", "web", "app", "audit.js"),
                   encoding="utf-8").read()
        self.assertIn("s.first_prompt || when", src,
                      "행 제목이 첫 프롬프트를 쓰지 않거나 물러날 자리가 없다")


if __name__ == "__main__":
    unittest.main()
