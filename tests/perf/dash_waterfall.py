#!/usr/bin/env python3
"""dash_waterfall.py — 대시보드 탭별 왕복·실패·재시도·그리기 시간 실측 도구 (REQ-20260909-086-62x6).

시험이 아니라 **도구**다: tests/__main__ 은 test_ 접두 파일만 줍는다. 전후 비교용으로
같은 조건에서 두 번 돌려 표를 나란히 놓는 것이 쓰임이다.

무엇을 재나 — 실서버(기본 http://127.0.0.1:9909)를 실제 Chromium(Playwright, `s9 shot`
이 쓰는 Windows 쪽 러너와 같은 것)으로 열고 Board → Docs → 문서 하나 열기 → Graph →
Audit → Terminal → Settings 를 차례로 누르며 **단계마다**:
  - 왕복: 그 단계가 시작한 뒤 브라우저가 낸 요청 수(전체 / 그중 /api)
  - 실패: 연결 리셋·빈 응답(requestfailed) + 502·503·504 응답
  - 재시도: 같은 method+url 이 실패한 뒤 다시 나간 요청 수(s9Fetch 의 150ms·400ms 재시도)
  - 첫 그리기: 누른 순간부터 화면(#view 또는 body)의 첫 DOM 변경 뒤 첫 프레임까지 ms
  - 마지막 요청 완료: 누른 순간부터 그 단계의 마지막 요청(스트림 제외)이 끝날 때까지 ms
  - 마지막 그리기: 누른 순간부터 마지막 DOM 변경 뒤 프레임까지 ms
  - 재시도 지연(임계경로): 실패→재시도 사슬 중 첫 시도 시작에서 마지막 시도 시작까지의
    최댓값 — 리셋이 없었다면 줄었을 시간의 하한
한 단계는 「스트림(EventSource·/stream·/events·sse)이 아닌 요청이 하나도 진행 중이지
않고 idle-ms(기본 1200ms) 동안 새 요청이 없을 때」 끝난 것으로 본다(상한 max-ms).
runs(기본 3) 회 반복해 중앙값을 표로 낸다. 회마다 새 브라우저 컨텍스트(캐시 없음)다.

사용법:
  python3 tests/perf/dash_waterfall.py                       # 3회, 기본 탭 순서
  python3 tests/perf/dash_waterfall.py --runs 5 --json /tmp/before.json
  python3 tests/perf/dash_waterfall.py --tabs board,docs,audit --verbose
  python3 tests/perf/dash_waterfall.py --compare /tmp/before.json /tmp/after.json   # 두 결과 나란히
러너: /mnt/c/Temp/s9-webkit/node-v*/node.exe + node_modules/playwright (bin/s9.py 의
_shot_pw_direct 와 같은 자리). 없으면 `bin/s9 shot --engine chromium ...` 의 설치 안내를 따른다.
리눅스에서 `node` 와 playwright 가 있으면(--node 로 지정) 그것으로도 돈다.
"""
import argparse
import glob
import json
import os
import re
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PW_DIR_WSL = "/mnt/c/Temp/s9-webkit"
DEFAULT_TABS = "board,docs,graph,audit,terminal,settings"

PROBE_JS = r"""
'use strict';
const { chromium } = require('playwright');
const [,, url, runsS, tabsCsv, idleS, maxS, headedS] = process.argv;
const runs = parseInt(runsS, 10), idleMs = parseInt(idleS, 10), maxMs = parseInt(maxS, 10);
const tabs = tabsCsv.split(',').filter(Boolean);
const STREAM_RE = /eventsource|\/stream|\/events|sse=|\/api\/terminal\/(sse|tail)|ccstream/i;
const isStream = (r) => r.type === 'eventsource' || STREAM_RE.test(r.url);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// 화면 쪽 관찰자: 누른 순간(t0)과 첫/마지막 DOM 변경 뒤 프레임 시각을 기록한다.
const OBS = `(() => {
  const w = window; w.__s9 = { t0: performance.now(), first: null, last: null, n: 0 };
  if (w.__s9obs) w.__s9obs.disconnect();
  const root = document.getElementById('view') || document.body;
  w.__s9obs = new MutationObserver(() => {
    w.__s9.n++;
    requestAnimationFrame(() => { const t = performance.now();
      if (w.__s9.first === null) w.__s9.first = t; w.__s9.last = t; });
  });
  w.__s9obs.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });
})()`;

async function measure(page, reqs, name, action) {
  const startIdx = reqs.length;
  await page.evaluate(OBS).catch(() => {});
  const t0 = Date.now();
  await action();
  // 끝 판정: 스트림이 아닌 요청이 모두 끝나고 idleMs 동안 새 요청이 없다.
  let timeout = false;
  for (;;) {
    const now = Date.now();
    const mine = reqs.slice(startIdx).filter(r => !isStream(r));
    const inflight = mine.filter(r => r.end === null).length;
    const lastEnd = mine.reduce((m, r) => Math.max(m, r.end || 0, r.start), t0);
    if (inflight === 0 && now - lastEnd >= idleMs && now - t0 >= 300) break;
    if (now - t0 > maxMs) { timeout = true; break; }
    await sleep(50);
  }
  const paint = await page.evaluate(() => {
    const s = window.__s9 || {}; return { t0: s.t0, first: s.first, last: s.last, n: s.n };
  }).catch(() => ({}));
  const mine = reqs.slice(startIdx);
  const rows = mine.map(r => ({
    method: r.method, url: r.url.replace(/^https?:\/\/[^/]+/, ''), type: r.type,
    start: r.start - t0, end: r.end === null ? null : r.end - t0,
    status: r.status, failed: r.failed, err: r.err || '', stream: isStream(r),
  }));
  // 실패·재시도: 같은 method+url 이 실패(리셋·빈 응답·502~504)한 뒤 다시 나간 것.
  const bad = (r) => r.failed || (r.status >= 502 && r.status <= 504);
  const byKey = new Map();
  for (const r of rows.filter(r => !r.stream)) {
    const k = r.method + ' ' + r.url; if (!byKey.has(k)) byKey.set(k, []); byKey.get(k).push(r);
  }
  let retries = 0, retryPathMs = 0;
  const failedUrls = [];
  for (const [k, list] of byKey) {
    list.sort((a, b) => a.start - b.start);
    let seenBad = false, firstBadStart = null;
    for (const r of list) {
      if (seenBad) { retries++; retryPathMs = Math.max(retryPathMs, r.start - firstBadStart); }
      if (bad(r)) { seenBad = true; if (firstBadStart === null) firstBadStart = r.start; failedUrls.push(r.url + (r.err ? ' ' + r.err : ' ' + r.status)); }
    }
  }
  const nonStream = rows.filter(r => !r.stream);
  const api = nonStream.filter(r => r.url.startsWith('/api'));
  const okApi = api.filter(r => !bad(r) && r.end !== null);
  const lastDone = nonStream.reduce((m, r) => Math.max(m, r.end || 0), 0);
  const rel = (v) => (v === null || v === undefined || paint.t0 === undefined) ? null : Math.round(v - paint.t0);
  return {
    step: name, timeout,
    requests: nonStream.length, api: api.length, streams: rows.length - nonStream.length,
    failed: nonStream.filter(bad).length, retries, retry_path_ms: Math.round(retryPathMs),
    first_draw_ms: rel(paint.first), last_draw_ms: rel(paint.last), mutations: paint.n || 0,
    last_done_ms: Math.round(lastDone),
    api_ok_ms_median: okApi.length ? Math.round(median(okApi.map(r => r.end - r.start))) : null,
    api_ok_ms_sum: Math.round(okApi.reduce((s, r) => s + (r.end - r.start), 0)),
    failed_urls: failedUrls, rows,
  };
}
function median(a) { const s = [...a].sort((x, y) => x - y); const n = s.length;
  return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; }

(async () => {
  for (let run = 1; run <= runs; run++) {
    let navResets = 0;
    const browser = await chromium.launch({ headless: headedS !== '1' });
    try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const reqs = []; const idx = new Map();
    page.on('request', (rq) => { const r = { url: rq.url(), method: rq.method(), type: rq.resourceType(),
      start: Date.now(), end: null, status: 0, failed: false, err: '' }; reqs.push(r); idx.set(rq, r); });
    page.on('requestfinished', async (rq) => { const r = idx.get(rq); if (!r) return; r.end = Date.now();
      try { const res = await rq.response(); r.status = res ? res.status() : 0; } catch (e) {} });
    page.on('requestfailed', (rq) => { const r = idx.get(rq); if (!r) return; r.end = Date.now();
      r.failed = true; r.err = (rq.failure() || {}).errorText || 'failed'; });
    const consoleErrs = [];
    page.on('pageerror', (e) => consoleErrs.push(String(e.message || e)));
    const steps = [];
    steps.push(await measure(page, reqs, 'load(#' + tabs[0] + ')', async () => {
      // 첫 탐색도 중계 리셋을 맞는다(실측 2026-09-09: 첫 goto 가 ERR_CONNECTION_RESET) —
      // s9 shot 의 SHOT_NAV_RETRIES 와 같이 소켓 오류만 다시 시도하고, 그 실패는
      // requestfailed 로 이 단계의 실패 수에 남는다.
      for (let a = 0; ; a++) {
        try { await page.goto(url + '/#' + tabs[0], { waitUntil: 'domcontentloaded' }); break; }
        catch (e) { if (a >= 8 || !/net::ERR_|ECONNRESET/.test(String(e))) throw e; navResets++; await sleep(500); }
      }
      await page.evaluate(OBS).catch(() => {});
    }));
    for (let i = 0; i < tabs.length; i++) {
      const t = tabs[i];
      if (!(i === 0 && steps.length)) {   // 첫 탭은 load 가 이미 열었다 — 그래도 한 번 더 누른다(전환 비용)
      }
      steps.push(await measure(page, reqs, 'tab:' + t, async () => {
        await page.click('header [data-tab="' + t + '"]');
      }));
      if (t === 'docs') {
        const sel = '#view .doclist .row[data-doc]';
        try { await page.waitForSelector(sel, { timeout: 10000 }); } catch (e) {}
        const has = await page.$(sel);
        steps.push(await measure(page, reqs, 'docs:open', async () => {
          if (has) await page.click(sel); else throw new Error('문서 목록에 행이 없다: ' + sel);
        }));
      }
    }
    // 회마다 바로 내보낸다 — 뒤 회가 죽어도 앞 회의 실측은 남는다(2026-09-09: 2회째 첫
    // 탐색이 네 번 연속 리셋되어 1회째 결과까지 잃었다).
    process.stdout.write('S9WF-RUN ' + JSON.stringify({ run, steps, page_errors: consoleErrs, nav_resets: navResets }) + '\n');
    } catch (e) {
      process.stdout.write('S9WF-RUN ' + JSON.stringify({ run, steps: [], error: String(e && e.message || e).split('\n')[0], nav_resets: navResets }) + '\n');
    }
    await browser.close();
  }
  process.stdout.write('S9WF-END\n');
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""


def win_path(p):
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", p or "")
    return (m.group(1).upper() + ":\\" + m.group(2).replace("/", "\\")) if m else p


def find_runner(node_arg):
    """(node 실행 파일, 프로브를 둘 디렉터리(WSL 경로), 프로브 경로를 node 에 줄 때의 변환)"""
    if node_arg:
        return node_arg, os.path.join(HERE, ".pw"), (lambda p: p)
    nodes = sorted(glob.glob(os.path.join(PW_DIR_WSL, "node-v*-win-x64", "node.exe")))
    if nodes and os.path.isdir(os.path.join(PW_DIR_WSL, "node_modules", "playwright")):
        return nodes[-1], PW_DIR_WSL, win_path
    return None, None, None


def run_probe(args):
    node, pw_dir, conv = find_runner(args.node)
    if not node:
        sys.stderr.write("dash_waterfall: Playwright 러너가 없다 — `bin/s9 shot --engine chromium <url>` 을 한 번 "
                         "실행하면 설치 안내가 나온다(C:\\Temp\\s9-webkit 에 node + playwright + chromium). "
                         "리눅스 node 를 쓰려면 --node <node 경로> (playwright 가 require 되는 자리에 둔다).\n")
        sys.exit(3)
    probe = os.path.join(pw_dir, f"s9-waterfall-{os.getpid()}.js")
    with open(probe, "w", encoding="utf-8") as f:
        f.write(PROBE_JS)
    cmd = [node, conv(probe), args.url.rstrip("/"), str(args.runs), args.tabs,
           str(args.idle_ms), str(args.max_ms), "1" if args.headed else "0"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=args.runs * (len(args.tabs.split(",")) + 2) * (args.max_ms / 1000 + 10) + 120)
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass
    out = p.stdout.decode("utf-8", "replace")
    data = [json.loads(l[9:]) for l in out.splitlines() if l.startswith("S9WF-RUN ")]
    if p.returncode != 0 or not any(r.get("steps") for r in data):
        sys.stderr.write(p.stderr.decode("utf-8", "replace")[-4000:])
        sys.stderr.write(f"\ndash_waterfall: 프로브 실패 (exit {p.returncode}, {time.time() - t0:.0f}s, 살아남은 회 0)\n")
        sys.exit(p.returncode or 2)
    return {"url": args.url, "runs": args.runs, "tabs": args.tabs, "idle_ms": args.idle_ms,
            "max_ms": args.max_ms, "taken_s": round(time.time() - t0, 1),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "data": data}


METRICS = [("requests", "왕복"), ("api", "api"), ("failed", "실패"), ("retries", "재시도"),
           ("retry_path_ms", "재시도지연ms"), ("first_draw_ms", "첫그리기ms"),
           ("last_done_ms", "마지막요청ms"), ("last_draw_ms", "마지막그리기ms"),
           ("api_ok_ms_median", "api중앙ms")]


def med(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    return round(statistics.median(v)) if v else None


def summarize(result):
    """단계별 중앙값 dict 목록."""
    runs = [r for r in result["data"] if r.get("steps")]
    names = max((r["steps"] for r in runs), key=len)
    names = [s["step"] for s in names]
    rows = []
    for i, name in enumerate(names):
        steps = [r["steps"][i] for r in runs if i < len(r["steps"]) and r["steps"][i]["step"] == name]
        row = {"step": name, "n": len(steps), "timeout": sum(1 for s in steps if s["timeout"])}
        for k, _ in METRICS:
            row[k] = med([s.get(k) for s in steps])
        rows.append(row)
    return rows


def fmt_table(rows, headers):
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    line = lambda r: " | ".join(str(c).rjust(w) if i else str(c).ljust(w) for i, (c, w) in enumerate(zip(r, widths)))
    out = [line(headers), "-+-".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)


def print_summary(result, verbose=False):
    rows = summarize(result)
    hdr = ["단계"] + [h for _, h in METRICS] + ["시한초과"]
    tbl = [[r["step"]] + [("-" if r[k] is None else r[k]) for k, _ in METRICS] + [f'{r["timeout"]}/{r["n"]}'] for r in rows]
    print(f'# dash_waterfall — {result["url"]} · {result["runs"]}회 중앙값 · idle {result["idle_ms"]}ms · {result["at"]} · {result["taken_s"]}s')
    print(fmt_table(tbl, hdr))
    tot = {k: sum(r[k] or 0 for r in rows) for k in ("requests", "api", "failed", "retries", "last_done_ms")}
    print(f'합계(중앙값의 합): 왕복 {tot["requests"]} · api {tot["api"]} · 실패 {tot["failed"]} · 재시도 {tot["retries"]} · 마지막요청ms {tot["last_done_ms"]}')
    dead = [r for r in result["data"] if not r.get("steps")]
    for r in dead:
        print(f'run {r["run"]}: 첫 탐색 실패로 버림 — {r.get("error")} (탐색 리셋 {r.get("nav_resets")}회)')
    navs = [r.get("nav_resets", 0) for r in result["data"]]
    print(f'첫 탐색(index.html) 리셋 횟수 회별: {navs}')
    errs = [e for r in result["data"] for e in r.get("page_errors", [])]
    if errs:
        print(f"페이지 오류 {len(errs)}건: " + " | ".join(errs[:5]))
    if verbose:
        for r in result["data"]:
            print(f'\n## run {r["run"]}')
            for s in r["steps"]:
                print(f'- {s["step"]}: 왕복 {s["requests"]}(api {s["api"]}, 스트림 {s["streams"]}) 실패 {s["failed"]} 재시도 {s["retries"]} '
                      f'첫그리기 {s["first_draw_ms"]} 마지막요청 {s["last_done_ms"]} 마지막그리기 {s["last_draw_ms"]}'
                      + (" 시한초과" if s["timeout"] else ""))
                for u in s["failed_urls"]:
                    print(f"    실패: {u}")
                for q in s["rows"]:
                    if q["stream"]:
                        continue
                    dur = "-" if q["end"] is None else f'{q["end"] - q["start"]}'
                    print(f'    {q["start"]:>6} +{dur:>5} {q["status"] or (q["err"] or "…")} {q["method"]} {q["url"][:90]}')


def print_compare(a, b):
    ra, rb = {r["step"]: r for r in summarize(a)}, {r["step"]: r for r in summarize(b)}
    keys = ("requests", "failed", "retries", "first_draw_ms", "last_done_ms")
    hdr = ["단계"] + [f"{h} 전→후" for k, h in METRICS if k in keys]
    tbl = []
    for step in ra:
        if step not in rb:
            continue
        tbl.append([step] + [f'{ra[step][k]}→{rb[step][k]}' for k, _ in METRICS if k in keys])
    print(f'# 전후 비교 — 전 {a["at"]} / 후 {b["at"]}')
    print(fmt_table(tbl, hdr))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:9909")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tabs", default=DEFAULT_TABS, help="누를 탭 순서(쉼표). docs 뒤에는 문서 하나를 연다")
    ap.add_argument("--idle-ms", type=int, default=1200, help="이만큼 새 요청이 없으면 단계 끝")
    ap.add_argument("--max-ms", type=int, default=15000, help="단계 상한")
    ap.add_argument("--json", help="원자료를 이 파일에 저장(--compare 에 쓴다)")
    ap.add_argument("--verbose", action="store_true", help="회별·요청별 상세")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--node", help="리눅스 node 경로(playwright 가 require 되는 자리)")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE.json", "AFTER.json"))
    args = ap.parse_args(argv)
    if args.compare:
        with open(args.compare[0]) as f:
            a = json.load(f)
        with open(args.compare[1]) as f:
            b = json.load(f)
        print_compare(a, b)
        return 0
    result = run_probe(args)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    print_summary(result, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
