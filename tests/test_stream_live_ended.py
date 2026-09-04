"""끝난 세션은 live 가 아니다 (REQ-20260827-010-62x6 반려 재작업).

사용자 반려: "Stream 화면은 본문이 다 보이지도 않고, 스크롤도 안되고."

무인 워커가 직접 찍어서 원인을 짚었다. 어제 22:14 에 끝난 세션이 화면에
`● live` 로 떠 있었다. 바인딩에는 `"ended": "1"` 이 분명히 적혀 있는데,
`resolve_stream_path()` 가 **"바인딩이 있고 transcript 파일이 디스크에 남아
있으면 살아있다"** 로만 판정했다 — `ended` 도, 마지막 활동도 보지 않는다.
한 번이라도 돌았고 파일이 남아 있으면 영원히 live 였다.

그 거짓말이 화면에서 둘로 나타난다. `term.scrollTop = d.live ? scrollHeight : 0`
이라 **열자마자 맨 아래로 뛰어 본문 앞부분이 안 보이고**, follow 폴링이 죽은
세션을 영원히 따라간다. 반려 사유의 앞 절반이 이 한 줄에서 나온다.

고치면서 지킬 것: **live 를 끄는 것이지 접근을 막는 게 아니다.** 끝난 세션의
기록을 못 읽게 되면 이 화면의 존재 이유가 사라진다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ stream_live_ended
"""
import json
import os
import subprocess
import tempfile
import unittest
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")

from portpool import free_port, urlopen_retry, wait_server  # noqa: E402


class StreamLiveEnded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="s9slive-")
        cls.env = {**os.environ, "S9_ROOT": cls.tmp, "S9_MACHINE": "testbox",
                   "S9_PORT_GUARD": "off"}
        cls.env.pop("S9_SESSION", None)
        subprocess.run([S9, "init"], capture_output=True, env=cls.env,
                       timeout=20)

        tdir = os.path.join(cls.tmp, "transcripts")
        os.makedirs(tdir, exist_ok=True)

        def lines(f):
            for i in range(3):
                f.write(json.dumps({
                    "type": "assistant",
                    "timestamp": f"2026-08-26T22:14:0{i}+09:00",
                    "message": {"role": "assistant",
                                "content": [{"type": "text",
                                             "text": f"line {i}"}]}}) + "\n")

        def transcript(name):
            p = os.path.join(tdir, name + ".jsonl")
            with open(p, "w", encoding="utf-8") as f:
                lines(f)
            return p

        def binding(sid, **kw):
            b = {"machine": "testbox", "session": sid, "user": "", "history": [],
                 "ended": "", **kw}
            p = os.path.join(cls.tmp, "state", "sessions",
                             f"testbox__{sid}.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(b, f)

        # A: 어제 끝난 세션 — 기록은 남아 있다 (사용자가 본 그 상황)
        cls.A = "aaaa0001"
        binding(cls.A, ended="1", transcript_path=transcript(cls.A),
                attach_pid="1")
        # B: 지금 도는 세션 — 이 프로세스를 붙여 생존을 증명한다
        cls.B = "bbbb0002"
        binding(cls.B, transcript_path=transcript(cls.B),
                attach_pid=str(os.getpid()))
        # C: transcript_path 가 디렉토리 — exists 는 통과시키고 isfile 은 막는다
        cls.C = "cccc0003"
        cdir = os.path.join(tdir, "cccc0003-dir")
        os.makedirs(cdir, exist_ok=True)
        binding(cls.C, transcript_path=cdir, attach_pid=str(os.getpid()))
        mirror = os.path.join(cls.tmp, "streams", cls.C + ".jsonl")
        os.makedirs(os.path.dirname(mirror), exist_ok=True)
        with open(mirror, "w", encoding="utf-8") as f:
            lines(f)          # 미러는 transcript 를 그대로 복사한 것이다
        # D: 바인딩 없음 — 미러 폴백 (기존 동작)
        cls.D = "dddd0004"
        with open(os.path.join(cls.tmp, "streams", cls.D + ".jsonl"),
                  "w", encoding="utf-8") as f:
            lines(f)

        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env=cls.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(timeout=5)

    def stream(self, sid):
        # 붙자마자 끊기는 갈래를 되건다 — 되걸기는 portpool 한 자리에 있다
        # (REQ-20260904-003). 이 파일이 그 비대칭에 넘어간 셋째였다.
        q = urllib.parse.urlencode({"session": sid})
        _code, body = urlopen_retry(
            f"http://127.0.0.1:{self.port}/api/stream?{q}", timeout=10)
        return json.loads(body)

    # N1. 끝난 세션은 live 가 아니다
    def test_stream_live_ended(self):
        """StreamLiveEnded 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_ended_is_not_live"):
                d = self.stream(self.A)
                self.assertFalse(d.get("live"), d)

            # N2. 그래도 이벤트는 그대로 온다 — live 를 끄는 것이지 못 읽게 하는 게 아니다
        with self.subTest("n2_ended_still_readable"):
                d = self.stream(self.A)
                self.assertTrue(d.get("events"), d)

            # B1. 지금 도는 세션은 예전대로 live
        with self.subTest("b1_running_is_live"):
                d = self.stream(self.B)
                self.assertTrue(d.get("live"), d)

            # B2. transcript_path 가 디렉토리면 통과하지 않는다 — exists 가 아니라 isfile
            #     (REQ-20260827-018 에서 같은 자리를 한 번 배웠다)
        with self.subTest("b2_directory_is_not_a_transcript"):
                d = self.stream(self.C)
                self.assertFalse(d.get("live"), d)
                self.assertTrue(d.get("events"), d)     # 미러로 읽힌다

            # R1. 바인딩이 없으면 예전대로 미러 폴백 · live 아님
        with self.subTest("r1_mirror_fallback"):
            d = self.stream(self.D)
            self.assertFalse(d.get("live"), d)
            self.assertTrue(d.get("events"), d)

if __name__ == "__main__":
    unittest.main()
