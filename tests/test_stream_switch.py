"""대화 기록 미러를 끄고 켠다 (REQ-20260827-042-62x6).

사용자 판정: 기본은 켠다 · 기본 보관 1주일(설정 변경 가능) · 끄면 화면에서 Stream
탭이 안 보이고 미러도 안 하고 깃헙에도 안 올라간다.

**끄면 전부 내린다**는 결정에는 이유가 있다. 문서별 스트림은 미러가 아니라 **원본을
먼저 보므로**, 미러만 꺼도 그 원본이 있는 머신에서는 계속 열린다. 그러면 스위치가
"껐는데 왜 보이지?"가 되고, 언젠가 Claude Code 가 제 기록을 지우는 날 **말없이
사라진다.** 이 저장소가 계속 싸워 온 실패 모양이다. 그래서 스위치의 뜻을 하나로
만든다 — "나는 대화 기록을 쓰지 않는다".

깃헙 부분은 저절로 성립한다: 끄면 아무것도 안 쓰이므로 올라갈 것이 없다.
조건부 ignore 규칙보다 튼튼하다 — **없어서 안 올라가는 것**이다.

실행: python3 tests/ stream_switch
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import unittest
from webasset import index_path   # 화면은 조각이다 — 계약은 이어 붙인 한 장을 본다 (REQ-20260829-027)

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")
STOP_HOOK = os.path.join(HERE, "..", "bin", "s9-audit-response")
INDEX = index_path()


class env_as:
    """S9_ROOT·S9_USER·S9_MACHINE 를 세운 채로 모듈을 불러 쓰는 구간.

    머신 이름도 함께 세운다 — 바인딩을 훑는 자리가 **이 머신 것만** 보게 된
    뒤로(REQ-20260902-017 `_local_binding_glob`), 하위 프로세스는
    `testbox__*.json` 을 쓰는데 안에서 부른 모듈은 진짜 머신 이름을 찾아
    "아무 바인딩도 없다"가 된다. 그러면 진행 중인 세션의 기록이 지워진다.
    """

    def __init__(self, root, user="alice", machine="testbox"):
        self.vals = {"S9_ROOT": root, "S9_USER": user, "S9_MACHINE": machine}

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.vals}
        os.environ.update(self.vals)
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _load(name, path):
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s9sw-")
        self.env = {**os.environ, "S9_ROOT": self.root, "S9_MACHINE": "testbox",
                    "S9_USER": "alice"}
        self.env.pop("S9_SESSION", None)
        self.cli("init")
        self.cli("user", "add", "alice")

    def cli(self, *argv, expect=0):
        r = subprocess.run([S9, *argv], capture_output=True, text=True,
                           env=self.env, timeout=30)
        if expect is not None:
            self.assertEqual(r.returncode, expect,
                             f"s9 {' '.join(argv)}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def set_cfg(self, **kw):
        d = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "settings.json")
        cur = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                cur = json.load(f)
        cur.update(kw)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cur, f)

    def mirror(self, name, age_days=0, body="a\n"):
        d = os.path.join(self.root, "streams")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name + ".jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        if age_days:
            t = time.time() - age_days * 86400
            os.utime(p, (t, t))
        return p


class MirrorSwitch(Base):
    """N1·N2·R2 — 미러를 쓰는가."""

    def drive(self):
        src = os.path.join(self.root, "sess-2222.jsonl")
        with open(src, "w", encoding="utf-8") as f:
            f.write("x\n")
        with env_as(self.root):
            m = _load("s9_sw_stop", STOP_HOOK)
            return m.mirror_transcript(src)

    def mirrored(self):
        """기록이 놓이는 자리 — 사람마다 갈린다 (REQ-20260827-078)."""
        return os.path.join(self.root, "users", "alice", "streams",
                            "sess-2222.jsonl")

    # N1. 설정이 없으면 켜진 것 — 쓰는 자리만 사람별로 갈렸다
    def test_n1_default_on(self):
        self.assertEqual(self.drive(), "full")
        self.assertTrue(os.path.exists(self.mirrored()))
        # 옛 공용 자리에는 새로 쓰지 않는다 — 섞이면 "누구 것을 누가 보는가"를
        # 나중에 가를 수 없다.
        self.assertFalse(os.path.exists(
            os.path.join(self.root, "streams", "sess-2222.jsonl")))

    # N2. 꺼 두면 쓰지 않는다
    def test_n2_off_writes_nothing(self):
        self.set_cfg(stream_mirror="off")
        self.assertEqual(self.drive(), "off")
        self.assertFalse(os.path.exists(self.mirrored()))

    # R2. 설정이 깨져 있어도 켜진 것으로 본다 — 기록을 남기는 쪽이 안전하다
    def test_r2_broken_config_is_on(self):
        d = os.path.join(self.root, "users", "alice", "config")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "settings.json"), "w") as f:
            f.write("{ not json")
        self.assertEqual(self.drive(), "full")


class Retention(Base):
    """N3·B1·B2·B3 — 보관 기간."""

    def prune(self):
        # 모듈 상수(ROOT·USERS·STATE·STREAMS)는 **import 시점의 S9_ROOT** 로
        # 정해진다 — 손으로 몇 개만 덮으면 나머지가 실 리포를 가리켜, 테스트가
        # 통과해도 아무것도 지키지 못한다. 그래서 환경을 세운 뒤 불러온다.
        with env_as(self.root):
            m = _load("s9_sw_mod_" + str(id(self)), S9)
            return m.prune_streams()

    # N3. 기본 7일 — 지난 것은 정리, 최근 것은 남는다
    def test_n3_default_seven_days(self):
        self.mirror("aaaa1111", age_days=9)
        self.mirror("bbbb2222", age_days=2)
        self.prune()
        s = os.path.join(self.root, "streams")
        self.assertFalse(os.path.exists(os.path.join(s, "aaaa1111.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(s, "bbbb2222.jsonl")))

    # B1. 진행 중 REQ 가 붙들고 있는 세션은 지나도 안 지운다
    def test_b1_active_session_kept(self):
        sid = "cccc3333"
        self.mirror(sid, age_days=30)
        rid = self.cli("new", "request", "--title", "t", "--summary", "s",
                       "--goal", "g", "--size", "S", "--user", "alice",
                       "--body", "x").split()[0]
        env = {**self.env, "S9_SESSION": sid}
        subprocess.run([S9, "status", rid, "in-progress", "--note", "t"],
                       capture_output=True, env=env, timeout=20)
        self.prune()
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "streams", sid + ".jsonl")),
            "진행 중인 세션의 기록이 지워졌다")

    # B2. 0 이하이면 무제한 보관 — 아무것도 안 지운다
    def test_b2_zero_means_forever(self):
        self.set_cfg(stream_keep_days=0)
        self.mirror("dddd4444", age_days=90)
        self.prune()
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "streams", "dddd4444.jsonl")))

    # B3. 꺼도 이미 있던 미러는 지우지 않는다 — 끄는 것과 지우는 것은 다른 결정이다
    def test_b3_off_does_not_delete(self):
        self.set_cfg(stream_mirror="off", stream_keep_days=0)
        self.mirror("eeee5555", age_days=1)
        self.prune()
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "streams", "eeee5555.jsonl")))


class Surface(Base):
    """N4·F1 — 사람에게 보이는 자리."""

    # N4. `s9 stream` 이 지금 상태를 말한다
    def test_n4_status_command(self):
        self.mirror("ffff6666")
        out = self.cli("stream")
        self.assertIn("켜짐", out)
        self.assertIn("7", out)          # 보관일
        self.set_cfg(stream_mirror="off")
        self.assertIn("꺼짐", self.cli("stream"))

    # F2 의 뿌리 — 화면이 자리를 내릴 **근거**를 서버가 실어 보낸다.
    # 목록만 비우면 "탭은 있는데 비어 있다"가 되고 사용자는 그걸 고장으로 읽는다.
    # 이 값이 없으면 화면은 판단할 수 없다 (없을 때는 켜진 것으로 본다 — R2).
    def test_f2_whoami_carries_flag(self):
        with env_as(self.root):
            self.assertIs(_load("s9_sw_on", S9).whoami_info().get(
                "stream_mirror"), True)
        self.set_cfg(stream_mirror="off")
        with env_as(self.root):
            self.assertIs(_load("s9_sw_off", S9).whoami_info().get(
                "stream_mirror"), False)

    # F1. 꺼져 있으면 resume 이 거부하고 이유를 말한다 — 조용히 실패하지 않는다
    def test_f1_resume_refuses_with_reason(self):
        self.set_cfg(stream_mirror="off")
        self.mirror("aaaa1111-2222-3333-4444-555555555555")
        out = self.cli("resume", "aaaa1111", "--yes", expect=1)
        self.assertIn("꺼져", out, out)


class Screen(unittest.TestCase):
    """F2 — 꺼진 계정의 **화면**에는 스트림 자리가 없다.

    서버가 목록을 비우는 것만으로는 부족하다. 탭은 그대로 남고 안이 비므로
    사용자는 그걸 설정의 결과가 아니라 **고장으로 읽는다.** 그래서 서버가
    whoami 에 `stream_mirror` 를 실었는데(이미 구현됨), 화면이 그 값을 실제로
    읽지 않으면 실은 것이 없는 것과 같다 — 여기서 그 연결을 붙든다.

    화면 소스를 글자로 검사한다. 브라우저를 띄우지 않고 지킬 수 있는 계약만
    담되, "있더라"가 아니라 **어느 자리에 어떤 순서로** 있는지를 본다.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX, encoding="utf-8") as f:
            cls.src = f.read()

    def fn(self, name):
        """`async function <name>(` 부터 다음 최상위 function 앞까지."""
        i = self.src.index("function " + name + "(")
        j = self.src.find("\nfunction ", i + 1)
        k = self.src.find("\nasync function ", i + 1)
        end = min([x for x in (j, k) if x > 0] or [len(self.src)])
        return self.src[i:end]

    # R2 의 화면 쪽 짝 — 모르면 켜진 것으로 본다.
    # 서버가 낡아 이 값을 안 주거나 whoami 가 통째로 실패했을 때 기록이 말없이
    # 사라지는 쪽보다 남아 있는 쪽이 안전하다. `=== true` 로 쓰면 그 반대가 된다.
    def test_unknown_means_on(self):
        self.assertRegex(
            self.src, r"streamOn\s*=\s*\(\)\s*=>[^\n]*stream_mirror\s*!==\s*false")

    # 탭 자체가 사라진다 — 비어 있는 탭을 남기지 않는다
    def test_tab_hidden_when_off(self):
        vis = self.fn("applyStreamVisibility")
        self.assertIn('[data-tab="stream"]', vis)
        self.assertRegex(vis, r"hidden\s*=\s*!\s*streamOn\(\)")
        # 화면을 세우는 자리에서 실제로 불려야 한다 — 정의만 있으면 죽은 코드다.
        # REQ-20260828-039 에서 그 자리가 boot() 에서 loadWhoami() 로 옮겨졌다:
        # 신원이 **늦게 도착해도** 탭이 따라오려면, 부르는 자리가 신원을 받는
        # 자리여야 한다. 부트는 그 함수를 부른다.
        self.assertIn("applyStreamVisibility();", self.fn("loadWhoami"))
        self.assertIn("loadWhoami()", self.fn("boot"))

    # 북마크·뒤로가기로 #stream 에 들어와도 빈 탭에 앉히지 않는다
    def test_hash_falls_back_to_board(self):
        route = self.fn("applyRoute")
        self.assertRegex(
            route, r'parts\[0\]\s*===\s*"stream"\s*&&\s*!\s*streamOn\(\)')
        self.assertRegex(route, r'parts\[0\]\s*=\s*"board"')

    # 문서별 스트림 터미널도 함께 내린다 — 스위치의 뜻은 하나다
    def test_per_doc_stream_gated(self):
        i = self.src.index("const streamSec =")
        self.assertIn("streamOn()", self.src[i:i + 160])

    # 꺼 두고 그려도 "미러링합니다"라고 말하지 않는다.
    # 서버가 빈 목록을 주므로 그대로 그리면 no-streams 안내가 나오는데, 그건
    # 미러링을 안 하기로 한 사용자에게 미러링 중이라고 말하는 **거짓말**이다.
    def test_off_branch_precedes_fetch(self):
        r = self.fn("renderStream")
        off = r.index("꺼져 있습니다")
        self.assertLess(off, r.index('"/api/streams"'))
        self.assertLess(off, r.index("훅이 턴 종료마다"))
        # 되돌리는 법을 함께 준다. **적는 것에서 누르는 것으로 바뀌었다** —
        # 전에는 "터미널에서 s9 user config … stream_mirror on" 이라고 적어 두었는데,
        # 대시보드로 일하는 사람에게 터미널로 가라고 말하는 화면이라는 것이
        # REQ-20260828-013 의 사유였다. 계약(되돌릴 길을 준다)은 그대로고 형태만
        # 바뀌었으므로 여기서 확인하는 것도 바꾼다.
        shown = r[off:r.index("return;", off)]   # 화면에 실제로 그리는 대목만
        self.assertIn("설정에서 켜기", shown)
        self.assertNotIn("s9 user config", shown)

    # 없는 자리로 안내하지 않는다 — 터미널의 줄 생략 안내가 Stream 탭을 가리킨다
    def test_trim_notice_no_dead_pointer(self):
        t = self.fn("termTrim")
        self.assertIn("streamOn()", t)
        self.assertRegex(t, r'streamOn\(\)\s*\?\s*"전체 이력은 Stream 탭')


if __name__ == "__main__":
    unittest.main()
