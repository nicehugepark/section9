/* 머리글 마크의 눈 — 둘러보고, 커서를 좇는 렌즈 (REQ-20260914-001·002-62x6).

   주인(2026-09-14 13:46): 「타치코마가 조금 더 활동적으로 움직였으면 좋겠다.
   마우스 커서를 위로 올리면 더 위로 쳐다봤으면 좋겠고.」

   1차(001)는 얌전했다 — 반지름의 20% 안에서만 움직이고, 커서는 400px 안에
   들어와야 좇았다. 그래서 화면 어디를 가리키든 눈은 대개 제자리였다. 2차에서
   바꾼 것 셋.
     · **폭** — 상한을 돔 반지름의 30% 로 넓혔다. 아래로만 18% 인데, 점 무리가
       이미 중심보다 아래에 앉아 있어 같은 폭을 주면 테를 파고든다(그 여유를
       시험이 잰다 — tests/test_mark_motion.py N3).
     · **거리** — 커서를 **화면 어디에 있든** 좇는다. 멀면 상한의 45%, 마크에
       가까울수록 100% 로 커진다. 경계가 없으니 들어오고 나갈 때 튀지 않는다.
       세로를 줄이지 않는다 — 커서가 마크보다 위에 있으면 그만큼 올려다본다.
     · **결** — 옮겨 갈 때는 빠르게(110~180ms) 가고 오래 머문다(0.7~1.8초).
       느리게 미끄러지면 기계가 아니라 액체로 보인다.

   움직임의 규율은 그대로다. 크기는 렌즈 안(상한 MAX) · 때는 규칙적이지 않게
   (난수 간격) · 값은 `transform` 만(자리를 읽으면 레이아웃이 다시 돈다) ·
   사람이 「움직임 줄이기」를 켰거나(prefers-reduced-motion) 탭이 안 보이면
   (document.hidden) 타이머를 끈다. 렌즈에는 눈꺼풀이 없으므로 「깜빡임」은
   무리가 120ms 동안 잠깐 줄었다 돌아오는 것으로 대신한다. */
(function () {
  "use strict";

  var svg = document.querySelector(".brand svg.mark");
  if (!svg) { return; }
  var pupil = svg.querySelector(".pupil");
  if (!pupil) { return; }

  var LENS_R = 27.4;               // 돔 반지름 (viewBox 눈금) — 테 안쪽이다
  var MAX = LENS_R * 0.30;         // **이동 상한** — 돔 반지름의 30%
  var MAX_DOWN = LENS_R * 0.18;    // 아래로만 좁다 — 점 무리가 이미 아래에 앉아 있다
  var FAR = 900;                   // 이만큼(화면 px) 밖이면 더 멀어져도 같은 세기
  var NEAR_MIN = 0.45;             // 아무리 멀어도 상한의 이만큼은 그쪽을 본다
  var MOVE_MS = [110, 180];        // 둘러보러 옮겨 가는 시간 — 빠르게
  var TRACK_MS = 190;              // 커서를 좇아가는 시간
  var GAP_MS = [2200, 5200];       // 다음 둘러봄까지
  var HOLD_MS = [700, 1800];       // 딴 데를 보고 머무는 시간
  var REACT_MS = [9000, 17000];    // 렌즈 반응(줄었다 돌아옴)까지
  var REACT_DUR = 120;
  var REACT_SCALE = 0.85;
  var TRACK_GAP = 60;              // 커서를 다시 보는 최소 간격(ms)

  var timers = [];
  var box = null;                  // 마크의 자리 — 들고 있다가 창이 바뀔 때만 다시 잰다
  var curX = 0, curY = 0;          // 지금 눈이 가 있는 자리
  var aimX = 0, aimY = 0;          // 커서가 부르는 자리
  var away = false;                // 둘러보는 중인가
  var lastTrack = 0;

  var lessMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function still() { return !!(lessMotion && lessMotion.matches); }
  function unseen() { return document.hidden === true; }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function wait(ms, fn) { timers.push(setTimeout(fn, Math.round(ms))); }

  /* 상한 — 어떤 값이 들어와도 렌즈 밖으로는 못 나간다. 아래쪽만 더 좁다. */
  function capped(x, y) {
    var d = Math.sqrt(x * x + y * y);
    if (d > MAX) { x = x * MAX / d; y = y * MAX / d; }
    if (y > MAX_DOWN) { y = MAX_DOWN; }
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

  function home() { look(aimX, aimY, TRACK_MS); }

  function roam() {
    wait(rnd(GAP_MS[0], GAP_MS[1]), function () {
      if (unseen() || still()) { return; }
      away = true;
      var a = Math.random() * Math.PI * 2;
      var m = MAX * rnd(0.7, 1);
      look(Math.cos(a) * m, Math.sin(a) * m, rnd(MOVE_MS[0], MOVE_MS[1]));
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
    if (!away) { look(aimX, aimY, TRACK_MS); }
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
