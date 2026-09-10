"""카탈로그가 없는 뿌리에서도 시험은 진짜 코퍼스를 본다 (REQ-20260910-054).

`index/catalog.jsonl` 은 vault/ 에서 만드는 파생 인덱스라 커밋하지 않는다
(projects/section9/CONTEXT.md). 그래서 **갓 만든 worktree 와 갓 clone 한
저장소에는 없다** — vault/ 는 track 되니 문서는 다 있는데 색인만 없다.

실측 2026-09-10 (worktree state/worktrees/w-910-052-62x6 에서 python3 tests/):
failures=12 errors=2, 다섯 파일. test_short_ref 는 `len(refs)==0` 으로
ZeroDivisionError 까지 냈다. 코드는 멀쩡한데 자리 때문에 지는 실패라,
worktree 를 받는 작업자마다 이 실패를 다시 만났다.

고정하는 계약 셋.
1. 카탈로그가 없고 vault/ 에 문서가 있으면 러너가 **한 번 만든다**.
2. 이미 있으면 손대지 않는다 — 진짜로 깨진 카탈로그는 그대로 져야 드러난다.
3. vault/ 가 없는 빈 뿌리에서는 아무것도 하지 않는다.

실행: python3 tests/ worktree_catalog
"""
import importlib.machinery
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def runner():
    """러너(tests/__main__.py)를 모듈로 싣는다 — main() 은 돌리지 않는다."""
    path = os.path.join(HERE, "__main__.py")
    spec = importlib.util.spec_from_loader(
        "s9testrunner", importlib.machinery.SourceFileLoader(
            "s9testrunner", path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class WorktreeCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = runner()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="s9wtcat-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _fake_root(self, docs=3):
        """worktree 를 닮은 뿌리 — bin/ 과 vault/ 는 있고 index/ 는 없다.

        bin/ 은 심볼릭 링크다: 본체는 `S9_ROOT` 로 뿌리를 받으니 사본이 필요
        없고, 4.5MB 를 매번 복사하면 이 시험이 곧 값이 된다.
        """
        os.symlink(os.path.join(REPO, "bin"), os.path.join(self.tmp, "bin"))
        vault = os.path.join(self.tmp, "vault", "requests")
        os.makedirs(vault)
        for i in range(docs):
            doc = f"REQ-20260910-{900 + i}-wtct"
            with open(os.path.join(vault, doc + ".md"), "w",
                      encoding="utf-8") as f:
                f.write("---\n"
                        f"id: {doc}\n"
                        "type: request\n"
                        f"title: 카탈로그 시험 {i}\n"
                        "status: open\n"
                        "user: nicehugepark\n"
                        "created: 2026-09-10T00:00:00+09:00\n"
                        "---\n\n## Original\n\n색인 대상 한 건.\n")
        return self.tmp

    def _cat(self, root):
        return os.path.join(root, "index", "catalog.jsonl")

    # ① 없으면 만든다
    def test_a_root_without_a_catalog_gets_one(self):
        root = self._fake_root()
        self.assertFalse(os.path.exists(self._cat(root)), "전제가 틀렸다")
        made = self.mod.ensure_catalog(root)
        self.assertTrue(made, "카탈로그를 만들었다고 답하지 않았다")
        self.assertTrue(os.path.exists(self._cat(root)),
                        "만들었다면서 파일이 없다")
        with open(self._cat(root), encoding="utf-8") as f:
            rows = [l for l in f if l.strip()]
        self.assertGreaterEqual(len(rows), 3,
                                "vault 의 문서가 색인에 들어오지 않았다")

    # ② 있으면 손대지 않는다 — 깨진 카탈로그는 그대로 져야 드러난다
    def test_an_existing_catalog_is_left_alone(self):
        root = self._fake_root()
        os.makedirs(os.path.join(root, "index"))
        with open(self._cat(root), "w", encoding="utf-8") as f:
            f.write("")            # 비었어도 **있는** 것이다
        before = os.stat(self._cat(root))
        self.assertFalse(self.mod.ensure_catalog(root),
                         "있는 카탈로그를 다시 만들었다")
        after = os.stat(self._cat(root))
        self.assertEqual((before.st_mtime_ns, before.st_size),
                         (after.st_mtime_ns, after.st_size),
                         "손대지 않기로 한 파일이 바뀌었다")

    # ③ 빈 뿌리는 이 함수의 몫이 아니다
    def test_a_root_without_a_vault_is_not_touched(self):
        self.assertFalse(self.mod.ensure_catalog(self.tmp))
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "index")),
                         "색인할 문서도 없는데 index/ 를 만들었다")

    # ④ 러너가 실제로 이 전제를 세우는가 — 부르는 자리가 있어야 계약이다
    def test_the_runner_calls_it_before_running(self):
        with open(os.path.join(HERE, "__main__.py"), encoding="utf-8") as f:
            src = f.read()
        body = src.split("def main()", 1)
        self.assertEqual(len(body), 2, "main() 을 못 찾았다")
        self.assertIn("ensure_catalog()", body[1],
                      "러너가 실행 전에 카탈로그 전제를 세우지 않는다")


if __name__ == "__main__":
    unittest.main()
