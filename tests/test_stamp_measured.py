"""화면에 뜨는 시각도 실측인가 (REQ-20260903-013-62x6).

같은 지적이 두 번째다. 첫 번째(REQ-20260826-038)에 답한 것은 **기록**이었다 —
Stop 훅이 문서에 남는 도장을 실제 시각으로 바로잡는다. 그런데 사용자가 읽는 것은
문서가 아니라 **화면**이고, 화면에 나간 글자는 훅이 못 고친다. 20분 도는 턴이면
20분 과거를 적은 채로 나가고, 읽는 사람에게는 재지 않고 지어낸 숫자로 보인다.

사용자 지적: "시각 표시할 때 실제 측정 시간을 출력하는것 맞나? 그냥 단순 추정치를
출력하는것 같은데.. 반드시 측정시간을 알려준 표기법으로 출력하게 해."

그래서 **재는 자리를 하나 세운다**: `s9 now`. 답을 쓰기 직전에 부르면 그 자리에서
잰 값이 응답 머리 형식 그대로 나온다 — 형식도 시간대도 모델이 지어낼 자리가 없다.
`date` 로 대신하지 않는 이유는 그것이 개인 설정 `timezone` 을 모르기 때문이다.

곁들여, KST 상수가 남아 있던 자리 둘을 없앤다. 프롬프트 훅은 이미 걷어냈는데
(REQ-20260828-024) Stop 훅과 역할 에이전트 원천에는 그대로였다 — KST 아닌 사람에게
**확신 있게 틀린 시각**을 적어 주는 자리다.

격리: 임시 S9_ROOT. 실행: python3 tests/ stamp_measured
"""
import datetime
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")
RESP_HOOK = os.path.join(ROOT, "bin", "s9-audit-response")
PROMPT_HOOK = os.path.join(ROOT, "bin", "s9-audit-prompt")
PROTOCOL = os.path.join(ROOT, "harness", "common", "PROTOCOL.md")
ROSTER = os.path.join(ROOT, "harness", "claude", "gen_roster.py")
AGENTS = os.path.join(ROOT, "harness", "claude", "agents")
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")

STAMP = re.compile(r"\A\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+\Z")


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class MeasuredStamp(unittest.TestCase):
    """`s9 now` — 재는 자리."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9now-")
        self.env = {**os.environ, "S9_ROOT": self.root}
        self.env.pop("S9_TZ", None)
        subprocess.run([S9, "init"], capture_output=True, env=self.env)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _now(self, *extra, **kw):
        env = {**self.env, **kw.pop("env", {})}
        out = subprocess.run([S9, "now", *extra], capture_output=True,
                             encoding="utf-8", env=env, timeout=20)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_now_is_a_real_reading(self):
        """지금 시각을 응답 머리 형식으로 — 벽시계와 어긋나지 않는다."""
        with self.subTest("m1_shape"):
            got = self._now()
            self.assertRegex(got, STAMP)
        with self.subTest("m2_matches_the_wall_clock"):
            before = datetime.datetime.now().astimezone()
            got = self._now()
            after = datetime.datetime.now().astimezone()
            # 라벨을 떼고 벽시계와 견준다. 시간대는 시스템 로컬(설정 없음)이라
            # naive 로 비교해도 같은 자로 잰 값이다.
            read = datetime.datetime.strptime(got[:19], "%Y-%m-%d %H:%M:%S")
            lo = before.replace(tzinfo=None) - datetime.timedelta(seconds=2)
            hi = after.replace(tzinfo=None) + datetime.timedelta(seconds=2)
            self.assertTrue(lo <= read <= hi, f"{got} not in [{lo}, {hi}]")

    def test_now_as_prints_the_whole_head_line(self):
        """모델이 형식을 지어낼 자리가 없다 — 줄째로 준다."""
        line = self._now("--as", "lead")
        self.assertTrue(line.startswith("`[") and line.endswith(" - lead]`"),
                        line)
        self.assertRegex(line[2:-len(" - lead]`")], STAMP)

    def test_timezone_follows_the_setting_not_a_constant(self):
        """KST 상수가 아니다 — 시각도 라벨도 함께 따라간다."""
        ny = self._now(env={"S9_TZ": "America/New_York"})
        seoul = self._now(env={"S9_TZ": "Asia/Seoul"})
        with self.subTest("m3_label_follows"):
            self.assertTrue(seoul.endswith("KST"), seoul)
            self.assertRegex(ny, r"(EST|EDT)\Z")
        with self.subTest("m4_clock_follows"):
            # 같은 순간을 두 시간대로 읽었으니 시각 자체가 달라야 한다.
            self.assertNotEqual(ny[:13], seoul[:13])


class ResponseHookHasNoConstant(unittest.TestCase):
    """Stop 훅의 보정 — KST 라벨을 못박지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load("s9resp_meas", RESP_HOOK)

    def test_stop_hook_stamp(self):
        now = "2026-09-03 20:30:00 EDT"
        with self.subTest("m5_foreign_zone_stamp_is_recognised"):
            # 예전 정규식은 " KST - " 를 글자로 요구했다. EST 사용자가 규약대로
            # 적으면 못 알아보고 **머리에 도장을 하나 더 붙였다** — 두 개가 된다.
            text = "`[2026-09-03 20:00:00 EDT - designer]`\n\n표를 그렸다."
            fixed, drift = self.m.correct_stamp(text, now)
            self.assertEqual(fixed.count("`["), 1, fixed)
            self.assertTrue(fixed.startswith(f"`[{now} - designer]`"), fixed)
            self.assertEqual(drift, 1800)
        with self.subTest("m6_numeric_offset_label"):
            text = "`[2026-09-03 20:00:00 +09:00 - lead]`\n\n본문"
            fixed, _ = self.m.correct_stamp(text, now)
            self.assertEqual(fixed.count("`["), 1, fixed)
        with self.subTest("m7_no_hardcoded_kst_left"):
            src = _read(RESP_HOOK)
            self.assertNotIn("def now_kst", src)
            self.assertNotIn("timedelta(hours=9)", src)
        with self.subTest("m8_now_stamp_asks_the_one_place"):
            # 물러섬이 있어도 1순위는 `s9 now` 여야 한다 — 답이 둘이면 갈린다.
            src = _read(RESP_HOOK)
            self.assertRegex(src, r'def now_stamp\(')
            self.assertIn('"now"', src)


class InstructionSaysMeasure(unittest.TestCase):
    """지시가 실제로 「재라」고 말하는가 — 원천과 생성물이 같은 글자인가."""

    def test_prompt_hook_injects_the_measure_order(self):
        m = _load("s9prompt_meas", PROMPT_HOOK)
        ctx = m.stamp_context()
        with self.subTest("m9_says_measure_before_writing"):
            self.assertIn("답을 쓰기 직전에 재라", ctx)
        with self.subTest("m10_hands_over_the_command"):
            self.assertIn("now --as lead", ctx)
        with self.subTest("m11_injected_value_is_labelled_as_arrival"):
            # 「현재 시각」이라 부르면 그대로 베껴 쓴다. 이 값이 무엇인지 말한다.
            self.assertIn("도착한 시각", ctx)
        with self.subTest("m16_no_measured_badge"):
            # 정확하면 표시가 필요 없다 — 딱지는 믿지 못할 때나 다는 것이고,
            # 값이 틀어져도 계속 붙어 있는다 (REQ-20260903-014).
            self.assertNotIn("(실측)", ctx)

    def test_protocol_and_agents_carry_the_same_rule(self):
        proto = _read(PROTOCOL)
        with self.subTest("m12_protocol"):
            self.assertIn("답을 쓰기 직전에 재라", proto)
            self.assertIn("s9 now --as lead", proto)
        with self.subTest("m13_claude_md_is_generated_from_it"):
            # Claude 세션이 실제로 읽는 것은 이 파일이다. 원천을 고쳤는데
            # 생성물이 안 따라오면 고친 것이 아니다.
            self.assertIn("답을 쓰기 직전에 재라", _read(CLAUDE_MD))
        with self.subTest("m14_roster_source"):
            self.assertIn("now --as {name}", _read(ROSTER))
        with self.subTest("m15_generated_agents"):
            # README.md 는 로스터 설명서지 에이전트가 아니다 (s9-install 도 제외한다).
            names = [f for f in os.listdir(AGENTS)
                     if f.endswith(".md") and f != "README.md"]
            self.assertGreater(len(names), 20)
            for f in names:
                body = _read(os.path.join(AGENTS, f))
                role = f[:-3]
                self.assertIn(f"now --as {role}", body, f)
                # 상수 KST 로 라벨을 못박는 지시가 남아 있으면 안 된다.
                self.assertNotIn("%H:%M:%S KST", body, f)


if __name__ == "__main__":
    unittest.main()
