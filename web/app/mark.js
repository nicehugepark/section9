/* 머리글 마크의 눈 — 둘러보고, 커서를 좇고, 가끔 뒤를 본다 (REQ-20260914-001·002-62x6).

   주인(2026-09-14 14:02): 「괜찮은 움직임이 됐다. 그런데 가끔 뒤(화면에서 보이지
   않는 곳)도 돌아보고 훨씬 더 넓은 각으로 움직였으면 좋겠고, 또 아주 가끔씩
   뱅그르르 돌아가는 효과도 있으면 좋겠다.」

   커서를 좇는 몫(v3)은 그대로 두고 그 위에 둘을 얹었다.

   **뒤돌아보기** — 눈이 옆으로 돌아 점 셋이 **테 뒤로 사라졌다가** 같은 쪽이나
   반대쪽에서 돌아온다. 렌즈가 구체를 도는 것처럼 보이려면 둘이 필요하다:
     · **납작해짐** — 가장자리로 갈수록 가로로 줄어든다(scaleX 1 → 0.22).
       구체 위의 무늬는 옆으로 갈수록 그렇게 보인다.
     · **잘림** — 돔 원으로 오려 낸다(인라인 SVG 의 clipPath). 오려 내지 않으면
       점이 테 밖의 허공에 떠서 「뒤로 갔다」가 아니라 「밖으로 나갔다」로 읽힌다.
   사라진 채로 오래 두지 않는다(0.3~0.8초) — 그 이상이면 고장으로 보인다.
   돌아올 쪽은 난수다: 같은 쪽이면 「돌아봤다 왔다」, 반대쪽이면 「한 바퀴 돌았다」.

   **뱅그르르** — 아주 가끔(2.5~5.5분) 점 셋이 **렌즈 중심**을 축으로 한 바퀴 돌고
   제자리로 온다. 축이 다르므로 무리(.pupil)와 회전(.spin)은 **다른 그룹**이다 —
   무리는 제 무게중심을 축으로 납작해지고, 회전은 렌즈 중심을 돈다. 한 그룹에
   둘을 얹으면 축이 하나뿐이라 회전이 무리를 렌즈 밖으로 던진다.

   **끼어들지 않는다** — 사람이 커서를 움직이는 중(1.5초 안)이면 둘 다 그 회차를
   건너뛴다. 사람이 보고 있는 것을 가로채면 눈이 고장 난 것처럼 보인다.

   규율은 그대로다: 크기는 렌즈 안(뒤돌아보기만 예외 — 그때는 테가 가린다) · 때는
   난수 · 값은 `transform` 만 · 「움직임 줄이기」(prefers-reduced-motion)나 안 보이는
   탭(document.hidden)에서는 타이머를 끈다. */
(function () {
  "use strict";

  var svg = document.querySelector(".brand svg.mark");
  if (!svg) { return; }
  var pupil = svg.querySelector(".pupil");
  if (!pupil) { return; }
  var spinner = svg.querySelector(".spin");

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
  var BUSY_MS = 1500;              // 커서가 이 안에 움직였으면 끼어들지 않는다

  /* 뒤돌아보기 */
  var BEHIND_GAP = [18000, 42000]; // 18~42초에 한 번 — 둘러보기 대여섯 번에 한 번꼴
  var BEHIND_OUT = 34;             // 이만큼 밀면 점 셋이 돔 밖이라 테가 가린다
  var BEHIND_FLAT = 0.22;          // 가장자리에서의 가로 배율
  var BEHIND_OUT_MS = 300;         // 돌아 나가는 시간
  var BEHIND_HIDE_MS = [300, 800]; // 뒤에 머무는 시간
  var BEHIND_IN_MS = 320;          // 돌아오는 시간
  var EASE_IN = "cubic-bezier(.55,.06,.68,.19)";

  /* 뱅그르르 */
  var SPIN_GAP = [150000, 330000]; // 2.5~5.5분에 한 번
  var SPIN_MS = 820;

  var timers = [];
  var box = null;                  // 마크의 자리 — 들고 있다가 창이 바뀔 때만 다시 잰다
  var curX = 0, curY = 0;          // 지금 눈이 가 있는 자리
  var aimX = 0, aimY = 0;          // 커서가 부르는 자리
  var away = false;                // 둘러보는 중인가
  var behindOn = false;            // 뒤를 보는 중인가
  var spinOn = false;              // 도는 중인가
  var lastTrack = 0;

  var lessMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function still() { return !!(lessMotion && lessMotion.matches); }
  function unseen() { return document.hidden === true; }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(r) { return rnd(r[0], r[1]); }
  function wait(ms, fn) { timers.push(setTimeout(fn, Math.round(ms))); }
  function busy() { return away || behindOn || spinOn; }
  function handsOn() { return Date.now() - lastTrack < BUSY_MS; }

  /* 상한 — 어떤 값이 들어와도 렌즈 밖으로는 못 나간다. 아래쪽만 더 좁다. */
  function capped(x, y) {
    var d = Math.sqrt(x * x + y * y);
    if (d > MAX) { x = x * MAX / d; y = y * MAX / d; }
    if (y > MAX_DOWN) { y = MAX_DOWN; }
    return [x, y];
  }

  /* 한 곳에서만 쓴다 — 자리(translate)·가로 눌림(scaleX)·크기(scale)가 한 값이다. */
  function apply(x, y, ms, sx, sy, ease) {
    pupil.style.transitionTimingFunction = ease || "";
    pupil.style.transitionDuration = Math.round(ms) + "ms";
    pupil.style.transform = "translate(" + x.toFixed(2) + "px," + y.toFixed(2) +
      "px) scale(" + sx.toFixed(3) + "," + sy.toFixed(3) + ")";
  }

  function look(x, y, ms, scale) {
    var p = capped(x, y);
    curX = p[0]; curY = p[1];
    apply(curX, curY, ms, scale || 1, scale || 1);
  }

  function measure() { box = svg.getBoundingClientRect(); }

  function home() { look(aimX, aimY, TRACK_MS); }

  function roam() {
    wait(pick(GAP_MS), function () {
      if (unseen() || still()) { return; }
      if (busy()) { roam(); return; }
      away = true;
      var a = Math.random() * Math.PI * 2;
      var m = MAX * rnd(0.7, 1);
      look(Math.cos(a) * m, Math.sin(a) * m, pick(MOVE_MS));
      wait(pick(HOLD_MS), function () {
        away = false;
        home();
        measure();               // 그 사이 헤더가 접혔을 수 있다 — 여기서만 다시 잰다
        roam();
      });
    });
  }

  /* 뒤돌아보기 — 납작해지며 테 뒤로 갔다가 같은 쪽이나 반대쪽에서 돌아온다. */
  function behind() {
    wait(pick(BEHIND_GAP), function () {
      if (unseen() || still()) { return; }
      if (busy() || handsOn()) { behind(); return; }   // 끼어들지 않는다
      behindOn = true;
      var side = Math.random() < 0.5 ? -1 : 1;
      var back = Math.random() < 0.5 ? -side : side;
      apply(side * BEHIND_OUT, rnd(-3, 3), BEHIND_OUT_MS, BEHIND_FLAT, 1, EASE_IN);
      wait(BEHIND_OUT_MS + pick(BEHIND_HIDE_MS), function () {
        // 테 뒤라 안 보인다 — 여기서 반대쪽으로 옮겨도 사람 눈에는 없는 일이다
        apply(back * BEHIND_OUT, 0, 0, BEHIND_FLAT, 1);
        wait(30, function () {
          apply(aimX, aimY, BEHIND_IN_MS, 1, 1);
          curX = aimX; curY = aimY;
          wait(BEHIND_IN_MS, function () { behindOn = false; behind(); });
        });
      });
    });
  }

  /* 뱅그르르 — 렌즈 중심을 축으로 한 바퀴. 축이 달라 그룹이 따로다. */
  function spin() {
    if (!spinner) { return; }
    wait(pick(SPIN_GAP), function () {
      if (unseen() || still()) { return; }
      if (busy() || handsOn()) { spin(); return; }
      spinOn = true;
      spinner.style.transitionDuration = SPIN_MS + "ms";
      spinner.style.transform = "rotate(360deg)";
      wait(SPIN_MS + 40, function () {
        spinner.style.transitionDuration = "0ms";
        spinner.style.transform = "rotate(0deg)";   // 360 과 같은 자리라 안 보인다
        spinOn = false;
        spin();
      });
    });
  }

  function react() {
    wait(pick(REACT_MS), function () {
      if (!unseen() && !still() && !busy()) {
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
    if (!busy()) { look(aimX, aimY, TRACK_MS); }
  }

  function stop() {
    for (var i = 0; i < timers.length; i++) { clearTimeout(timers[i]); }
    timers = [];
    away = behindOn = spinOn = false;
  }

  function start() {
    stop();
    if (still()) {                 // 움직임 줄이기 — 가운데 아래, 그대로 선다
      aimX = 0; aimY = 0;
      pupil.style.transitionDuration = "0ms";
      pupil.style.transform = "";
      if (spinner) { spinner.style.transitionDuration = "0ms"; spinner.style.transform = ""; }
      return;
    }
    measure();
    roam();
    behind();
    spin();
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
