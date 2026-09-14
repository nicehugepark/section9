/* 머리글 마크의 눈 — 가끔 둘러보는 렌즈 (REQ-20260914-001-62x6).

   주인(2026-09-14 10:24): 「저 타치코마 눈을 움직이게 할 수는 없나? 그냥 흰 원이
   아니라 정말 타치코마의 눈처럼 입체감 있게 움직였으면」.

   **「살아 있는 기계」가 아니라 「가끔 둘러보는 렌즈」다.** 눈에 띄되 산만하지
   않아야 하므로 규율이 넷이다.
     · 움직임의 크기 — 렌즈 반지름의 20% 를 넘지 않는다(MAX). 18px 마크에서
       1.35 화소다. 그 이상이면 점 셋이 렌즈 밖으로 밀려나 얼굴이 깨진다.
     · 움직임의 때 — 규칙적이면 초침이 되고 사람은 그것을 계속 본다. 그래서
       간격이 난수다(3~7초).
     · 움직임의 값 — `transform` 만 바꾼다. 좌표(cx/cy)를 고치면 그때마다
       그림이 다시 계산되고, 자리를 읽으면(getBoundingClientRect) 레이아웃이
       다시 돈다. 자리는 한 번 재서 들고 있다가 창 크기가 바뀔 때만 다시 잰다.
     · 움직이지 않아야 할 때 — 사람이 「움직임 줄이기」를 켰거나(prefers-reduced-
       motion) 이 탭이 안 보이면(document.hidden) 타이머를 **건다가 아니라 끈다**.
       안 보이는 창에서 도는 타이머는 배터리만 쓴다.

   옮겨 가는 데 걸리는 시간과 감속은 CSS(web/css/header.css)가 정한다 — 값은
   여기서 주고 그 값에 이르는 길은 저기서 정한다. 「깜빡임」은 없다: 렌즈에는
   눈꺼풀이 없으므로 무리가 잠깐 줄었다 돌아오는 것으로 대신한다. */
(function () {
  "use strict";

  var svg = document.querySelector(".brand svg.mark");
  if (!svg) { return; }
  var pupil = svg.querySelector(".pupil");
  if (!pupil) { return; }

  var LENS_R = 24;                 // 렌즈 반지름 (viewBox 눈금)
  var MAX = LENS_R * 0.2;          // **이동 상한** — 반지름의 20%, 곧 4.8 눈금
  var NEAR = 400;                  // 포인터가 이만큼(화면 px) 안에 들면 따라본다
  var FOLLOW = 0.85;               // 따라볼 때 쓰는 상한의 비율
  var MOVE_MS = [200, 350];        // 둘러보러 옮겨 가는 시간
  var BACK_MS = 300;               // 제자리로 돌아오는 시간
  var GAP_MS = [3000, 7000];       // 다음 둘러봄까지
  var HOLD_MS = [600, 1400];       // 딴 데를 보고 머무는 시간
  var REACT_MS = [9000, 17000];    // 렌즈 반응(줄었다 돌아옴)까지
  var REACT_DUR = 120;             // 그 반응에 걸리는 시간
  var REACT_SCALE = 0.85;
  var TRACK_MS = 80;               // 포인터를 다시 보는 최소 간격

  var timers = [];
  var box = null;                  // 마크의 자리 — 들고 있다가 창이 바뀔 때만 다시 잰다
  var curX = 0, curY = 0;          // 지금 눈이 가 있는 자리
  var aimX = 0, aimY = 0;          // 포인터가 부르는 자리
  var away = false;                // 둘러보는 중인가
  var lastTrack = 0;

  var lessMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function still() { return !!(lessMotion && lessMotion.matches); }
  function unseen() { return document.hidden === true; }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function wait(ms, fn) { timers.push(setTimeout(fn, Math.round(ms))); }

  /* 상한 — 어떤 값이 들어와도 렌즈 반지름의 20% 밖으로는 못 나간다. */
  function capped(x, y) {
    var d = Math.sqrt(x * x + y * y);
    if (d > MAX) { x = x * MAX / d; y = y * MAX / d; }
    return [x, y];
  }

  function look(x, y, ms, scale) {
    var p = capped(x, y);
    curX = p[0]; curY = p[1];
    pupil.style.transitionDuration = Math.round(ms) + "ms";
    pupil.style.transform = "translate(" + curX.toFixed(2) + "px," +
      curY.toFixed(2) + "px)" + (scale ? " scale(" + scale + ")" : "");
  }

  function measure() { box = svg.getBoundingClientRect(); }

  /* 둘러보기를 마치고 돌아오는 자리 — 포인터가 가까이 있으면 그쪽, 없으면 가운데. */
  function home() { look(aimX, aimY, BACK_MS); }

  function roam() {
    wait(rnd(GAP_MS[0], GAP_MS[1]), function () {
      if (unseen() || still()) { return; }
      away = true;
      var a = Math.random() * Math.PI * 2;
      var m = MAX * rnd(0.55, 1);
      /* 가로로 더 넓게 본다 — 사람도 기계도 눈은 좌우로 더 많이 움직인다. */
      look(Math.cos(a) * m, Math.sin(a) * m * 0.8, rnd(MOVE_MS[0], MOVE_MS[1]));
      wait(rnd(HOLD_MS[0], HOLD_MS[1]), function () {
        away = false;
        home();
        measure();               // 그 사이 헤더가 접혔을 수 있다 — 여기서만 다시 잰다
        roam();
      });
    });
  }

  function react() {
    wait(rnd(REACT_MS[0], REACT_MS[1]), function () {
      if (!unseen() && !still()) {
        var x = curX, y = curY;
        look(x, y, REACT_DUR, REACT_SCALE);
        wait(REACT_DUR, function () { look(x, y, REACT_DUR, 1); });
      }
      react();
    });
  }

  function track(e) {
    if (still() || unseen() || !box) { return; }
    var now = Date.now();
    if (now - lastTrack < TRACK_MS) { return; }
    lastTrack = now;
    var dx = e.clientX - (box.left + box.width / 2);
    var dy = e.clientY - (box.top + box.height / 2);
    var d = Math.sqrt(dx * dx + dy * dy);
    if (d > NEAR || d < 1) {
      aimX = 0; aimY = 0;
    } else {
      /* 경계에서 0, 마크 위에서 상한의 85% — 경계를 넘나들어도 튀지 않는다. */
      var m = MAX * FOLLOW * (1 - d / NEAR);
      aimX = dx / d * m; aimY = dy / d * m;
    }
    if (!away) { look(aimX, aimY, BACK_MS); }
  }

  function stop() {
    for (var i = 0; i < timers.length; i++) { clearTimeout(timers[i]); }
    timers = [];
    away = false;
  }

  function start() {
    stop();
    if (still()) {                 // 움직임 줄이기 — 가운데 아래, 그대로 선다
      aimX = 0; aimY = 0;
      pupil.style.transitionDuration = "0ms";
      pupil.style.transform = "";
      return;
    }
    measure();
    roam();
    react();
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
