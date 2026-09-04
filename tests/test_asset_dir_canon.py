"""첨부 폴더는 문서의 정식 id 하나다 (REQ-20260828-026-62x6).

사용자: "만들어지는 asset 디렉토리가 해시값이 없는 게 존재하는데 중복 발생
가능성이 있는것아닌가?"

`doc_asset_dir(doc_id)` 가 **부른 사람이 넘긴 문자열**을 그대로 폴더 이름으로
썼다. `locate()` 는 짧은 id 도 alias 로 찾아 주므로 문서는 제대로 찾고 폴더만
짧은 이름으로 만들어진다. 결과 셋:

  ① 한 문서의 첨부가 두 폴더로 갈린다 (REQ-20260828-007 은 짧은 폴더 7개 +
     정식 폴더 3개)
  ② 정식 id 로 물으면 못 찾는다 — /api/asset?doc=<짧은id> 는 200, <정식id> 는 404
  ③ 접미사는 **인스턴스 식별자**다. 짧은 이름은 그것을 버리므로 다른 인스턴스의
     같은 번호 문서와 폴더 이름이 겹친다. 인스턴스 간 병합에서 실제 충돌이 난다.

폴더 이름은 부른 사람의 문자열이 아니라 **문서가 스스로 밝히는 정식 id** 여야
한다. 그리고 이미 갈린 것은 합치되 **본문 참조도 함께 고쳐 써야** 한다 —
파일만 옮기고 참조를 두면 화면이 깨진다.

격리: S9_ROOT=mktemp. 실행: python3 tests/ asset_dir_canon
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
S9 = os.path.join(HERE, "..", "bin", "s9")


class AssetDirCanon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="s9adc-")
        cls.env = {**os.environ, "S9_ROOT": cls.root, "S9_MACHINE": "testbox"}
        cls.env.pop("S9_SESSION", None)
        cls.cli("init")
        cls.cli("user", "add", "alice")
        cls.rid = cls.cli("new", "request", "--title", "첨부 시험",
                          "--summary", "s", "--size", "S", "--user", "alice",
                          "--body", "x").split()[0]
        assert "-" in cls.rid
        cls.short = "-".join(cls.rid.split("-")[:3])   # 접미사 뗀 형태
        spec = importlib.util.spec_from_loader(
            "s9_adc", importlib.machinery.SourceFileLoader("s9_adc", S9))
        os.environ["S9_ROOT"] = cls.root
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("S9_ROOT", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def cli(cls, *a):
        r = subprocess.run([S9, *a], capture_output=True, text=True,
                           env=cls.env, stdin=subprocess.DEVNULL)
        assert r.returncode == 0, f"{a}: {r.stderr}"
        return r.stdout.strip()

    # N1. 짧은 id 로 불러도 정식 id 폴더를 준다.
    def test_asset_dir_canon(self):
        """AssetDirCanon 의 계약을 한 항목으로 — 검사는 그대로다."""
        with self.subTest("n1_short_id_gives_canonical_dir"):
                self.assertNotEqual(self.short, self.rid, "시험 전제가 깨졌다")
                self.assertEqual(os.path.basename(self.m.doc_asset_dir(self.short)),
                                 self.rid,
                                 "부른 사람의 문자열이 폴더 이름이 된다 — "
                                 "한 문서의 첨부가 두 폴더로 갈린다")

            # N2. 정식 id 로 부르면 그대로.
        with self.subTest("n2_canonical_id_unchanged"):
                self.assertEqual(os.path.basename(self.m.doc_asset_dir(self.rid)),
                                 self.rid)

            # B1. 문서가 없으면 "" — 기존 계약.
        with self.subTest("b1_missing_doc_is_empty"):
                self.assertEqual(self.m.doc_asset_dir("REQ-20260101-999"), "")

            # B2. 이미 갈린 폴더를 합치고 본문 참조도 고쳐 쓴다.
        with self.subTest("b2_merge_moves_files_and_rewrites_body"):
                path = self.m.locate(self.rid)
                legacy = os.path.join(os.path.dirname(path), "assets", self.short)
                os.makedirs(legacy, exist_ok=True)
                with open(os.path.join(legacy, "a.png"), "wb") as f:
                    f.write(b"A")
                meta, body = self.m.read_doc(path)
                self.m.write_doc(path, meta,
                                 body + f"\n[Image: assets/{self.short}/a.png]\n")

                moved = self.m.merge_legacy_asset_dirs()
                self.assertGreaterEqual(len(moved), 1, "합친 것이 없다")

                canon = self.m.doc_asset_dir(self.rid)
                self.assertTrue(os.path.isfile(os.path.join(canon, "a.png")),
                                "파일이 정식 폴더로 안 왔다")
                self.assertFalse(os.path.isdir(legacy), "짧은 폴더가 남았다")
                _m2, body2 = self.m.read_doc(path)
                self.assertIn(f"assets/{self.rid}/a.png", body2,
                              "본문 참조를 안 고쳤다 — 파일만 옮기면 화면이 깨진다")
                self.assertNotIn(f"assets/{self.short}/a.png", body2)

            # B3. 같은 이름이 양쪽에 있으면 **덮지 않는다** — 첨부 소실 금지.
        with self.subTest("b3_name_clash_never_overwrites"):
            path = self.m.locate(self.rid)
            canon = self.m.doc_asset_dir(self.rid, make=True)
            with open(os.path.join(canon, "clash.png"), "wb") as f:
                f.write(b"CANON")
            legacy = os.path.join(os.path.dirname(path), "assets", self.short)
            os.makedirs(legacy, exist_ok=True)
            with open(os.path.join(legacy, "clash.png"), "wb") as f:
                f.write(b"LEGACY")

            self.m.merge_legacy_asset_dirs()

            with open(os.path.join(canon, "clash.png"), "rb") as f:
                self.assertEqual(f.read(), b"CANON", "정식 폴더의 파일을 덮었다")
            kept = [n for n in os.listdir(canon) if n.startswith("clash")]
            self.assertEqual(len(kept), 2,
                             f"겹친 파일이 사라졌다: {kept}")

if __name__ == "__main__":
    unittest.main()
