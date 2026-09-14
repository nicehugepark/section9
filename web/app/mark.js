/* 머리글 마크의 눈 — 가족 몫으로 고르고, 뽑아서 짓는다 (REQ-20260914-001·002-62x6).

   주인의 말이 여기까지 끌고 왔다.
     14:24 「훨씬 더 다양한 패턴을 원한다」 → 재주를 손으로 늘리지 않고 **표**로.
     15:05 「점 3개가 따로 노는 건 호러다」 → 점 셋은 **하나의 시선**.
     16:49 「커서를 쫓아가던 기능이 꺼진 것 같다」 → 커서가 오면 **재주를 끊는다**.
     17:35 「구르기가 아무리 기다려도 몇 번 안 나온다」 → 희귀도가 아니라 **가족 몫**.
     18:00 「비슷한 것을 제외하고 아주 최대한 다양하게」 → 표가 아니라 **뽑는 방법**.

   ## 자리 넷

   · **표(TRICKS)** — 재주 하나는 {이름 · 가족 · 희귀도 · 길이 · 하는 일}이다.
     표정은 손으로 적은 스물여섯, 곱은 경로 × 속도, 구르기는 **꼴마다 대표 하나**,
     연쇄는 그 셋을 잇는 것.
   · **시계(stage)** — 유휴 때마다 **가족을 몫으로** 뽑고(구르기 35 · 표정 35 ·
     곱 20 · 연쇄 10) 그 가족의 섞은 주머니에서 하나를 꺼낸다. 희귀도는 가족 안에서만
     쓴다 — 희귀도는 「이 재주가 얼마나 드문가」이지 「이 갈래가 얼마나 자주 나오는가」가
     아니기 때문이다.
   · **뽑기(rollDraw · reseed)** — 구르기는 실행할 때마다 방향(0~360 연속) · 기울기 ·
     바퀴(0.5~3 연속) · 완급 곡선 · 꼴의 세기 · 맺음을 범위에서 뽑아 새로 짓는다.
     표정·곱·연쇄도 폭과 빠르기를 매번 새로 뽑는다(V). **표는 유한하지만 뽑기는
     유한하지 않다** — 같은 것이 두 번 나오지 않는다.
   · **새로움 검사(fresh)** — 뽑은 값을 정규화한 벡터로 두고 최근 스무 번과의 거리를
     재, 문턱(0.28)보다 가까우면 다시 뽑는다. 문턱은 눈으로 갈리는 최소 차이에서
     나왔다: 방향 30도(0.259) · 바퀴 0.5(0.200) · 속도 30%(0.300).

   ## 움직이는 층이 셋인 까닭 — 축이 셋이다

   `transform-origin` 은 요소당 하나다.
     · `.pupil` — 무리 전체. 축은 무리의 무게중심. 자리·크기·눌림·기울기.
     · `.spin`  — 회전. 축은 **렌즈 중심**.
     · `.d0·.d1·.d2` — 점 하나씩. 축은 그 점의 한가운데.

   ## 구체가 도는 것처럼 보이게 하는 법

   평면 도형이 구를 도는 것처럼 보이려면 둘이 함께 있어야 한다 — 진행 방향으로
   **납작해지고**(그 방향의 배율이 cos), 가장자리에서 **테 뒤로 가려진다**(돔 원
   clipPath). 비스듬한 축은 그 방향으로 눌러야 하므로 회전·눌림·되돌림을 곱한
   matrix 를 쓴다(`slide()`).

   ## 경계는 재주가 아니라 붓에 있다

   무리를 옮기는 붓(`capped`)은 배율까지 셈에 넣고, 점을 옮기는 붓(`dcap`)은 옮긴
   거리가 아니라 **옮긴 자리**로 잰다. 재주가 어떤 값을 주어도 그 둘을 지나야 화면에
   닿으므로, 재주를 하나씩 흉내 내지 않고도 「돔 밖으로 못 나간다」가 참이다.

   ## 커서

   반경 320 화소 안에서 커서가 움직이면 **재주를 끊고** 좇는다. 반경 밖은 보지 않고,
   커서가 멎고 1.5초가 지나면 눈이 제자리로 오고 재주가 다시 돈다.

   「움직임 줄이기」(prefers-reduced-motion)나 안 보이는 탭(document.hidden)에서는
   타이머를 끈다. 옮기는 것은 `transform` 뿐이다.

   검토 보조: 주소에 `?mark=show`(+`&from=N`·`&rep=N`)를 붙이면 표를 차례로 돌린다.
   화면에서는 언제나 가족 몫 + 섞은 주머니다. 제품의 길이 아니다. */
(function () {
  "use strict";

  var svg = document.querySelector(".brand svg.mark");
  if (!svg) { return; }
  var pupil = svg.querySelector(".pupil");
  if (!pupil) { return; }
  var spinner = svg.querySelector(".spin");
  var dots = [svg.querySelector(".d0"), svg.querySelector(".d1"), svg.querySelector(".d2")];
  if (!dots[0]) { dots = []; }

  /* 점의 제자리를 **조각에서 읽는다** — 좌표를 코드에도 적으면 새김이 바뀔 때마다
     두 곳을 고쳐야 하고, 한 곳을 잊으면 점이 테를 넘는다. 읽어 두면 상한도
     자리 바꾸기도 여기서 나온다. */
  var BASE = [], CENTER = [32, 32], REACH = 0, MID = [32, 32];
  (function () {
    var i, c, sx = 0, sy = 0;
    for (i = 0; i < dots.length; i++) {
      c = dots[i].querySelector("circle");
      BASE.push([+c.getAttribute("cx"), +c.getAttribute("cy"), +c.getAttribute("r")]);
      sx += BASE[i][0]; sy += BASE[i][1];
    }
    if (!BASE.length) { return; }
    MID = [sx / BASE.length, sy / BASE.length];               // 무리의 무게중심
    for (i = 0; i < BASE.length; i++) {                        // 무게중심에서 가장 먼 잉크
      REACH = Math.max(REACH, Math.sqrt(Math.pow(BASE[i][0] - MID[0], 2)
              + Math.pow(BASE[i][1] - MID[1], 2)) + BASE[i][2]);
    }
  })();

  var LENS_R = 28.9;               // 돔 반지름 (viewBox 눈금) — 테 안쪽이다
  var MAX = LENS_R * 0.30;         // **이동 상한** — 돔 반지름의 30%
  var MAX_DOWN = LENS_R * 0.18;    // 아래쪽만 좁다 — 무리가 이미 중심보다 아래다
  var DOT_MAX = MAX * 1.05;       // 점 하나가 홀로 갈 수 있는 가장 먼 거리
  /* 뒤로 밀어내는 거리 — 위로 구를 때가 가장 빡빡하다. 무리의 무게중심이 렌즈
     중심보다 8.56 아래에 앉아 있어, 위로 밀면 그만큼을 먼저 까먹는다. 아래 점이
     테 안에 남지 않으려면 46 이 필요하다(34 로는 위로 구를 때 점 하나가 테 안에
     남아 허공에 떠 보였다). */
  var HIDE = 46;
  /* 구르기의 **방향 불변식** (REQ-20260914-002-62x6, 주인 18:28: 「눈 2개가 왼쪽으로
     돌아갈 때 입은 오른쪽으로 돌아가는 경우가 있는 것 같다」).

     한 점의 화면 속도는 진행 방향 u 위에서 이렇다:
         v = (π/2)·[ HIDE·cos(a) − (1−K_MIN)·sin(a)·((p−O)·u) ],  a = t·T_MAX·π/2
     앞선 점은 `(p−O)·u` 가 크므로 뒤 항이 먼저 커진다 — 어느 순간 **앞선 점만
     부호가 뒤집혀** 무리가 갈라진다. 뒤집히는 자리는 `cot(a) = (1−K_MIN)·proj/HIDE`
     이고, 종전(K_MIN 0 · T_MAX 1 · HIDE 34)에는 t=0.866 에서 일어났다 — 지나감의
     마지막 13퍼센트다.
     둘로 막는다: **끝을 0.85 에서 자르고**(그 너머는 어차피 테 뒤다) **납작해짐에
     바닥을 둔다**(0.35). 그러면 뒤집히는 자리가 t=0.912 로 밀려 지나감 밖에 있다
     (문턱 cot 0.240 > 0.103, 2.3배 여유). */
  var T_MAX = 0.85;
  var K_MIN = 0.35;
  var CURVE_MAX = 40;              // 한 지나감 동안 축이 도는 최대 각(아래 주석)
  /* 커서를 보는 반경 — 마크 한가운데에서 320 화소. 1440 폭 화면의 22 퍼센트이고,
     머리글의 브랜드와 첫 탭 몇 개가 들어가는 거리다. 이보다 넓게 잡으면 사람이
     아래 칸에서 일하는 내내 눈이 손을 좇아 산만하고, 좁게 잡으면 마크에 다가가도
     안 쳐다본다. (REQ-20260914-002-62x6, 주인 16:49) */
  var NEAR_R = 320;
  var NEAR_MIN = 0.35;             // 반경 가장자리에서의 세기 — 들어올 때 튀지 않게
  var CALM_MS = 1500;              // 커서가 멎은 뒤 이만큼 지나면 재주가 다시 돈다
  var TRACK_MS = 190;              // 커서를 좇아가는 시간
  var TRACK_GAP = 60;              // 커서를 다시 보는 최소 간격(ms)
  var IDLE_MS = [800, 2500];       // 재주와 재주 사이 — 짧게(주인 17:35)
  var LINEAR = "linear";
  var EASE_IN = "cubic-bezier(.55,.06,.68,.19)";
  var EASE_IO = "cubic-bezier(.45,.05,.25,1)";
  var BOUNCE = "cubic-bezier(.34,1.4,.64,1)";   // 튕기듯 — 장난스러운 결

  var timers = [];
  var box = null;                  // 마크의 자리 — 창이 바뀔 때만 다시 잰다
  var aimX = 0, aimY = 0;          // 커서가 부르는 자리
  var busy = false;                // 재주를 부리는 중인가
  var lastTrack = 0;
  var lastPaint = 0;
  var lastPick = -1;
  var following = false;           // 커서를 좇는 중인가 — 그동안 재주는 쉰다
  var calmTimer = null;            // 커서가 멎기를 기다리는 시계(timers 와 따로 산다)
  var bag = [];                    // 섞은 주머니 — 뽑는 순서가 표 순서를 안 드러내게

  var lessMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function still() { return !!(lessMotion && lessMotion.matches); }
  function unseen() { return document.hidden === true; }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(r) { return rnd(r[0], r[1]); }
  function sign() { return Math.random() < 0.5 ? -1 : 1; }
  function wait(ms, fn) { timers.push(setTimeout(fn, Math.round(ms))); }

  /* ---- 붓 ------------------------------------------------------------ */

  /* 상한 — 재주가 어떤 값을 주어도 렌즈 밖으로는 못 나간다(뒤로 도는 재주는
     제 손으로 `slide()` 를 쓰므로 이 길을 지나지 않는다). */
  function capped(x, y, s) {
    var d = Math.sqrt(x * x + y * y);
    if (d > MAX) { x = x * MAX / d; y = y * MAX / d; }
    if (y > MAX_DOWN) { y = MAX_DOWN; }
    /* 커지는 재주까지 셈에 넣는다 — 무리가 s 배면 잉크의 가장 먼 끝도 s 배다.
       무게중심이 렌즈 중심보다 아래에 앉아 있으므로 그 치우침도 함께 뺀다. */
    var lim = LENS_R - REACH * (s || 1) - 0.4;
    var ox = MID[0] - CENTER[0] + x, oy = MID[1] - CENTER[1] + y;
    var m = Math.sqrt(ox * ox + oy * oy);
    if (lim > 0 && m > lim) {
      ox = ox * lim / m; oy = oy * lim / m;
      x = ox - (MID[0] - CENTER[0]); y = oy - (MID[1] - CENTER[1]);
    }
    return [x, y];
  }

  function css(el, tr, ms, ease) {
    if (!el) { return; }
    el.style.transitionTimingFunction = ease || "";
    el.style.transitionDuration = Math.round(ms / V.spd) + "ms";
    el.style.transform = tr;
  }

  /* 무리 — 자리(x,y)·크기(s)·가로 눌림(sx)·기울기(rot). 자리는 늘 상한 안이다. */
  function P(x, y, ms, o) {
    o = o || {};
    var s = o.s === undefined ? 1 : o.s;
    var p = capped(x * V.amp, y * V.amp, s);
    var sx = (o.sx === undefined ? 1 : o.sx) * s;
    var sy = (o.sy === undefined ? 1 : o.sy) * s;
    css(pupil, "translate(" + p[0].toFixed(2) + "px," + p[1].toFixed(2) + "px) scale("
        + sx.toFixed(3) + "," + sy.toFixed(3) + ")"
        + (o.rot ? " rotate(" + o.rot.toFixed(1) + "deg)" : ""),
        ms, o.ease);
  }

  /* 구체를 도는 것처럼 지나간다 — 축이 `deg` 인 회전. t 는 0(가운데)에서
     1(가장자리). 진행 방향으로 납작해지고, 그 방향으로 밀려 테 뒤로 들어간다. */
  function slide(deg, t, ms, ease, wob, wobF) {
    var th = deg * Math.PI / 180;
    var ux = -Math.sin(th), uy = Math.cos(th);      // 진행 방향(축의 직각)
    var a2 = t * T_MAX * Math.PI / 2;
    var k = K_MIN + (1 - K_MIN) * Math.cos(a2);     // 납작해짐 — 바닥이 있다
    var c = ux, s2 = uy;
    var a = k * c * c + s2 * s2, b = (k - 1) * c * s2, d = k * s2 * s2 + c * c;
    var off = HIDE * Math.sin(a2);
    var wx = 0, wy = 0;
    if (wob) {                       // 진행 방향의 직각으로 잔 흔들림 — 비틀거리며
      var w = Math.sin(t * Math.PI * (wobF || 5)) * wob;
      wx = -uy * w; wy = ux * w;
    }
    css(pupil, "matrix(" + a.toFixed(4) + "," + b.toFixed(4) + "," + b.toFixed(4) + ","
        + d.toFixed(4) + "," + (ux * off + wx).toFixed(2) + "," + (uy * off + wy).toFixed(2) + ")",
        ms, ease);
  }

  function S(deg, ms, ease) { css(spinner, "rotate(" + deg + "deg)", ms, ease); }

  /* 점 하나 — 옮긴 **자리**가 돔 안인지로 잰다. 옮긴 거리로 재면 이미 가장자리에
     앉은 점(아래 하나)이 같은 거리에 테를 넘는다. */
  function dcap(i, x, y) {
    var b = BASE[i];
    if (!b) { return [x, y]; }
    var ox = b[0] - CENTER[0] + x, oy = b[1] - CENTER[1] + y;
    var lim = LENS_R - b[2] - 0.4, m = Math.sqrt(ox * ox + oy * oy);
    if (m > lim) { ox = ox * lim / m; oy = oy * lim / m; }
    return [ox - (b[0] - CENTER[0]), oy - (b[1] - CENTER[1])];
  }

  function D(i, x, y, ms, o) {
    o = o || {};
    var q = dcap(i, x, y); x = q[0]; y = q[1];
    css(dots[i], "translate(" + x.toFixed(2) + "px," + y.toFixed(2) + "px)"
        + (o.s === undefined ? "" : " scale(" + o.s.toFixed(3) + ")")
        + (o.rot ? " rotate(" + o.rot.toFixed(1) + "deg)" : ""), ms, o.ease);
  }

  /* 쉼 자세 — 어떤 재주도 여기서 끝난다. 끝내 주지 않으면 다음 재주가 남의
     자세 위에 얹혀 렌즈 밖으로 걸어 나간다. */
  function rest(ms) {
    P(aimX, aimY, ms === undefined ? TRACK_MS : ms);
    css(spinner, "rotate(0deg)", 0);
    for (var i = 0; i < dots.length; i++) { css(dots[i], "translate(0,0)", ms || 160); }
  }

  /* 걸음들을 차례로 — [기다릴 ms, 할 일] 의 목록. */
  function seq(list, done) {
    var i = 0;
    (function next() {
      if (i >= list.length) { if (done) { done(); } return; }
      var s = list[i++];
      s[1]();
      wait(s[0], next);
    })();
  }

  /* 한 곡선을 n 걸음으로 — 구체 회전처럼 이어져 보여야 하는 것에 쓴다. */
  function ramp(n, gap, fn, done) {
    var list = [], i;
    for (i = 0; i < n; i++) {
      list.push([gap, (function (k) { return function () { fn(k / (n - 1)); }; })(i)]);
    }
    seq(list, done);
  }

  /* ---- 새로움 검사 -------------------------------------------------
     주인(2026-09-14 18:00): 「방향, 축, 각, 속도, 모양 조합은 무궁무진하다. 비슷한
     것을 제외하고 아주 최대한 다양하게 만들어라.」

     **표는 아무리 길어도 유한하다.** 백을 적든 천을 적든 한참 보면 되풀이가 보인다.
     그래서 구르기는 표에 적힌 벌이 아니라 **뽑는 방법**이 되었다 — 실행할 때마다
     방향·기울기·바퀴·완급·꼴·맺음을 범위에서 뽑으므로 같은 구르기가 두 번 나오지
     않는다. 표에는 꼴마다 대표 하나만 있고, 그 하나가 매번 다른 것을 짓는다.

     그것만으로는 「비슷한 것」이 연달아 나올 수 있다. 그래서 뽑은 값을 정규화한
     벡터로 두고 **최근 스무 번과의 거리**를 잰다 — 가장 가까운 것보다 문턱만큼
     떨어질 때까지 다시 뽑는다. 문턱 0.28 은 눈으로 갈리는 최소 차이에서 나왔다:
     방향 30도(=0.259) · 바퀴 0.5(=0.200) · 속도 30%(=0.300). 하나만 달라도
     0.2~0.3 이므로, 문턱을 그 언저리에 두면 「방향만 조금 다른 것」은 걸러지고
     「방향이 확 다르거나 둘 이상이 다른 것」은 통과한다. */

  var NOVEL = 0.28;
  var seenRoll = [], seenVar = [];

  function nearest(list, v) {
    var m = 9, i, j, d, s2;
    for (i = 0; i < list.length; i++) {
      if (list[i].length !== v.length) { continue; }
      s2 = 0;
      for (j = 0; j < v.length; j++) { d = v[j] - list[i][j]; s2 += d * d; }
      d = Math.sqrt(s2);
      if (d < m) { m = d; }
    }
    return m;
  }

  function remember(list, v) { list.push(v); if (list.length > 20) { list.shift(); } }

  /* 열네 번까지 다시 뽑고, 그래도 안 되면 그중 가장 먼 것을 쓴다 — 영영 못 뽑아
     화면이 멎는 일이 없게. */
  function fresh(list, make, thr) {
    var best = null, bestD = -1, i, c, d;
    for (i = 0; i < 14; i++) {
      c = make();
      d = nearest(list, c.v);
      if (d >= (thr === undefined ? NOVEL : thr)) { remember(list, c.v); return c.p; }
      if (d > bestD) { bestD = d; best = c; }
    }
    remember(list, best.v);
    return best.p;
  }

  /* 재주마다 새로 뽑는 **폭과 빠르기의 결** — 표정·곱·연쇄도 매번 조금씩 다르다.
     성격(무엇을 하는가)은 표가 지키고, 이 둘이 그 위에 변주를 얹는다. */
  var V = {amp: 1, spd: 1};
  function reseed() {
    V = fresh(seenVar, function () {
      var a = rnd(0.72, 1.18), b = rnd(0.72, 1.35);
      return {v: [(a - 0.72) / 0.46, (b - 0.72) / 0.63], p: {amp: a, spd: b}};
    }, 0.22);
  }

  /* ---- 재주 표 --------------------------------------------------------
     희귀도: 흔함 8 · 가끔 4 · 드묾 2 · 아주 드묾 1 (뽑히는 무게).
     hides=true 는 일부러 테 뒤로 가는 재주다 — 상한(capped)을 지나지 않는다. */

  var TRICKS = [
    /* --- 함께 움직이는 표정 ------------------------------------------ */

    {name: "곁눈질", fam: "표정", rare: "흔함", ms: 620, run: function (done) {
      var a = Math.random() * Math.PI * 2, m = MAX * rnd(0.5, 0.85);
      seq([[300, function () { P(Math.cos(a) * m, Math.sin(a) * m, 170); }],
           [200, function () { rest(220); }]], done);
    }},

    {name: "응시", fam: "표정", rare: "흔함", ms: 1900, run: function (done) {
      var a = Math.random() * Math.PI * 2, m = MAX * rnd(0.6, 1);
      seq([[1500, function () { P(Math.cos(a) * m, Math.sin(a) * m, 200); }],
           [260, function () { rest(240); }]], done);
    }},

    {name: "두리번", fam: "표정", rare: "흔함", ms: 1100, run: function (done) {
      var s = sign();
      seq([[240, function () { P(MAX * 0.8 * s, -MAX * 0.3, 150); }],
           [240, function () { P(-MAX * 0.8 * s, -MAX * 0.2, 150); }],
           [240, function () { P(MAX * 0.5 * s, MAX * 0.4, 150); }],
           [240, function () { rest(200); }]], done);
    }},

    {name: "끄덕임", fam: "표정", rare: "흔함", ms: 1150, run: function (done) {
      seq([[200, function () { P(0, MAX_DOWN, 180, {ease: EASE_IO}); }],
           [200, function () { P(0, -MAX * 0.45, 180, {ease: EASE_IO}); }],
           [200, function () { P(0, MAX_DOWN * 0.8, 180, {ease: EASE_IO}); }],
           [280, function () { rest(260); }]], done);
    }},

    {name: "도리도리", fam: "표정", rare: "흔함", ms: 1250, run: function (done) {
      var s = sign();
      seq([[200, function () { P(MAX * 0.8 * s, 0, 180, {ease: EASE_IO}); }],
           [200, function () { P(-MAX * 0.8 * s, 0, 180, {ease: EASE_IO}); }],
           [200, function () { P(MAX * 0.6 * s, 0, 180, {ease: EASE_IO}); }],
           [200, function () { P(-MAX * 0.4 * s, 0, 180, {ease: EASE_IO}); }],
           [280, function () { rest(260); }]], done);
    }},

    {name: "갸웃", fam: "표정", rare: "흔함", ms: 1500, run: function (done) {
      var s = sign();
      seq([[800, function () { P(MAX * 0.35 * s, -MAX * 0.15, 420,
                                {rot: 15 * s, ease: EASE_IO}); }],
           [420, function () { P(aimX, aimY, 400, {rot: 0, ease: EASE_IO}); }]], done);
    }},

    {name: "힐끗힐끗", fam: "표정", rare: "흔함", ms: 1450, run: function (done) {
      var s = sign();
      seq([[130, function () { P(MAX * 0.9 * s, -MAX * 0.2, 110); }],
           [330, function () { P(aimX, aimY, 150); }],
           [130, function () { P(MAX * 0.9 * s, -MAX * 0.2, 110); }],
           [420, function () { rest(200); }]], done);
    }},

    {name: "숨 쉬기", fam: "표정", rare: "흔함", ms: 2100, run: function (done) {
      seq([[700, function () { P(aimX, aimY, 680, {s: 1.14, ease: EASE_IO}); }],
           [700, function () { P(aimX, aimY, 680, {s: 0.94, ease: EASE_IO}); }],
           [600, function () { rest(560); }]], done);
    }},

    {name: "느린 깜빡", fam: "표정", rare: "흔함", ms: 760, run: function (done) {
      seq([[340, function () { P(aimX, aimY, 320, {s: 0.72, ease: EASE_IO}); }],
           [340, function () { rest(320); }]], done);
    }},

    {name: "두 번 깜빡", fam: "표정", rare: "가끔", ms: 660, run: function (done) {
      seq([[120, function () { P(aimX, aimY, 110, {s: 0.78}); }],
           [120, function () { P(aimX, aimY, 110, {s: 1}); }],
           [120, function () { P(aimX, aimY, 110, {s: 0.78}); }],
           [200, function () { rest(150); }]], done);
    }},

    {name: "스캔", fam: "표정", rare: "가끔", ms: 1350, run: function (done) {
      var s = sign();
      seq([[420, function () { P(-MAX * s, 0, 400, {ease: EASE_IO}); }],
           [520, function () { P(MAX * s, 0, 500, {ease: LINEAR}); }],
           [300, function () { rest(280); }]], done);
    }},

    {name: "빙 둘러보기", fam: "표정", rare: "가끔", ms: 2000, run: function (done) {
      var dir = sign();
      ramp(12, 140, function (t) {
        var a = t * Math.PI * 2 * dir;
        P(Math.sin(a) * MAX, -Math.cos(a) * MAX * 0.85, 145, {ease: LINEAR});
      }, function () { rest(240); wait(250, done); });
    }},

    {name: "흔들흔들", fam: "표정", rare: "가끔", ms: 2200, run: function (done) {
      ramp(10, 190, function (t) {
        var a = Math.sin(t * Math.PI * 4) * (1 - t * 0.5);
        P(MAX * 0.85 * a, 0, 195, {rot: 9 * a, ease: LINEAR});
      }, function () { rest(280); wait(290, done); });
    }},

    {name: "깡충깡충", fam: "표정", rare: "가끔", ms: 1350, run: function (done) {
      seq([[190, function () { P(0, -MAX * 0.9, 170, {ease: BOUNCE}); }],
           [190, function () { P(0, MAX_DOWN * 0.7, 170, {ease: EASE_IO}); }],
           [190, function () { P(0, -MAX * 0.7, 170, {ease: BOUNCE}); }],
           [190, function () { P(0, MAX_DOWN * 0.5, 170, {ease: EASE_IO}); }],
           [280, function () { rest(260); }]], done);
    }},

    {name: "신나서 통통", fam: "표정", rare: "가끔", ms: 1500, run: function (done) {
      var s = sign();
      seq([[170, function () { P(MAX * 0.5 * s, -MAX * 0.8, 150, {s: 1.08, ease: BOUNCE}); }],
           [170, function () { P(MAX * 0.7 * s, MAX_DOWN * 0.6, 150, {ease: EASE_IO}); }],
           [170, function () { P(-MAX * 0.5 * s, -MAX * 0.8, 150, {s: 1.08, ease: BOUNCE}); }],
           [170, function () { P(-MAX * 0.6 * s, MAX_DOWN * 0.6, 150, {ease: EASE_IO}); }],
           [380, function () { rest(340); }]], done);
    }},

    {name: "기지개", fam: "표정", rare: "가끔", ms: 2200, run: function (done) {
      seq([[900, function () { P(0, -MAX * 0.35, 860, {s: 1.18, ease: EASE_IO}); }],
           [500, function () { P(0, -MAX * 0.2, 460, {s: 1.1, ease: EASE_IO}); }],
           [600, function () { rest(560); }]], done);
    }},

    {name: "궁금해 다가감", fam: "표정", rare: "가끔", ms: 1800, run: function (done) {
      seq([[420, function () { P(0, -MAX * 0.3, 380, {s: 1.2, ease: EASE_IO}); }],
           [760, function () { P(MAX * 0.25 * sign(), -MAX * 0.3, 300, {s: 1.2, ease: EASE_IO}); }],
           [500, function () { rest(460); }]], done);
    }},

    {name: "멀어짐", fam: "표정", rare: "가끔", ms: 1700, run: function (done) {
      seq([[520, function () { P(0, MAX_DOWN * 0.5, 480, {s: 0.8, ease: EASE_IO}); }],
           [700, function () { P(0, MAX_DOWN * 0.5, 300, {s: 0.8, ease: EASE_IO}); }],
           [420, function () { rest(400); }]], done);
    }},

    {name: "무리 회전", fam: "표정", rare: "가끔", ms: 1000, run: function (done) {
      seq([[880, function () { P(aimX, aimY, 860, {rot: 360 * sign(), ease: EASE_IO}); }],
           [60, function () { P(aimX, aimY, 0); }]], done);
    }},

    {name: "졸음", fam: "표정", rare: "가끔", ms: 2100, run: function (done) {
      seq([[1100, function () { P(0, MAX_DOWN, 1050, {s: 0.88, ease: EASE_IO}); }],
           [260, function () { P(0, -MAX * 0.6, 130, {s: 1.12}); }],
           [420, function () { rest(300); }]], done);
    }},

    {name: "툭 벌어짐", fam: "표정", rare: "드묾", ms: 560, run: function (done) {
      seq([[130, function () { P(aimX, aimY, 110, {s: 1.22}); }],
           [380, function () { rest(360); }]], done);
    }},

    {name: "놀람", fam: "표정", rare: "드묾", ms: 900, run: function (done) {
      seq([[110, function () { P(0, -MAX * 0.5, 90, {s: 1.22}); }],
           [180, function () { P(0, -MAX * 0.2, 160, {s: 1.05}); }],
           [520, function () { rest(480); }]], done);
    }},

    {name: "부르르", fam: "표정", rare: "드묾", ms: 800, run: function (done) {
      var n = 8, list = [], i;
      for (i = 0; i < n; i++) {
        list.push([70, (function () {
          return function () { P(rnd(-1, 1) * MAX * 0.45, rnd(-1, 1) * MAX * 0.3, 60, {ease: LINEAR}); };
        })()]);
      }
      list.push([220, function () { rest(200); }]);
      seq(list, done);
    }},

    {name: "다다닥 두리번", fam: "표정", rare: "드묾", ms: 1150, run: function (done) {
      var n = 7, list = [], i;
      for (i = 0; i < n; i++) {
        list.push([120, (function () {
          var a = Math.random() * Math.PI * 2, m = MAX * rnd(0.6, 1);
          return function () { P(Math.cos(a) * m, Math.sin(a) * m, 95); };
        })()]);
      }
      list.push([260, function () { rest(220); }]);
      seq(list, done);
    }},

    /* --- 점이 따로 노는 재주 — **소수만** 남긴다 -----------------------
       주인(2026-09-14 15:05): 「점 3개의 움직임이 인간이 봤을 때 불쾌한 움직임들이
       존재한다. 장난스러운 움직임이 아닌 움직임은 호러스러우니 정리를 좀 해.」
       점 셋은 **하나의 시선**이다 — 삼각형이 굳은 채 함께 움직이면 장난스럽고,
       제각각 기어 다니면 벌레가 된다. 그래서 `solo: true` 는 둘뿐이고, 둘 다
       흩어지자마자 곧 모인다. */

    {name: "물결", fam: "표정", rare: "드묾", ms: 1250, solo: true, run: function (done) {
      if (!dots.length) { return done(); }
      var d = DOT_MAX * 0.45;
      seq([[150, function () { D(0, 0, -d, 150, {ease: EASE_IO}); }],
           [150, function () { D(0, 0, 0, 150); D(1, 0, -d, 150, {ease: EASE_IO}); }],
           [150, function () { D(1, 0, 0, 150); D(2, 0, -d, 150, {ease: EASE_IO}); }],
           [200, function () { D(2, 0, 0, 180); }],
           [300, function () { rest(200); }]], done);
    }},

    {name: "흩어졌다 곧 모이기", fam: "표정", rare: "아주 드묾", ms: 1100, solo: true, run: function (done) {
      if (!dots.length) { return done(); }
      var d = DOT_MAX * 0.8;
      seq([[380, function () {
             D(0, -d, -d * 0.4, 340, {ease: EASE_IO});
             D(1, d, -d * 0.4, 340, {ease: EASE_IO});
             D(2, 0, d * 0.5, 340, {ease: EASE_IO});
           }],
           [460, function () {
             D(0, 0, 0, 420, {ease: BOUNCE}); D(1, 0, 0, 420, {ease: BOUNCE});
             D(2, 0, 0, 420, {ease: BOUNCE});
           }],
           [200, function () { rest(200); }]], done);
    }},

    /* --- 무리째 구르는 것은 아래 「구르기 가족」이 맡는다 -------------- */
  ];

  /* 구르기 가족 — 이 마크에서 가장 「타치코마」다운 움직임이라 갈래를 따로 둔다
     (REQ-20260914-002-62x6, 주인 16:49 「구르기 종류를 좀 더 늘려서」).
     축 × 바퀴 수 × 맺음 중에서 **눈으로 구별되는 것만** 골랐다 — 넷을 다 곱하면
     마흔여덟이지만 절반은 서로 같아 보인다(같은 축·같은 바퀴에서 완급만 다른 것).
     그래서 축·바퀴마다 맺음을 둘씩만 고른 스물넷이다. 무리가 굳은 채 구르는 것뿐
     — 점이 따로 노는 것은 없다. */

  /* 굴러가는 **방위** 여덟 (주인 2026-09-14 17:45: 「구르기는 방향과 축을 정말
     다양하게 하도록 해라」). 종전에는 축 넷에 방향이 한쪽뿐이었다 — 축이 세로면
     늘 같은 쪽으로만 굴렀다. 이제 표는 **어디로 굴러가는가**로 갈린다.
     `slide()` 는 축 각을 받으므로 진행 방향 u=(-sinθ, cosθ) 을 뒤집어 축을 구한다. */
  var ROLL_DIRS = [
    {n: "위", x: 0, y: -1}, {n: "오른쪽 위", x: 0.71, y: -0.71},
    {n: "오른쪽", x: 1, y: 0}, {n: "오른쪽 아래", x: 0.71, y: 0.71},
    {n: "아래", x: 0, y: 1}, {n: "왼쪽 아래", x: -0.71, y: 0.71},
    {n: "왼쪽", x: -1, y: 0}, {n: "왼쪽 위", x: -0.71, y: -0.71}
  ];

  /* 「…로」와 「…으로」 — 받침이 있으면(ㄹ 빼고) 「으로」다. 이름을 손으로 적어 두면
     방위를 더할 때마다 조사를 틀린다(실제로 「오른쪽으에서」가 나왔다). */
  function toward(w) {
    var c = w.charCodeAt(w.length - 1) - 0xAC00;
    var j = (c >= 0 && c < 11172) ? c % 28 : 0;
    return w + ((j === 0 || j === 8) ? "로" : "으로");
  }
  function dirAxis(d) { return Math.atan2(-d.x, d.y) * 180 / Math.PI; }

  /* 구르는 **꼴** 여섯 — 같은 방위라도 이것이 다르면 눈이 갈라 본다. */
  var ROLL_SHAPES = [
    {n: "곧게", ax: function (p, t, a) { return a; }, wob: 0},
    {n: "휘어져", ax: function (p, t, a) { return a + (t - 0.5) * 54; }, wob: 0},
    {n: "텀블링으로", ax: function (p, t, a) { return a + p * 90; }, wob: 0},
    {n: "비틀거리며", ax: function (p, t, a) { return a; }, wob: 3.2},
    {n: "반동으로", ax: function (p, t, a) { return a; }, wob: 0, half: true},
    {n: "8자로", ax: function (p, t, a) { return a + (p % 2 ? 68 : -68); }, wob: 0}
  ];


  var ROLL_TURNS = [
    {n: "반 바퀴", t: 0.5}, {n: "한 바퀴", t: 1},
    {n: "두 바퀴", t: 2}, {n: "세 바퀴", t: 3}
  ];
  /* 속도는 구르기에서만 셋이다 — 무리가 그냥 옮겨 다닐 때는 「보통」이 「느리게」와
     눈으로 안 갈리지만(v8), 같은 한 바퀴라도 느리면 굴러가는 것이고 빠르면 휙 도는
     것이다. 걸음 수와 간격이 함께 바뀐다. */
  var ROLL_SPEEDS = [
    {n: "느리게", steps: 8, gap: 110}, {n: "보통", steps: 6, gap: 70},
    {n: "빠르게", steps: 5, gap: 38}
  ];
  var ROLL_FINS = [
    {n: "부드럽게", ease: EASE_IO, end: "제자리"},
    {n: "툭", ease: LINEAR, end: "제자리"},
    {n: "튕겨 멈춤", ease: EASE_IO, end: "흔들리며"},
    {n: "감속", ease: EASE_IN, end: "제자리"},
    {n: "반대편에서 멈춤", ease: EASE_IO, end: "반대편"}
  ];

  function landing(end, done) {
    if (end === "반대편") {
      var s2 = sign();
      seq([[300, function () { P(MAX * 0.7 * s2, 0, 280, {ease: EASE_IO}); }],
           [320, function () { rest(300); }]], done);
    } else if (end === "흔들리며") {
      seq([[120, function () { P(MAX * 0.55, 0, 110, {ease: EASE_IO}); }],
           [110, function () { P(-MAX * 0.34, 0, 100, {ease: EASE_IO}); }],
           [100, function () { P(MAX * 0.18, 0, 90, {ease: EASE_IO}); }],
           [220, function () { rest(200); }]], done);
    } else { rest(200); wait(220, done); }
  }

  /* 바퀴가 늘면 한 바퀴의 걸음을 줄인다 — 안 그러면 「느리게 세 바퀴」가 6.6초가
     되어 시계를 막는다(v11 의 첫 띠에서 잡혔다). 같은 그림을 거듭 보는 것이라
     걸음을 줄여도 느린 맛은 남는다. 어느 구르기도 3초를 넘지 않는다(가장 긴 것 2.94초). */
  function rollPace(sp, turns) {
    var k = turns >= 3 ? 0.45 : (turns >= 2 ? 0.7 : 1);
    return {steps: k < 1 ? Math.max(4, sp.steps - 2) : sp.steps,
            gap: Math.max(26, Math.round(sp.gap * k))};
  }

  function rollMs(tn, sp0) {
    var sp = rollPace(sp0, tn.t);
    return Math.max(1, Math.round(tn.t)) * (sp.steps * sp.gap * 2 + 260) + 360;
  }

  /* 한 「지나감」 — 납작해지며 테 뒤로 갔다가, 반 바퀴면 같은 쪽에서 한 바퀴면
     반대쪽에서 펴지며 돌아온다. 두·세 바퀴는 이것을 거듭한다. 꼴(sh)이 지나갈 때마다
     축을 어떻게 틀지 정하고, 숨는 시간은 한 장면 안팎(80~180ms)이다. */
  function roll(deg, sh, turns, sp0, ease, end, done) {
    sh = sh || ROLL_SHAPES[0];
    if (sh.half) { turns = 0.5; }
    var sp = rollPace(sp0, turns);
    var same = turns === 0.5, left = Math.max(1, Math.round(turns)), a = deg, p = 0;
    (function next() {
      if (left-- <= 0) { return landing(end, done); }
      var b = same ? a : a + 180, q = p++;
      ramp(sp.steps, sp.gap, function (t) { slide(sh.ax(q, t, a), t, sp.gap, ease, sh.wob, sh.wobF); },
        function () {
          wait(pick([80, 180]), function () {
            slide(b, 1, 0);
            wait(30, function () {
              ramp(sp.steps, sp.gap,
                function (t) { slide(sh.ax(q, 1 - t, b), 1 - t, sp.gap, LINEAR, sh.wob, sh.wobF); },
                function () { a = b; next(); });
            });
          });
        });
    })();
  }

  /* 구르기는 **표에 적힌 벌이 아니라 뽑는 방법**이다. 표에는 꼴마다 대표 하나만
     있고, 그 하나가 실행할 때마다 방향(0~360 연속) · 축 기울기 · 바퀴(0.5~3 연속) ·
     완급 곡선 양끝 · 꼴의 세기 · 맺음을 범위에서 뽑아 새로 짓는다. 뽑은 값은
     정규화한 벡터로 새로움 검사를 거치므로 최근 스무 번과 비슷한 것은 다시 뽑는다. */

  function rollDraw(si) {
    return fresh(seenRoll, function () {
      var deg = rnd(0, 360), tilt = rnd(-26, 26), back = Math.random() < 0.5;
      var turns = rnd(0.5, 3), spd = rnd(0, 1);
      var ein = rnd(0, 0.85), eout = rnd(0.15, 1);
      var curve = 0, tumble = 0, wobA = 0, wobF = rnd(3.5, 9), fig = 0, half = false;
      /* 축이 **지나감 안에서** 도는 것은 휘어짐뿐이다(텀블링·8자는 지나감마다
         한 번 바뀌므로 그 안에서는 축이 고정이다 — 갈라짐을 안 만든다). 축이 도는
         만큼 점마다 진행 직각으로 다른 속도가 생기므로, 그것이 공통 속도의 절반을
         넘지 않게 자른다: (Δθ 라디안)·7.26 < 0.55 × 16.9 → Δθ < 47도. 40 으로 둔다. */
      if (si === 1) { curve = rnd(24, CURVE_MAX); }
      else if (si === 2) { tumble = rnd(58, 122); }
      else if (si === 3) { wobA = rnd(2.2, 4.8); }
      else if (si === 4) { half = true; turns = rnd(0.4, 0.85); }
      else if (si === 5) { fig = rnd(44, 88); }
      var p = {si: si, deg: deg, tilt: tilt, back: back, turns: turns, spd: spd,
               ein: ein, eout: eout, curve: curve, tumble: tumble,
               wobA: wobA, wobF: wobF, fig: fig, half: half};
      var th = deg * Math.PI / 180;
      return {p: p, v: [
        (Math.cos(th) + 1) / 2, (Math.sin(th) + 1) / 2,   // 방향 — 30도 차이 = 0.259
        (turns - 0.5) / 2.5,                              // 바퀴 — 0.5 차이 = 0.200
        spd,                                              // 빠르기 — 30% 차이 = 0.300
        (tilt + 26) / 52, ein, eout,
        curve / 64, tumble / 122, wobA / 4.8, fig / 88,
        back ? 1 : 0
      ]};
    });
  }

  var DIR_STEP = 360 / ROLL_DIRS.length;

  function rollName2(p) {
    var deg = (p.deg % 360 + 360) % 360;
    /* 진행 방향의 화면 각 — u=(-sinθ, cosθ) 이므로 방위 이름은 그 벡터로 찾는다 */
    var th = deg * Math.PI / 180, ux = -Math.sin(th), uy = Math.cos(th);
    var best = 0, bd = -9, i, d;
    for (i = 0; i < ROLL_DIRS.length; i++) {
      d = ux * ROLL_DIRS[i].x + uy * ROLL_DIRS[i].y;
      if (d > bd) { bd = d; best = i; }
    }
    var off = Math.round(Math.acos(Math.max(-1, Math.min(1, bd))) * 180 / Math.PI);
    var w = ROLL_DIRS[best].n + (off >= 4 ? " " + off + "도" : "");
    var head = p.back ? w + "에서" : toward(w);
    var turns = p.turns < 0.7 ? "반 바퀴"
      : (Math.abs(p.turns - Math.round(p.turns)) < 0.12
         ? ["", "한 바퀴", "두 바퀴", "세 바퀴"][Math.round(p.turns)]
         : p.turns.toFixed(1) + "바퀴");
    var pace = p.ein > 0.55 && p.eout > 0.7 ? "느리게 시작해 빨라짐"
      : (p.ein < 0.25 && p.eout < 0.5 ? "빠르게 시작해 느리게"
         : (p.spd > 0.66 ? "빠르게" : (p.spd < 0.33 ? "느리게" : "고르게")));
    var end = p.fin === "흔들리며" ? "흔들리며 멈춤"
      : (p.fin === "반대편" ? "반대편에서 멈춤" : "제자리에 멈춤");
    return head + " " + ROLL_SHAPES[p.si].n + " " + turns + "·" + pace + "·" + end;
  }

  /* 꼴마다 대표 하나 — 여섯 줄이 무한한 구르기를 낸다. */
  (function () {
    var si;
    for (si = 0; si < ROLL_SHAPES.length; si++) {
      (function (si) {
        TRICKS.push({
          name: "구르기 · " + ROLL_SHAPES[si].n, fam: "구르기",
          rare: "흔함", ms: 3000, hides: true, shape: si,
          run: function (done) {
            var p = rollDraw(si);
            p.fin = ["제자리", "흔들리며", "반대편", "제자리"][Math.floor(rnd(0, 4))];
            var sp = {n: "", steps: Math.round(8 - 3 * p.spd),
                      gap: Math.round(110 - 72 * p.spd)};
            var sh = {
              n: ROLL_SHAPES[si].n, half: p.half, wob: p.wobA, wobF: p.wobF,
              ax: function (q, t, a) {
                return a + (t - 0.5) * p.curve + q * p.tumble
                       + (q % 2 ? p.fig : -p.fig);
              }
            };
            window.__S9_ROLL = rollName2(p);      // 검토 보조 — 방금 지은 것의 이름
            roll(p.deg + p.tilt + (p.back ? 180 : 0), sh, p.turns, sp,
                 "cubic-bezier(" + p.ein.toFixed(2) + ",0," + p.eout.toFixed(2) + ",1)",
                 p.fin, done);
          }
        });
      })(si);
    }
  })();

  /* 주인이 이름으로 부른 넷 — 표에 그 이름 그대로 둔다 (2026-09-14 17:35). */
  (function () {
    var S0 = ROLL_SPEEDS[0], S1 = ROLL_SPEEDS[1], S2 = ROLL_SPEEDS[2];
    TRICKS.push({name: "빙그르르", fam: "구르기", rare: "흔함", ms: 1100,
      run: function (done) {            // 제자리 회전 한 바퀴 — 렌즈 중심이 축이다
        seq([[900, function () { S(360 * sign(), 860, EASE_IO); }],
             [140, function () { S(0, 0); }]], done);
      }});
    TRICKS.push({name: "데구르르", fam: "구르기", rare: "흔함", ms: rollMs(ROLL_TURNS[2], S0),
      run: function (done) {            // 느리게 두 바퀴 굴러가며 감속
        roll(rnd(0, 360), ROLL_SHAPES[0], 2, S0, EASE_IN, "제자리", done);
      }});
    TRICKS.push({name: "데굴데굴", fam: "구르기", rare: "흔함", ms: rollMs(ROLL_TURNS[3], S1),
      run: function (done) {            // 통통 튀며 세 바퀴
        roll(rnd(0, 360), ROLL_SHAPES[3], 3, S1, BOUNCE, "흔들리며", done);
      }});
    TRICKS.push({name: "휘리리릭", fam: "구르기", rare: "흔함", ms: rollMs(ROLL_TURNS[3], S2),
      run: function (done) {            // 빠르게 세 바퀴 돌고 탁 멈춤
        roll(rnd(0, 360), ROLL_SHAPES[2], 3, S2, LINEAR, "제자리", done);
      }});
  })();

  /* ---- 재주 짓는 틀 ---------------------------------------------------
     손으로 스물여덟을 적고 나니 다음 요구는 「네 배」였다. 표를 손으로 네 배
     늘리면 다섯 배 요구가 왔을 때 또 손으로 늘려야 하고, 그 사이에 같은 재주가
     이름만 달리 두 번 들어간다. 그래서 **원소를 정의하고 곱한다**.

       경로(12) × 속도(3) × 대상(4) = 144 가지.

     각도·폭·어느 점이 움직이는지는 **표가 아니라 실행 때** 뽑는다 — 그것까지
     표에 올리면 같은 그림이 각도만 달리 수십 줄로 늘어난다(줄 수는 늘지만 보는
     사람에게는 같은 재주다). 희귀도는 원소의 크기에서 나온다: 요란한 속도는
     드묾, 점을 따로 놀리는 대상은 가끔. */

  var PATHS = [
    {n: "직선", f: function (t) { return [Math.sin(t * Math.PI), 0]; }},
    {n: "호", f: function (t) { var a = (t - 0.5) * Math.PI; return [Math.sin(a), -Math.cos(a) * 0.5]; }},
    {n: "원", f: function (t) { var a = t * Math.PI * 2; return [Math.sin(a), -Math.cos(a)]; }},
    {n: "8자", f: function (t) { var a = t * Math.PI * 2; return [Math.sin(a), Math.sin(a * 2) * 0.5]; }},
    {n: "나선", f: function (t) { var a = t * Math.PI * 4, r = t < 0.5 ? t * 2 : (1 - t) * 2; return [Math.cos(a) * r, Math.sin(a) * r]; }},
    {n: "지그재그", f: function (t) { return [(Math.floor(t * 6) % 2 ? -1 : 1) * 0.9, (t - 0.5) * 2]; }},
    {n: "리사주", f: function (t) { var a = t * Math.PI * 2; return [Math.sin(a * 3), Math.sin(a * 2)]; }},
    {n: "진자", f: function (t) { var a = Math.sin(t * Math.PI * 2); return [a, -Math.abs(a) * 0.25]; }},
    {n: "별", f: function (t) { var a = t * Math.PI * 4, r = 0.45 + 0.55 * Math.abs(Math.cos(a * 2.5)); return [Math.sin(a) * r, -Math.cos(a) * r]; }},
    {n: "사각", f: function (t) { return corner(t, [[-1, -1], [1, -1], [1, 1], [-1, 1]]); }},
    {n: "삼각", f: function (t) { return corner(t, [[0, -1], [0.95, 0.6], [-0.95, 0.6]]); }},
    {n: "물결", f: function (t) { return [t * 2 - 1, Math.sin(t * Math.PI * 3) * 0.5]; }}
  ];

  function corner(t, pts) {
    var s = t * pts.length, i = Math.floor(s) % pts.length, u = s - Math.floor(s);
    var a = pts[i], b = pts[(i + 1) % pts.length];
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
  }

  /* 속도는 **둘**뿐이다 (주인 16:49 「차이가 구분이 안 되는 비슷한 패턴이 너무
     많다」). 종전에는 느리게·보통·요란하게 셋이었는데, 띠로 훑어 보니 「보통」은
     어느 경로에서도 「느리게」와 눈으로 갈리지 않았다 — 같은 그림이 조금 빠를
     뿐이다. 갈리는 것은 **느긋한가 부산한가**다. */
  var SPEEDS = [
    {n: "느리게", steps: 10, gap: 190, ease: EASE_IO, rare: "흔함"},
    {n: "요란하게", steps: 12, gap: 60, ease: LINEAR, rare: "드묾"}
  ];

  /* 곱하는 셋째 축은 **대상이 아니라 결**이다 (REQ-20260914-002-62x6, 주인 15:05).
     종전에는 「무리 · 점 하나 · 점 셋 따로 · 짝」으로 곱했는데, 점을 따로 놀리는
     세 갈래가 표의 3/4 를 차지해 화면이 벌레처럼 읽혔다. 점 셋은 **하나의 시선**이니
     곱하는 것은 무리가 어떻게 움직이는가 — 몇 번 · 얼마나 크게 · 어떤 완급으로. */
  /* 결도 경로마다 **하나**다. 네 결을 다 곱하면 「원·느리게·한 번」과
     「원·느리게·작게」처럼 폭만 다른 짝이 생기는데, 폭은 실행 때 무작위로 뽑으므로
     표에 두 줄로 있을 까닭이 없다. 경로마다 그 그림이 가장 잘 사는 결 하나만
     남기고, 폭과 각도는 실행 때 뽑는다. */
  var MOODS = [
    {n: "한 번", rep: 1, amp: 1, ease: EASE_IO},
    {n: "두 번", rep: 2, amp: 0.78, ease: EASE_IO},
    {n: "튕기듯", rep: 1, amp: 0.95, ease: BOUNCE}
  ];
  /* 경로마다 고른 결 — PATHS 와 같은 차례 */
  var PATH_MOOD = [1, 2, 0, 0, 0, 2, 0, 1, 0, 0, 2, 1];

  function combo(path, sp, md) {
    return {
      name: path.n + "·" + sp.n + "·" + md.n, fam: "곱",
      rare: sp.rare === "드묾" ? "드묾" : (md.n === "작게" ? "흔함" : sp.rare),
      ms: sp.steps * md.rep * sp.gap + 340,
      run: function (done) {
        var ang = Math.random() * Math.PI * 2;      // 각도는 실행 때 뽑는다
        var ca = Math.cos(ang), sa = Math.sin(ang);
        var A = MAX * md.amp * rnd(0.72, 1);
        var n = sp.steps * md.rep;
        ramp(n, sp.gap, function (t) {
          var q = path.f((t * md.rep) % 1);
          P((q[0] * ca - q[1] * sa) * A, (q[0] * sa + q[1] * ca) * A,
            sp.gap, {ease: md.ease === BOUNCE ? BOUNCE : sp.ease});
        }, function () { rest(180); wait(200, done); });
      }
    };
  }

  (function () {
    var i, j;
    for (i = 0; i < PATHS.length; i++) {
      for (j = 0; j < SPEEDS.length; j++) {
        TRICKS.push(combo(PATHS[i], SPEEDS[j], MOODS[PATH_MOOD[i]]));
      }
    }
  })();

  /* 연쇄 재주 — 손으로 지은 것 둘·셋을 잇는다. 하나로는 못 내는 **이야기**가
     나온다(두리번거리다 놀라고 한참 바라본다). 아주 드물게만 나온다. */
  var CHAINS = [
    ["두리번", "놀람", "응시"], ["곁눈질", "빙그르르"], ["스캔", "툭 벌어짐"],
    ["졸음", "놀람"], ["끄덕임", "기지개"], ["도리도리", "갸웃"],
    ["힐끗힐끗", "두 번 깜빡"], ["깡충깡충", "느린 깜빡"], ["빙 둘러보기", "응시"],
    ["흔들흔들", "졸음"], ["궁금해 다가감", "멀어짐"],
    ["데굴데굴", "휘리리릭"], ["데구르르", "빙그르르"],
    ["휘리리릭", "빙그르르", "느린 깜빡"], ["놀람", "데굴데굴"]
  ];

  (function () {
    var byName = {}, i, j;
    for (i = 0; i < TRICKS.length; i++) { byName[TRICKS[i].name] = TRICKS[i]; }
    for (i = 0; i < CHAINS.length; i++) {
      (function (parts) {
        var got = [], ms = 0;
        for (j = 0; j < parts.length; j++) {
          if (!byName[parts[j]]) { return; }
          got.push(byName[parts[j]]); ms += byName[parts[j]].ms;
        }
        TRICKS.push({
          name: parts.join(" → "), fam: "연쇄", rare: "아주 드묾", ms: ms + 240,
          run: function (done) {
            var n = 0;
            (function step() {
              if (n >= got.length) { return done(); }
              got[n++].run(function () { wait(120, step); });
            })();
          }
        });
      })(CHAINS[i]);
    }
  })();

  /* ---- 시계 ----------------------------------------------------------- */

  var WEIGHT = {"흔함": 8, "가끔": 4, "드묾": 2, "아주 드묾": 1};

  /* 뽑기는 **가족 몫 + 섞은 주머니**다 (주인 2026-09-14 17:35: 「구르기 … 여전히
     너무 부족해서 아무리 기다려도 몇 번 노출되지 않는다」).

     종전에는 표 전체를 한 주머니에 넣고 희귀도로만 섞었다. 그러면 구르기가 쉰둘
     있어도 표정·곱·연쇄에 섞여 제 몫이 보장되지 않는다 — 희귀도는 「이 재주가
     얼마나 드문가」를 말하지 「이 갈래가 얼마나 자주 나오는가」를 말하지 않는다.
     그래서 **먼저 가족을 몫으로 뽑고, 그 가족 안에서 섞은 주머니를 쓴다.**

     몫: 구르기 35 · 표정 35 · 곱 20 · 연쇄 10.
       · 구르기 35 — 주인이 보고 싶다고 한 것이다. 재주 하나가 1~3초이고 사이가
         0.8~2.5초이니 평균 세 번에 한 번, **10초 안팎에 한 번**은 구른다.
       · 표정 35 — 구르기만 나오면 기계 체조가 된다. 끄덕임·갸웃 같은 잔잔한 것이
         같은 몫으로 섞여야 「가끔 구르는 눈」으로 읽힌다.
       · 곱 20 — 경로가 주는 변주. 눈에 띄지 않게 바탕을 채운다.
       · 연쇄 10 — 가장 긴 것(3~5초)이라 자주 나오면 다른 것이 밀린다. */
  var FAMS = [
    {n: "구르기", w: 35}, {n: "표정", w: 35}, {n: "곱", w: 20}, {n: "연쇄", w: 10}
  ];
  var bags = {};

  function refill(fam) {
    var i, k, w, b = [];
    for (i = 0; i < TRICKS.length; i++) {
      if (TRICKS[i].fam !== fam) { continue; }
      w = WEIGHT[TRICKS[i].rare] || 1;
      for (k = 0; k < w; k++) { b.push(i); }
    }
    for (i = b.length - 1; i > 0; i--) {          // 피셔–예이츠
      k = Math.floor(Math.random() * (i + 1));
      w = b[i]; b[i] = b[k]; b[k] = w;
    }
    bags[fam] = b;
  }

  function choose() {
    var total = 0, i, r;
    for (i = 0; i < FAMS.length; i++) { total += FAMS[i].w; }
    r = Math.random() * total;
    var fam = FAMS[FAMS.length - 1].n;
    for (i = 0; i < FAMS.length; i++) {
      r -= FAMS[i].w;
      if (r <= 0) { fam = FAMS[i].n; break; }
    }
    if (!bags[fam] || !bags[fam].length) { refill(fam); }
    if (!bags[fam].length) { return 0; }
    var k = bags[fam].pop();
    if (k === lastPick && bags[fam].length) {     // 바로 앞엣것은 다시 안 뽑는다
      var j = Math.floor(Math.random() * bags[fam].length);
      var t = bags[fam][j]; bags[fam][j] = k; k = t;
    }
    return k;
  }

  function stage() {
    wait(pick(IDLE_MS), function () {
      if (unseen() || still() || following) { return; }
      if (busy) { stage(); return; }
      var i = choose(), t = TRICKS[i];
      lastPick = i;
      reseed();                     // 재주마다 폭과 빠르기를 새로 뽑는다
      window.__S9_LAST = t.name + "|" + t.fam + "|" + Date.now();   // 검토 보조
      busy = true;
      var ended = false;
      var end = function () {
        if (ended) { return; }
        ended = true;
        busy = false;
        rest();
        stage();
      };
      /* 지킴이는 **변주까지 셈에 넣는다** — 폭·빠르기 씨앗(V.spd)이 0.72 이면
         같은 재주가 1.4배 길어진다. 그것을 빼고 재면 긴 구르기가 끝나기 전에
         잘린다(띠에서 3.8초짜리가 잡혔다). */
      wait(t.ms / V.spd + 500, end);
      t.run(end);
    });
  }

  /* ---- 커서 ----------------------------------------------------------- */

  function measure() { box = svg.getBoundingClientRect(); }

  /* 커서를 좇는다 — **재주를 끊고**.

     v5 에서 재주 표와 시계를 들이면서 이 기능이 사실상 꺼졌다. `track()` 이
     `if (!busy)` 로 재주 중에는 아무것도 쓰지 않았는데, 재주 하나가 1~2.5초이고
     사이가 1.4~4.2초라 절반 가까이가 「재주 중」이었다 — 연쇄 재주는 5초를 넘겼다.
     사람이 커서를 움직이는 동안 눈이 반응하지 않으니 꺼진 것으로 보였다.
     고치는 길은 조건을 무르게 하는 것이 아니라 **재주를 끊는 것**이다: 반경 안에서
     커서가 움직이면 그 자리에서 시계를 멈추고 커서를 본다. */
  function track(e) {
    if (still() || unseen() || !box) { return; }
    var dx = e.clientX - (box.left + box.width / 2);
    var dy = e.clientY - (box.top + box.height / 2);
    var d = Math.sqrt(dx * dx + dy * dy);
    if (d > NEAR_R) { return; }          // 반경 밖에서 움직이는 커서는 보지 않는다
    var now = Date.now();
    lastTrack = now;
    if (!following) { following = true; stop(); }   // 재주를 끊는다
    clearTimeout(calmTimer);
    calmTimer = setTimeout(calm, CALM_MS);          // 멎으면 재주로 돌아간다
    if (now - lastPaint < TRACK_GAP) { return; }
    lastPaint = now;
    if (d < 1) { return; }
    var m = MAX * (NEAR_MIN + (1 - NEAR_MIN) * (1 - d / NEAR_R));
    aimX = dx / d * m; aimY = dy / d * m;
    P(aimX, aimY, TRACK_MS);
  }

  /* 커서가 멎었거나 반경을 떠났다 — 눈을 제자리로 두고 시계를 다시 건다. */
  function calm() {
    following = false;
    aimX = 0; aimY = 0;
    if (!unseen() && !still()) { rest(360); stage(); }
  }


  /* ---- 오르내림 -------------------------------------------------------- */

  function stop() {
    for (var i = 0; i < timers.length; i++) { clearTimeout(timers[i]); }
    timers = [];
    busy = false;
  }

  function halt() { stop(); clearTimeout(calmTimer); following = false; }

  function start() {
    halt();
    if (still()) {                 // 움직임 줄이기 — 쉼 자세로 그대로 선다
      aimX = 0; aimY = 0;
      css(pupil, "", 0);
      css(spinner, "", 0);
      for (var i = 0; i < dots.length; i++) { css(dots[i], "", 0); }
      return;
    }
    measure();
    if (/[?&]mark=show(&|$)/.test(location.search)) { showAll(); return; }
    stage();
  }

  /* 검토 보조 — 재주를 표 순서대로 한 번씩. 제품의 길이 아니다. */
  function showAll() {
    var m = /[?&]from=(\d+)/.exec(location.search);
    var r = /[?&]rep=(\d+)/.exec(location.search);
    var i = m ? +m[1] : 0;      // 띠를 여러 장으로 나눠 찍을 때 쓰는 시작 자리
    var rep = r ? Math.max(1, +r[1]) : 1, turn = 0;
    /* 검토용 — 같은 꼴을 백 번 지어 보고 이웃 거리를 재는 자리. 제품의 길이 아니다. */
    window.__S9_DRAW = function (si, n) {
      var out = [], k, seen = [], keys = {};
      for (k = 0; k < n; k++) {
        var before = seenRoll.length;
        var p = rollDraw(si);
        out.push(seenRoll[seenRoll.length - 1]);
        keys[JSON.stringify(seenRoll[seenRoll.length - 1])] = 1;
      }
      var worst = 9;
      for (k = 1; k < out.length; k++) {
        var d = nearest(out.slice(Math.max(0, k - 20), k), out[k]);
        if (d < worst) { worst = d; }
      }
      return {n: out.length, unique: Object.keys(keys).length, minGap: worst};
    };
    window.__S9_TRICKS = TRICKS.map(function (t) { return t.name; });
    (function next() {
      if (i >= TRICKS.length) { window.__S9_TRICK = "(끝)"; return; }
      var t = TRICKS[i];
      if (++turn >= rep) { turn = 0; i++; }
      window.__S9_TRICK = t.name + (rep > 1 ? " #" + (turn === 0 ? rep : turn) : "");
      reseed();
      busy = true;
      var ended = false;
      var end = function () {
        if (ended) { return; }
        ended = true;
        busy = false; rest(120);
        wait(360, next);
      };
      wait(t.ms / V.spd + 500, end);
      t.run(end);
    })();
  }

  document.addEventListener("visibilitychange", function () {
    if (unseen()) { halt(); } else { start(); }
  });
  window.addEventListener("resize", measure, { passive: true });
  window.addEventListener("pointermove", track, { passive: true });
  if (lessMotion) {
    if (lessMotion.addEventListener) { lessMotion.addEventListener("change", start); }
    else if (lessMotion.addListener) { lessMotion.addListener(start); }  // 사파리 15
  }

  if (window.requestAnimationFrame) { window.requestAnimationFrame(start); }
  else { start(); }
})();
