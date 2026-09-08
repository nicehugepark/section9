"""무게는 벽에 닿기 전에 보여야 한다 (REQ-20260908-045-62x6).

주인 물음 2026-09-08: 「한 디렉토리에 영원히 쌓이는 구조가 맞는지 검토 필요.」

architect 실측으로 답이 갈렸다. 주인이 걱정한 자리(`projects/*/assets` = 184KB,
미디어 0)에는 무게가 없고, 139.5MB 는 전부 **우리가 review 마다 찍는 검증 캡처**가
vault 에 쌓인 것이었다. 저장소 나이 15일에 .git 296MB, 에셋 9.3MB/일.

커지는 것 자체는 결함이 아니다 — **안 보이는 것**과 **벽**이 결함이다.

- 벽: GitHub 은 파일 하나가 100MB 를 넘으면 push 를 거부한다. 지금 최대 파일은
  5MB 라 png 로는 못 닿지만, 1080p60 화면 녹화는 80초면 닿는다. 그리고 한 번
  이력에 들어가면 이력 재작성 말고는 뺄 길이 없다 — 이 저장소는 streams/ 158MB
  로 그 값을 이미 한 번 치렀다.
- 안 보임: 15일 동안 아무 화면에도 그 숫자가 없었다.

그래서 둘을 세운다. ① 커밋 시점의 크기 검사(10MB 알림 · 25MB 거절, 사유를 적으면
지나감) ② digest 한 줄(총량 · 개수 · 하루 증가율 · 최대 파일).

실행: python3 tests/ asset_weight
"""
import importlib.machinery
import importlib.util
import io
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
GUARD = os.path.join(HERE, "..", "bin", "s9-guard")


def _load(name, path, root):
    prev = os.environ.get("S9_ROOT")
    os.environ["S9_ROOT"] = root
    try:
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, path))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        if prev is None:
            os.environ.pop("S9_ROOT", None)
        else:
            os.environ["S9_ROOT"] = prev


class TheSizeGate(unittest.TestCase):
    """25MB 는 커밋이 막는다 — 100MB 벽을 보이는 거절로 앞당긴다."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9size-")
        os.makedirs(os.path.join(cls.root, "state"))
        cls.g = _load("s9_guard_size", GUARD, cls.root)
        # guard 는 제 자리를 스스로 찾는다 — 시험의 임시 뿌리를 쥐어 준다
        cls.g.ROOT = cls.root

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _make(self, name, mb):
        p = os.path.join(self.root, name)
        with open(p, "wb") as f:
            f.write(b"\0" * int(mb * 1024 * 1024))
        self.addCleanup(os.remove, p)
        return name

    def _run(self, staged, env=None):
        out = io.StringIO()
        prev = os.environ.get(self.g.SIZE_OK_ENV)
        if env is None:
            os.environ.pop(self.g.SIZE_OK_ENV, None)
        else:
            os.environ[self.g.SIZE_OK_ENV] = env
        try:
            self.g.file_size_gate(staged, out)
            return None, out.getvalue()
        except SystemExit as e:
            return e.code, out.getvalue()
        finally:
            if prev is None:
                os.environ.pop(self.g.SIZE_OK_ENV, None)
            else:
                os.environ[self.g.SIZE_OK_ENV] = prev

    # 정상 — 보통 크기는 아무 말도 하지 않는다
    def test_ordinary_files_say_nothing(self):
        code, said = self._run([self._make("small.png", 0.2)])
        self.assertIsNone(code)
        self.assertEqual(said, "", "작은 파일에 말을 얹으면 큰 파일의 말이 묻힌다")

    # 경계 — 10MB 는 알리되 막지 않는다
    def test_ten_megabytes_warns_but_passes(self):
        code, said = self._run([self._make("mid.png", 11)])
        self.assertIsNone(code, "10MB 에서 막으면 안 된다")
        self.assertIn("mid.png", said)
        self.assertIn("100MB", said, "왜 큰 것이 문제인지 함께 말해야 한다")

    # 실패 — 25MB 는 막는다
    def test_twenty_five_megabytes_stops_the_commit(self):
        code, said = self._run([self._make("huge.mp4", 26)])
        self.assertEqual(code, 1, "막지 않았다 — 100MB 는 되돌릴 수 없는 벽이다")
        self.assertIn("huge.mp4", said)
        self.assertIn(self.g.SIZE_OK_ENV, said, "지나가는 길을 안 알려 준다")

    # 경계 — 사유를 적으면 지나간다 (길 없는 검사는 검사를 끄게 만든다)
    def test_a_reason_lets_it_through(self):
        code, said = self._run([self._make("huge2.mp4", 26)],
                               env="REQ-20260908-045-62x6")
        self.assertIsNone(code)
        self.assertIn("REQ-20260908-045", said, "지나간 사실이 안 보인다")

    # 회귀 — 없는 파일(삭제를 담은 커밋)에 걸려 넘어지지 않는다
    def test_a_deleted_path_is_not_measured(self):
        code, said = self._run(["없는파일.png"])
        self.assertIsNone(code)
        self.assertEqual(said, "")


class TheWeightLine(unittest.TestCase):
    """세는 자리가 없으면 다음에도 15일 뒤에야 안다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9weight-")
        os.makedirs(os.path.join(self.root, "state"))
        d = os.path.join(self.root, "vault", "requests", "2026", "09",
                         "assets", "REQ-1")
        os.makedirs(d)
        with open(os.path.join(d, "shot.png"), "wb") as f:
            f.write(b"\0" * (3 * 1024 * 1024))
        with open(os.path.join(d, "note.txt"), "w") as f:
            f.write("x")
        os.makedirs(os.path.join(d, ".text"))
        with open(os.path.join(d, ".text", "shot.png.txt"), "w") as f:
            f.write("사이드카")
        self.m = _load("s9_weight", S9, self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_it_measures_what_is_there(self):
        st = self.m.asset_weight(force=True)
        self.assertEqual(st["files"], 2, "첨부 개수가 틀렸다")
        self.assertGreaterEqual(st["bytes"], 3 * 1024 * 1024)
        self.assertTrue(st["max_path"].endswith("shot.png"))

    def test_the_line_says_the_numbers(self):
        self.m.asset_weight(force=True)
        line = self.m.asset_weight_line()
        self.assertIn("MB", line)
        self.assertIn("shot.png", line, "무엇이 제일 큰지 말해야 한다")

    def test_the_first_measure_does_not_guess_a_rate(self):
        st = self.m.asset_weight(force=True)
        self.assertNotIn("per_day", st,
                         "첫 측정에 증가율을 지어냈다 — 짐작한 숫자는 없느니만 못하다")

    def test_the_rate_comes_from_two_measures(self):
        import time
        t0 = time.time()
        self.m.asset_weight(force=True, now=t0)
        with open(os.path.join(self.root, "vault", "requests", "2026", "09",
                               "assets", "REQ-1", "more.png"), "wb") as f:
            f.write(b"\0" * (1024 * 1024))
        st = self.m.asset_weight(force=True, now=t0 + 86400)
        self.assertIn("per_day", st)
        self.assertAlmostEqual(st["per_day"] / (1024 * 1024), 1.0, places=1)

    def test_a_big_file_is_called_out(self):
        with open(os.path.join(self.root, "vault", "requests", "2026", "09",
                               "assets", "REQ-1", "big.mp4"), "wb") as f:
            f.write(b"\0" * (26 * 1024 * 1024))
        self.m.asset_weight(force=True)
        self.assertIn("25MB", self.m.asset_weight_line(),
                      "커밋이 막을 크기인데 그 사실을 안 말한다")

    def test_nothing_to_measure_says_nothing(self):
        shutil.rmtree(os.path.join(self.root, "vault"))
        self.m.asset_weight(force=True)
        self.assertEqual(self.m.asset_weight_line(), "",
                         "잴 것이 없는데 줄을 만들면 digest 가 시끄러워진다")


if __name__ == "__main__":
    unittest.main()
