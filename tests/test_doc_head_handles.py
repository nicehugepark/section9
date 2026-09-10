"""문서 머리 표의 두 줄 — TOKENS 와 PROJECT (REQ-20260907-014 · REQ-20260907-010).

카드가 이미 말하는 것을 문서 머리도 같은 말로 말해야 한다. 지키는 것은 둘이다.

  ① **토큰 한 줄은 카드와 같은 함수가 짓는다** — 「출력 · 입력 · 캐시」 글자도
     넷을 따로 적는 title 도 `tokensLineHTML` 한 곳에서 나온다. 기록이 없는
     문서에는 행 자체가 서지 않는다(0 으로 그리면 「안 썼다」로 읽힌다).
  ② **보이는 글자가 곧 손잡이다** — PROJECT 칸이 카드와 같은 `projBtnHTML` 로
     서고, 누르면 카드가 쓰는 그 길(events.js 위임 → projectDoc → /api/doc/set)
     로 들어간다. 새 API 도 새 창도 만들지 않는다.

소스 글자를 대조하지 않는다 — 실서버를 띄우고 실브라우저에서 문서 하나를
실제로 그려 그 표를 읽는다. 문서는 vault 의 그때 사정에 매이지 않도록
`/api/doc` 응답만 가로채 손에 쥐여 준다.

실행: python3 tests/ doc_head_handles
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

# 문서 하나를 손에 쥐여 주고 머리 표를 읽는 한 벌.
ROWS = r"""
(async () => {
  const fetch0 = window.fetch, w0 = window.__whoami, p0 = window.__projects;
  /* 신원 위에 role 만 덮어쓴다 — `w0 || {}` 로 물러나면 신원이 아직 안 온 판에서
     화면이 그 사이 받아 온 진짜 신원으로 role 을 덮어써(loadWhoami) 이 블록이
     정한 얼굴과 갈린다. 전제가 깨지면 전제가 실패하게 둔다. */
  if (!w0) throw new Error('신원이 아직 안 왔다 — 준비 신호가 재료를 안 기다렸다');
  window.__projects = [{slug: 'demo', title: '데모', members: []}];
  const base = {type: 'request', status: 'in-progress', title: '견본',
                user: 'x', size: 'S', project: 'demo',
                created: '2026-09-07T00:00:00+09:00'};
  const cell = td => ({
    text: td.textContent.trim(),
    tag: (td.firstElementChild || {}).tagName || '',
    title: (td.querySelector('[title]') || {getAttribute: () => ''})
             .getAttribute('title') || '',
    set: (td.querySelector('[data-projset]') || {getAttribute: () => null})
           .getAttribute('data-projset')});
  const show = async meta => {
    window.fetch = async (url, opt) => String(url).includes('/api/doc?')
      ? {ok: true, json: async () => ({meta, body: '', path: 'vault/x.md'})}
      : fetch0(url, opt);
    /* 색인에도 같은 줄을 둔다 — 문서 화면의 벨트·정책은 카탈로그 행을 먹는다. */
    const was = catalog;
    catalog = was.concat([Object.assign({tags: []}, meta)]);
    try { await loadDoc(meta.id); }
    finally { window.fetch = fetch0; catalog = was; }
    const v = document.querySelector('#viewer');
    const out = {keys: [], row: {}};
    for (const tr of v.querySelectorAll('.metatbl tr')){
      const k = tr.children[0].textContent.trim();
      out.keys.push(k);
      out.row[k] = cell(tr.children[1]);
    }
    return out;
  };
  const mk = (id, extra) => Object.assign({}, base, {id}, extra || {});
  const tok = {in: 708, out: 5391, cache_read: 2208961, cache_create: 130361};
  const out = {};
  window.__whoami = Object.assign({}, w0, {role: 'admin'});
  out.withTokens = await show(mk('REQ-T1', {tokens: tok}));
  out.noTokens = await show(mk('REQ-T2'));
  out.badTokens = await show(mk('REQ-T3', {tokens: ''}));
  out.numTokens = await show(mk('REQ-T4', {tokens: 12345}));
  // 카드와 같은 함수인가 — 같은 입력이 같은 글자를 낸다
  out.cardLine = tokensLineHTML({tokens: tok});
  // 손잡이의 얼굴들
  out.done = await show(mk('REQ-T5', {status: 'done'}));
  out.doc = await show({id: 'DOC-T1', type: 'knowledge', status: 'published',
                        title: '견본', user: 'x', project: 'demo',
                        created: '2026-09-07T00:00:00+09:00'});
  out.bare = await show(mk('REQ-T6', {project: ''}));
  out.doneBare = await show(mk('REQ-T7', {status: 'done', project: ''}));
  window.__whoami = Object.assign({}, w0, {role: 'viewer'});
  out.viewer = await show(mk('REQ-T8'));
  window.__whoami = w0;
  window.__projects = p0;
  return out;
})()
"""

# 실제로 눌러 본다 — 창이 뜨고, 고른 값이 카드와 같은 경로로 나간다.
CLICK = r"""
(async () => {
  const fetch0 = window.fetch, choose0 = window.s9choose;
  const w0 = window.__whoami, p0 = window.__projects;
  if (!w0) throw new Error('신원이 아직 안 왔다 — 준비 신호가 재료를 안 기다렸다');
  window.__whoami = Object.assign({}, w0, {role: 'admin'});
  window.__projects = [{slug: 'demo', title: '데모', members: []},
                       {slug: 'next', title: '다음', members: []}];
  const meta = {id: 'REQ-T9', type: 'request', status: 'in-progress',
                title: '견본', user: 'x', size: 'S', project: 'demo',
                created: '2026-09-07T00:00:00+09:00'};
  const sent = {};
  window.fetch = async (url, opt) => {
    if (String(url).includes('/api/doc/set')){
      sent.url = String(url);
      sent.body = JSON.parse(opt.body);
      return {ok: true, json: async () => ({ok: false, error: '거절 문장'})};
    }
    if (String(url).includes('/api/doc?'))
      return {ok: true, json: async () => ({meta, body: '', path: 'vault/x.md'})};
    return fetch0(url, opt);
  };
  const asked = {};
  window.s9choose = async o => { asked.opts = (o.items || o.options || []).length;
                                 return {key: 'next'}; };
  const was = catalog;
  catalog = was.concat([Object.assign({tags: []}, meta)]);
  try{
    await loadDoc(meta.id);
    const b = document.querySelector('.metatbl [data-projset]');
    if (!b) return {clicked: false};
    b.click();                     // 위임 한 길로 들어가는지까지 본다
    for (let i = 0; i < 40 && !sent.body; i++)
      await new Promise(r => setTimeout(r, 50));
    const d = document.querySelector('.dlgbox');
    const no = d && d.querySelector('.dlgno, .dlgyes');
    if (no) no.click();
    return {clicked: true, sent, showing:
      (document.querySelector('#viewer') || {}).dataset.showing || ''};
  } finally {
    catalog = was;
    window.fetch = fetch0;
    window.s9choose = choose0;
    window.__whoami = w0;
    window.__projects = p0;
  }
})()
"""


class TheDocumentHeadCarriesTheSameTwoLines(unittest.TestCase):
    """실서버 + 실브라우저 — 문서를 실제로 그려 그 표를 읽는다."""

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
        cls.marker = "s9dochead-%d" % os.getpid()
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
                 "http://127.0.0.1:%d/#docs" % cls.port],
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
            # 이 시험은 손잡이의 얼굴을 신원의 role 로 가른다(admin/viewer) —
            # 그 신원까지 이름으로 적어 기다린다. 준비 신호를 여기서 손으로
            # 짓지 않는 까닭은 cdpreal.wait_ready 에 있다 (REQ-20260907-057).
            wait_ready(cls.ws, needs=("whoami",), sels="#viewer")
            cls.rows = cls.await_(ROWS)
            cls.click = cls.await_(CLICK)
            unmeasured = [k for k in ("rows", "click")
                          if getattr(cls, k) is None]
        except AssertionError:
            # 화면이 터진 것은 브라우저가 없는 것이 아니다 — 건너뛰지 않는다.
            cls.tearDownClass()
            raise
        except (ConnectionError, StopIteration, OSError, RuntimeError,
                urllib.error.URLError) as e:
            cls.tearDownClass()
            raise unittest.SkipTest("실브라우저 미검증 — %r" % e)
        if unmeasured:
            cls.tearDownClass()
            raise AssertionError("판은 섰는데 재지 못했다: %s"
                                 % ", ".join(unmeasured))

    @classmethod
    def await_(cls, expr):
        r = cls.ws.call("Runtime.evaluate", expression=expr,
                        returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            # 브라우저가 없어 못 재는 것(건너뛰기)과 판이 섰는데 계약이 안 지켜진
            # 것(실패)은 다른 사실이다 — 뒤엣것을 건너뛰기로 접지 않는다
            # (REQ-20260907-057).
            raise AssertionError("화면에서 터졌다 — %s" % json.dumps(
                r["exceptionDetails"], ensure_ascii=False)[:600])
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

    # ---- ① 토큰 한 줄 -------------------------------------------------------
    def test_the_tokens_row_says_what_the_card_says(self):
        """S1 · S6 — 글자는 카드와 같은 함수가 짓는다."""
        cell = self.rows["withTokens"]["row"].get("tokens")
        self.assertIsNotNone(cell, "tokens 가 있는 문서에 행이 없다")
        self.assertEqual(cell["text"], "출력 5.4k · 입력 708 · 캐시 2.3M")
        box = self.rows["withTokens"]["row"]
        self.assertIn("출력 5.4k", box["tokens"]["text"])
        self.assertIn(cell["text"], self.rows["cardLine"],
                      "카드와 문서가 다른 글자를 짓는다 — 함수가 갈렸다")

    def test_the_four_numbers_stay_in_the_title(self):
        """S2 — 합친 캐시 뒤의 넷은 손을 얹었을 때 원값으로 읽힌다."""
        t = self.rows["withTokens"]["row"]["tokens"]["title"]
        for n in ("5391", "708", "2208961", "130361"):
            self.assertIn(n, t, "title 에 %s 가 없다" % n)

    def test_no_record_means_no_row(self):
        """S3 · S4 — 기록이 없거나 모양이 다르면 행이 서지 않는다(0 금지)."""
        for k in ("noTokens", "badTokens", "numTokens"):
            self.assertNotIn("tokens", self.rows[k]["keys"],
                             "%s 에서 없는 값을 그렸다" % k)

    def test_the_row_sits_right_after_size(self):
        """S5 — 크기(접수 때) 다음에 실제로 든 값이 온다."""
        keys = self.rows["withTokens"]["keys"]
        self.assertIn("size", keys)
        self.assertEqual(keys[keys.index("size") + 1], "tokens")

    # ---- ② 프로젝트 손잡이 --------------------------------------------------
    def test_the_project_cell_is_the_handle(self):
        """S1 — 살아 있는 요청에서는 그 글자가 곧 버튼이다."""
        c = self.rows["withTokens"]["row"]["project"]
        self.assertEqual(c["tag"], "BUTTON")
        self.assertEqual(c["text"], "demo")
        self.assertEqual(c["set"], "REQ-T1", "누를 문서를 안 들고 있다")
        self.assertIn("눌러서 바꿉니다", c["title"])

    def test_the_places_that_cannot_be_pressed(self):
        """S2 · S3 · S4 — 카드와 같은 규칙으로 얼굴이 갈린다."""
        for k in ("done", "doc", "viewer"):
            c = self.rows[k]["row"]["project"]
            self.assertEqual(c["tag"], "SPAN", "%s 에 버튼이 섰다" % k)
            self.assertIsNone(c["set"])
            self.assertEqual(c["text"], "demo")
        self.assertNotIn("project", self.rows["doneBare"]["keys"],
                         "고칠 수 없는 빈 사실이 행으로 섰다")
        b = self.rows["bare"]["row"]["project"]
        self.assertEqual(b["tag"], "BUTTON")
        self.assertEqual(b["text"], "프로젝트 없음")

    def test_pressing_it_goes_the_way_the_card_goes(self):
        """S5 · S6 — 창이 뜨고 고른 값이 /api/doc/set 으로 간다(새 API 없음)."""
        c = self.click
        self.assertTrue(c["clicked"], "머리 표에 누를 자리가 없다")
        self.assertIn("/api/doc/set", c["sent"]["url"])
        self.assertEqual(c["sent"]["body"].get("id"), "REQ-T9")
        self.assertEqual(c["sent"]["body"].get("project"), "next")
        self.assertEqual(c["showing"], "REQ-T9",
                         "손잡이 누름이 다른 문서를 여는 누름으로 샜다")


if __name__ == "__main__":
    unittest.main()
