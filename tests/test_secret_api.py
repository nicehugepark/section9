"""비밀을 화면에서 다룬다 — 값은 절대 나가지 않는다 (REQ-20260828-012-62x6).

사용자(08:36): "세션을 껐다켜거나 시크릿 관련 기능들이 다 완료된걸로 아는데 왜
볼 수가 없지?"

볼 수 없던 이유는 단순하다 — **화면이 없었다.** REQ-20260827-035 는 CLI 만
만들고 `done` 이 됐고, `web/index.html` 에 "secret" 이라는 낱말은 한 번도 나오지
않았다. 이 사람은 대시보드로 일한다. 거기서 보이지 않으면 없는 기능이다.

**경계**: 이 API 의 뜻은 "모델이 값을 안 본다"가 아니다 — 그건 이 하네스에서
보장할 수 없다(REQ-20260827-035 에 적어 둔 한계). 뜻은 **실수로 새는 길을
닫는다**는 것이다. 값이 응답·로그·오류 문구에 섞이면 브라우저 기록·캡처·스트림
어디로든 따라간다.

경로도 주지 않는다 — 어느 쪽(internal/external)에 있는지만.

실행: python3 tests/ secret_api
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class SecretApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = open(S9, encoding="utf-8").read()
        i = cls.src.index('parsed.path == "/api/secrets"')
        # 끝을 글자 수로 자르면 주석 한 줄에 계약이 슬라이스 밖으로 밀린다
        cls.listing = cls.src[i:cls.src.index('parsed.path == "/api/users"')]
        j = cls.src.index('parsed.path == "/api/secret/set"')
        cls.setter = cls.src[j:cls.src.index('parsed.path == "/api/secret/rm"')]
        # **쓰는 자리는 한 곳이다** (REQ-20260828-017) — 형식·권한·빈 값 규칙은
        # 이제 secret_write() 안에 있고 API 도 CLI 도 그 함수를 지난다. 계약을
        # 핸들러 본문에서 재면 "두 벌 중 한 벌만 고쳐진" 상태를 못 잡는다.
        k = cls.src.index("def secret_write(")
        cls.writer = cls.src[k:cls.src.index("def secret_remove(")]

    # N1. 목록은 키만 준다
    def test_secret_api(self):
        """SecretApi 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_keys_only"):
                self.assertIn('"key": k', self.listing)
                self.assertNotIn("secret_value", self.listing,
                                 "목록이 값을 읽고 있다")

            # B1. 경로도 주지 않는다 — 값이 아니어도 필요 없는 것은 흘리지 않는다
        with self.subTest("b1_no_paths"):
                self.assertIn('"where"', self.listing)
                # 가려진 이름도 함께 — 목록에 안 나오는 것이 "사라졌다"로 읽히면 안 된다
                self.assertIn('"shadowed"', self.listing)
                self.assertNotIn("os.path.relpath(p0", self.listing)
                self.assertNotIn('"path"', self.listing)

            # N2. 넣을 때 값을 응답에 담지 않는다
        with self.subTest("n2_set_echoes_key_only"):
                # 돌려주는 것은 키·둔 곳·가려짐뿐이다 — 값은 어디에도 없다
                m = re.search(r'self\._json\(\{"ok": True, "key": key, "where": where,',
                              self.setter)
                self.assertIsNotNone(m, "set 응답이 키·둔 곳만 담지 않는다")
                self.assertNotIn("val}", self.setter)
                self.assertNotIn('"value"', self.setter.split("self._json")[-1])

            # N3. **쓰는 자리는 한 곳** — 화면과 CLI 가 같은 함수를 지난다
        with self.subTest("n3_one_place_writes"):
                self.assertIn("secret_write(actor, key, val, where)", self.setter,
                              "API 가 파일을 직접 쓴다 — CLI 와 두 벌이 된다")
                self.assertNotIn("os.open(", self.setter, "핸들러가 파일을 직접 연다")
                cli = self.src[self.src.index("def cmd_secret("):]
                cli = cli[:cli.index("# ------------------------------------------- 대화")]
                self.assertIn("secret_write(user, key, val, secret_where(args))", cli,
                              "CLI 가 다른 길로 쓴다")

            # N4. 바깥으로 못 쓸 때 **조용히 안으로 떨어뜨리지 않는다**
        with self.subTest("n4_external_refusal_is_loud"):
                self.assertIn('if where == "external":', self.writer)
                self.assertIn('if st != "ok":', self.writer)
                self.assertIn("raise ValueError(SECRET_EXT_BLOCK", self.writer,
                              "바깥을 못 쓰는데 막지 않는다")

            # B2. 파일 권한을 좁힌다 — 같은 머신의 다른 계정이 읽으면 안 된다
        with self.subTest("b2_permissions"):
                self.assertIn("0o700", self.writer)
                self.assertIn("0o600", self.writer)

            # B3. 키 형식을 가린다 — 경로를 벗어나는 이름을 받지 않는다
        with self.subTest("b3_key_validated"):
                self.assertIn("SECRET_KEY_RE.fullmatch", self.writer)
                import importlib.machinery, importlib.util
                spec = importlib.util.spec_from_loader(
                    "s9_sec", importlib.machinery.SourceFileLoader("s9_sec", S9))
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                for bad in ("../x", "a/b", "", "a b"):
                    self.assertIsNone(m.SECRET_KEY_RE.fullmatch(bad), bad)
                self.assertIsNotNone(m.SECRET_KEY_RE.fullmatch("API_TOKEN"))

            # F1. 빈 값은 넣지 않는다 — 빈 비밀은 "지워졌나 안 넣었나"를 흐린다
        with self.subTest("f1_empty_refused"):
            self.assertIn("빈 값은 저장하지 않는다", self.writer)

if __name__ == "__main__":
    unittest.main()
