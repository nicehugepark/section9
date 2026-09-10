"""카드에서 프로젝트를 바꾼다 — 필터·손잡이·창의 계약 (REQ-20260906-053-62x6).

프로젝트 없는 요청을 찾아 채우는 일이 여태 터미널에만 있었다(`s9 set <id>
--project <slug>`). 화면은 어느 요청이 어디에 속하는지 말한 적조차 없었으니
고칠 수도 없었다. 이 파일이 지키는 것은 셋이다.

  ① **치울 더미가 보인다** — 프로젝트 필터에 「프로젝트 없음」이 서고, 고르면
     프로젝트가 빈 것만 남는다. 한때 라벨에 건수(N)를 붙였는데 그 수는 카탈로그
     전체(세션·지식 포함)의 것이라 요청만 그리는 Board 에서 「235 인데 하나도 없다」
     가 됐다(REQ-20260909-021) — 숫자는 걷고 거름만 남겼다.
  ② **보이는 글자가 곧 손잡이다** — 카드의 프로젝트 표기 자체를 누른다(담당
     배지가 세운 직접 조작 문법). 요청이 아니거나 끝난 문서, 그리고 아무것도
     쓸 수 없는 관찰 계정에서는 그냥 글자로 선다.
  ③ **판정도 문구도 서버 한 곳이다** — 창은 내가 쓸 수 있는 프로젝트만 내놓고
     (서버가 어차피 거절할 선택지를 손에 쥐여 주지 않는다), 거절당하면 서버가
     낸 문장이 **글자 그대로** 뜬다.

이 파일은 소스 글자를 대조하지 않는다 — 실서버를 띄우고 실브라우저에서 그
함수들을 실제로 불러 돌아온 값을 본다(tests/BUDGET.json 이 세운 방향).

실행: python3 tests/ project_card_screen
"""
import json
import os
import shutil
import subprocess
import time
import unittest
import urllib.error
import urllib.request

from cdpreal import WS, chrome_path, reclaim, wait_ready
from portpool import free_port, wait_server

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S9 = os.path.join(ROOT, "bin", "s9")

# ---- 브라우저 안에서 실제로 부르는 것들 ------------------------------------

# ① 필터: 「프로젝트 없음」 옵션은 서지 않는다 — 프로젝트 없는 문서는 존재하지
#    않아야 하니(REQ-20260909-026) 필터 축이 아니라 결함이다. 옵션은 전체 + slug 뿐이고,
#    slug 를 고르면 그 프로젝트의 것만 남는다.
FILTER = r"""
(() => {
  /* 세 건을 손에 쥐여 주고 화면이 무엇을 세우고 무엇을 거르는지 본다 — vault 에
     지금 마침 프로젝트 없는 문서가 있느냐에 시험이 매이면 계약이 조용히 흔들린다. */
  const el = document.querySelector('#f-project'), keep = el.value;
  const was = catalog;
  const row = (id, project) => ({id, project, type: 'request', status: 'open',
                                 user: 'x', title: id, tags: []});
  catalog = [row('REQ-A', 'demo'), row('REQ-B', ''), row('REQ-C', '')];
  const out = {};
  const isNone = o => /프로젝트 없음/.test(o.textContent) || o.value === '__none__';
  try{
    fillProjects();
    const opts = [...el.options].map(o => ({v: o.value, t: o.textContent}));
    out.first = opts[0];
    out.none = [...el.options].some(isNone);
    out.values = opts.map(o => o.v);
    el.value = 'demo';
    out.rows = filtered().map(r => r.id).sort();
    el.value = keep;
    /* '내 것만' ON 에서도 서지 않는다 — 신원을 고정해 언제나 잰다 (REQ-20260907-057). */
    const w1 = window.__whoami;
    window.__whoami = {user: '__s9mine__', registered: true, role: 'admin'};
    out.me = viewMe();
    const had = localStorage.getItem('s9mine');
    localStorage.setItem('s9mine', '1');
    fillProjects();
    out.mine = [...el.options].some(isNone);
    if (had === null) localStorage.removeItem('s9mine');
    else localStorage.setItem('s9mine', had);
    window.__whoami = w1;
  } finally {
    catalog = was;
    fillProjects();
    el.value = keep;
  }
  return out;
})()
"""

# ②③ 손잡이의 얼굴들과 창의 목록
FACES = r"""
(() => {
  const w0 = window.__whoami, p0 = window.__projects;
  const box = document.createElement('div');
  const read = html => { box.innerHTML = html; const e = box.firstElementChild;
    return e ? {tag: e.tagName, set: e.getAttribute('data-projset') || '',
                text: e.textContent, title: e.getAttribute('title') || ''}
             : null; };
  window.__whoami = Object.assign({}, w0 || {}, {role: 'admin'});
  window.__projects = [{slug: 'demo', title: '데모', members: []}];
  const out = {};
  out.set = read(projBtnHTML(
    {id: 'REQ-1', type: 'request', status: 'in-progress', project: 'demo'}));
  out.bare = read(projBtnHTML(
    {id: 'REQ-2', type: 'request', status: 'in-progress', project: ''}));
  out.done = read(projBtnHTML(
    {id: 'REQ-3', type: 'request', status: 'done', project: 'demo'}));
  out.doc = read(projBtnHTML(
    {id: 'DOC-1', type: 'knowledge', status: 'published', project: 'demo'}));
  out.doneBare = read(projBtnHTML(
    {id: 'REQ-4', type: 'request', status: 'cancelled', project: ''}));
  window.__whoami = Object.assign({}, w0 || {}, {role: 'viewer'});
  out.viewer = read(projBtnHTML(
    {id: 'REQ-5', type: 'request', status: 'in-progress', project: 'demo'}));
  out.viewerBare = read(projBtnHTML(
    {id: 'REQ-6', type: 'request', status: 'open', project: ''}));
  window.__whoami = w0;
  /* 창의 목록 — 내가 contributor 이상인 프로젝트만.

     신원은 여기서 **고정한다.** 종전엔 화면이 받아 둔 whoami 에 기대
     (`viewMe() || '__nobody__'`) 멤버 목록을 지었는데, /api/whoami 는 스크립트가
     다 실린 뒤에 오는 비동기 응답이라 판이 섰다는 신호보다 늦을
     수 있다. 병렬 전체 실행에서 실제로 늦었고, 그때 이 블록의 me 는
     '__nobody__' 인데 projectPick 안의 viewMe() 는 '' 이라 멤버가 한 건도 안 맞아
     목록이 「지금 이것」 하나로 줄었다 — 단독 실행만 통과하던
     'own' not found 간헐 실패의 정체다 (REQ-20260907-055). 이 블록이 재는 것은
     멤버 역할 판정이지 신원을 어디서 받아 오는지가 아니다. */
  window.__whoami = {user: '__s9pick__', registered: true, role: 'admin'};
  const me = viewMe();
  out.me = me;
  window.__projects = [
    {slug: 'mine', title: '내 것', members: [{user: me, active: true,
                                              role: 'contributor'}]},
    {slug: 'own', title: '내가 주인', members: [{user: me, active: true,
                                                 role: 'owner'}]},
    {slug: 'watch', title: '보기만', members: [{user: me, active: true,
                                                role: 'viewer'}]},
    {slug: 'gone', title: '만료', members: [{user: me, active: false,
                                             role: 'owner'}]},
    {slug: 'other', title: '남의 것', members: [{user: '__x__', active: true,
                                                 role: 'owner'}]}];
  out.pick = projectPick({id: 'REQ-1', project: 'mine'});
  out.pickBare = projectPick({id: 'REQ-2', project: ''});
  out.pickStranger = projectPick({id: 'REQ-3', project: 'other'});
  window.__projects = undefined;
  out.pickLost = projectPick({id: 'REQ-4', project: ''});
  window.__projects = p0;
  window.__whoami = w0;
  return out;
})()
"""

# ③ 거절 문장은 서버의 것 그대로 — 창을 실제로 띄워 그 글자를 읽는다
REFUSE = r"""
(async () => {
  const choose0 = window.s9choose, fetch0 = window.fetch;
  const sent = {};
  window.s9choose = async () => ({key: 'demo'});
  window.fetch = async (url, opt) => {
    // 우리 경로만 가로챈다 — 화면은 이 사이에도 제 일(폴링)을 계속한다.
    if (!String(url).includes('/api/doc/set')) return fetch0(url, opt);
    sent.url = String(url);
    sent.body = JSON.parse(opt.body);
    return {ok: true, json: async () => ({ok: false,
      error: '프로젝트 「demo」의 멤버가 아닙니다 — 서버가 낸 그 문장'})};
  };
  try{
    await projectDoc('REQ-20260906-053-62x6');
    await new Promise(r => setTimeout(r, 120));
    const d = document.querySelector('.dlgbox');
    const out = {sent, open: !d.hidden,
                 title: (d.querySelector('.dlgt') || {}).textContent || '',
                 desc: (d.querySelector('.dlgs') || {}).textContent || ''};
    const no = d.querySelector('.dlgno, .dlgyes');
    if (no) no.click();
    return out;
  } finally {
    window.s9choose = choose0;
    window.fetch = fetch0;
  }
})()
"""


class TheProjectIsChangedFromTheCard(unittest.TestCase):
    """실서버 + 실브라우저 — 화면의 함수를 실제로 불러 값을 본다."""

    srv = None
    proc = None
    ws = None
    prof_wsl = None

    @classmethod
    def setUpClass(cls):
        chrome = chrome_path(pixel_contract=False)
        if chrome is None:
            raise unittest.SkipTest("실브라우저 미검증 — Chrome/Edge 를 찾지 못했다")
        cls.port = free_port()
        cls.srv = subprocess.Popen(
            [S9, "serve", "--host", "127.0.0.1", "--port", str(cls.port)],
            env={**os.environ, "S9_ROOT": ROOT, "S9_REWORK_WATCH": "off"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.marker = "s9prjcard-%d" % os.getpid()
        cls.win = chrome.startswith("/mnt/")
        cls.prof_wsl = (("/mnt/c/Temp/" + cls.marker) if cls.win
                        else "/tmp/" + cls.marker)
        prof_arg = ("C:\\Temp\\" + cls.marker) if cls.win else cls.prof_wsl
        if cls.win:
            os.makedirs("/mnt/c/Temp", exist_ok=True)
        try:
            wait_server(cls.port)
            cls.proc = subprocess.Popen(
                [chrome, "--headless=new", "--disable-gpu",
                 "--user-data-dir=" + prof_arg, "--no-first-run",
                 "--no-default-browser-check", "--disable-extensions",
                 "--disable-background-networking", "--remote-debugging-port=0",
                 "--window-size=1440,900",
                 "http://127.0.0.1:%d/" % cls.port],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            dev = os.path.join(cls.prof_wsl, "DevToolsActivePort")
            cdp = None
            for _ in range(160):
                if os.path.exists(dev):
                    try:
                        with open(dev, encoding="utf-8") as f:
                            cdp = int(f.read().splitlines()[0])
                        break
                    except (ValueError, IndexError, OSError):
                        pass
                time.sleep(0.25)
            if cdp is None:
                raise ConnectionError("DevToolsActivePort 미출현")
            pages = json.loads(urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % cdp, timeout=10).read())
            page = next(p for p in pages if p.get("type") == "page")
            cls.ws = WS(page["webSocketDebuggerUrl"])
            # 창의 목록 판정이 신원 위에 서므로 신원까지 기다린다 — 판이
            # 섰다는 신호만으로 재면 조용히 다른 것을 잰다 (REQ-20260907-055).
            wait_ready(cls.ws, needs=("whoami",), sels="#f-project")
            cls.filter = cls.await_(FILTER)
            cls.faces = cls.await_(FACES)
            cls.refuse = cls.await_(REFUSE)
            for k in ("filter", "faces", "refuse"):
                if getattr(cls, k) is None:
                    raise ConnectionError("%s 를 재지 못했다" % k)
        except (ConnectionError, StopIteration, OSError, RuntimeError,
                urllib.error.URLError) as e:
            cls.tearDownClass()
            raise unittest.SkipTest("실브라우저 미검증 — %r" % e)

    @classmethod
    def await_(cls, expr):
        r = cls.ws.call("Runtime.evaluate", expression=expr,
                        returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    @classmethod
    def tearDownClass(cls):
        if cls.ws is not None:
            try:
                cls.ws.close()
            except OSError:
                pass
            cls.ws = None
        if cls.proc is not None:
            try:
                cls.proc.terminate()
            except OSError:
                pass
            cls.proc = None
        reclaim(cls.marker, cls.win)
        if cls.srv is not None:
            cls.srv.terminate()
            try:
                cls.srv.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.srv.kill()
            cls.srv = None
        if cls.prof_wsl:
            shutil.rmtree(cls.prof_wsl, ignore_errors=True)

    # ---- ① 「프로젝트 없음」 옵션이 없다 ---------------------------------------
    def test_the_filter_has_no_bare_option(self):
        """옵션은 전체 + slug 뿐이다 — 프로젝트 없는 문서가 둘 있어도 그것을 고르는
        축은 서지 않는다(REQ-20260909-026: 그런 문서는 있으면 안 되는 결함이다)."""
        f = self.filter
        self.assertEqual(f["first"]["v"], "", "첫 옵션은 여전히 전체다")
        self.assertFalse(f["none"], "「프로젝트 없음」 옵션이 다시 섰다 (REQ-20260909-026)")
        self.assertNotIn("__none__", f["values"])
        self.assertIn("demo", f["values"], "slug 옵션이 서지 않았다")

    def test_the_filter_keeps_only_that_project(self):
        """slug 를 고르면 그 프로젝트의 것만 남는다 — 라벨과 거름이 같다."""
        f = self.filter
        self.assertEqual(f["rows"], ["REQ-A"],
                         "라벨이 말한 것과 실제로 걸러진 것이 다르다")
        self.assertEqual(f.get("me"), "__s9mine__",
                         "화면이 읽는 신원이 시험이 고정한 값이 아니다 — "
                         "'내 것만' 가드의 전제가 안 섰다")
        self.assertFalse(f["mine"], "'내 것만' 에서도 그 옵션은 서지 않는다")

    # ---- ② 보이는 글자가 곧 손잡이다 ---------------------------------------
    def test_the_words_on_the_card_are_the_handle(self):
        """slug 가 곧 버튼이고, 빈 자리에는 「프로젝트 없음」이 선다."""
        s, b = self.faces["set"], self.faces["bare"]
        self.assertEqual(s["tag"], "BUTTON")
        self.assertEqual(s["text"], "demo", "카드는 slug 하나만 적는다")
        self.assertEqual(s["set"], "REQ-1", "누를 문서를 안 들고 있다")
        self.assertIn("데모", s["title"], "제목은 title 로 붙는다")
        self.assertIn("눌러서 바꿉니다", s["title"])
        self.assertEqual(b["tag"], "BUTTON")
        self.assertEqual(b["text"], "프로젝트 없음")
        self.assertEqual(b["title"], "눌러서 프로젝트를 정합니다")

    def test_the_finished_and_the_watcher_get_plain_words(self):
        """끝난 문서·요청 아닌 문서·관찰 계정에는 손잡이가 서지 않는다."""
        for key in ("done", "doc", "viewer"):
            face = self.faces[key]
            self.assertIsNotNone(face, "%s: 값이 있는데 글자가 사라졌다" % key)
            self.assertEqual(face["tag"], "SPAN",
                             "%s: 못 하는 조작에 버튼이 섰다" % key)
            self.assertEqual(face["set"], "", "%s: 누를 문서를 들고 있다" % key)
            self.assertEqual(face["text"], "demo")
        for key in ("doneBare", "viewerBare"):
            self.assertIsNone(self.faces[key],
                              "%s: 고칠 수 없는 빈 사실을 세웠다" % key)

    # ---- ③ 판정도 문구도 서버 한 곳이다 ------------------------------------
    def test_the_window_offers_only_what_i_can_write(self):
        """창에는 내가 contributor 이상인 프로젝트만 선다 — 「없음」(빼는 길)은
        걷었다(REQ-20260909-026: 프로젝트 없는 문서는 두지 않는다)."""
        pick = self.faces["pick"]
        self.assertTrue(self.faces["me"],
                        "화면의 신원이 비었다 — 목록 판정의 전제가 안 섰다")
        keys = [it["key"] for it in pick["items"]]
        self.assertTrue(all(keys), "key 가 빈 항목이 있다 — 취소와 구별되지 않는다")
        self.assertNotIn("없음", [it["label"] for it in pick["items"]],
                         "빼는 길이 다시 섰다 (REQ-20260909-026)")
        self.assertNotIn("__none__", keys)
        self.assertIn("mine", keys)
        self.assertIn("own", keys)
        for out in ("watch", "gone", "other"):
            self.assertNotIn(out, keys,
                             "서버가 거절할 선택지(%s)를 쥐여 줬다" % out)
        cur = [it for it in pick["items"] if it["cur"]]
        self.assertEqual([it["key"] for it in cur], ["mine"])
        self.assertEqual(cur[0]["note"], "지금 이것")
        # 지금 속한 곳이 내 목록에 없어도 창이 거짓말하지 않는다
        self.assertIn("other",
                      [it["key"] for it in self.faces["pickStranger"]["items"]])
        # 빈 자리(결함 문서)에서도 「없음」은 서지 않는다 — 어느 것도 「지금 이것」이
        # 아니고, 옮길 곳만 선다 (REQ-20260909-026)
        bare = self.faces["pickBare"]["items"]
        self.assertTrue(bare, "빈 자리에 옮길 곳이 하나도 없다")
        self.assertFalse(any(it["cur"] for it in bare))
        self.assertNotIn("없음", [it["label"] for it in bare])
        # 못 받은 것과 없는 것은 다른 화면이다
        self.assertIn("받지 못했습니다", self.faces["pickLost"]["empty"])
        self.assertEqual(self.faces["pickLost"]["items"], [])
        self.assertIn("멤버로 들어가면", pick["empty"])

    def test_the_refusal_is_the_servers_own_sentence(self):
        """거절 창에는 서버가 낸 문장이 글자 그대로 뜬다."""
        r = self.refuse
        self.assertEqual(r["sent"]["url"], "/api/doc/set",
                         "저장 경로가 하나가 아니다")
        self.assertEqual(r["sent"]["body"]["project"], "demo")
        self.assertEqual(r["sent"]["body"]["id"], "REQ-20260906-053-62x6")
        self.assertTrue(r["open"], "거절을 말하는 창이 안 떴다")
        self.assertIn("프로젝트를 바꾸지 못했습니다", r["title"])
        self.assertEqual(
            r["desc"],
            "프로젝트 「demo」의 멤버가 아닙니다 — 서버가 낸 그 문장",
            "서버 문장을 화면이 고쳐 썼다")


if __name__ == "__main__":
    unittest.main()
