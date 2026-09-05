"""도는 잡의 칩이 **전체 수까지** 말한다 (REQ-20260905-006-62x6).

사용자(2026-09-05): "얼마나 기다려야 할지 감을 잡기 위한 전체 개수도 알고 싶을
뿐이다." 종전 칩은 「테스트 4분째 · 1,204건」으로 **지나온 수만** 말했다 — 그
수가 큰 것인지 작은 것인지 잴 자가 화면에 없었으니, 숫자는 있는데 감은 없었다.
전체 수는 서버가 처음부터 실어 보내고 있었다(`jobs_running` 의 total) —
화면이 안 그렸을 뿐이다.

이 시험이 붙잡는 계약 넷:

① **분수는 전체 수가 있을 때만.** 전체 수가 없으면(옛 러너·미선언) 억지
   분수를 짓지 말고 알던 것만 말한다. `0/1,204` 나 `?/1,204` 는 모르는 것을
   아는 척하는 표기다.
② **불가능한 값을 그리지 않는다.** 지나온 수가 전체 수를 넘으면 눌러 그린다 —
   「305/301」은 정보가 아니라 고장으로 읽히고, 한 번 고장으로 읽힌 칩은
   다음 숫자도 안 믿긴다.
③ **복수는 분수를 섞지 않는다.** 동시에 도는 잡들은 세는 단위가 서로 다를 수
   있어(병렬은 파일, 직렬은 시험 개수) 합치면 뜻 없는 수가 된다.
③b **종류는 셋 다 이름을 받는다** (2차 요구). 기본값 하나를 무표기로 두면 그
   얼굴이 두 뜻이 된다 — 「골라 부른 것」과 「종류를 모르는 것(옛 러너)」이 같은
   글자가 되기 때문이다. 이름 없는 얼굴은 모르는 얼굴 하나뿐이어야 한다.
④ **막대도 퍼센트도 남은 시간도 없다.** 금지의 근거는 「끝을 모른다」였는데
   이제 끝을 알지만, 파일마다 무게가 열 배씩 갈려서(REQ-20260905-001 실측)
   「120/301」은 시간의 60% 지점이 아니다. 분수는 약속하지 않고 막대는 한다.

계약을 정규식으로 "그렇게 생겼다"만 보지 않고, `jobChip` 을 그대로 떼어 node 로
**실행**한다 (test_workspace_chip 과 같은 방식). 조각 순서·눌러 그리기 같은
조립의 계약은 글자 찾기로는 안 보인다. node 가 없으면 실행 검증만 건너뛰고
소스 계약은 그대로 본다.

실행: python3 tests/ job_progress
"""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = index_path()
S9 = os.path.join(HERE, "..", "bin", "s9")
S9_SRC = S9 + ".py"        # 본체 소스 — bin/s9 는 발사대다 (REQ-20260905-003)
RUNNER = os.path.join(HERE, "__main__.py")


def find_node():
    n = shutil.which("node") or shutil.which("nodejs")
    if n:
        return n
    for pat in ("/home/*/.vscode-server/bin/*/node",
                "/root/.vscode-server/bin/*/node"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


NODE = find_node()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def grab(src, pattern, what):
    m = re.search(pattern, src, re.S | re.M)
    assert m, f"{what} 를 못 찾았다 — 이름이 바뀌었으면 이 시험도 따라가야 한다"
    return m.group(0)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(INDEX)
        cls.kinds = grab(cls.src, r"^const JOB_KIND = \{[^\n]*\};", "JOB_KIND")
        cls.chip = grab(cls.src, r"^function jobChip\(jobs\)\{.*?^\}", "jobChip")

    def chipOf(self, *jobs):
        """jobChip 을 node 로 실제 실행한 결과 — {label, title} 또는 None."""
        if not NODE:
            self.skipTest("node 없음 — 실행 검증 생략 (소스 계약은 별도 검사)")
        script = "\n".join([
            "const esc = s => String(s == null ? '' : s);",
            self.kinds, self.chip,
            "console.log(JSON.stringify(jobChip(%s)));" % json.dumps(list(jobs)),
        ])
        p = subprocess.run([NODE, "-e", script], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, f"node 실행 실패:\n{p.stderr[-2000:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])

    def job(self, **kw):
        r = {"name": "테스트", "mins": 4, "done": 0, "total": 0, "quiet_sec": 0,
             "kind": ""}
        r.update(kw)
        return r


class TheProgressIsAFraction(Base):
    """P — 지나온 수와 전체 수가 한 값으로 선다."""

    # N1 — 요청 그 자체: 전체 수가 함께 보인다
    def test_n1_fraction_shows_both_numbers(self):
        c = self.chipOf(self.job(done=120, total=301))
        self.assertEqual(c["label"], "테스트 4분째 · 120/301건")
        # 단위는 **분모 뒤 한 번만** — 「120건/301건」은 낱말 그대로 옮긴 흔적이다
        self.assertNotIn("건/", c["label"], "단위를 두 번 붙였다")
        self.assertIn("301건 중 120건까지 지나왔습니다", c["title"])

    # N1b — 세 자리 구분은 두 수에 똑같이 (조건 분기 없이 값이 작으면 안 붙는다)
    def test_n1b_thousands_separator_on_both(self):
        c = self.chipOf(self.job(done=1204, total=3120))
        self.assertEqual(c["label"], "테스트 4분째 · 1,204/3,120건")

    # B1 — 전체 수를 모르면 억지 분수를 짓지 않고 알던 것만 말한다
    def test_b1_no_total_falls_back(self):
        c = self.chipOf(self.job(done=1204, total=0))
        self.assertEqual(c["label"], "테스트 4분째 · 1,204건")
        self.assertNotIn("/", c["label"], "모르는 전체 수를 분모로 지어냈다")
        self.assertIn("여기 숫자가 곧 진행입니다", c["title"])
        # 전체 수도 지나온 수도 없으면 존재와 경과만 — 「0건」은 정보가 아니다
        self.assertEqual(self.chipOf(self.job())["label"], "테스트 4분째")

    # B2 — 전체 수는 첫 순간부터 보인다: 그것이 곧 사용자가 물은 것이다
    def test_b2_total_visible_from_the_first_moment(self):
        c = self.chipOf(self.job(mins=0, done=0, total=301))
        self.assertEqual(c["label"], "테스트 0분째 · 0/301건")

    # B3 — 불가능한 값은 그리지 않는다
    def test_b3_done_never_exceeds_total(self):
        c = self.chipOf(self.job(done=305, total=301))
        self.assertEqual(c["label"], "테스트 4분째 · 301/301건")

    # B4 — 조각 순서: 종류 · 이름 · 경과 · 분수 · 잠잠 (폭은 K4 가 잰다)
    def test_b4_quiet_rides_behind_the_fraction(self):
        c = self.chipOf(self.job(done=120, total=301, quiet_sec=90))
        self.assertEqual(c["label"], "테스트 4분째 · 120/301건 · 90초 잠잠")
        c = self.chipOf(self.job(kind="full", mins=59, done=1204, total=3120,
                                 quiet_sec=90))
        self.assertEqual(c["label"],
                         "전체 테스트 59분째 · 1,204/3,120건 · 90초 잠잠")

    # B5 — 복수는 분수를 섞지 않는다 (단위가 서로 다를 수 있다)
    def test_b5_many_jobs_count_jobs_not_cases(self):
        c = self.chipOf(self.job(mins=5, done=120, total=301),
                        self.job(name="테스트 2", mins=2, done=9, total=88))
        self.assertEqual(c["label"], "도는 일 2건 · 5분째")
        self.assertNotIn("/", c["label"], "복수 얼굴에 분수가 섞였다")

    # F1 — 도는 잡이 없으면 아무것도 그리지 않는다 (빈 칩은 자리도 안 먹는다)
    def test_f1_nothing_when_nothing_runs(self):
        self.assertIsNone(self.chipOf())

    # F2 — 값이 숫자가 아니어도 칩이 깨지지 않는다
    def test_f2_junk_values_do_not_break_the_chip(self):
        c = self.chipOf({"name": "테스트", "mins": 4, "done": None,
                         "total": "abc", "quiet_sec": None})
        self.assertEqual(c["label"], "테스트 4분째")
        c = self.chipOf(self.job(done=-5, total=301))
        self.assertEqual(c["label"], "테스트 4분째 · 0/301건")

    # K1 — 종류 셋이 저마다 이름을 받는다 (2차 요구)
    def test_k1_every_kind_gets_a_name(self):
        want = {"full": "전체 테스트 4분째 · 120/301건",
                "smoke": "스모크 테스트 4분째 · 120/301건",
                "targeted": "표적 테스트 4분째 · 120/301건"}
        for k, label in want.items():
            c = self.chipOf(self.job(kind=k, done=120, total=301))
            self.assertEqual(c["label"], label)
            self.assertTrue(c["title"].startswith(label.split(" 4분")[0] + "가"),
                            f"{k} 툴팁이 라벨과 다른 이름을 쓴다: {c['title']}")

    # K2 — 모르는 종류는 이름을 짓지 않는다 (옛 러너·서버가 거른 값)
    def test_k2_unknown_kind_gets_no_name(self):
        for k in ("", None, "bogus", "FULL"):
            c = self.chipOf(self.job(kind=k, done=120, total=301))
            self.assertEqual(c["label"], "테스트 4분째 · 120/301건",
                             f"모르는 종류({k!r})에 이름을 지어 붙였다")

    # K3 — 「전체」가 한 화면에서 두 뜻이 되지 않는다 (tech-writer·translator 지적)
    def test_k3_the_word_whole_means_one_thing(self):
        c = self.chipOf(self.job(kind="full", done=120, total=301))
        self.assertEqual(c["title"].count("전체"), 1,
                         "「전체」가 종류와 총량 두 뜻으로 겹쳤다")
        self.assertIn("301건 중 120건까지 지나왔습니다", c["title"])

    # K4 — 칩 폭이 가장 긴 얼굴을 덮는다. **실브라우저 실측이 근거다**
    # (1440px·11.5px 에서 ch=6.39px): 「↻ 전체 테스트 59분째 · 1,204/3,120건 ·
    # 90초 잠잠」이 250px 이고 34ch=217px 라 잘리고 있었다. 40ch=256px.
    # 글자 수로 재면 안 된다 — 한글 한 음절이 ch 의 두 배 가까이 먹는다.
    def test_k4_the_longest_face_fits_the_chip(self):
        css = read(os.path.join(HERE, "..", "web", "css", "header.css"))
        m = re.search(r"\.svchip button\{[^}]*max-width:(\d+)ch", css, re.S)
        self.assertTrue(m, "칩 폭 상한을 못 찾았다 — 이 시험이 따라가야 한다")
        self.assertGreaterEqual(int(m.group(1)), 40,
                                "가장 긴 얼굴(실측 250px)이 다시 잘린다")

    # F3 — 막대도 퍼센트도 남은 시간도 없다 (금지의 근거는 바뀌었어도 결론은 같다)
    def test_f3_no_bar_no_percent_no_eta(self):
        c = self.chipOf(self.job(done=120, total=301))
        for word in ("%", "퍼센트", "남음", "예상"):
            self.assertNotIn(word, c["label"] + c["title"],
                             f"못 지킬 약속({word})이 칩에 들어왔다")
        self.assertNotIn("progress", self.chip.lower(), "진행바를 그리려 한다")


class TheServerCarriesTheNumbers(Base):
    """S — 화면은 서버가 실은 값만 옮긴다 (재판정 없음)."""

    # N2 — 서버가 전체 수와 지나온 수를 둘 다 싣는다
    def test_n2_server_ships_total_and_done(self):
        src = read(S9_SRC)
        rows = grab(src, r"^def jobs_running\(now=None\):.*?^    return out",
                    "jobs_running")
        for key in ('"total"', '"done"'):
            self.assertIn(key, rows, f"서버 잡 행에 {key} 가 없다")
        info = grab(src, r'elif parsed\.path == "/api/serveinfo":.*?\n\n',
                    "/api/serveinfo")
        self.assertIn("jobs_running()", info, "칩이 먹는 응답에 잡이 안 실린다")

    # R2 — 러너의 두 경로가 모두 전체 수와 종류를 선언한다
    def test_r2_both_runner_paths_declare_total_and_kind(self):
        run = read(RUNNER)
        self.assertIn("jobfile.start(len(files), kind=job_kind", run,
                      "병렬 경로가 전체 파일 수·종류를 선언하지 않는다")
        self.assertIn("jobfile.start(suite.countTestCases(), kind=job_kind",
                      run, "직렬 경로가 전체 시험 개수·종류를 선언하지 않는다")
        job = read(os.path.join(HERE, "jobfile.py"))
        self.assertIn('"total": int(total or 0)', job,
                      "잡 파일이 전체 수를 안 적는다")
        self.assertIn('"kind": str(kind or "")', job,
                      "잡 파일이 종류를 안 적는다")

    # K5 — 종류 판정은 **러너 한 줄뿐이다.** 잡 파일의 args 로 되짚는 두 번째
    # 판정을 두지 않는다 — args 는 `sys.argv[1:4]` 라 잘리고, `--changed` 가
    # 고른 파일은 명령줄에 아예 없어 되짚을 길이 없다.
    def test_k5_the_kind_is_judged_once_by_the_runner(self):
        run = read(RUNNER)
        self.assertEqual(run.count("job_kind ="), 1,
                         "종류 판정이 러너 안에서 두 벌이 됐다")
        self.assertIn(
            'job_kind = "full" if not argv else ("smoke" if smoke '
            'else "targeted")', run, "종류 판정 한 줄이 사라졌다")
        src = read(S9_SRC)
        rows = grab(src, r"^def jobs_running\(now=None\):.*?^    return out",
                    "jobs_running")
        self.assertNotIn("args", rows.split('"args"')[-1].split('"kind"')[0]
                         if '"kind"' in rows else "args",
                         "서버가 args 를 되짚어 종류를 다시 판정한다")
        self.assertIn("JOB_KINDS", rows, "서버가 모르는 종류를 거르지 않는다")
        kinds = grab(src, r"^JOB_KINDS = \([^)]*\)", "JOB_KINDS")
        for k in ("full", "smoke", "targeted"):
            self.assertIn(f'"{k}"', kinds, f"서버가 {k} 를 모른다")

    # R3 — 얼굴을 화면에서 볼 길이 있어야 한다 (실데이터로는 몇 분뿐이다)
    def test_r3_every_face_is_reachable_from_the_url(self):
        notice = read(os.path.join(HERE, "..", "web", "app", "notice.js"))
        for par in ("jobtotal", "jobdone", "jobn", "jobquiet", "jobkind"):
            self.assertIn(par, notice, f"?{par}= 로 세울 길이 없다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
