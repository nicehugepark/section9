/* 머리글 마크의 눈 — 재주 표와 그것을 고르는 시계 (REQ-20260914-001·002-62x6).

   주인(2026-09-14 14:24): 「움직이는 패턴이 더 다양해졌으면 좋겠다. … 정말 다양한
   패턴이 들어가서 한참을 쳐다보고 그것만 바라보아도 재미가 있을만큼 … 빙그르르
   돌아가는 것도 수평으로만 돌아가지 말고, 수직이나 다양한 축으로 돌아갈 수
   있도록 … 예시를 든 것뿐이지 예시뿐만이 아니라 훨씬 더 다양한 패턴을 원한다.」

   **패턴을 덧붙이지 않고 구조를 바꿨다.** 종전(v4)은 「둘러보기·뒤돌아보기·
   뱅그르르」 셋이 각자 제 타이머를 들고 있었다 — 넷째를 더하려면 타이머와
   끼어들기 규칙을 한 벌 더 써야 했고, 열여덟을 더하면 그것이 열여덟 벌이 된다.
   그래서 자리를 둘로 갈랐다.

     · **재주 표**(TRICKS) — 재주 하나는 {이름 · 희귀도 · 길이 · 하는 일}이다.
       새 재주를 더하는 일이 표에 줄 하나를 더하는 일이 된다.
     · **시계**(stage) — 유휴 때마다 희귀도 가중치로 하나를 뽑아 돌린다. 같은
       것을 연달아 뽑지 않고, 사람이 커서를 움직이는 중이면 그 회차를 건너뛴다.

   **희귀도가 곧 크기다.** 흔한 재주는 잔잔하고(곁눈질·응시), 드문 재주는 크다
   (뒤돌아보기·자리 바꾸기·두 바퀴). 큰 것이 자주 나오면 산만하고, 작은 것만
   나오면 죽은 화면이다.

   **움직이는 층이 셋이다.** 한 층에 다 얹을 수 없는 까닭은 층마다 **축이 다르기**
   때문이다(`transform-origin` 은 요소당 하나다).
     · `.pupil` — 무리 전체. 축은 무리의 무게중심. 자리·크기·눌림·기울기.
     · `.spin`  — 회전. 축은 **렌즈 중심**. 무리가 렌즈 안을 도는 것.
     · `.d0·.d1·.d2` — 점 하나씩. 축은 그 점의 한가운데. 흩어지고 자리를 바꾼다.

   **구체가 도는 것처럼 보이게 하는 법.** 평면 도형이 구를 도는 것처럼 보이려면
   둘이 함께 있어야 한다 — 진행 방향으로 **납작해지고**(그 방향의 배율이 cos),
   가장자리에서 **테 뒤로 가려진다**(돔 원 clipPath). 축이 세로면 가로로 지나가고,
   가로면 세로로 지나간다. 비스듬한 축은 그 방향으로 눌러야 하므로 회전·눌림·
   되돌림을 곱한 matrix 를 쓴다(`slide()`).

   규율은 그대로다: 자리는 렌즈 안(뒤로 도는 재주만 예외 — 그때는 테가 가린다) ·
   값은 `transform` 만 · 「움직임 줄이기」(prefers-reduced-motion)나 안 보이는 탭
   (document.hidden)에서는 타이머를 끈다.

   검토 보조: 주소에 `?mark=show` 를 붙이면 재주를 표 순서대로 한 번씩 돌린다.
   드문 재주를 사람이 기다려 볼 수 없어 둔 길이다(제품 기능이 아니다). */
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

  var LENS_R = 28.2;               // 돔 반지름 (viewBox 눈금) — 테 안쪽이다
  var MAX = LENS_R * 0.30;         // **이동 상한** — 돔 반지름의 30%
  var MAX_DOWN = LENS_R * 0.18;    // 아래쪽만 좁다 — 무리가 이미 중심보다 아래다
  var DOT_MAX = MAX * 1.05;       // 점 하나가 홀로 갈 수 있는 가장 먼 거리
  var HIDE = 34;                   // 이만큼 밀면 무리가 돔 밖이라 테가 가린다
  var FAR = 900;                   // 이만큼(화면 px) 밖이면 더 멀어져도 같은 세기
  var NEAR_MIN = 0.45;             // 아무리 멀어도 상한의 이만큼은 그쪽을 본다
  var TRACK_MS = 190;              // 커서를 좇아가는 시간
  var TRACK_GAP = 60;              // 커서를 다시 보는 최소 간격(ms)
  var BUSY_MS = 1500;              // 커서가 이 안에 움직였으면 재주를 부리지 않는다
  var IDLE_MS = [1400, 4200];      // 재주와 재주 사이
  var LINEAR = "linear";
  var EASE_IN = "cubic-bezier(.55,.06,.68,.19)";
  var EASE_IO = "cubic-bezier(.45,.05,.25,1)";
  var BOUNCE = "cubic-bezier(.34,1.4,.64,1)";   // 튕기듯 — 장난스러운 결

  var timers = [];
  var box = null;                  // 마크의 자리 — 창이 바뀔 때만 다시 잰다
  var aimX = 0, aimY = 0;          // 커서가 부르는 자리
  var busy = false;                // 재주를 부리는 중인가
  var lastTrack = 0;
  var lastPick = -1;

  var lessMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function still() { return !!(lessMotion && lessMotion.matches); }
  function unseen() { return document.hidden === true; }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(r) { return rnd(r[0], r[1]); }
  function sign() { return Math.random() < 0.5 ? -1 : 1; }
  function wait(ms, fn) { timers.push(setTimeout(fn, Math.round(ms))); }
  function handsOn() { return Date.now() - lastTrack < BUSY_MS; }

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
    el.style.transitionDuration = Math.round(ms) + "ms";
    el.style.transform = tr;
  }

  /* 무리 — 자리(x,y)·크기(s)·가로 눌림(sx)·기울기(rot). 자리는 늘 상한 안이다. */
  function P(x, y, ms, o) {
    o = o || {};
    var s = o.s === undefined ? 1 : o.s;
    var p = capped(x, y, s);
    var sx = (o.sx === undefined ? 1 : o.sx) * s;
    var sy = (o.sy === undefined ? 1 : o.sy) * s;
    css(pupil, "translate(" + p[0].toFixed(2) + "px," + p[1].toFixed(2) + "px) scale("
        + sx.toFixed(3) + "," + sy.toFixed(3) + ")"
        + (o.rot ? " rotate(" + o.rot.toFixed(1) + "deg)" : ""),
        ms, o.ease);
  }

  /* 구체를 도는 것처럼 지나간다 — 축이 `deg` 인 회전. t 는 0(가운데)에서
     1(가장자리). 진행 방향으로 납작해지고, 그 방향으로 밀려 테 뒤로 들어간다. */
  function slide(deg, t, ms, ease) {
    var th = deg * Math.PI / 180;
    var ux = -Math.sin(th), uy = Math.cos(th);      // 진행 방향(축의 직각)
    var k = Math.cos(t * Math.PI / 2);              // 그 방향의 배율 — 가장자리에서 0
    var c = ux, s2 = uy;
    var a = k * c * c + s2 * s2, b = (k - 1) * c * s2, d = k * s2 * s2 + c * c;
    var off = HIDE * Math.sin(t * Math.PI / 2);
    css(pupil, "matrix(" + a.toFixed(4) + "," + b.toFixed(4) + "," + b.toFixed(4) + ","
        + d.toFixed(4) + "," + (ux * off).toFixed(2) + "," + (uy * off).toFixed(2) + ")",
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

  /* ---- 재주 표 --------------------------------------------------------
     희귀도: 흔함 8 · 가끔 4 · 드묾 2 · 아주 드묾 1 (뽑히는 무게).
     hides=true 는 일부러 테 뒤로 가는 재주다 — 상한(capped)을 지나지 않는다. */

  var TRICKS = [
    /* --- 함께 움직이는 표정 ------------------------------------------ */

    {name: "곁눈질", rare: "흔함", ms: 620, run: function (done) {
      var a = Math.random() * Math.PI * 2, m = MAX * rnd(0.5, 0.85);
      seq([[300, function () { P(Math.cos(a) * m, Math.sin(a) * m, 170); }],
           [200, function () { rest(220); }]], done);
    }},

    {name: "응시", rare: "흔함", ms: 1900, run: function (done) {
      var a = Math.random() * Math.PI * 2, m = MAX * rnd(0.6, 1);
      seq([[1500, function () { P(Math.cos(a) * m, Math.sin(a) * m, 200); }],
           [260, function () { rest(240); }]], done);
    }},

    {name: "두리번", rare: "흔함", ms: 1100, run: function (done) {
      var s = sign();
      seq([[240, function () { P(MAX * 0.8 * s, -MAX * 0.3, 150); }],
           [240, function () { P(-MAX * 0.8 * s, -MAX * 0.2, 150); }],
           [240, function () { P(MAX * 0.5 * s, MAX * 0.4, 150); }],
           [240, function () { rest(200); }]], done);
    }},

    {name: "끄덕임", rare: "흔함", ms: 1150, run: function (done) {
      seq([[200, function () { P(0, MAX_DOWN, 180, {ease: EASE_IO}); }],
           [200, function () { P(0, -MAX * 0.45, 180, {ease: EASE_IO}); }],
           [200, function () { P(0, MAX_DOWN * 0.8, 180, {ease: EASE_IO}); }],
           [280, function () { rest(260); }]], done);
    }},

    {name: "도리도리", rare: "흔함", ms: 1250, run: function (done) {
      var s = sign();
      seq([[200, function () { P(MAX * 0.8 * s, 0, 180, {ease: EASE_IO}); }],
           [200, function () { P(-MAX * 0.8 * s, 0, 180, {ease: EASE_IO}); }],
           [200, function () { P(MAX * 0.6 * s, 0, 180, {ease: EASE_IO}); }],
           [200, function () { P(-MAX * 0.4 * s, 0, 180, {ease: EASE_IO}); }],
           [280, function () { rest(260); }]], done);
    }},

    {name: "갸웃", rare: "흔함", ms: 1500, run: function (done) {
      var s = sign();
      seq([[800, function () { P(MAX * 0.35 * s, -MAX * 0.15, 420,
                                {rot: 15 * s, ease: EASE_IO}); }],
           [420, function () { P(aimX, aimY, 400, {rot: 0, ease: EASE_IO}); }]], done);
    }},

    {name: "힐끗힐끗", rare: "흔함", ms: 1450, run: function (done) {
      var s = sign();
      seq([[130, function () { P(MAX * 0.9 * s, -MAX * 0.2, 110); }],
           [330, function () { P(aimX, aimY, 150); }],
           [130, function () { P(MAX * 0.9 * s, -MAX * 0.2, 110); }],
           [420, function () { rest(200); }]], done);
    }},

    {name: "숨 쉬기", rare: "흔함", ms: 2100, run: function (done) {
      seq([[700, function () { P(aimX, aimY, 680, {s: 1.14, ease: EASE_IO}); }],
           [700, function () { P(aimX, aimY, 680, {s: 0.94, ease: EASE_IO}); }],
           [600, function () { rest(560); }]], done);
    }},

    {name: "느린 깜빡", rare: "흔함", ms: 760, run: function (done) {
      seq([[340, function () { P(aimX, aimY, 320, {s: 0.72, ease: EASE_IO}); }],
           [340, function () { rest(320); }]], done);
    }},

    {name: "두 번 깜빡", rare: "가끔", ms: 660, run: function (done) {
      seq([[120, function () { P(aimX, aimY, 110, {s: 0.78}); }],
           [120, function () { P(aimX, aimY, 110, {s: 1}); }],
           [120, function () { P(aimX, aimY, 110, {s: 0.78}); }],
           [200, function () { rest(150); }]], done);
    }},

    {name: "스캔", rare: "가끔", ms: 1350, run: function (done) {
      var s = sign();
      seq([[420, function () { P(-MAX * s, 0, 400, {ease: EASE_IO}); }],
           [520, function () { P(MAX * s, 0, 500, {ease: LINEAR}); }],
           [300, function () { rest(280); }]], done);
    }},

    {name: "빙 둘러보기", rare: "가끔", ms: 2000, run: function (done) {
      var dir = sign();
      ramp(12, 140, function (t) {
        var a = t * Math.PI * 2 * dir;
        P(Math.sin(a) * MAX, -Math.cos(a) * MAX * 0.85, 145, {ease: LINEAR});
      }, function () { rest(240); wait(250, done); });
    }},

    {name: "흔들흔들", rare: "가끔", ms: 2200, run: function (done) {
      ramp(10, 190, function (t) {
        var a = Math.sin(t * Math.PI * 4) * (1 - t * 0.5);
        P(MAX * 0.85 * a, 0, 195, {rot: 9 * a, ease: LINEAR});
      }, function () { rest(280); wait(290, done); });
    }},

    {name: "깡충깡충", rare: "가끔", ms: 1350, run: function (done) {
      seq([[190, function () { P(0, -MAX * 0.9, 170, {ease: BOUNCE}); }],
           [190, function () { P(0, MAX_DOWN * 0.7, 170, {ease: EASE_IO}); }],
           [190, function () { P(0, -MAX * 0.7, 170, {ease: BOUNCE}); }],
           [190, function () { P(0, MAX_DOWN * 0.5, 170, {ease: EASE_IO}); }],
           [280, function () { rest(260); }]], done);
    }},

    {name: "신나서 통통", rare: "가끔", ms: 1500, run: function (done) {
      var s = sign();
      seq([[170, function () { P(MAX * 0.5 * s, -MAX * 0.8, 150, {s: 1.08, ease: BOUNCE}); }],
           [170, function () { P(MAX * 0.7 * s, MAX_DOWN * 0.6, 150, {ease: EASE_IO}); }],
           [170, function () { P(-MAX * 0.5 * s, -MAX * 0.8, 150, {s: 1.08, ease: BOUNCE}); }],
           [170, function () { P(-MAX * 0.6 * s, MAX_DOWN * 0.6, 150, {ease: EASE_IO}); }],
           [380, function () { rest(340); }]], done);
    }},

    {name: "기지개", rare: "가끔", ms: 2200, run: function (done) {
      seq([[900, function () { P(0, -MAX * 0.35, 860, {s: 1.18, ease: EASE_IO}); }],
           [500, function () { P(0, -MAX * 0.2, 460, {s: 1.1, ease: EASE_IO}); }],
           [600, function () { rest(560); }]], done);
    }},

    {name: "궁금해 다가감", rare: "가끔", ms: 1800, run: function (done) {
      seq([[420, function () { P(0, -MAX * 0.3, 380, {s: 1.2, ease: EASE_IO}); }],
           [760, function () { P(MAX * 0.25 * sign(), -MAX * 0.3, 300, {s: 1.2, ease: EASE_IO}); }],
           [500, function () { rest(460); }]], done);
    }},

    {name: "멀어짐", rare: "가끔", ms: 1700, run: function (done) {
      seq([[520, function () { P(0, MAX_DOWN * 0.5, 480, {s: 0.8, ease: EASE_IO}); }],
           [700, function () { P(0, MAX_DOWN * 0.5, 300, {s: 0.8, ease: EASE_IO}); }],
           [420, function () { rest(400); }]], done);
    }},

    {name: "무리 회전", rare: "가끔", ms: 1000, run: function (done) {
      seq([[880, function () { P(aimX, aimY, 860, {rot: 360 * sign(), ease: EASE_IO}); }],
           [60, function () { P(aimX, aimY, 0); }]], done);
    }},

    {name: "졸음", rare: "가끔", ms: 2100, run: function (done) {
      seq([[1100, function () { P(0, MAX_DOWN, 1050, {s: 0.88, ease: EASE_IO}); }],
           [260, function () { P(0, -MAX * 0.6, 130, {s: 1.12}); }],
           [420, function () { rest(300); }]], done);
    }},

    {name: "툭 벌어짐", rare: "드묾", ms: 560, run: function (done) {
      seq([[130, function () { P(aimX, aimY, 110, {s: 1.22}); }],
           [380, function () { rest(360); }]], done);
    }},

    {name: "놀람", rare: "드묾", ms: 900, run: function (done) {
      seq([[110, function () { P(0, -MAX * 0.5, 90, {s: 1.22}); }],
           [180, function () { P(0, -MAX * 0.2, 160, {s: 1.05}); }],
           [520, function () { rest(480); }]], done);
    }},

    {name: "부르르", rare: "드묾", ms: 800, run: function (done) {
      var n = 8, list = [], i;
      for (i = 0; i < n; i++) {
        list.push([70, (function () {
          return function () { P(rnd(-1, 1) * MAX * 0.45, rnd(-1, 1) * MAX * 0.3, 60, {ease: LINEAR}); };
        })()]);
      }
      list.push([220, function () { rest(200); }]);
      seq(list, done);
    }},

    {name: "다다닥 두리번", rare: "드묾", ms: 1150, run: function (done) {
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

    {name: "물결", rare: "드묾", ms: 1250, solo: true, run: function (done) {
      if (!dots.length) { return done(); }
      var d = DOT_MAX * 0.45;
      seq([[150, function () { D(0, 0, -d, 150, {ease: EASE_IO}); }],
           [150, function () { D(0, 0, 0, 150); D(1, 0, -d, 150, {ease: EASE_IO}); }],
           [150, function () { D(1, 0, 0, 150); D(2, 0, -d, 150, {ease: EASE_IO}); }],
           [200, function () { D(2, 0, 0, 180); }],
           [300, function () { rest(200); }]], done);
    }},

    {name: "흩어졌다 곧 모이기", rare: "아주 드묾", ms: 1100, solo: true, run: function (done) {
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

    /* --- 무리째 구르는 것 ---------------------------------------------- */

    {name: "뱅그르르", rare: "드묾", ms: 1000, run: function (done) {
      seq([[860, function () { S(360 * sign(), 820, EASE_IO); }],
           [120, function () { S(0, 0); }]], done);
    }},

    {name: "두 바퀴", rare: "아주 드묾", ms: 1450, run: function (done) {
      seq([[1260, function () { S(720 * sign(), 1220, EASE_IO); }],
           [160, function () { S(0, 0); }]], done);
    }},

    {name: "구르기", rare: "드묾", ms: 1700, run: function (done) {
      var dir = sign();
      S(360 * dir, 1500, EASE_IO);
      ramp(9, 160, function (t) {
        var a = t * Math.PI * 2 * dir;
        P(Math.sin(a) * MAX * 0.7, -Math.cos(a) * MAX * 0.5, 165, {ease: LINEAR});
      }, function () { S(0, 0); rest(220); wait(230, done); });
    }},

    {name: "세로축 돌기", rare: "드묾", ms: 1500, hides: true, run: function (done) {
      turn(0, done);
    }},

    {name: "가로축 돌기", rare: "드묾", ms: 1500, hides: true, run: function (done) {
      turn(90, done);
    }},

    {name: "비스듬한 축 돌기", rare: "아주 드묾", ms: 1600, hides: true, run: function (done) {
      turn(rnd(20, 70) * sign(), done);
    }},

    {name: "반 바퀴만", rare: "드묾", ms: 1250, hides: true, run: function (done) {
      turn(rnd(-30, 30), done, true);
    }}
  ];

  /* 구체가 한 바퀴(또는 반 바퀴) 도는 것 — 나갈 때는 납작해지며 테 뒤로,
     들어올 때는 반대쪽(반 바퀴면 같은 쪽)에서 펴지며 돌아온다. */
  function turn(deg, done, half) {
    var back = half ? deg : deg + 180;
    ramp(6, 70, function (t) { slide(deg, t, 70, LINEAR); },
      function () {
        wait(pick([160, 420]), function () {
          slide(back, 1, 0);                     // 테 뒤라 옮겨도 안 보인다
          wait(40, function () {
            ramp(6, 70, function (t) { slide(back, 1 - t, 70, LINEAR); },
              function () { rest(150); wait(160, done); });
          });
        });
      });
  }


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

  var SPEEDS = [
    {n: "느리게", steps: 10, gap: 190, ease: EASE_IO, rare: "흔함"},
    {n: "보통", steps: 9, gap: 120, ease: EASE_IO, rare: "가끔"},
    {n: "요란하게", steps: 12, gap: 60, ease: LINEAR, rare: "드묾"}
  ];

  /* 곱하는 셋째 축은 **대상이 아니라 결**이다 (REQ-20260914-002-62x6, 주인 15:05).
     종전에는 「무리 · 점 하나 · 점 셋 따로 · 짝」으로 곱했는데, 점을 따로 놀리는
     세 갈래가 표의 3/4 를 차지해 화면이 벌레처럼 읽혔다. 점 셋은 **하나의 시선**이니
     곱하는 것은 무리가 어떻게 움직이는가 — 몇 번 · 얼마나 크게 · 어떤 완급으로. */
  var MOODS = [
    {n: "한 번", rep: 1, amp: 1, ease: EASE_IO},
    {n: "두 번", rep: 2, amp: 0.72, ease: EASE_IO},
    {n: "작게", rep: 1, amp: 0.5, ease: EASE_IO},
    {n: "튕기듯", rep: 1, amp: 0.9, ease: BOUNCE}
  ];

  function combo(path, sp, md) {
    return {
      name: path.n + "·" + sp.n + "·" + md.n,
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
    var i, j, k;
    for (i = 0; i < PATHS.length; i++) {
      for (j = 0; j < SPEEDS.length; j++) {
        for (k = 0; k < MOODS.length; k++) { TRICKS.push(combo(PATHS[i], SPEEDS[j], MOODS[k])); }
      }
    }
  })();

  /* 연쇄 재주 — 손으로 지은 것 둘·셋을 잇는다. 하나로는 못 내는 **이야기**가
     나온다(두리번거리다 놀라고 한참 바라본다). 아주 드물게만 나온다. */
  var CHAINS = [
    ["두리번", "놀람", "응시"], ["곁눈질", "뱅그르르"], ["스캔", "툭 벌어짐"],
    ["졸음", "놀람"], ["끄덕임", "기지개"], ["도리도리", "갸웃"],
    ["힐끗힐끗", "두 번 깜빡"], ["깡충깡충", "느린 깜빡"], ["빙 둘러보기", "응시"],
    ["흔들흔들", "졸음"], ["궁금해 다가감", "멀어짐"], ["다다닥 두리번", "구르기"]
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
          name: parts.join(" → "), rare: "아주 드묾", ms: ms + 240,
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

  function choose() {
    var total = 0, i, w = [];
    for (i = 0; i < TRICKS.length; i++) {
      w[i] = (i === lastPick) ? 0 : (WEIGHT[TRICKS[i].rare] || 1);
      total += w[i];
    }
    var r = Math.random() * total;
    for (i = 0; i < TRICKS.length; i++) {
      r -= w[i];
      if (r <= 0) { return i; }
    }
    return 0;
  }

  function stage() {
    wait(pick(IDLE_MS), function () {
      if (unseen() || still()) { return; }
      if (busy || handsOn()) { stage(); return; }   // 사람이 보고 있으면 비킨다
      var i = choose(), t = TRICKS[i];
      lastPick = i;
      busy = true;
      var ended = false;
      var end = function () {
        if (ended) { return; }
        ended = true;
        busy = false;
        rest();
        stage();
      };
      wait(t.ms + 400, end);       // 재주가 끝을 못 알려도 시계는 멈추지 않는다
      t.run(end);
    });
  }

  /* ---- 커서 ----------------------------------------------------------- */

  function measure() { box = svg.getBoundingClientRect(); }

  function track(e) {
    if (still() || unseen() || !box) { return; }
    var now = Date.now();
    if (now - lastTrack < TRACK_GAP) { return; }
    lastTrack = now;
    var dx = e.clientX - (box.left + box.width / 2);
    var dy = e.clientY - (box.top + box.height / 2);
    var d = Math.sqrt(dx * dx + dy * dy);
    if (d < 0.5) { return; }
    /* 거리로 자르지 않는다 — 멀면 옅게, 가까우면 끝까지. 세로도 줄이지 않는다. */
    var t = 1 - Math.min(1, d / FAR);
    var m = MAX * (NEAR_MIN + (1 - NEAR_MIN) * t);
    aimX = dx / d * m; aimY = dy / d * m;
    if (!busy) { P(aimX, aimY, TRACK_MS); }
  }

  /* ---- 오르내림 -------------------------------------------------------- */

  function stop() {
    for (var i = 0; i < timers.length; i++) { clearTimeout(timers[i]); }
    timers = [];
    busy = false;
  }

  function start() {
    stop();
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
    var i = m ? +m[1] : 0;      // 띠를 두 장으로 나눠 찍을 때 쓰는 시작 자리
    window.__S9_TRICKS = TRICKS.map(function (t) { return t.name; });
    (function next() {
      if (i >= TRICKS.length) { window.__S9_TRICK = "(끝)"; return; }
      var t = TRICKS[i++];
      window.__S9_TRICK = t.name;
      busy = true;
      var ended = false;
      var end = function () {
        if (ended) { return; }
        ended = true;
        busy = false; rest(120);
        wait(360, next);
      };
      wait(t.ms + 400, end);
      t.run(end);
    })();
  }

  document.addEventListener("visibilitychange", function () {
    if (unseen()) { stop(); } else { start(); }
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
