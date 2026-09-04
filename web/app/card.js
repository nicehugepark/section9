/* card.js — 카드 한 장 — 멈춤·작업 자리·깨우기·판정 전이, 그리고 Board 컬럼 */
"use strict";
/* 손잡이의 낱말은 **한 곳**에 있다 (REQ-20260829-024 라운드4, designer 지적).

   글자가 HTML 을 짓는 자리와 눌린 뒤 다시 칠하는 자리 두 곳에 있었다. 그래서
   개명 한 번에 둘이 갈렸고, 처음 그려진 낱말과 한 번 눌렀다 돌아온 낱말이
   다른 화면이 실제로 났다 — 이 화면이 판정 버튼에서 세 번 배운 그 규칙이다.

   낱말 자체는 사용자가 고른 것이다(라운드4 반려: "깨우기, 세우기 라는 용어가
   너무 어색한데"). 멈춘 것도 중단해 둔 것도 하는 일이 같아 **한 낱말**을
   쓴다 — 처지의 차이는 버튼이 아니라 그 위의 줄이 말한다. */
const WAKE_LABEL = "이어가기", WAKE_GOING = "이어가는 중…";
const STOP_LABEL = "중단하기", STOP_GOING = "중단 중…";
/* 낱말이 갈린 이유는 뜻이 갈리기 때문이다 (REQ-20260830-042 ux-writer 판정).
   도는 것을 끊는 쪽은 「중단하기」(지금 멈춘다), 앞으로 못 맡게 하는 쪽은
   「중단해 두기」(앞으로 안 맡게 해 둔다). 한 낱말(중단)의 상만 다르므로
   사용자가 고른 낱말은 지켜지고 뜻은 갈린다. 진행형은 공용 「중단 중…」. */
/* 정책 단추는 **정책 문법**으로 말한다 (REQ-20260901-005 3차 판정).
   「저절로 이어지지 않게 하기」였다 — 처음 보는 개념을 부정형으로 데뷔시키고
   (REQ-20260830-039 가 「맡은 손」을 반려한 그 사유의 재발), 「이어지다」가
   무주어라 무엇이 이어지는지 못 말했으며, 배운 낱말 「이어가기」와 어간이
   같아 "내가 이어가기를 못 하게 되나"로 오독됐다(사용자 질문이 낱말을 직접
   짚었다). 「자동 OO 끄기」는 자동 갱신·자동 재생으로 굳은 온/오프 정책
   문법이라 부정을 「끄기」 한 낱말이 흡수하고, 목적어가 확정 재개 동사
   「이어받다」(DOC-20260831-005 규칙 3)를 실어 주어 결함을 닫는다. 「자동」은
   개체 이름이 아니라 정책 한정어라 규칙 2 와도 안 부딪힌다. */
const STOP_HOLD_LABEL = "자동 이어받기 끄기";
/* 확인 창 셋의 꼬리는 **한 문장**이다 (REQ-20260830-042 ux-writer).
   전에는 「같은 자리에 생기는」·「같은 자리의」로 갈려 있었고, 무엇보다 ▶ 와 ⏸ 가
   함께 서 있던 동안에는 이 문장이 거짓에 가까웠다 — 그 자리에 이미 둘이 있으니
   "대신 선다"가 성립하지 않았다. 배타 노출이 이 문장을 참으로 만든다. */
const STOP_ASK_TAIL = "다시 맡기려면 그 자리에 대신 서는 「이어가기」를"
  + " 누르면 됩니다.";
const DRIFT_LABEL = "끝났는지 확인";
/* ⏸ 의 네 갈래 (REQ-20260830-035). 손잡이의 **이름은 넷 다 「중단하기」**다 —
   뜻은 툴팁·창·응답이 가른다(낱말을 갈래마다 새로 지으면 낱말이 네 벌이 되고,
   사람이 배운 한 낱말이 화면마다 다른 것을 가리키게 된다).

   문안은 ux-writer 가 REQ-035 문서에 적은 것을 **그대로** 옮겼다. 화면이 문장을
   짓지 않는다 — 서버 응답도 `d.message` 를 그대로 띄운다.

   `who` = 지금 이 요청에 무엇이 붙어 있나(신원) · `tip` = 손잡이에 손이 얹혔을
   때 · `ask` = 확인 창. `ask` 가 없는 갈래(idle)는 창을 세우지 않는다: 잃는 것이
   없고 「이어가기」 한 번으로 되돌아간다(s9-design 4절 — 확인은 되돌릴 수 없을 때만).

   **`row` 였던 것이 `who` 가 됐다** (REQ-20260830-040 designer 개정안 규칙 1).
   이 문장들은 사실 줄의 손 위 글이었는데, 그 줄이 폐지됐다 — 「맡은 창 일하는 중」·
   「담당 없음」은 in-progress 열 이름과 점이 이미 한 말의 되풀이였고, 카드마다
   글자 줄을 하나씩 더 세워 오너가 다듬어 둔 카드를 다시 어지럽혔다. 신원은 이제
   **점과 툴팁과 낭독기**가 진다: 이 문장 하나가 id 줄의 손 위 글이 되고, 같은
   문장이 시각적 숨김 글자로 그 줄에 함께 실린다(툴팁 전용은 접근성 후퇴다).

   낱말 판정 (REQ-20260830-039 tech-writer 전수 점검):
     · 「맡은 손」 — 가리킬 실체가 없는 조어라 반려. 개념어는 「담당」·「없음」.
     · 「손길」 — idle 본문에서 걷어냈다. 같은 카드의 캡션 「손길」(마지막으로
       만진 때)과 같은 낱말이 다른 것을 가리키던 자리다.
     · 「세워 두다」 — 사용자가 반려한 「세우기」의 활용형 잔재라 「중단해 두다」로.
     · 「집다」 — 채택어 「담당」과 한 뿌리인 「맡다」로 모은다.
     · 「조각」(서브에이전트 몫) — 은유를 걷고 「일 하나」·「하던 일」로.
     · 유지: 「맡은 창」(실제 터미널 창을 가리킨다) · 「일손」(사전 낱말이고
       늘 "나눠 맡은"을 달고 나온다) — 재론 금지 근거가 039 문서에 있다. */
const STOP_KIND = {
  worker: {
    who: "백그라운드 작업이 이 요청을 맡아 진행 중입니다",
    tip: "백그라운드 작업이 돌고 있습니다 — 중단하면 하던 일이 거기서 끝나고"
      + " 사유가 문서에 남습니다",
    /* 확인 창의 갈래를 가르는 것은 **주체가 아니라 결과**다 — 여기서 곧장
       끊기느냐(worker), 전해 놓고 기다리느냐(session·agent)다. 그래서 제목이
       주체 이름을 안 진다. `ask` 를 갈래마다 지우지 마라: `stopDoc` 이
       `!stopAsk` 면 창 없이 곧장 중단한다(REQ-20260902-005 안전 함정). */
    ask: {title: "지금 하던 일을 여기서 끊을까요?",
      desc: "지금 하던 일은 문서에 적힌 데까지만 남고, 그 뒤로 진행 중이던 것은"
        + " 사라집니다. 중단한 사실과 사유는 문서에 남습니다. " + STOP_ASK_TAIL,
      ok: STOP_LABEL}},
  session: {
    who: "이 요청을 맡은 창이 지금 일하고 있습니다",
    tip: "맡은 창이 일하고 있습니다 — 중단하라고 전하면 곧바로 멎지 않을 수 있습니다",
    ask: {title: "일하는 창에 중단하라고 전할까요?",
      desc: "지금 하던 말은 그 창이 마치는 데까지 이어질 수 있어 곧바로 멎지"
        + " 않습니다. 멈추면 어디까지 했는지와 사유가 문서에 남습니다. 그동안"
        + " 이 요청은 저절로 이어지지 않습니다. " + STOP_ASK_TAIL,
      ok: "중단하라고 전하기"}},
  agent: {
    who: "이 요청을 나눠 맡은 일손이 일 하나를 진행 중입니다",
    tip: "나눠 맡은 일손이 일 하나를 하고 있습니다 — 중단하라고 전하면 하던 일은"
      + " 마치고 멈춥니다",
    ask: {title: "나눠 맡은 일손에 중단하라고 전할까요?",
      desc: "지금 맡은 일은 마치고 멈추므로 곧바로 멎지 않습니다. 어디까지"
        + " 했는지와 중단한 사유는 문서에 남습니다. " + STOP_ASK_TAIL,
      ok: "중단하라고 전하기"}},
  /* idle 은 ux-writer 가 처음부터 "줄을 세우지 말라"고 했다("도는 것이 없으니
     적을 사실이 없다"). 그 권고를 지키지 못한 것은 ⏸ 가 줄을 필요로 했기
     때문인데, 손잡이가 id 줄로 옮겨 간 지금은 세울 이유가 아예 없다 — 권고를
     제자리로 돌린다. */
  idle: {
    who: "지금 이 요청을 담당하는 것이 없습니다",
    // 이 갈래의 단추는 카드를 떠나 문서 화면의 낱말 단추가 됐다(holdLockHTML) —
    // 도는 것을 끊는 행위가 아니라 앞으로에 대한 정책이기 때문이다.
    /* 단추(「자동 이어받기 끄기」)가 축을, 이 글이 사실을 말한다
       (REQ-20260901-005 translator 검수). 조건은 확정어 「담당」 하나로
       부른다 — 조건절이 자리마다 다른 말이면 3차 반려를 만든 「동사 5벌」
       사고가 조건절로 옮겨 앉는다. 결과는 「이어지지 않습니다」로
       좁혀 말한다: 「아무것도 뜨지 않습니다」는 내가 여는 창까지 삼켜
       거짓이 된다. */
    tip: "지금 이 요청에 담당이 없습니다 — 이대로 두면 잠시 뒤 저절로"
      + " 이어집니다. 꺼 두면 「▶ 이어가기」를 누를 때까지 이어지지"
      + " 않습니다."},
};
/* 손잡이의 **얼굴**은 글리프, **이름**은 그대로 낱말 (REQ-20260830-032 오너 판정).

   사용자: "세우고 깨우고 관련 디자인을 일반적인 play, pause 버튼(영어 글자
   버튼이 아니고, 세모와 이퀄사인을 세워놓은 것)을 사용해보는 건 어때?"

   낱말은 죽이지 않는다 — 사용자가 직접 고른 말이고(라운드4), 눈으로 못 읽어도
   손이 얹히면(title) 읽히고 화면 낭독기(aria-label)에는 그대로 들린다. 글리프는
   `<svg>` 다: 이모지는 폰트마다 다른 그림이 나오고 색이 잉크를 안 따른다.
   `currentColor` 라 hover 반전에서 배경과 함께 뒤집힌다.

   **전송 문법에 있는 두 행위만** 글리프다(▶ 이어가기 · ⏸ 중단하기). 셋째
   손잡이 「끝났는지 확인」은 낱말로 남는다 — 아래 stallHTML 에 근거를 적었다. */
/* **그림은 원 안에 산다** (REQ-20260831-006).

   사용자: "pause 버튼의 글리프가 원 안에서 균형이 안 맞고 치우쳐 있다."

   자를 대 보니 치우침은 0 이었다(2배가 아니라 14배로 찍어 화소로 실측:
   가로 +0.00 · 세로 +0.00). 어긋난 것은 위치가 아니라 **여백**이다. 손이
   얹히면 그림은 13px 원 안에 담기는데, 옛 ⏸ 의 잉크는 5.71 × 8.29px 이라
   원과의 틈이 좌우 3.64 · 상하 2.36 · **모서리 1.47** 로 갈렸다 — 눈은 원
   안에서 축 방향 여백이 아니라 **테의 굵기**를 보므로, 위아래가 좁고 좌우가
   넓은 이 그림은 세로로 눌린 것으로, 즉 "안 맞는" 것으로 읽힌다.

   그래서 그림을 원에 맞춘다. ⏸ 는 낮추고 벌려(세로 9→7.2, 가로 6.2→6.6),
   ▶ 는 줄이고 오른쪽으로 민다(삼각형의 무게중심은 밑변 쪽에 있어, 상자를
   가운데 두면 왼쪽으로 치우쳐 보인다 — 재생 단추가 늘 쓰는 그 보정이다).
   실측 결과 두 그림 모두 모서리 틈이 2.0~2.6px 로 올라와 축 방향 틈(3.1~3.5)과
   같은 눈금에 든다. 과녁(27px)도 원(13px)도 1px 안 건드렸다 — 고친 것은
   그 안에 든 그림뿐이다. */
/* **그림의 눈금과 화면의 눈금을 같은 눈금으로** (REQ-20260831-006 반려).

   사용자: "pause 버튼은 마우스를 올려보면 여전히 상하좌우 대칭이 아니다."

   1차는 소수점으로 맞췄다(2.7 · 7.2 · 0.79…). 그 값들이 옳았는지 실포인터를
   얹고 16배로 다시 쟀더니, 원은 13.000 × 13.000 이고 잉크는 그 안에 0.000 으로
   가운데 있었다 — 그런데 **틈은 좌우 3.438 · 상하 3.188 로 갈렸고, 테는 방향에
   따라 2.062 에서 6.500 까지** 오르내렸다. 눈이 읽는 것은 그 테다.

   더 나쁜 것은 1배 화소에서 드러났다. `viewBox` 는 12칸인데 `.gly` 는 11px 이라
   **한 칸이 0.9167px** 다 — 그림의 어떤 좌표도 화소 격자에 앉지 않는다. 두 막대
   사이 1칸(0.92px)은 실화면에서 밝기 9분의 1로 앉아 **사실상 사라졌고**(정수
   격자에 맞춘 1배 캡처로 확인), ⏸ 는 두 막대가 아니라 실금 하나 든 덩어리로
   읽힌다. 소수를 더 다듬어도 이건 안 낫는다 — 눈금 자체가 어긋나 있어서다.

   그래서 **한 칸을 한 화소로 만든다**: `viewBox="0 0 11 11"` 이면 11px 그림에서
   1칸 = 1px 이고, 정수 좌표는 그대로 화소 경계에 앉는다(점의 좌표계를 하나로
   세운 것과 같은 처방 — 국소 보정이 아니라 눈금을 고친다).

   그 눈금 위에서 잉크를 **7 × 7 정사각**으로 둔다. 11칸 그림에서 2..9 이고,
   13px 원 안에서는 3..10 이라 **상하좌우 틈이 모두 3px** 로 같아진다 — 축
   방향이든 모서리든 테가 한 값이다. ⏸ 는 막대 3 · 틈 1 (옛 2.57 : 0.92 의 비율을
   그대로 격자에 앉힌 값)이라 그 1px 이 이제 온전히 켜진다.

   ▶ 만 **한 칸 오른쪽**이다(3..10). 삼각형은 상자가 아니라 무게중심으로 가운데를
   잡아야 하는데(밑변 쪽에 쏠려 있다), 1칸 밀면 무게중심이 (3+3+10)/3 = 5.33 로
   상자 한가운데 5.5 에 0.17 까지 붙는다. 1차의 +0.79px 과 뜻은 같고 값만 정수다 —
   밑변의 세로 획이 화소 경계에 앉아 흐려지지 않는다. */
/* **그림 상자와 원을 한 상자로** (REQ-20260831-019 — 사용자 실화면 재현).

   사용자: "pause hover 이미지를 보면 여전히 상하좌우 대칭이 아니다."
   그리고: "디자인, ui 화면은 반드시 브라우저를 통해 직접 보라고 했을텐데."

   앞선 검증(REQ-20260831-006)은 배율 1 에서만 쟀고 거기선 편차가 0.000 이었다.
   사용자 화면은 Windows 표시 배율(125%)이다. 그 배율로 브라우저를 띄워
   (에뮬레이션이 아니라 `--force-device-scale-factor`) 실포인터를 얹고 16배로
   화소를 뜨니 어긋남이 그대로 나왔고, 사용자가 올린 캡처를 화소로 재도 같은
   모습이었다 — 원 17×16 화소, 그림이 원 중심에서 **0.63화소 왼쪽**.

   뿌리는 좌표가 아니라 **반올림**이다(상세와 처방은 actions.css 의 벨트 관문
   주석에 있다 — 원의 모양을 배경 사각이 아니라 mask 가 정하게 했다).

   그림 쪽에서 할 몫은 **상자를 하나로 만드는 것**이다. 종전 그림 상자는 11px
   이라 13px 원 안에 1px 씩 들여 놓인 **다른 상자**였고, 그 1px 은 1.25 배에서
   1.25 화소가 되어 반화소에 걸렸다. 이제 그림 상자를 원과 같은 13px 로 키우고
   눈금도 13 칸으로 옮긴다 — SVG 뷰포트가 원이 서는 바로 그 사각이라 둘이 같이
   간다. 눈금 규칙(한 칸 = 한 화소)은 그대로고, 잉크도 그대로 7×7(3..10)이다:
   바뀐 것은 그림이 들고 다니던 **빈 테두리 1px** 를 걷어낸 것뿐이라 보이는
   그림은 같다. ▶ 만 한 칸 오른쪽(4..11)인 것도 그대로 — 삼각형은 상자가 아니라
   무게중심으로 가운데를 잡는다.

   실측(거울 대칭 잔차 — 그림을 접었을 때 남는 차이, 0 이 완전 대칭 · ledger):
     배율 1     좌우 0.001 → 0.000 · 상하 0.001 → 0.000
     배율 1.25  좌우 0.087 → 0.022 · 상하 0.060 → 0.014
     배율 1.5   좌우 0.027 → 0.028 · 상하 0.026 → 0.020
   남은 1.5 의 몫은 그림 자체의 반화소다(7px 잉크 × 1.5 = 10.5화소라 어느 쪽에
   걸리는지가 카드의 화면 위치로 정해진다) — 감추지 않고 적어 둔다. */
const GLYPH_PLAY = '<svg class="gly" viewBox="0 0 13 13" aria-hidden="true"'
  + ' focusable="false"><path d="M4 3 L11 6.5 L4 10 Z" fill="currentColor"/></svg>';
const GLYPH_PAUSE = '<svg class="gly" viewBox="0 0 13 13" aria-hidden="true"'
  + ' focusable="false"><rect x="3" y="3" width="3" height="7" fill="currentColor"/>'
  + '<rect x="7" y="3" width="3" height="7" fill="currentColor"/></svg>';
/* 눌린 뒤의 얼굴을 한 붓이 칠한다 — 글리프 단추와 낱말 단추 둘 다.

   **이름은 요소가 들고 다닌다**(`data-name`). 칠하는 쪽이 상수를 골라 쓰면
   드리프트 카드에서 실제로 틀렸다: 「끝났는지 확인」을 눌렀다 거절당하면
   paintWake 가 WAKE_LABEL 을 박아 「이어가기」로 바뀌어 돌아왔다. 이름을
   그리는 자리와 되돌리는 자리가 갈라지면 늘 이렇게 된다.

   `textContent` 로 글리프 단추를 칠하면 `<svg>` 가 통째로 지워진다 — 글리프
   단추는 이름을 **글자가 아니라 aria-label 로** 갈아 끼운다.

   **잠금은 `disabled` 가 아니다** (REQ-20260831-009). `disabled` 를 걸면
   브라우저가 그 요소에서 포커스를 걷어 body 로 보낸다 — 키보드로 ▶ 에 닿아
   Enter 를 친 손이 그 순간 자기 자리를 잃는다(CDP 실측: activeAfter=BODY).
   게다가 disabled 요소의 이름 변경은 대개 낭독기에 통지되지 않아, 「이어가는
   중…」이라고 갈아 끼운 이름이 아무에게도 안 들린다. 연타를 막는 것은 원래
   `wokePending`/`stopPending` 이지 이 속성이 아니므로(누르는 자리 두 곳이 그
   관문을 먼저 지난다), 잠금은 **보이되 닿는** `aria-disabled` 로 말한다. */
// 그린 얼굴과 칠하는 얼굴이 같은 말을 하도록, 잠금 표시는 여기 한 곳에서 온다.
const DEED_BUSY = ' aria-disabled="true"';
function faceDeed(b, going, goingLabel){
  if (going) b.setAttribute("aria-disabled", "true");
  else b.removeAttribute("aria-disabled");
  b.classList.toggle("busy", going);
  const name = going ? goingLabel : (b.dataset.name || "");
  // 얹은 손에게 하는 말: 평소엔 무슨 일이 일어나는지(data-tip), 도는 중엔 그 사실.
  b.title = going ? goingLabel : (b.dataset.tip || name);
  if (b.classList.contains("ico")) b.setAttribute("aria-label", name);
  else b.textContent = name;
}
const wokeAt = new Map();          // REQ id → 누른 시각(ms)
const WOKE_HOLD = 180000;          // 3분. 스폰이 조용히 죽어도 다시 누를 수 있게
function wokePending(id){
  const t = wokeAt.get(id);
  if (t == null) return false;
  if (Date.now() - t > WOKE_HOLD){ wokeAt.delete(id); return false; }
  return true;
}
/* 세우기도 같은 기억을 쓴다 (REQ-20260829-024). 다만 잠금은 짧다 — 세우기는
   서버가 SIGTERM 뒤 최대 5초를 기다렸다 답하고, 그 답이 오면 곧 행에서
   `worker` 가 사라져 손잡이 자체가 없어진다. 깨우기의 3분은 "스폰이 조용히
   죽어도 다시 누를 수 있게"라는 다른 사정에서 온 수라 그대로 쓰지 않는다. */
const stopAt = new Map();          // REQ id → 누른 시각(ms)
const STOP_HOLD = 20000;
function stopPending(id){
  const t = stopAt.get(id);
  if (t == null) return false;
  if (Date.now() - t > STOP_HOLD){ stopAt.delete(id); return false; }
  return true;
}
/* **멈춤 술어는 화면에 하나뿐이다** (REQ-20260828-041 2차 반려).

   화면에는 갈래가 둘 남아 있었다. ① 카드만 `!bl.length` 관문을 가져, 선행 대기
   줄이 선 요청은 카드에서 손잡이를 통째로 잃었는데 문서 화면은 그 관문을 몰라
   같은 요청을 깨울 수 있었다 — **같은 요청이 두 자리에서 다른 말을 한다**.
   ② 점은 `live_kind` 를, 손잡이는 `stalled_mins` 를 각자 읽었다. 서버가 라운드1
   에서 둘을 한 벌로 만들어도, 화면이 두 필드를 따로 읽는 한 한쪽만 서는 조합이
   남는다 — 그것이 사용자가 본 "멈췄다고 적혀 있는데 누를 게 없는 카드"다.

   그래서 판정을 여기 한 곳으로 모은다. 점·줄·손잡이·열 머리 수·정렬이 전부 이
   함수를 먹으므로 어긋날 자리가 구조적으로 없다.

   **화면은 분을 짓지 않는다**: 서버가 실어 준 값을 옮길 뿐이고(REQ-20260828-036),
   분이 없으면 서버가 준 이유(live_reason)를 그대로 쓴다. 스스로 세기 시작하면
   CLI(`s9 stalled`)와 다른 수를 말하게 된다.

   **문은 하나, 얼굴은 둘.** 문(멈췄나?)은 서버가 지금 다시 잰 `stalled_mins`
   하나가 연다 — 색인에 굳은 작업자 기록은 문을 열지 못한다(어제 22:36 의 정지가
   오늘 카드를 칠하던 자리다). `live_kind` 는 문 안에서 **얼굴만** 고른다:
   처리 주체가 죽은 것이 기록돼 있으면 실패의 사각(정지 신호의 관습), 아니면
   같은 사각의 속 빈 형태. 이렇게 하면 점·줄·손잡이가 셋 다 같은 문을 지나므로
   "멈췄다고 그려 놓고 못 누르는 카드"도, 그 반대(누를 수 있는데 점은 조용한
   카드)도 구조적으로 생길 수 없다.

   반환: null(안 멈췄다) 또는 {mins, face, reason}
     face "dead" = 처리 주체가 죽었다(spawn_failed) · "mild" = 진전이 끊겼다 */
function stallState(r){
  if (!r || r.type !== "request" || r.status !== "in-progress") return null;
  if (r.stalled_mins == null) return null;   // 서버가 안 잰 것은 멈춤이 아니다
  return {mins: r.stalled_mins,
          face: r.live_kind === "spawn_failed" ? "dead" : "mild",
          reason: r.live_reason || ""};
}

/* ---- 누가 만들고 누가 맡았나 (REQ-20260902-021, DOC-20260902-001 §2 축1+2) ----

   `user` 가 **담당자**로 재정의되면서(D2) 화면이 답해야 할 물음이 하나 늘었다:
   배지의 이름이 만든 사람인가 맡은 사람인가. 둘이 갈리는 순간(재할당·에이전트
   생성)부터 이름 하나로는 못 답한다.

   **낱말은 우리 말로, 내부어는 화면에 안 낸다.** `lease`·`claim`·`takeover`·
   `assignee` 는 사람이 터미널에 치는 낱말이 아니라 이 코드가 자기끼리 쓰는
   말이다 — 화면을 닫고 그 일을 하려면 사람이 치는 것은 `s9 assign` 하나뿐이고,
   그것마저 이 제품이 스스로 지은 이름이라 원어 보존 조항(pull·push)이 걸리지
   않는다. 그래서 화면에는 「담당」·「만든이」·「이 컴퓨터로 가져오기」가 선다.

   **역할 이름은 그대로 둔다** — `designer`·`ux-writer` 는 이 저장소의 문서
   앞머리(`agents:`)와 위임 지시문에 같은 글자로 박힌 이름이라, 화면에서만
   옮기면 "그게 그거인가"를 매번 이어 붙여야 한다(상태 이름 done·in-progress
   가 한글로 안 서는 그 이유, REQ-20260828-007). 이름이 아닌 것 둘만 우리
   말이다: `lead:*` → 「리드」(이 저장소의 한국어 산문이 이미 쓰는 말),
   `worker:*` → 「백그라운드 작업」(REQ-20260902-005 확정어). */
/* 만든 사람 — 필드가 없는 옛 문서는 `user`(생성자=담당자였다)로 읽는다.
   서버의 `doc_creator` 와 **같은 규칙**이다: 읽는 규칙이 두 벌이면 카드와
   CLI 가 다른 이름을 말한다 (D6 — 파일은 하나도 고치지 않고 읽을 때 맞춘다). */
const docCreator = r => String((r && (r.creator || r.user)) || "");
function originWho(r){
  const a = String((r && r.origin_actor) || "");
  if (!a) return "";
  if (a.startsWith("sub:")) return a.slice(4);
  if (a.startsWith("lead")) return "리드";
  if (a.startsWith("worker")) return "백그라운드 작업";
  return a;
}
/* 기원 한 조각 — 「사람이 직접」 · 「에이전트 designer」 · 「REQ-… 처리 중」.
   **옛 문서는 아무것도 그리지 않는다**: origin 이 빈 값인 것은 "사람이 직접이
   아니다"가 아니라 **모른다**이고, 모르는 것을 「기록 없음」이라고 적으면
   화면이 없는 사실을 한 줄 만들어 낸다 (D6 — 지어내지 않는다). */
function originBits(r, link){
  const o = String((r && r.origin) || "");
  if (!o) return [];
  const who = originWho(r);
  if (o === "human") return ["사람이 직접"];
  const bits = [who ? (who === "리드" || who === "백그라운드 작업"
                        ? who : `에이전트 ${who}`) : "에이전트"];
  if (o === "derived" && r.origin_req)
    bits.push(link ? `${dlink(r.origin_req, esc(shortId(r.origin_req)))} 처리 중`
                   : `${esc(shortId(r.origin_req))} 처리 중`);
  return bits;
}
/* 카드가 지는 몫은 **놀라운 사실 하나**다.

   대안 셋을 재 봤다. ㉠ 카드에 「만든 사람 · 맡은 사람 · 기원」을 통째로 한 줄
   — 카드마다 한 줄이 늘고, 그 줄의 대부분은 배지가 이미 말한 것을 되풀이한다
   (s9-design 「카드 사실 줄」: 정상의 서술은 줄 자격이 없다). ㉡ 툴팁에만 —
   손이 없는 사람에게는 없는 것과 같다. ㉢ **기존 메타 줄(.m)에 조각 하나**,
   그것도 배지가 못 하는 말이 있을 때만. 채택은 ㉢ 이다: 새 줄 0, 새 층 0,
   되돌릴 것 0. 온전한 한 줄은 문서 머리가 진다(훑는 자리와 읽는 자리의 몫이
   다르다 — 작업 자리 칩이 카드에서 내려간 그 판단, REQ-20260829-030 4차).

   배지가 못 하는 말은 둘뿐이다: 만든 사람이 담당자와 다르다 · 사람이 아닌
   것이 만들었다. 둘 다 아니면 조각도 없다. */
function lineageChip(r){
  const creator = docCreator(r);
  const owner = String((r && r.user) || "");
  const o = String((r && r.origin) || "");
  const who = (o && o !== "human") ? (originWho(r) || "에이전트")
            : (creator && creator !== owner) ? creator : "";
  if (!who) return "";
  return `<span class="lin" title="${esc(lineageTell(r))}">`
    + `<span class="lincap">만든이</span>${esc(who)}</span>`;
}
// 손 위의 글과 낭독기가 함께 읽는 한 문장 — 조각이 줄인 것을 여기서 다 말한다.
function lineageTell(r){
  const creator = docCreator(r);
  const owner = String((r && r.user) || "");
  const bits = [];
  if (creator) bits.push(`만든 사람 ${creator}`);
  if (owner) bits.push(`맡은 사람 ${owner}`);
  const ob = originBits(r, false).map(x => x.replace(/<[^>]*>/g, ""));
  return bits.concat(ob).join(" · ");
}
/* 문서 머리의 온전한 한 줄. 카드와 **같은 재료**(originBits)를 쓰므로 두 화면이
   갈라질 자리가 없다 — 같은 사실을 두 함수가 지으면 한쪽만 고쳐진다. */
function lineageRowHTML(r){
  if (!r || r.type !== "request") return "";
  const creator = docCreator(r), owner = String(r.user || "");
  const cells = [];
  if (creator) cells.push(`<span class="lincap">만든 사람</span>`
    + `<span class="badge" style="--ah:${tagHue(creator)}">${badgeFace(creator)}</span>`);
  if (owner) cells.push(`<span class="lincap">맡은 사람</span>`
    + `<span class="badge" style="--ah:${tagHue(owner)}">${badgeFace(owner)}</span>`);
  /* 기원은 **제 칸을 갖지 않는다** — 「만든 사람」 칸의 뒤에 붙는다.
     따로 세우면 라벨 없는 조각(「리드 · REQ-014 처리 중」)이 줄 끝에 떠서,
     그것이 누구의 무엇인지 말해 주는 것이 사라진다. 만든 계정과 그것을 쥔
     손은 한 사실의 두 겹이니 한 칸이 맞다. 계정이 없는 옛 문서에서만 카드가
     쓰는 그 낱말(「만든이」)로 홀로 선다 — 두 화면이 같은 값을 다르게 부르지
     않게 한다. */
  const ob = originBits(r, true);
  if (ob.length){
    if (creator) cells[0] += ` ${ob.join(" · ")}`;
    else cells.push(`<span class="lincap">만든이</span>${ob.join(" · ")}`);
  }
  if (!cells.length) return "";
  return `<div class="lineage">`
    + cells.map(c => `<span class="lincell">${c}</span>`).join("") + `</div>`;
}

/* ---- 다른 컴퓨터가 쥔 요청 (REQ-20260902-021 · D1 이관 경로 (b)) ----------

   문서에 적힌 리스는 「담당자 + 처음 집은 머신」이다. 다른 컴퓨터의 리스는
   **벽시계만** 본다(pid·경로는 그 컴퓨터에서만 참) — 그래서 이 화면이 아는
   것도 벽시계뿐이고, 말할 수 있는 것도 「저기서 진행 중」까지다.

   **시계는 하나여야 한다.** 이 수(초)는 bin/s9 의 `DOC_LEASE_TTL` 과 같은
   수다 — 갈라지면 화면이 「진행 중」이라 쓴 카드를 서버는 free 로 보고 워커를
   띄운다. `SLOW_WIN` 이 서버의 STALLED_WIN 과 대조되는 것과 같은 규율이고,
   대조는 tests/test_assign_screen.py 가 한다. */
const LEASE_TTL = 1800;
function leaseElsewhere(r){
  // 진행 축의 사실이다 — 「진행 중」이라 말하려면 정말로 진행 중이어야 한다.
  // 끝난 카드에 남은 리스는 30분 뒤 저절로 식지만, 그 30분 동안 done 열에
  // 「어디서 진행 중」이 서면 그것은 거짓말이다.
  if (!r || r.type !== "request" || r.status !== "in-progress") return null;
  const l = r.lease || null;
  if (!l || !l.machine) return null;
  const mine = (window.__whoami || {}).machine || "";
  if (!mine || l.machine === mine) return null;   // 제 자리는 남의 자리가 아니다
  const t = Date.parse(l.renewed || l.since || "");
  if (isNaN(t)) return null;
  const age = Math.floor((Date.now() - t) / 1000);
  if (age >= LEASE_TTL) return null;              // 만료 — 아무도 안 쥐고 있다
  return {machine: l.machine, user: l.user || "", mins: Math.floor(age / 60)};
}
/* 「이 컴퓨터로 가져오기」는 **담당자 본인과 admin** 에게만 선다 (D1 (b)).
   남에게는 손잡이가 없다 — 여기서 숨기는 것은 권한이 아니라 **뜻**이다:
   남의 일을 내 컴퓨터로 끌어오는 것은 담당을 바꾸는 일이고, 그 길은 옆에
   따로 있다(담당 바꾸기). 두 손잡이가 같은 일을 하면 사람은 어느 쪽이
   되돌릴 수 있는 쪽인지 못 고른다. */
function canTakeover(r){
  const me = viewMe();
  return !!me && (me === String((r && r.user) || "") || isAdmin());
}
function elsewhereRowHTML(r){
  const e = leaseElsewhere(r);
  if (!e) return "";
  const when = e.mins < 1 ? "방금" : `${e.mins}분 전`;
  const row = `<div class="rvpt elsew" title="이 요청은 ${esc(e.machine)} 에서`
    + ` ${esc(when)}까지 움직였습니다 — 이 컴퓨터에서는 진행을 볼 수 없습니다">`
    + `<span class="rvcap">다른 컴퓨터</span>${esc(e.machine)} 에서 진행 중`
    + ` · ${esc(when)}</div>`;
  if (!canTakeover(r)) return row;
  /* 낱말 손잡이는 제 줄을 갖는다 — 「끝났는지 확인」이 세운 그 실측 규칙
     (.deedrow.wordy): 좁은 칸에서 같은 줄에 세우면 문장이 잘려 버튼이 무엇에
     대한 것인지 말하는 근거가 사라진다. */
  return `<div class="deedrow wordy">` + row
    + `<div class="acts"><button type="button" class="deed"`
    + ` data-takeover="${esc(r.id)}"`
    + ` title="이 요청의 진행을 이 컴퓨터로 옮깁니다 — ${esc(e.machine)} 는`
    + ` 다음 차례에 손을 뗍니다">이 컴퓨터로 가져오기</button></div></div>`;
}
/* 담당 바꾸기 손잡이. **권한 없는 사람에게도 선다** — 숨기면 화면이 권한 판정을
   한 벌 더 갖게 되고(서버와 갈라질 자리), 사람은 "왜 나는 못 하나"를 물을 데가
   없다. 누르면 서버의 거부 문장이 그대로 뜬다: 문구는 한 벌이다. */
/* 문서 화면의 「담당 바꾸기」는 **행동 띠**에 선다 (REQ-20260830-046 이 세운
   자리: 행동은 한 무리에 모여 제목과 함께 붙박인다). 혈통 줄의 배지에 또
   달지 않는다 — 한 화면에서 같은 행동에 손잡이가 둘이면 사람은 둘이 다른
   일인지 먼저 의심한다. 카드에서는 반대다: 띠가 없으므로 배지가 곧 손잡이다.
   낱말·길·창은 한 벌이라(assignDoc) 두 자리가 갈라질 데가 없다. */
function assignBtnHTML(r){
  if (!r || r.type !== "request" || TERMINAL.has(r.status)) return "";
  return `<button type="button" class="deed asgn" data-assign="${esc(r.id)}"`
    + ` title="이 요청을 맡을 사람을 바꿉니다">담당 바꾸기</button>`;
}
/* 카드의 담당 배지는 **그 자체가 손잡이**다 (직접 조작 — 바꿀 값을 누른다).

   카드에 낱말 단추를 하나 더 세우지 않는 이유는 자리가 아니라 위계다: 카드의
   결정은 「이 요청에 지금 무엇을 하나」 하나이고, 담당 바꾸기는 그 아래 급이다.
   누를 수 있다는 것은 이 화면이 **이미 가진** 문법이 말한다 — 점선 밑줄
   (`.wsat`·`.pname` 이 쓰는 그 밑줄) 하나뿐이고, 사람이 새로 배울 것은 없다.
   요청이 아니거나 끝난 문서에서는 그냥 글자로 선다(없는 조작을 가리키지 않는다). */
// 배지의 속 — 이니셜 링(calm 전용 마크)과 이름. 배지가 서는 자리 셋(카드 ·
// 문서 머리의 만든 사람 · 맡은 사람)이 한 함수를 쓴다.
/* 이름을 따로 감싸는 것은 **밑줄이 이름의 것이기 때문**이다 (REQ-20260902-021
   반려). 단추 전체에 밑줄을 주면 calm 스킨의 이니셜 링(.av — 18px 원)
   **밑으로도** 점선이 지나가, 원 아래 잘린 선이 깨진 그림처럼 보인다. 누를 수
   있다고 말하는 것은 이름이지 마크가 아니다. */
function badgeFace(u){
  return `<i class="av">${esc(String(u).slice(0, 1).toUpperCase())}</i>`
    + `<span class="bnm">${esc(u)}</span>`;
}
function ownerBadgeHTML(r){
  const u = (r && r.user) || "?";
  const face = badgeFace(u);
  const st = ` style="--ah:${tagHue(u)}"`;
  if (!r || r.type !== "request" || TERMINAL.has(r.status))
    return `<span class="badge"${st}>${face}</span>`;
  return `<button type="button" class="badge asgnb"${st}`
    + ` data-assign="${esc(r.id)}"`
    + ` title="맡은 사람 ${esc(u)} — 눌러서 담당을 바꿉니다">${face}</button>`;
}
/* 이 요청에 지금 **사람이 할 수 있는 일**을 짓는 한 함수 (REQ-20260828-041,
   REQ-20260829-024).

   보드 카드와 문서 화면이 각자 글자를 가지면 한쪽만 고쳐진다 — 판정 버튼이
   그 이유로 세 번 반려됐다 (REQ-20260828-007). 같은 함수를 부르면 갈라질 자리가
   없다. 안 멈춘 행에는 빈 문자열을 돌려준다 — 부르는 쪽이 조건을 따로 갖지
   않게 하려는 것이다(그 조건이 갈래를 낳았다).

   손잡이는 이제 둘이다. 멈춘 것은 **깨우고**, 도는 것은 **세운다**. 둘을 한
   함수에 둔 이유도 같다: 부르는 자리가 둘(카드·문서)인데 조건을 따로 두면
   같은 요청이 한 자리에선 세워지고 다른 자리에선 안 세워진다 — 이 화면이
   이미 한 번 겪은 갈래다. 둘은 사실상 배타적이다(도는 것은 멈춘 것이 아니다).
   그래도 겹쳐 서는 순간이 있으면 그대로 둘 다 그린다: 서버가 그렇게 말한
   것이고, 화면이 서버의 말을 지우는 자리는 두지 않는다. */
/* ---- 카드가 글자로 말할 자격 (REQ-20260830-040 designer 개정안) -------------

   사용자: "기껏 중지, 시작 버튼을 작게 만들어서 카드를 다듬어뒀더니 또 디자인이
   이렇다. 그리고 기능도 이게 맞는건가?"

   맞는 지적이었고 원인은 둘이었다. ① 「⏸ 는 카드에 하나」 사다리가 **손잡이만**
   지배하고 줄은 지배하지 않아, 잡 전용 갈래가 사다리 밖에서 따로 줄을 세우고
   같은 카드에 담당 줄이 또 섰다. ② 줄 자격의 기준이 없었다 — 「진행 중 자동
   작업 0분째」·「맡은 창 일하는 중」·「담당 없음」·「손길 3분 전 · 34분째 조용」은
   전부 **정상의 서술**이고, in-progress 열 이름과 점이 이미 한 말이다.

   그래서 자격을 세운다. **줄은 「정상이 아니다」 또는 「당신이 할 일이 있다」를
   말할 때만 선다**:
     줄(글자)  중단 · 멈춤(+고친 것 있음) · 선행 대기 · 오래 걸림
     점        지금 무엇이 붙어 있는가 (livedot 다섯 얼굴)
     툴팁·숨김 글자  신원 · 경과 분 · 잡 이름 (holdTell)
   그리고 **축마다 하나, 최대 둘**이다: 관계 축(선행 대기, cardHTML) 1줄 +
   진행 축 1줄. 진행 축 사다리는 중단 > 멈춤 > 오래 걸림 > (없음). */
/* 서버의 멈춤 창과 **같은 수**를 쓴다 (개정안 규칙 3).

   「테스트 4분째」·「자동 작업 0분째」는 사실이지 신호가 아니다 — 캡션이 정상을
   서술하면 그 줄은 신호가 아니라 배경이 되고, 배경이 카드에서 가장 큰 자리를
   먹는다(실측: 그 줄들이 선 카드 210px, 같은 열의 open 카드 90px).
   새 수를 짓지 않는다: 서버가 이미 가진 STALLED_WIN 을 그대로 재사용해 그보다
   오래 걸린 것만 「오래 걸림」으로 세운다. 「0분째」는 이 한 줄로 사라진다.
   두 수가 갈라지면 화면이 CLI(`s9 stalled`)와 다른 말을 하게 되므로,
   tests/test_stall_pair.py 가 bin/s9 의 수와 이 수를 대조한다. */
// 단위는 초 — bin/s9 의 STALLED_WIN 과 **같은 수**여야 한다.
const SLOW_WIN = 900;
/* 긴 잡 조각 (REQ-20260830-022) — 서버가 pid 생존·명령줄 대조를 지나 실은 값만
   옮긴다(화면 재판정 없음). **자기 줄은 갖지 않는다** (규칙 2): 이긴 사실 줄의
   꼬리로 붙고, 이긴 줄이 없으면 신원 문장까지만 간다. 종전에는 이 조각이 한 줄을
   통째로 쓰는 동안 정작 중요한 멈춤 줄이 폭을 잃고 잘렸다. */
function jobBit(r){
  return ((r && r.jobs) || [])
    .map(j => `${esc(j.name)} ${fmtStall(+j.mins || 0)}`).join(" · ");
}
/* 꼬리는 **하나뿐이다** (REQ-20260830-043 사용자 실측).

   사용자: "레이아웃이 정확했으면 좋겠다." 캡처에서 멈춤 줄이 이렇게 끝났다 —
   「멈춤 42분째 진전 없음 · 마지막 20:39 · 테스트 …」. 조각을 무게순으로 잇고
   넘치면 뒤부터 잘리게 두었는데, **잘린 조각은 정보가 아니라 고장으로 읽힌다**:
   「· 테스트 …」는 무엇이 몇 분째인지 하나도 말하지 못하면서 자리만 먹는다.

   그래서 자르는 대신 **고른다**. 꼭 서야 하는 사실(N분째 진전 없음) 뒤에 무게순
   후보를 늘어놓고 이긴 하나만 붙인다. 떨어진 조각은 사라지지 않는다 — 신원
   문장(holdTell)이 툴팁과 숨김 글자로 그대로 나른다. 「이긴 줄이 없으면
   툴팁으로」(REQ-20260830-040 규칙 2)를 「자리가 없으면 툴팁으로」까지 편 것이다.

   무게 순서는 부르는 쪽이 정한다: 「고친 것 있음」은 손잡이의 낱말을 바꾸는
   근거라 맨 앞이고, 「마지막 HH:MM」은 바로 앞의 「N분째」와 같은 사실을 다른
   꼴로 되풀이하므로 맨 뒤다. */
function factTail(...bits){
  const t = bits.filter(Boolean)[0];
  return t ? ` · ${t}` : "";
}
/* 판정 큐의 한 줄 (REQ-20260831-015, DOC-20260831-002 규칙 2).

   사용자가 겪은 일: 선행이 아직 판정 전인데 연관 후행이 먼저 구현·판정됐고,
   선행이 반려되자 후행이 딸려 무너질 뻔했다. 결정문이 고른 답은 **잠금이
   아니라 순서와 경고**다 — 잠글 키(판정 의존 간선)가 저장 구조에 없고, 잠그면
   끝난 작업이 in-progress 에 갇혀 스톨·워처·클레임이 오판한다.

   그래서 화면이 지는 몫은 둘이다. 열은 `review_order` 로 세워 **묶음이 붙어
   서고 선행이 위에** 오게 하고(reviewKey), 카드는 그 사실을 한 줄로 말한다.

   **사다리인 이유** — 둘 다 관계 축이다(s9-design 「카드 사실 줄」: 축마다 한 줄,
   카드 최대 두 줄). 낡음이 먼저 판정을 이긴다: 순서는 정렬이 이미 눈으로
   말한다(선행이 바로 위에 서 있다) — 이 줄이 없어도 잃는 것이 적다. 낡음은
   정렬이 말할 수 없는 것이고, 「지금 판정해도 되는가」라는 더 앞선 물음이다.
   진 조각은 이긴 줄의 꼬리로 붙어 사라지지 않는다(factTail).

   **가리키는 것은 이름이다.** id 만 세우면 무슨 건인지 떠오르지 않은 채
   "먼저 보라"는 말만 남는다 — 판정 카드가 요약을 얻은 이유와 같다
   (REQ-20260826-023). 카탈로그에 없는 대상만 짧은 id 로 떨어진다.

   **잠그지 않는다.** 경고-only 다: 승인·반려 버튼은 그대로 눌린다(A안 기각). */
/* 낱말은 ux-writer 확정본이다 (REQ-20260831-015 --label ux-writer 노트).
   「판정 짝」(리드 초안)은 국어에 없는 그 자리 합성어이자 실제로는 N건이라
   기각됐고, 「선행 판정」은 `선행` 을 선행 대기(진짜 막힘)와 나눠 써서 경고-only
   줄이 잠금으로 읽히게 만든다. 「낡음」은 사실이 아니다 — 낡은 것이 아니라
   지금 바뀌는 중이다. 캡션은 이 화면의 문법 그대로 **이 카드의 사실을 말하는
   명사구**이고, 상대 문서는 본문이 가리킨다. */
const JQ_AHEAD = "판정 순서";
const JQ_CHURN = "바뀌는 중";
function judgeQueueHTML(r){
  if (!r || r.type !== "request" || r.status !== "review") return "";
  const look = id => { const d = catFind(id); return d && d.title ? d.title : shortId(id); };
  const prior = r.review_prior || [], churn = r.review_stale || [];
  if (!prior.length && !churn.length) return "";
  const more = n => n > 1 ? `<span class="depmore"> 외 ${n - 1}건</span>` : "";
  const named = ids => esc(ids.map(i => shortId(i) + " " + look(i)).join(" · "));
  // 「먼저」 세 글자는 뺄 수 없다 — 없으면 본문의 제목이 앞 것인지 뒤 것인지가
  // 안 정해진다 (ux-writer).
  const aheadTip = `먼저 판정하는 편이 좋은 요청입니다 — ${named(prior)}`
    + ` (순서 안내일 뿐이라 지금 이 요청부터 판정해도 막히지 않습니다)`;
  if (churn.length)
    return `<div class="rvpt churn" title="이 요청과 이어진 작업이 아직 진행 중입니다`
      + ` — ${named(churn)}. 지금 판정한 내용이 곧 달라질 수 있습니다`
      + `${prior.length ? `. ${aheadTip}` : ""}">`
      + `<span class="rvcap">${JQ_CHURN}</span>${esc(look(churn[0]))}${more(churn.length)}`
      + factTail(prior.length ? `먼저 ${esc(shortId(prior[0]))}` : "") + `</div>`;
  return `<div class="rvpt ahead" title="${aheadTip}">`
    + `<span class="rvcap">${JQ_AHEAD}</span>먼저 ${esc(look(prior[0]))}${more(prior.length)}</div>`;
}
/* 판정 큐의 정렬 키 (REQ-20260831-015). 서버가 실은 값을 그대로 쓰되, 없는
   행은 **서버가 단독 묶음에 지어 주는 그 꼴**로 떨어진다 — `<created>|<id>|000`.
   같은 자로 재야 섞여 있어도 열이 뒤집히지 않는다: 필드가 없다고 빈 문자열을
   주면 옛 행이 통째로 맨 위로 뛰고, 없다고 정렬을 통째로 포기하면 새 행의
   묶음이 흩어진다. 화면은 이 키를 짓기만 하지 판정하지 않는다 — 묶음이
   무엇인지는 서버(review_family) 한 곳이 안다. */
function reviewKey(r){
  return r.review_order || `${r.created || ""}|${r.id}|000`;
}
/* ⏸ 한 개의 HTML. **카드에 ⏸ 는 하나뿐**이고, 그 자리는 이제 사실 줄이 아니라
   id 줄이다 (규칙 4) — 자리 규칙은 deedBeltHTML 주석에 있다.

   `wordy` (REQ-20260830-046): 문서 화면에서는 글리프에 낱말을 붙인다 — 카드의
   27px 원형이 정당한 이유(224px 칸의 폭 다툼)가 1030px 문서에는 없고, 낱말 없는
   11px 회색 글리프가 "안 보인다"의 절반이었다. 얼굴만 갈리고 이름·길·상태는
   같다. wgly 는 ico 가 아니라 낱말 단추 계보다 — 스킨별 알약 모양을 그대로
   물려받고, faceDeed 의 낱말 규칙(textContent)이 상태를 칠한다(실패 복귀 시
   글리프는 다음 그리기가 되살린다 — 문서는 곧 다시 그려진다). 조건 두 벌 금지. */
function stopBtnHTML(r, wordy){
  const kind = (r.stoppable || {}).kind;
  if (!kind) return "";
  const going = stopPending(r.id);
  const tip = (STOP_KIND[kind] || {}).tip || STOP_KIND.idle.tip;
  return `<button type="button" class="deed stop ${wordy ? "wgly" : "ico"}${going ? " busy" : ""}"`
    + ` data-stop="${esc(r.id)}" data-kind="${esc(kind)}"${going ? DEED_BUSY : ""}`
    + ` data-name="${STOP_LABEL}" data-tip="${esc(tip)}"`
    + ` aria-label="${going ? STOP_GOING : STOP_LABEL}"`
    + ` title="${going ? STOP_GOING : esc(tip)}">${GLYPH_PAUSE}`
    + (wordy ? `<span class="lbl">${STOP_LABEL}</span>` : "") + `</button>`;
}
/* 사람이 중단해 둔 자리인가 — 술어 하나 (REQ-20260829-024 라운드4).
   줄(stoppedRowHTML)과 ▶ 의 갈래(wakeBtnHTML)가 각자 조건을 가지면 줄은 「중단」
   이라 적었는데 손잡이는 「이어가기」가 아닌 다른 것을 부르는 조합이 생긴다 —
   이 화면이 판정 버튼에서 세 번 배운 그 결함이다. */
function heldState(r){
  return !!(r && r.type === "request" && r.stopped && !r.worker);
}
/* 신원은 줄을 떠나 **툴팁과 낭독기**로 간다 (규칙 1, 그리고 규칙 4의 필수 조건).

   한 문장을 두 곳이 함께 쓴다: id 줄에 손이 얹히면 `title` 로 읽히고, 눈으로
   못 읽는 사람에게는 **같은 문장이 시각적 숨김 글자로 그 줄에 실린다**. 툴팁
   전용으로 두면 키보드·낭독기 경로가 끊긴다 — designer 가 이 개정을 통과시키며
   단 조건이 정확히 그것이다.

   문장 = 신원(STOP_KIND[kind].who) + 사실 조각(경과 분·잡 이름·마지막 손길).
   사실 조각은 괄호로 뒤에 붙인다: 신원 문장이 먼저 읽혀야 "무엇이 붙어 있나"에
   답이 되고, 수는 그 답을 뒷받침하는 것이지 답이 아니다.

   손길 사실(REQ-20260830-019·021)은 줄을 잃었지만 사라지지는 않는다 —
   "조용함을 감추지 않는다"는 그 요청의 뜻은 여기서 지켜진다. 줄로 세우지 않을
   뿐이다: 붙어 있는 카드가 조용한 것은 아직 정상이고, 정상은 줄이 아니라 점과
   이 문장이 말한다. */
function holdTell(r){
  if (!r || r.type !== "request" || r.status !== "in-progress") return "";
  const k = STOP_KIND[(r.stoppable || {}).kind] || {};
  const bits = [];
  // 분은 서버가 준 초를 단위만 바꿔 옮긴다 — 화면이 시계를 대면 CLI 와 갈린다.
  if (r.worker) bits.push(fmtStall(Math.floor((+r.worker.age || 0) / 60)));
  const jb = jobBit(r);
  if (jb) bits.push(jb);
  if (r.stall_state === "attached" && r.hand_mins != null && r.quiet_mins != null)
    bits.push(`마지막 손길 `
      + (r.hand_mins < 1 ? "방금" : `${fmtStall(r.hand_mins).replace(/째$/, "")} 전`)
      + ` · ${fmtStall(r.quiet_mins)} 조용`);
  return (k.who || "") + (bits.length ? ` (${bits.join(" · ")})` : "");
}
/* ▶ 는 카드에 하나다 — 멈춘 것을 이어가거나(`data-wake`), 사람이 중단해 둔 것을
   되돌린다(`data-restart`). 둘은 배타적이다: 중단해 둔 카드는 멈춤 판정을 이긴다.
   낱말 손잡이(「끝났는지 확인」)는 여기 서지 않는다 — 아래 driftBtnHTML 참조. */
function wakeBtnHTML(r, wordy){
  const held = heldState(r);
  const st = held ? null : stallState(r);
  if (!held && !st) return "";
  if (st && r.commit_drift) return "";
  const going = wokePending(r.id);
  /* 손 위의 글은 **[이 카드의 처지] — [누르면 무엇이 되나]** 다 (REQ-20260830-042
     ux-writer). 단추가 하나로 줄면 "왜 지금 이것 하나인가"가 화면에 없어지는데,
     첫 마디를 붙이는 것으로 족하다.
     멈춤 갈래의 꼬리 한 줄은 카드에서 사라진 정책(잠그기)의 길을 알려 준다 —
     그 단추는 카드를 열면 나오는 문서의 **맨 위 행동 띠**에 있다(REQ-20260830-046:
     "문서를 열면 있다"고만 말해 놓고 바닥까지 훑게 만든 것이 실사고다). */
  /* 재개의 동사는 **「이어받다」** 다 (DOC-20260831-005 규칙 3). 「시작합니다」는
     새로 나는 일처럼 읽히고 「진행합니다」는 주체가 새 주인처럼 읽히는데, 이
     단추가 하는 일은 **앞선 일이 있고 그것이 내 것이었다** 이다 — 사용자의
     문장("요청하고, 멈췄고, 다시 시작했을 뿐")이 그대로 이 낱말이다. */
  const tip = held
    ? "사람이 중단해 둔 요청입니다 — 누르면 하던 일이 다시 이어집니다"
    : "담당 없이 멈춰 있습니다 — 누르면 멈춘 자리에서 다시 이어집니다."
      + " 자동 이어받기 끄기 단추는 카드를 열면 맨 위에 있습니다";
  // 속성 이름을 조립하지 않는다(`data-${...}`) — 짓는 자리를 세는 회귀 시험도,
  // 다음 사람의 grep 도 조립된 이름을 못 찾는다.
  const at = held ? `data-restart="${esc(r.id)}"` : `data-wake="${esc(r.id)}"`;
  return `<button type="button" class="deed wake ${wordy ? "wgly" : "ico"}${going ? " busy" : ""}"`
    + ` ${at}${going ? DEED_BUSY : ""}`
    + ` data-name="${WAKE_LABEL}" data-tip="${esc(tip)}"`
    // 글리프 단추는 이름을 글자가 아니라 여기로 실어 낸다 — 낭독기에도, 손에도.
    + ` aria-label="${going ? WAKE_GOING : WAKE_LABEL}"`
    + ` title="${going ? WAKE_GOING : esc(tip)}">${GLYPH_PLAY}`
    + (wordy ? `<span class="lbl">${WAKE_LABEL}</span>` : "") + `</button>`;
}
/* 셋째 손잡이만 낱말이고, **자기 줄을 지킨다** (REQ-20260830-032 · -040 규칙 4).

   ▶ 는 "이어간다"를 말하는데 드리프트 카드가 청하는 일은 "끝났는지 보라"다 —
   같은 그림에 두 뜻을 실으면 그 둘을 가르는 것은 바로 위 줄의 「고친 것 있음」
   뿐인데, 그 줄은 ellipsis 라 뒤부터 잘린다. ✓ 로 가르는 길도 막혀 있다:
   같은 카드의 「승인 done」이 이미 승인의 그림이다. 규칙은 하나다 —
   **전송 문법에 있는 것만 글리프, 나머지는 낱말.**
   낱말은 87px 라 글리프처럼 id 줄에 얹으면 식별자를 밀어낸다. 드문 갈래 하나라
   자기 줄(.deedrow.wordy)을 그대로 둔다. */
const DRIFT_TIP = "고친 것이 있는데 문서가 안 닫혔습니다 — 다 됐는지"
  + " 확인해서, 됐으면 마무리하고 아니면 이어갑니다";
function driftBtnHTML(r){
  const going = wokePending(r.id);
  return `<div class="acts wakerow"><button type="button" class="deed wake`
    + `${going ? " busy" : ""}" data-wake="${esc(r.id)}"${going ? DEED_BUSY : ""}`
    + ` data-name="${DRIFT_LABEL}" data-tip="${esc(DRIFT_TIP)}"`
    + ` title="${going ? WAKE_GOING : esc(DRIFT_TIP)}">`
    + `${going ? WAKE_GOING : DRIFT_LABEL}</button></div>`;
}
/* 손잡이 벨트 — **▶ 와 ⏸ 는 사실 줄을 떠나 id 줄에 선다** (규칙 4).

   글리프가 사실 줄의 오른쪽 끝에 붙어 있던 동안, 손잡이의 자리는 카드마다
   달랐다(멈춤 줄 · 진행 중 줄 · 담당 줄 · 빈 줄). 자리가 사실을 따라다니면
   사람은 매번 찾아야 하고, 좁은 칸에서는 그 27px 이 문장에서 빼앗은 폭이라
   「멈춤 27분째 진전 없음…」이 잘렸다.

   id 줄은 **모든 카드에 이미 있는 줄**이다. 여기 세우면 새 높이가 한 번뿐이고
   (글리프 과녁 27px), 자리가 카드마다 고정되며, 점(무엇이 도나)과 손잡이(그것을
   세운다)가 한 벨트에 선다 — 뜻이 맞는 이웃이다. 덤으로 멈춤 줄이 폭을 되찾는다.

   벨트는 카드와 문서 화면이 **같은 것을 쓴다** — 조각을 둘로 나눠도 두 화면이
   각자 짓기 시작하면 한쪽만 고쳐진다(REQ-20260828-041 이 걷어 들인 그 갈래). */
/* 벨트에 서는 손잡이는 **하나뿐이고, 무엇이 설지는 상태가 정한다**
   (REQ-20260830-042 — 사용자: "이미 play, pause를 동시에 실행이 가능한 상태라는게
   모순적이다. 상태에 따라 버튼을 노출시키는게 어때?").

   맞는 지적이고, 모순은 조합이 아니라 **한 칸**에 있었다. 붙어 있는 카드
   (worker·session·agent)에는 ▶ 가 애초에 안 선다 — 서버가 붙은 것을 보면
   `stalled_mins` 를 안 싣기 때문이다. 반대로 멈춤·중단 카드는 정의상 idle 인데
   거기 ⏸ 가 「중단하기」라는 이름으로 섰다: **도는 것이 없는데 중단 단추가 있다.**

   뿌리는 한 글리프에 두 축을 실은 것이다. worker·session·agent 의 ⏸ 는 지금
   도는 것을 끊는 **행위**이고, idle 의 ⏸ 는 앞으로 안 맡게 잠그는 **정책**이었다.
   재생기의 ⏸ 에는 둘째 뜻이 없다 — ▶⏸ 는 "한 축의 두 방향, 하나만 참"이라는
   약속을 그림 자체로 한다. 그 약속을 지키려면 idle 에서 ⏸ 를 지우면 된다.

   **관문은 여기 한 곳이다.** 두 단추 함수에 각자 조건을 심으면 두 벌이 되고,
   이 파일이 세 번 덴 "한쪽만 고쳐진다"가 재발한다. 정책(idle 잠금)이 갈 곳은
   문서 화면의 낱말 단추다 — 아래 holdLockHTML. */
function deedBeltHTML(r, wordy){
  const kind = (r.stoppable || {}).kind;
  const attached = !!kind && kind !== "idle";
  // 붙어 있으면 끊는 쪽, 아니면 잇는 쪽. 그 함수의 held/stall 조건이 멈춤과
  // 중단을 다시 가르고, 어느 쪽도 아니면 빈 문자열이 온다.
  // wordy(문서 화면)는 얼굴만 갈린다 — 관문·조건은 이 한 곳 그대로다.
  const btn = attached ? stopBtnHTML(r, wordy) : wakeBtnHTML(r, wordy);
  if (!btn) return "";
  return `<span class="acts deedbelt">${btn}</span>`;
}
/* 신원 문장의 **낭독기 몫** — 눈으로는 없고 낭독기·검색에는 있다.

   벨트에 실어 두었더니 손잡이가 없는 카드(그냥 조용한 것)에서 문장까지 함께
   사라졌고, 손잡이가 있는 카드에서는 벨트 title 과 점 title 이 겹쳤다. 짓는
   자리는 holdTell 하나로 두고 **놓는 자리만** 화면이 고른다: 카드는 id 줄,
   문서는 사실 줄 뒤. 손 위의 글은 카드에서 식별자가 진다(cardHTML). */
function holdTellHTML(r){
  const t = holdTell(r);
  return t ? `<span class="vh">${esc(t)}</span>` : "";
}
/* 「자동 이어받기 끄기」 — **문서 화면에만** 서는 낱말 단추
   (REQ-20260830-042 · 이름은 REQ-20260901-005 로 개정, 근거는 STOP_HOLD_LABEL 곁에).

   idle 의 ⏸ 가 카드에서 사라지면서 갈 곳이 필요해진 기능 하나다. 이건 지금
   내리는 행위가 아니라 앞으로에 대한 **정책**이고, 보드 카드의 한 결정은 "이
   건을 지금 이어갈까"(=▶)다 — 판정 단추는 카드에 있어도 근거 전문은 문서가
   펴는, 그 층위 분리와 같다. 카드가 좁혀 쓰던 낱말도 여기선 풀어 쓴다.

   길은 **새로 파지 않는다**: 같은 `data-stop` + `data-kind="idle"` 이라 누르면
   기존 stopDoc 이 그대로 받고, 확인 창이 없는 갈래인 것도 그대로다.
   낱말이 갈린 이유는 뜻이 갈리기 때문이다 (ux-writer 판정) — 도는 것을 끊는
   쪽은 「중단하기」, 앞으로 못 맡게 하는 쪽은 「중단해 두기」. 한 낱말의 상만
   다르므로 사용자가 고른 낱말은 지켜지고 뜻은 갈린다. */
function holdLockHTML(r){
  if (!r || r.type !== "request" || r.status !== "in-progress") return "";
  if ((r.stoppable || {}).kind !== "idle") return "";
  /* 이미 사람이 중단해 둔 문서에는 서지 않는다 (REQ-20260830-046 designer ④).
     이 관문이 없던 동안 「▶ 이어가기」와 「자동 작업 중단해 두기」가 나란히
     섰다 — 042 가 카드에서 걷어낸 그 모순이 낱말로 갈아입고 문서에 옮겨 와
     있었다. 중단해 둔 상태에서 잠금은 이미 이뤄져 있으니 세울 것이 없다. */
  if (heldState(r)) return "";
  const going = stopPending(r.id);
  const tip = STOP_KIND.idle.tip;
  /* 줄(.lockrow)을 접었다 (REQ-20260830-046) — 이 단추는 이제 문서 머리의
     행동 띠(.dacts) 안에서 정책 잉크(.pol, 한 급 낮음)로 선다. 자기 줄로 서면
     행동들이 흩어지고, 그 흩어짐이 "안 보인다"의 나머지 절반이었다. */
  return `<button type="button" class="deed stop pol${going ? " busy" : ""}"`
    + ` data-stop="${esc(r.id)}" data-kind="idle"${going ? DEED_BUSY : ""}`
    + ` data-name="${STOP_HOLD_LABEL}" aria-describedby="pol-fore"`
    + ` data-tip="${esc(tip)}" title="${going ? STOP_GOING : esc(tip)}">`
    + `${going ? STOP_GOING : STOP_HOLD_LABEL}</button>`;
}
/* 예고 줄 — 단추가 서는 곳에 **함께** 서는 사실 한 줄 (REQ-20260901-005
   designer 1안). 개념(담당이 없으면 저절로 이어진다)을 가르칠
   자리는 단추 이름이 아니라 이 줄이다 — 이름이 세 번 실패한 바닥이 그 개념이
   화면 어디에도 안 서 있다는 것이었고, 이름은 그 위에서만 읽힌다.
   관문은 holdLockHTML 하나다: 여기서 조건을 다시 지으면 줄만 서고 단추가
   없는(또는 그 반대) 화면이 언젠가 생긴다. 캡션은 정책 이름 그대로 — 줄과
   단추가 한 물건임이 낱말로 보이고(translator 검수 ⑤), 단추의
   aria-describedby 가 이 줄의 id 를 가리켜 낭독기에도 같은 짝이 들린다. */
function holdForecastHTML(r){
  if (!holdLockHTML(r)) return "";
  return `<div class="rvpt fore" id="pol-fore">`
    + `<span class="rvcap">자동 이어받기</span>`
    + `담당이 없으면 이 요청은 저절로 이어집니다</div>`;
}
/* 진행 축의 **줄 하나** (REQ-20260830-040 규칙 2). 사다리는 구체성 순이다:

       중단 (사람이 세운 것)  >  멈춤 (진전이 끊긴 것)  >  오래 걸림  >  (없음)

   중단이 멈춤을 이기는 이유는 라운드4 반려가 세웠다: 중단하면 그 사유가 문서에
   적히고, 15분이 지나면 그 문서는 다시 '조용한' 것이 되어 멈춤 줄이 함께 서려
   한다 — 그러면 한 카드가 같은 요청을 두고 「멈춤」과 「중단」을 한꺼번에 말한다.
   사람이 자기 손으로 한 것이 더 구체적인 근거다(마커가 점을 이기는 그 규칙).

   **손잡이는 여기서 나오지 않는다** — ▶·⏸ 는 id 줄의 벨트(deedBeltHTML)가 진다.
   이 함수가 돌려주는 것은 글자 줄뿐이고, 예외는 낱말 손잡이 한 갈래다. */
function stallHTML(r){
  /* **진행 축의 맨 위는 「다른 컴퓨터」다** (REQ-20260902-021).

     아래 셋(중단 · 멈춤 · 오래 걸림)은 전부 **이 컴퓨터에 아무것도 없다**는
     사실을 재는데, 다른 컴퓨터가 리스를 쥐고 있으면 그 없음의 까닭이 이미
     밝혀져 있다. 그때 「멈춤 42분째 진전 없음」은 사실도 아니다 — 저쪽에서는
     지금 돌고 있다. 축마다 한 줄이므로(s9-design 「카드 사실 줄」) 이 줄이
     서면 아래 사다리는 서지 않는다. */
  const elsew = elsewhereRowHTML(r);
  if (elsew) return elsew;
  const stopped = stoppedRowHTML(r);
  if (stopped) return stopped;
  const st = stallState(r);
  if (!st) return slowRowHTML(r);
  // 마지막 시각을 못 읽으면 그 조각만 빠진다 — "· 마지막 " 로 끝나는 줄은 값이
  // 있는데 못 그린 것처럼 보인다.
  const last = fmtLast(r.updated || r.status_since);
  /* 꼬리 후보는 결정 무게순이고 **이긴 하나만** 선다 (factTail 주석 참조).
     「고친 것 있음」이 맨 앞인 것은 그것이 손잡이의 낱말을 바꾸는 근거라
     빠지면 버튼만 다른 이름으로 서는 근거 없는 손잡이가 되기 때문이고,
     「마지막 HH:MM」이 맨 뒤인 것은 바로 앞의 「N분째」와 같은 사실을 다른
     꼴로 되풀이하기 때문이다. */
  const row = `<div class="rvpt stall" title="이 문서가 마지막으로 바뀐 지 `
    + `${st.mins}분 됐습니다 — 그동안 이 문서에 아무것도 적히지 않았습니다`
    // 죽음이 기록돼 있으면 그 말을 함께 싣는다 — 점의 툴팁과 같은 문장이다.
    + (st.face === "dead" && st.reason ? ` (${esc(st.reason)})` : "") + `">`
    + `<span class="rvcap">멈춤</span>${fmtStall(st.mins)} 진전 없음`
    + factTail(r.commit_drift ? "고친 것 있음" : "", jobBit(r),
               last ? `마지막 ${esc(last)}` : "") + `</div>`;
  if (!r.commit_drift) return row;
  return `<div class="deedrow wordy">` + row + driftBtnHTML(r) + `</div>`;
}
/* 도는 작업자와 그 손잡이 — 깨우기의 반대편 (REQ-20260829-024).

   사용자: "반대로 진행 중인 작업들을 강제로 중단하는 기능도 만들어라. 그래야
   계정을 변경하거나 모델을 바꿀 때 그 기능을 같이 섞어서 사용할 수 있다."

   **조건은 서버가 준 `worker` 하나다.** 점(`live_kind`)으로 대신하지 않는다:
   그 값은 클레임 **전**(spawned)만 말하고, 작업자가 문서를 집는 순간 direct 로
   덮여 "지금 돌고 있다"는 사실이 행에서 사라진다 — 정작 세울 것이 있는 카드에
   손잡이가 안 서는 조합이다.

   줄을 함께 세우는 이유: 버튼만 있으면 무엇을 세우는지가 안 적힌다. 점은
   얹어야 읽히는 툴팁이고, 이 카드에서 세워지는 것은 **사람이 안 보는 곳에서
   도는 프로세스**라 카드 위에 글자로 한 번은 서야 한다.

   분은 서버가 준 초를 단위만 바꿔 옮긴다 — 화면이 스스로 시계를 대면 CLI 와
   다른 수를 말하게 된다 (REQ-20260828-036). */
function slowRowHTML(r){
  if (!r || r.type !== "request" || !r.worker) return "";
  const age = +r.worker.age || 0;
  // 임계 미만은 **정상**이다 — 정상은 줄이 아니라 점과 툴팁이 말한다.
  if (age < SLOW_WIN) return "";
  return `<div class="rvpt work" title="이 요청을 맡은 지 `
    + `${Math.floor(age / 60)}분 됐습니다 — 아직 도는 중이지만, 이만큼 걸리면`
    + ` 대개 막혀 있습니다. 중단하고 다시 맡기는 편이 빠를 수 있습니다">`
    // 캡션이 정상을 서술하면(「진행 중」) 그 줄은 신호가 아니다 — 캡션이 곧
    // 줄의 자격이므로, 자격을 준 사실(임계 초과)을 캡션이 그대로 말한다.
    //
    // **주체는 본문에서 내렸다** (DOC-20260831-005 규칙 4). 「오래 걸림 · 자동
    // 작업 18분째」였는데, ▶ 를 제 손으로 누른 사람에게 그 문장은 "내가
    // 눌렀는데 자동?"이었다 — 사용자 지적이 선 자리가 여기다. 이름을 바꾸는
    // 것으로 끝내지 않은 이유: 이 줄의 결정은 「중단하고 다시 맡길까」 하나인데
    // 주체를 알아도 그 결정이 안 바뀐다. 신원은 점과 툴팁의 몫이라고 이 화면이
    // 이미 정해 두었는데(REQ-20260830-040) 이 줄만 본문에 신원을 세우고 있었다.
    + `<span class="rvcap">오래 걸림</span>`
    + `${fmtStall(Math.floor(age / 60))}` + factTail(jobBit(r)) + `</div>`;
}
/* 사람이 세워 둔 요청과 그것을 되돌리는 손잡이 (REQ-20260829-024 라운드4).

   사용자: "멈춰놓고선, 다시 시작할 수 있는 기능이 없다."

   맞는 지적이었다. 세우면 그 사유가 문서에 적히고, 그 순간 이 요청은 '방금
   움직인 것'이 되어 멈춤 판정에서 빠진다 — 그래서 세운 직후 15분 동안 카드에
   **아무 손잡이도 없었다.** 세운 사람이 자기가 세운 것을 되돌릴 수 없는 화면은
   세우기가 절반만 있는 것과 같다.

   길은 깨우기와 **같은 길**이다(`wakeDoc` → `/api/wake`). 하는 일이 같은데
   길을 둘로 파면 한 벌만 고쳐진다 — 이 화면이 판정 버튼에서 세 번 배운 것이다.
   다른 것은 낱말뿐이라, 낱말만 손잡이가 들고 다닌다(`data-wlabel`). */
function stoppedRowHTML(r){
  if (!heldState(r)) return "";
  // 캡션이 이미 `중단` 을 말한다 — 본문은 언제였는지만 얹는다. 분은 서버가 준
  // 초를 단위만 바꿔 옮긴다. 손잡이(▶)는 id 줄의 벨트가 진다.
  const mins = fmtStall(Math.floor((+r.stopped.age || 0) / 60))
    .replace(/째$/, " 전");
  /* 꺼 둔 상태는 **본문 글자**로 선다 (REQ-20260901-005 designer ④) — 손 위의
     글(title)은 1초 지연에 터치 불가라, 상태를 title 에만 실으면 안 보인다.
     title 은 켜는 길(▶ 이어가기 = 지금 잇기 + 정책 켜기)을 마저 안내한다. */
  return `<div class="rvpt held" title="자동 이어받기를 사람이 꺼 두었습니다`
    + ` — 「▶ 이어가기」를 누르면 지금 이어가고 자동 이어받기도 함께 켜집니다">`
    + `<span class="rvcap">중단</span>${mins} · 자동 이어받기 꺼 둠`
    + factTail(jobBit(r)) + `</div>`;
}
/* ?stall=<분>[&stallkind=stalled|spawn_failed][&stalldep][&stallhold] — 멈춤 줄과
   `깨우기` 를 **진짜로 세운다** (REQ-20260828-041 반려).

   네 얼굴: 보통(분만) · 죽음이 기록된 것(stallkind=spawn_failed, 채운 사각) ·
   선행 대기와 동거(stalldep) · 누른 직후 잠김(stallhold, `깨우는 중…`).

   이 손잡이는 카탈로그 행에 `stalled_mins` 가 실릴 때만 그려지는데, 그 조건은
   저장소가 한동안 조용해야 성립한다 — 여러 세션이 몇 분마다 노트를 쓰는 이
   환경에서는 캡처를 찍으려는 바로 그 순간에 거의 없다. 그래서 이 단추는 두 번
   고쳐 올려지는 동안 **한 번도 눈으로 확인된 적이 없었다.** 진단 파라미터가
   예순 개 넘게 있는데 이 화면을 세우는 것만 없었다.

   그림을 따로 만들지 않는다 — 서버가 준 행에 **서버가 줬을 값**을 얹고, 그
   다음은 평소 그리던 길(cardHTML → stallHTML)이 그대로 그린다. 진단이 하는
   일은 값 하나를 넣는 것뿐이다. */
/* ?drift — 멈춤 줄에 「고친 것 있음」과 「끝났는지 확인」 손잡이를 세운다.
   ?hand=<분>[&handquiet=<분>] — 붙어 있으나 조용한 카드를 세운다. 줄은 이제
   서지 않고(REQ-20260830-040 규칙 1) 그 사실은 신원 문장(holdTell)으로 가지만,
   파라미터는 그대로 둔다 — 툴팁·숨김 글자에 그 조각이 실리는지 눈으로 볼 길이
   있어야 한다. 두 화면 다 실데이터에선 캡처 순간에 거의 없다. */
function driftProbe(rows){
  if (!/[?&]drift\b/.test(location.search) || !Array.isArray(rows)) return rows;
  for (const r of rows)
    if (r.type === "request" && r.status === "in-progress")
      r.commit_drift = true;
  return rows;
}
/* ?rvq — 판정 큐의 다섯 얼굴을 **진짜로** 세운다 (REQ-20260831-015).

   같은 이유다. 이 두 줄은 서버가 `review_prior`·`review_stale` 을 실어야
   그려지는데, 그러려면 연관된 요청 여럿이 하필 그 순간 함께 판정 대기이거나
   그중 하나가 돌고 있어야 한다. 실제로 이 요청을 만드는 사이에 살아 있던
   실사례(042 의 「바뀌는 중」)가 캡처를 찍기 전에 사라졌다 — 043 이 다른
   상태로 옮겨 갔기 때문이다. 진단이 없으면 이 줄도 "만들었다는데 본 적은
   없는" 것이 된다(깨우기가 두 번 그렇게 올라갔다).

   여기서도 그림을 따로 짓지 않는다: 서버가 줬을 값을 얹고 평소 그리던 길
   (cardHTML → judgeQueueHTML)이 그대로 그린다. 얼굴은 자리 순서로 돌린다 —
   선두(줄 없음) · 순서만 · 바뀌는 중만 · 둘 다(사다리와 꼬리) · 여러 건
   (「외 N건」). 다섯이 한 화면에 서야 사다리가 맞게 도는지 눈으로 본다. */
function rvqProbe(rows){
  if (!/[?&]rvq\b/.test(location.search) || !Array.isArray(rows)) return rows;
  const rv = rows.filter(r => r.type === "request" && r.status === "review");
  const ip = rows.filter(r => r.type === "request" && r.status === "in-progress");
  rv.forEach((r, n) => {
    const face = n % 5;
    if (face === 1 || face === 3) r.review_prior = rv.slice(0, 1).map(x => x.id);
    if (face === 4) r.review_prior = rv.slice(0, 3).map(x => x.id);
    if ((face === 2 || face === 3) && ip.length)
      r.review_stale = ip.slice(0, face === 3 ? 2 : 1).map(x => x.id);
  });
  return rows;
}
function handProbe(rows){
  const m = /[?&]hand=(\d+)/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const q = +((/[?&]handquiet=(\d+)/.exec(location.search) || [])[1] || 34);
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    // 서버 규칙 그대로: attached 는 stalled_mins 를 싣지 않는다.
    r.stall_state = "attached";
    r.hand_mins = Math.max(0, +m[1] + n);
    r.quiet_mins = q + 7 * n;
    r.stall_why = "다른 곳에서 이 요청을 만지는 중입니다 — 진단으로 세운 값";
    r.stalled_mins = null;
    n++;
  }
  return rows;
}
/* ?hold[=<갈래>] — 세우기의 네 갈래를 진짜로 세운다 (REQ-20260830-035).

   이 손잡이는 **서버가 `stoppable` 을 실어야** 그려지는데, 갈래 넷을 한 화면에
   모으려면 세션 하나·에이전트 하나·조용한 것 하나를 실제로 만들어야 한다. 진단이
   없으면 이 화면도 "만들었다는데 본 적은 없는" 것이 된다(깨우기가 두 번 그렇게
   올라갔다). 여기서도 그림을 따로 짓지 않는다 — 서버가 줬을 값을 얹고 평소
   그리던 길이 그대로 그린다. 갈래를 안 적으면 넷을 돌아가며 얹는다. */
function stopProbe(rows){
  const m = /[?&]hold(?:=(\w+))?\b/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const only = m[1], ring = ["worker", "session", "agent", "idle"];
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    const kind = only || ring[n % ring.length];
    // 서버의 우선순위를 그대로 흉내 낸다: worker 갈래는 도는 작업자가 근거다.
    if (kind === "worker" && !r.worker) r.worker = {pid: 515151 + n, age: 380 + 61 * n};
    if (kind !== "worker") delete r.worker;
    r.stoppable = kind === "idle" ? {kind: "idle", claimed: false}
      : kind === "worker" ? {kind: "worker"}
      : {kind: kind, session: "abcd1234", agent: kind === "agent" ? "a1" : undefined};
    n++;
  }
  return rows;
}
/* ?turn[=<조용한 분>] — 「일하는 중, 기록은 아직」의 긴 턴 갈래를 세운다
   (REQ-20260831-005).

   이 얼굴은 **한 세션이 도구만 부르며 20분을 보내는 동안**에만 실데이터에
   나타난다 — 캡처를 찍으려는 바로 그 순간에 그런 세션이 있으라는 요구는
   깨우기가 두 번 "본 적 없이" 올라간 그 요구와 같다. 붙어 있는 갈래(위임된
   작업자·손길)는 이미 `?hand=` 가 세우므로 여기서는 긴 턴만 만든다.

   그림을 따로 짓지 않는다: 서버가 줬을 값(live + quiet_mins, stalled_mins
   없음)을 행에 얹고 평소 그리던 길(cardHTML → busyState)이 그대로 그린다. */
function turnProbe(rows){
  const m = /[?&]turn(?:=(\d+))?\b/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const mins = Math.max(0, Math.min(9999, +(m[1] || 17)));
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    // 서버 규칙 그대로: 움직이는 것으로 판정한 행에는 멈춤을 안 싣는다.
    r.live = true;
    r.live_kind = "direct";
    r.live_age = 12 + n;
    r.stall_state = "moving";
    r.stall_why = "";
    r.quiet_mins = mins + 6 * n;
    r.stalled_mins = null;
    delete r.stopped;
    n++;
  }
  return rows;
}
function stallProbe(rows){
  // 한 카드의 두 손잡이는 부르는 자리를 하나로 둔다 — 진단이 늘어날 때마다
  // 파이프라인에 줄이 붙으면, 어느 진단이 어느 화면을 세우는지 흩어진다.
  workProbe(rows);
  heldProbe(rows);
  handProbe(rows);
  turnProbe(rows);
  stopProbe(rows);
  driftProbe(rows);
  rvqProbe(rows);
  spawnProbe(rows);
  leaseProbe(rows);
  linProbe(rows);
  const m = /[?&]stall=(\d+)/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const mins = Math.max(1, Math.min(9999, +m[1] || 20));
  const kind = (/[?&]stallkind=(\w+)/.exec(location.search) || [])[1] || "";
  const dep = /[?&]stalldep\b/.test(location.search);
  const hold = /[?&]stallhold\b/.test(location.search);
  const open = rows.filter(r => r.type === "request" && r.status === "open");
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    if (r.stalled_mins == null) r.stalled_mins = mins + 7 * n;
    if (kind && !r.live_kind){ r.live_kind = kind; r.live_reason = "진단으로 세운 값"; }
    // 선행 대기 줄과 **함께** 서는 카드 — 2차 반려가 뒤집은 그 자리다. 이 조합은
    // 실데이터에 거의 없어서(in-progress 인데 선행이 안 끝난 경우), 뒤집힌 규칙이
    // 맞게 그려지는지 눈으로 볼 길이 없었다.
    if (dep && open.length && !(r.blocked_by || []).length)
      r.blocked_by = [open[n % open.length].id];
    // 누른 직후의 잠긴 얼굴(`깨우는 중…`). 서버 왕복 중에만 보이는 화면이라
    // 손이 없으면 못 찍는다 — ?svchip= 이 낸 선례와 같은 자리다. 한 칸 걸러
    // 잠가 **잠긴 얼굴과 안 잠긴 얼굴이 한 화면에** 서게 한다.
    if (hold && n % 2 === 0) wokeAt.set(r.id, Date.now());
    n++;
  }
  return rows;
}
/* ?spawn[=<초>][&spawnwhy=wake|rework] — **막 뜬 백그라운드 작업의 점과 그 손 위
   글**을 진짜로 세운다 (REQ-20260831-025).

   이 얼굴이 서는 조건은 "스폰했는데 아직 문서를 못 집었다"라 실데이터에서는
   몇 초뿐이고, 그 몇 초에 캡처를 맞출 길이 없다. 그래서 이 갈래는 두 라운드
   동안 **눈으로 확인된 적이 없었고**, 앰버가 초록 ● 과 같은 화소라는 것도
   그동안 아무도 못 봤다(DOC-20260831-005 designer 실측). 같은 사고를 두 번
   겪지 않으려면 세우는 손잡이가 있어야 한다 — ?stall 이 낸 그 선례다.

   `spawnwhy` 를 안 주면 세 갈래(사람·반려·모름)가 한 화면에 번갈아 선다:
   문장이 실제로 갈리는지는 셋이 나란히 서야 보인다. */
function spawnProbe(rows){
  const m = /[?&]spawn(?:=(\d+))?\b/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const age = Math.max(0, Math.min(9999, +(m[1] || 8)));
  const why = (/[?&]spawnwhy=([\w-]+)/.exec(location.search) || [])[1] || "";
  const CYCLE = ["wake", "rework", ""];
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    // 점의 사다리에서 이 갈래까지 내려오려면 위의 문이 전부 닫혀 있어야 한다.
    r.live = false;
    r.live_kind = "spawned";
    r.live_age = age + n;
    r.spawn_reason = why || CYCLE[n % CYCLE.length];
    r.stall_state = "moving";
    r.stall_why = "";
    r.stalled_mins = null;
    delete r.stopped;
    delete r.worker;
    n++;
  }
  return rows;
}
/* ?work[=<분>][&workhold] — 도는 백그라운드 작업과 ⏸ 를 진짜로 세운다
   (REQ-20260829-024). 분이 임계(SLOW_WIN, 15분)를 넘으면 「오래 걸림」 줄까지
   서고, 그 아래면 줄 없이 점·툴팁만 남는다 — 두 얼굴을 `?work=20` 과 `?work=3`
   으로 나란히 볼 수 있어야 한다 (REQ-20260830-040 규칙 3).

   깨우기가 두 번 고쳐 올려지는 동안 한 번도 눈으로 확인된 적이 없던 이유가
   여기 그대로 있다: 이 손잡이는 **그 순간 백그라운드 작업이 돌고 있어야** 그려진다.
   사람이 캡처를 찍으려는 바로 그때 도는 작업자가 없으면 화면을 볼 길이 없고,
   그러면 또 "만들었다는데 본 적은 없는" 것이 된다.

   그림을 따로 짓지 않는다 — 서버가 줬을 값(`worker`)을 행에 얹고, 그다음은
   평소 그리던 길(cardHTML → stallHTML → slowRowHTML)이 그대로 그린다. */
/* ?lease=<분>[&leasepc=<이름>][&leasemine] — **다른 컴퓨터가 쥔 카드**를 진짜로
   세운다 (REQ-20260902-021).

   이 얼굴은 컴퓨터가 둘 있어야 성립한다 — 한 대에서는 캡처할 길이 아예 없다.
   `?stall` 이 낸 그 선례를 그대로 따른다: 그림을 따로 짓지 않고, **서버가 줬을
   값**(행의 `lease`)을 얹은 뒤 평소 그리던 길이 그대로 그리게 둔다. 만료
   (`?lease=40`)와 신선(`?lease=12`)을 나란히 볼 수 있어야 「30분이 지나면
   줄도 손잡이도 사라진다」가 눈으로 확인된다. `leasemine` 은 **제 컴퓨터의
   리스**를 얹는다 — 그때는 아무 줄도 서지 않아야 한다(제 자리를 남의 자리로
   그리지 않는다). */
function leaseProbe(rows){
  const m = /[?&]lease=(\d+)/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const mins = Math.max(0, Math.min(99999, +m[1] || 12));
  const mine = /[?&]leasemine\b/.test(location.search);
  const pc = (/[?&]leasepc=([\w.-]+)/.exec(location.search) || [])[1]
    || "MACBOOK-AIR";
  const here = (window.__whoami || {}).machine || "";
  const at = new Date(Date.now() - mins * 60000).toISOString();
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    r.lease = {user: r.user || "", machine: mine ? here : pc,
               session: "0f1e2d3c", since: at, renewed: at};
  }
  return rows;
}
/* ?lin=<human|agent|derived>[&lincreator=<이름>] — 「만든이」 조각과 문서 머리의
   혈통 줄을 세운다 (REQ-20260902-021). 옛 문서(origin 빈 값)가 아무것도 안
   그리는지는 이 진단을 **안 켠** 화면이 그대로 답한다. */
function linProbe(rows){
  const m = /[?&]lin=(\w+)/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const o = m[1];
  const cr = (/[?&]lincreator=([\w.-]+)/.exec(location.search) || [])[1] || "";
  const CYCLE = ["sub:designer", "lead:claude-opus-5", "worker:auto-resume"];
  let n = 0;
  for (const r of rows){
    if (r.type !== "request") continue;
    r.origin = o;
    r.origin_actor = o === "human" ? "" : CYCLE[n % CYCLE.length];
    if (o === "derived") r.origin_req = r.parent || r.id;
    if (cr) r.creator = cr;
    n++;
  }
  return rows;
}
/* ?jobrow[=<분>] — 카드의 긴 잡 조각을 세운다 (REQ-20260830-022). */
function jobRowProbe(rows){
  const m = /[?&]jobrow(?:=(\d+))?\b/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  for (const r of rows)
    if (r.type === "request" && r.status === "in-progress")
      r.jobs = [{name: "테스트", mins: +(m[1] || 4)}];
  return rows;
}
function workProbe(rows){
  jobRowProbe(rows);
  const m = /[?&]work(?:=(\d+))?\b/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const mins = Math.max(0, Math.min(9999, +(m[1] || 12)));
  const hold = /[?&]workhold\b/.test(location.search);
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    // 서버의 규칙을 그대로 흉내 낸다 (designer 지적): 도는 작업이 있으면
    // 서버는 멈춤을 싣지 않는다. 진단만 둘을 함께 세우면 **존재할 수 없는
    // 카드**를 지어내고, 다음 사람이 그 그림에 맞춰 화면을 고치게 된다.
    if (!r.worker) r.worker = {pid: 424242 + n, age: mins * 60 + 37 * n};
    r.stalled_mins = null;
    delete r.stopped;
    // 누른 직후의 잠긴 얼굴(`세우는 중…`)은 서버 왕복 중에만 보인다 — 한 칸
    // 걸러 잠가 두 얼굴이 한 화면에 서게 한다 (?stallhold 가 낸 선례).
    if (hold && n % 2 === 0) stopAt.set(r.id, Date.now());
    n++;
  }
  return rows;
}
/* ?held[=<분>][&heldhold] — 「중단」 줄과 「이어가기」를 진짜로 세운다
   (REQ-20260829-024 라운드4).

   이 줄은 **사람이 방금 중단한 요청이 있어야** 그려진다 — 캡처를 찍으려는 그
   순간에는 대개 없고, 만들려면 진짜 백그라운드 작업을 하나 죽여야 한다. 진단이
   없으면 이 화면은 또 "만들었다는데 본 적은 없는" 것이 된다(깨우기가 두 번
   그렇게 올라갔다). 여기서도 그림을 따로 짓지 않는다: 서버가 줬을 값을 얹고
   평소 그리던 길이 그대로 그린다. */
function heldProbe(rows){
  const m = /[?&]held(?:=(\d+))?\b/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const mins = Math.max(0, Math.min(9999, +(m[1] || 12)));
  const hold = /[?&]heldhold\b/.test(location.search);
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    if (!r.stopped)
      r.stopped = {at: Date.now() / 1000 - mins * 60, by: "nicehugepark",
                   age: mins * 60 + 41 * n};
    // 서버는 이 셋을 함께 싣지 않는다 — 진단도 그 규칙을 지킨다.
    delete r.worker;
    if (hold && n % 2 === 0) wokeAt.set(r.id, Date.now());
    n++;
  }
  return rows;
}
/* ---- 작업 자리 (REQ-20260829-030) ----------------------------------------

   백그라운드 작업은 worktree(격리된 사본)에 앉는 것이 기본이지만, 아직 commit 되지
   않은 코드가 있으면 그 사본이 **낡은 자리**가 되므로 본 저장소에 앉는다
   (REQ-20260829-028). 말없이 다르게 동작하면 다음 사람이 또 헤맨다 — 워크트리
   에서 고친 화면은 지금 도는 서버(9909)에 영영 안 나타나므로, 무엇을 어디서
   확인할지가 자리에 달려 있다.

   **화면은 판정하지 않는다.** 서버가 행에 실어 준 `workspace{kind,reason,wt,at}`
   를 옮길 뿐이다 — 멈춤 줄이 이미 세운 규칙이다(REQ-20260828-036: 화면이 스스로
   재기 시작하면 CLI 와 다른 말을 하게 된다). 여기에 판정을 한 줄이라도 적으면
   서버의 `workspace_decision` 과 두 벌이 되고, 그때부터 한 벌만 고쳐진다.

   **키는 없을 수 있다.** 그 문서에 새 코드로 스폰이 아직 없으면 서버가 키
   자체를 안 싣는다. 없으면 아무것도 그리지 않는다 — 빈 칸도, "미상"도 아니다.
   모르는 것에 자리를 주면 판이 매일 그 자리를 먹는다(같은 규칙을 취소 열에서
   한 번 더 쓴다 — REQ-20260829-031). */
/* 자리 이름이 아니라 **결과**를 쓴다 (REQ-20260830-001, tech-writer 판정 +
   translator 문안 + ux-writer 다듬음). 「본 저장소↔워크트리」는 대비로만 뜻이
   서는 한 쌍이라 여러 사람이 쓰는 화면에서 둘 다 배워야 하는 말이었다 —
   사용자: "둘의 차이를 잘 모르겠네." 축은 하나다: 언제 이 화면에 보이나. */
const WS_PLACE = {main: "바로 보임", worktree: "끝나면 보임"};
/* 자리에는 **표가 붙는다** (REQ-20260829-030 2차 반려: "어떤 화면에서 확인할 수
   있는지 모르겠다"). 1차는 낱말만 세웠는데, 메타 줄은 이미 이름·급·크기·태그가
   서는 자리라 낱말 하나는 지나가는 태그로 읽혔다 — 실제로 보드에 값이 붙은
   카드가 있었는데도 사람이 못 찾았다.

   지금 이 표가 서는 자리는 **문서의 메타 표 한 곳뿐**이다(4·5차 반려로 카드와
   헤더에서 차례로 내렸다). 그래도 표를 남기는 것은, 메타 표의 다른 칸들이
   전부 글자뿐이라 이 칸만 눌러서 펼 수 있다는 것을 표가 말해 주기 때문이다. */
const WS_MARK = "◇";
/* 사유 → [사람 말, 사람이 무엇을 하면 풀리는가].

   둘째 칸은 **비어 있어도 된다.** 풀 것이 없는 자리에 할 일을 지어내면 그
   문장은 매번 참이라 곧 안 읽히고, 진짜로 손이 필요한 자리까지 함께 묻힌다.
   실제로 손이 드는 것은 둘뿐이다 — 미커밋 코드(커밋)와 워크트리 쌓임(거두기). */
/* 말결은 창의 것이다 (REQ-20260830-007). 이 문장들이 서는 자리는 손 위의 글과
   창 하나뿐인데, 창의 다른 줄(WS_MEANS)은 존댓말이라 여기만 반말이면 한 창
   안에서 말이 두 결로 갈린다 — 사용자가 깨우기 창에서 지적한 그 어긋남이다. */
const WS_FIX_COMMIT = "commit 하면 다음 작업부터 다시 worktree 로 갑니다";
const WS_FIX_SWEEP = "다 쓴 worktree 를 거두면 다시 worktree 로 갑니다";
/* 자리가 **나에게 무슨 뜻인가** — 자리 이름·사유보다 이것이 먼저 궁금하다.
   사유는 왜 저기 앉았는지를 말할 뿐, 내가 지금 보고 있는 화면에서 그 작업을
   확인할 수 있는지는 말하지 않는다. 그게 이 요청이 애초에 세우려던 사실이다.
   자리 이름을 문장 안에 다시 적지 않는다 — 이름은 WS_PLACE 한 곳에서만 온다. */
const WS_MEANS = {main: "고친 내용은 이 화면에 바로 보입니다",
  worktree: "고친 내용은 작업이 끝난 뒤에 이 화면에 보입니다"};
/* 사유 중 **결과 말로 옮겨도 첫 줄(WS_MEANS)의 되풀이가 되는 것들은 내렸다**
   (REQ-20260830-001: off·create-failed·worktree-pile 은 시스템 낱말이 남고,
   fresh·fresh-outside·worktree-exists 는 옮기면 "그래서 나중에 보입니다"로
   수렴한다 — translator 판정 + ux-writer 동의). 운영자는 s9 doctor 로 본다. */
const WS_WHY = {
  "dirty-spine": ["모두가 쓰는 파일이 아직 commit 되지 않아, worktree 로 떼어 놓으면 "
                  + "그 코드가 빠진 낡은 사본에서 일하게 됩니다", WS_FIX_COMMIT],
  "dirty-overlap": ["이 요청이 고칠 파일이 아직 commit 되지 않았습니다", WS_FIX_COMMIT],
  "dirty-unknown": ["아직 commit 되지 않은 코드가 있고, 이 요청이 어느 파일을 "
                    + "고칠지는 문서에 적혀 있지 않습니다", WS_FIX_COMMIT],
  // 문장 안에 줄표를 넣지 않는다 — 손 위의 문장이 이미 줄표로 사유를 잇는다.
  "live-verify": ["살아 있는 서버로 확인해야 하는 작업이라서입니다", ""],
  "self-edit": ["작업 도구 자신을 고치는 일이라서입니다", ""],
};
/* 반환 null(그릴 것이 없다) 또는 {kind, wt, place, why, fix}.
   조건은 stallState 와 같은 자리에 둔다 — 카드와 문서 화면이 각자 관문을 가지면
   같은 요청이 두 자리에서 다른 말을 한다(REQ-20260828-041 2차가 그 병이었다). */
function wsState(r){
  if (!r || r.type !== "request" || r.status !== "in-progress") return null;
  const w = r.workspace;
  if (!w || !WS_PLACE[w.kind]) return null;   // 없는 것은 그리지 않는다
  const why = WS_WHY[w.reason] || ["", ""];
  return {kind: w.kind, place: WS_PLACE[w.kind],
          why: why[0], fix: why[1]};
}
// 손 위의 문장도 한 곳에서 짓는다 — 칩·창·헤더가 같은 말을 쓴다.
function wsTitle(s){
  // 자리 이름·워크트리 이름은 화면에서 내렸다 (REQ-20260830-001) — 뜻은
  // WS_MEANS 한 곳에서 온다. cd 할 사람의 값(w-xxxx)은 s9 worktree ls 의 몫.
  return `${WS_MEANS[s.kind] || ""}`
    + (s.why ? ` — ${s.why}` : "") + (s.fix ? `. ${s.fix}` : "");
}
/* 카드에는 서지 않는다 (REQ-20260829-030 4차 반려).

   사용자: "'◇ 본 저장소' 이 기능은 사용자에겐 굳이 노출할 필요가 없는 정보
   아닌가? … 시스템이 사용하는 변수아닌가? 문서에 포함은 되어도 상관은 없을 것
   같은데 카드에 보여주는건 혼란만 가중하는것같다."

   맞는 지적이고, 2·3차가 답을 **더 크게 만드는 쪽**으로 갔던 것이 잘못이었다.
   1차 반려("못 찾겠다")에 표를 붙였고, 2차("어디서 확인하나")에 창을 달았다 —
   못 찾는다는 말에 계속 키워서 답했는데, 정작 물음은 "이걸 왜 내가 보나"였다.
   보드는 **지금 무슨 일이 어디까지 왔나**를 훑는 판이고, 작업자가 어느 사본에
   앉았는지는 그 물음의 답이 아니다. 카드 아홉 장에 아홉 번 서면 그건 사실이
   아니라 배경이 된다.

   그래서 이 칩이 서는 자리는 이제 **하나뿐**이다 — 문서 화면의 메타 표.
   사용자가 "문서에 포함은 되어도 상관없다"고 한 자리이고, 제목 옆이 아니라
   표 안이다(제목 줄은 훑는 자리라 카드와 같은 문제가 된다).

   헤더 칩도 5차 반려로 내렸다(아래 wsBoardNote 자리의 주석에 경위가 있다).
   훑는 자리 둘에서 차례로 내려온 셈인데, 다섯 번의 반려가 가리킨 것은 하나다:
   **깃을 모르는 사람에게 이 사실은 읽을 것도 할 일도 아니다.**

   표 + 낱말, 그리고 **누를 수 있다** (REQ-20260829-030 2차 반려).

   1차는 손 위의 글(title)에만 설명을 뒀다. 손 위의 글은 찾은 사람에게만 열리는
   문이라, 못 찾았다는 반려에 답이 되지 못한다 — 이 화면은 이미 같은 값을 두 번
   치렀다(판정 창의 상태 이름을 귀띔에서 문장으로 내린 REQ-20260828-007 반려).
   그래서 표를 붙여 찾게 하고, 누르면 창이 열려 읽게 한다. 손 위의 글은 그대로
   둔다: 빠른 쪽은 여전히 얹기만 하면 된다.

   `<span>` 이다. 버튼 요소로 세우면 지우개 규칙(배경·테두리 없애기)이 붙는데,
   이 칩의 재질 계약은 "색면·테두리를 **주지 않는다**"라 지울 것도 없어야 맞다. */
function wsChip(r){
  const s = wsState(r);
  if (!s) return "";
  return `<span class="wsat${s.kind === "main" ? " here" : ""}" role="button"`
    + ` tabindex="0" data-wsat="${esc(r.id)}"`
    + ` title="${esc(wsTitle(s))} (눌러서 자세히)">`
    + `<i class="wsm">${WS_MARK}</i>${esc(s.place)}</span>`;
}
/* 칩을 누르면 그 요청 **하나**의 자리를 편다 (REQ-20260829-030 2차).

   이 창은 눈앞의 문서 한 건을 말한다 — 사람이 누른 것이 그 문서라, 답도 그
   문서여야 한다. 글은 새로 짓지 않는다: 자리·사유·푸는 법은 wsState 가 이미
   고른 것이고, 여기서 더하는 것은 "그래서 나에게 무슨 뜻인가"(WS_MEANS)
   한 줄뿐이다. (저장소 전체를 모아 말하던 헤더 칩은 5차 반려로 없앴다.)

   **뜻이 사유보다 먼저다** (3차 반려). 2차는 사유 → 뜻 → 푸는 법 순이었는데,
   사람이 이 칩을 누르며 품은 질문은 "왜 저기 앉았나"가 아니라 "그래서 이걸
   **어느 화면에서 확인하나**"다 — 반려문이 그대로 그 문장이었다. 창의 첫 줄이
   질문의 답이 아니면 사람은 답을 못 찾은 채로 창을 닫는다. 사유는 답을 받은
   뒤에 궁금해지는 것이라 둘째 줄로 내린다. */
function wsOpen(id){
  const s = wsState(catFind(id));
  if (!s) return;
  // 제목이 **답**을 진다 (REQ-20260902-005 designer 안): 어느 문서인지는
  // 창머리의 `doc:` 칸이 말하므로 제목 자리가 비고, 그 자리에 사람이 누르며
  // 품은 질문의 답(WS_MEANS)이 올라온다. 상태는 카드의 「진행 중」 줄이 말한다.
  s9dlg({kind: "alert", cap: "고친 내용", stop: false, doc: shortId(id),
    title: `${WS_MEANS[s.kind] || ""}`,
    descHtml: (s.why ? `<div class="wsrow">${esc(s.why)}.</div>` : "")
      + (s.fix ? `<div class="wsfix">${esc(s.fix)}.</div>` : ""),
    ok: "닫기"});
}
/* 헤더 칩(wsBoardNote)은 **없앴다** (REQ-20260829-030 5차 반려).

   사용자: "이 시스템이 워크트리도 만들고, 커밋도 해야하지. 하지만 사용자는
   깃을 전혀 모르는 상태에서도 요청이 잘 되느냐 마느냐, 질문이 답변을 받느냐
   마느냐 등만 관심분야다. 개발자나 엔지니어가 아닌 사용자가 이 시스템을
   사용한다고 가정하고 판단해라."

   그 칩이 하던 말은 「◇ 본 저장소에서 4건 · 커밋하면 다시 워크트리로 간다」
   였다. 깃을 모르는 사람에게 그것은 읽을 수 없는 문장이고, 읽어도 **자기가
   할 일이 아니다** — 커밋은 이 시스템이 알아서 하는 일이다. 헤더 칩은 사람
   손이 드는 사실만 서는 자리인데(REQ-20260827-018), 이 사실은 그 자격이 없다.

   1~4차가 답을 계속 **키우는 쪽**으로 갔던 것이 잘못이었다: 못 찾겠다 → 표를
   붙이고, 어디서 보나 → 창을 달고, 카드에 왜 있나 → 카드에서 내렸다. 물음은
   줄곧 "이걸 왜 내가 봐야 하나"였고, 옳은 답은 **안 보여 주는 것**이었다.

   사실이 사라지는 것은 아니다. `workspace` 는 문서의 메타 표에 남고(4차에서
   사용자가 "문서에 포함은 되어도 상관없다"고 했다), 운영하는 쪽은 `s9 doctor`·
   `s9 worktree ls` 로 본다 — 화면에서 내린 것은 **읽으라고 요구하는 자리**뿐이다.

   진행이 실제로 막히는 경우는 이것과 다르다. 그때는 카드가 「차례를 기다리는
   중」으로 말한다(REQ-20260829-036) — 깃을 몰라도 읽히는 문장이다. */
/* ?ws[=main/dirty-spine,worktree/fresh,…] — 자리 표시를 **진짜로 세운다**.

   서버가 이 값을 싣기 시작하는 것은 그 문서에 새 코드로 스폰이 한 번 일어난
   뒤부터라, 오늘 이 저장소에는 값을 가진 카드가 하나도 없다. 손잡이 하나가
   두 번 고쳐 올려지는 동안 한 번도 눈으로 확인된 적이 없던 일이 이미
   있었다(REQ-20260828-041) — 같은 일을 되풀이하지 않는다.

   그림을 따로 만들지 않는다: 서버가 줬을 값을 행에 얹고, 그다음은 평소 그리던
   길(cardHTML → wsChip · renderSvChip)이 그대로 그린다. 자리 판정은 여기서도
   하지 않는다 — 어느 사유가 어느 자리로 가는지는 서버가 아는 것이라, 진단은
   `kind/reason` 을 그대로 받아 적을 뿐 사유에서 자리를 유추하지 않는다. */
const WS_DEMO = ["main/dirty-spine", "worktree/fresh", "main/worktree-pile",
                 "main/self-edit", "worktree/fresh-outside", "main/dirty-overlap",
                 "main/live-verify", "main/dirty-unknown", "main/worktree-exists"];
function wsProbe(rows){
  const m = /[?&]ws(?:=([\w,/-]*))?(?:&|$)/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  const spec = (m[1] || "").split(",").filter(Boolean);
  const list = spec.length ? spec : WS_DEMO;
  let n = 0;
  for (const r of rows){
    if (r.type !== "request" || r.status !== "in-progress") continue;
    if (r.workspace) continue;               // 진짜 값이 있으면 덮지 않는다
    const [a, b] = list[n % list.length].split("/");
    const kind = b ? a : "main", reason = b || a;
    r.workspace = {kind, reason,
      wt: kind === "worktree" ? "w-" + String(r.id).slice(-12) : "",
      at: new Date().toISOString()};
    n++;
  }
  return rows;
}
/* ?cancelfresh[=N] — 취소 열이 **서는 날**을 세운다 (REQ-20260829-031).

   이 저장소의 취소 다섯 건은 전부 이틀이 넘었다. 그래서 "취소된 것이 있는
   날에는 반드시 보인다"는 쪽은 평소에 눈으로 볼 길이 없다 — 안 보이는 것만
   확인하고 마치면 감춘 것이 아니라 잃은 것일 수 있다. 새 문서를 지어내지 않고
   있는 취소 문서의 시각만 오늘로 당긴다. */
function cancelProbe(rows){
  const m = /[?&]cancelfresh(?:=(\d+))?/.exec(location.search);
  if (!m || !Array.isArray(rows)) return rows;
  let left = m[1] ? +m[1] : 2;
  for (const r of rows){
    if (left <= 0) break;
    if (r.type !== "request" || r.status !== "cancelled") continue;
    r.status_since = new Date(Date.now() - 3600 * 1000).toISOString();
    left--;
  }
  return rows;
}
/* 눌린 순간 화면이 먼저 답한다 — 서버 왕복(수백 ms)과 다음 폴링을 기다리면
   사람은 버튼이 죽은 줄 안다. 카드와 문서 화면에 같은 id 가 동시에 떠 있을 수
   있으므로 전부 고친다. */
function paintWake(id){
  const going = wokePending(id);
  // 중단해 둔 카드의 손잡이(`data-restart`)도 같은 붓이 칠한다 — 하는 일도
  // 낱말도 같고, 다른 것은 그 위에 선 줄뿐이다 (REQ-20260829-024 라운드4).
  const q = CSS.escape(id);
  document.querySelectorAll(`[data-wake="${q}"],[data-restart="${q}"]`)
    .forEach(b => faceDeed(b, going, WAKE_GOING));
}
/* 한 문서의 **벨트 손잡이**를 가리키는 자리 하나 (REQ-20260831-009). 벨트에는
   상태에 따라 ▶(`data-wake`)·⏸(`data-stop`)·↻(`data-restart`) 중 하나만 서므로
   (REQ-20260830-042 배타 노출), 셋을 한 셀렉터로 묻는 것이 곧 "그 카드의
   손잡이"를 묻는 것이다. */
function deedHandle(id){
  const q = CSS.escape(id);
  return document.querySelector(
    `[data-wake="${q}"],[data-stop="${q}"],[data-restart="${q}"]`);
}
/* **누른 손은 그 자리에 남는다** (REQ-20260831-009).

   답이 오면 카드를 다시 그리는데, 그리기는 손잡이 개체를 새것으로 갈아 끼운다
   — 키보드로 ▶ 에 닿아 Enter 를 친 손은 그 순간 자기가 서 있던 자리가 사라져
   보드 맨 앞으로 되돌아간다. `aria-disabled` 로 눌린 뒤의 포커스는 지켰지만
   (faceDeed), 재그리기는 그것만으로 건널 수 없다.

   규칙 셋. ① **내 자리였을 때만** 되돌린다 — 그 사이 사람이 다른 데로 갔으면
   빼앗지 않는다. ② 그 자리가 살아남았으면 아무 일도 하지 않는다. ③ **창이 서
   있으면 손은 창의 것이다** — 창을 열어 놓고 뒤의 카드로 포커스를 끌어오면
   사람이 읽던 자리가 사라진다(창이 닫힐 때 s9dlg 가 제 손으로 돌려보낸다). */
async function keepDeedFocus(id, fn){
  const held = document.activeElement;
  const q = CSS.escape(id);
  const mine = !!(held && held.closest && held.closest(
    `[data-wake="${q}"],[data-stop="${q}"],[data-restart="${q}"]`));
  await fn();
  if (!mine || held.isConnected) return;
  if (!(document.querySelector(".dlgbox") || {hidden: true}).hidden) return;
  const b = deedHandle(id);
  if (b) b.focus();
}
/* 멈춘 요청 하나를 사람이 눌러 다시 굴린다 (REQ-20260828-041).

   **화면은 이유를 짓지 않는다.** 서버가 준 `message` 를 그대로 옮긴다 —
   `action` 으로 문구를 갈라 쓰면 같은 말이 서버와 화면 두 벌이 되고, 그때부터
   한 벌만 고쳐진다. 화면이 읽는 것은 `ok` 와 `message` 둘뿐이다.

   `ok=false` 는 **오류가 아니라 설명**이다. `capped`(한도 소진)·`busy`(이미
   붙어 있음)·`moving`(아직 멈춘 게 아님)은 전부 정상적인 답이라, 붉은 실패로
   그리지 않는다(창머리 잉크를 .stop 으로 올리지 않는다). */
/* 눌림 기억의 **교차 청소** (REQ-20260830-042 designer — 배타가 새로 만드는
   유일한 결함).

   배타 노출이 서면 한 자리에서 얼굴이 바뀐다: ▶ 를 눌러 띄우면 몇 초 뒤 그
   자리에 ⏸ 가 선다. 그런데 두 기억(`wokeAt` 3분 · `stopAt` 20초)이 따로 살면,
   ▶ 를 누른 뒤 곧바로 ⏸ 로 중단했을 때 되돌아온 ▶ 가 **남은 3분 잠금** 때문에
   「이어가는 중…」으로 죽어 있다 — 방금 자기가 중단한 것을 다시 못 켠다.
   한쪽을 누르는 순간 반대편 기억은 뜻을 잃으므로 여기서 지운다. */
async function wakeDoc(id){
  if (wokePending(id)) return;              // 연타 — 이미 도는 중이다
  stopAt.delete(id);
  wokeAt.set(id, Date.now());
  paintWake(id);
  let d = null, reached = false;
  try{
    const r = await fetch("/api/wake", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id}))});  // actor는 서버 whoami 파생
    reached = true;
    d = await r.json();
  }catch(e){}
  if (!d || !d.message){
    wokeAt.delete(id); paintWake(id);
    // 서버가 답을 못 준 경우다 — 이유가 없으니 화면이 전송을 말한다(요청의
    // 사정을 지어내는 것과 다르다). 옛 서버에는 이 손잡이가 아직 없다.
    s9dlg({kind: "alert", cap: "연결", stop: true,
      title: reached ? "서버가 이어가기를 알지 못합니다"
                     : "서버에 닿지 못했습니다",
      desc: reached ? "s9 serve 를 다시 띄우면 이 버튼이 다시 생깁니다."
                    : "잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.",
      ok: "닫기"});
    return;
  }
  if (!d.ok){ wokeAt.delete(id); paintWake(id); }
  // 창은 wakeAnswer 가 세울지 말지 가른다. 창이 서면 손은 창의 것이라
  // keepDeedFocus 가 물러서고, 안 서면 재그리기를 건너 손잡이로 돌아온다.
  wakeAnswer(id, d);
  if (d.ok) await keepDeedFocus(id, () => refreshCatalog(true));
}
/* 답이 **창으로 설지를 가르는 자리**도 하나다 (REQ-20260830-049). 진단
   (`?dlg=wakewait`·`?dlg=wakespawn`·`?dlg=wakespawnws`)도 여기를 지난다 —
   창 짓는 함수만 부르고 이 판정을 건너뛰면, 진단으로 캡처해 고친 것이 사람이
   보는 화면이 아니게 된다(같은 병이 문안에서 한 번 났다, REQ-20260830-048).

   **성공에 덧붙일 예외 사실이 없으면 창은 서지 않는다.** 이어가기는 비파괴·
   자동·되돌림 가능(⏸)이라, 누른 손 아래에서 ▶ 가 ⏸ 로 서는 것이 이미 답이다
   — 그 위에 판을 하나 더 세우면 원인과 결과가 공간적으로 끊기고, 창이 자기가
   가리키는 그 카드를 가린다(designer 실측). 이 화면에서 창은 「물음 아니면
   거절」의 신호로 학습돼 있어, 아무 문제도 없는데 문제의 옷을 입고 나타난다.
   카드 사실 줄의 규율(REQ-20260830-040 「예외만 말한다」)을 창에 그대로 옮긴 것.

   **갈래는 화면이 다시 판정하지 않는다.** 워크스페이스가 무엇인지 여기서 캐면
   그리기와 답이 두 벌이 되므로, 읽는 것은 서버가 할 말을 가졌는가(`note`)
   하나다 — 말은 여전히 서버 한 곳에서 온다(bin/s9 `_wake_note`). */
function wakeAnswer(id, d){
  if (d.ok && !d.note) return null;
  return wakeDlg(id, d);
}
/* 깨우기의 답을 창으로 옮기는 자리는 **하나다** (REQ-20260829-030). 창을 따로
   지으면 보고 고친 것이 사람이 보는 창이 아니게 된다.

   **화면이 읽는 것은 `ok`·`message`·`note` 셋뿐이다.** 서버에 `action` 값이
   하나 늘어도(028 이 더한 `waiting`) 여기는 그대로다 — 값마다 문구를 갈라 쓰기
   시작하면 같은 말이 서버와 화면 두 벌이 되고, 그때부터 한 벌만 고쳐진다.
   `message`(한 절, 결과 그 자체)와 `note`(예외 사실 한 줄)는 급이 다른 말이라
   슬롯도 둘이다 — 한 창의 강조는 하나이므로, 화면이 한 문자열을 마침표로
   쪼개는 것은 금지다(문장 안 쉼표에서 깨진다, REQ-20260830-049).

   `ok=false` 는 **오류가 아니라 설명이다**. `waiting`(누가 무엇을 잡고 있어
   차례를 기다린다)·`busy`·`capped`·`moving` 이 전부 정상적인 답이라 창머리
   잉크를 붉히지 않는다(stop:false). 대기는 고장이 아니라 차례다. */
function wakeDlg(id, d){
  /* 눈썹은 **사람이 누른 그 낱말**이다 (REQ-20260830-007). `깨움` 은 동사를
     명사로 굳힌 시스템의 말이라, 사용자가 방금 누른 낱말과 같은 것인지 한 박자
     맞춰 봐야 한다 — 누른 낱말이 그대로 돌아와야 답으로 읽힌다. */
  return s9dlg({kind: "alert", cap: d.ok ? WAKE_LABEL : "이어가지 않음",
    stop: false,
    doc: shortId(id), title: d.message, desc: d.note || "", ok: "닫기"});
}
/* 눌린 순간 화면이 먼저 답한다 — 깨우기와 같은 규칙이다. */
function paintStop(id){
  const going = stopPending(id);
  document.querySelectorAll(`[data-stop="${CSS.escape(id)}"]`)
    .forEach(b => faceDeed(b, going, STOP_GOING));
}
/* 도는 작업자를 사람이 눌러 세운다 (REQ-20260829-024).

   **먼저 묻는다.** 깨우기는 아무 일도 안 하던 것을 굴리는 일이라 되돌릴 것이
   없지만, 세우기는 지금 일하고 있는 프로세스를 끝낸다 — 되돌릴 수 없는 쪽에는
   한 걸음을 더 둔다(계정 창이 "멈추고 바꾸기"를 묻는 그 자리와 같은 규칙).
   무엇을 잃는지도 함께 적는다: 하던 일은 문서에 적힌 데까지만 남는다.

   답은 서버의 `message` 를 그대로 옮긴다 — `action` 으로 문구를 갈라 쓰면 같은
   말이 서버와 화면 두 벌이 되고, 그때부터 한 벌만 고쳐진다(깨우기가 세운
   규칙). 화면이 읽는 것은 `ok` 와 `message` 둘뿐이다. */
/* 누를 때의 갈래는 **그릴 때 서버가 준 그 값**을 그대로 읽는다 (`data-kind`).
   화면이 카탈로그를 다시 뒤져 재판정하면 그리기와 누름이 두 벌이 되고, 그
   사이에 갈래가 바뀌면 사람이 본 창과 서버가 하는 일이 어긋난다. 못 찾으면
   창을 세우는 쪽(worker)으로 기운다 — 물어보는 실수가 안 물어보는 실수보다 싸다. */
function stopKindOf(id){
  const b = document.querySelector(`[data-stop="${CSS.escape(id)}"]`);
  return (b && b.dataset.kind) || "worker";
}
async function stopDoc(id){
  if (stopPending(id)) return;              // 연타 — 이미 세우는 중이다
  /* 맨 Enter 는 「그대로 두기」에 닿는다 (`safe` — REQ-20260830-008). 세우기는
     되돌릴 수 있는 일이지만("이어가기"), **되살릴 수 있다와 실수로 눌러도
     괜찮다는 다른 말이다**: 그 사이에 도는 작업이 하던 일을 잃는다. 창을 읽지
     않고 Enter 를 치는 손이 있고, 그 손이 배우는 규칙은 창마다 같아야 한다. */
  /* 창은 **한 자리에서만** 선다 (REQ-20260829-030 의 규칙). 갈래가 넷이라고
     창을 넷 지으면, 보고 고친 창이 사람이 보는 창이 아니게 된다 — 갈래는
     문안 표(STOP_KIND)에서 오고 세우는 자리는 여기 하나다.
     `ask` 가 없는 갈래(idle)는 창 없이 곧장 간다: 붙어 있는 손이 없어 잃는
     것이 없고, 「이어가기」 한 번으로 되돌아간다. */
  const stopAsk = (STOP_KIND[stopKindOf(id)] || {}).ask;
  const go = !stopAsk || await s9dlg({kind: "confirm", cap: STOP_LABEL, stop: false,
    safe: true, doc: shortId(id),
    // 어느 요청인지는 창머리의 주소가 말한다 — 제목은 물음 하나만 한다.
    title: stopAsk.title, desc: stopAsk.desc,
    ok: stopAsk.ok, cancel: "그대로 두기"});
  if (!go) return;
  wokeAt.delete(id);                        // 교차 청소 — wakeDoc 주석 참조
  stopAt.set(id, Date.now());
  paintStop(id);
  let d = null, reached = false;
  try{
    const r = await fetch("/api/stop", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id}))});  // actor는 서버 whoami 파생
    reached = true;
    d = await r.json();
  }catch(e){}
  stopAt.delete(id); paintStop(id);
  if (!d || !d.message){
    // 옛 서버에는 이 손잡이가 아직 없다 — 깨우기가 세운 그 문장과 같은 자리다.
    s9dlg({kind: "alert", cap: "연결", stop: true,
      title: reached ? "서버가 중단하기를 알지 못합니다"
                     : "서버에 닿지 못했습니다",
      desc: reached ? "s9 serve 를 다시 띄우면 이 버튼이 다시 생깁니다."
                    : "잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.",
      ok: "닫기"});
    return;
  }
  // 눈썹은 사람이 누른 그 낱말이다 — 깨우기 창이 세운 규칙과 같은 자리다.
  s9dlg({kind: "alert", cap: d.ok ? STOP_LABEL : "중단하지 않음", stop: false,
    doc: shortId(id), title: d.message, ok: "닫기"});
  if (d.ok) refreshCatalog(true);
}

/* 카드가 내주는 긴 글 한 덩어리 — 세 줄 + (잘렸으면) 그 자리에서 펴는 손잡이
   (REQ-20260829-009, 그 반려).

   확인 요청과 대기 사유는 같은 종류의 글이다: 사람이 손대기 전에 읽어야 하는
   문단이고, 둘 다 카드 폭에서는 다 못 읽는다. 한 함수로 지어야 한쪽만 고쳐져
   blocked 카드가 문장 벽으로 남는 일이 없다.

   본문을 캡션과 분리해 span 으로 싼다 — 클램프를 블록에 걸면 캡션이 세 줄 중
   한 줄을 먹는다. 손잡이는 클램프 박스 **밖**에 형제로 둔다: 안에 넣으면
   자기가 잘린다.

   손잡이는 **이 화면의 펼침 문법을 그대로 쓴다**(`data-expand` → `expanded`
   → `render()`). 그래서 15초 폴링이 보드를 다시 그려도 열어 둔 것이 접히지
   않고, 새 클릭 핸들러도 필요 없다 — 열 머리의 `+ N개 더 보기` 와 같은 길이다.
   `data-expand` 는 카드(문서 열기)보다 먼저 잡히므로 눌러도 Docs 로 새지 않는다.

   문구는 ux-writer 몫이라 이 두 상수에만 있다. */
const RVMORE_LABEL = "더 보기";
const RVLESS_LABEL = "접기";
/* 집어 둔 카드가 스스로를 부르는 이름 (REQ-20260829-011). 문구는 ux-writer
   몫이지만 폭 예산이 붙는다: id 줄에 남는 자리가 ~45px 이라 두어 자를 넘기면
   경과시각과 다시 자리를 다툰다. */
const PICKED_MARK = "대상";
function rvClamped(cap, text, key, open){
  return `<div class="rvpt clampy${open ? " open" : ""}">`
    + `<span class="rvcap">${esc(cap)}</span>`
    // 펼친 상자는 스크롤한다 — 키보드로도 닿아야 그 스크롤이 쓸모가 있다.
    + `<span class="rvtx"${open ? ` tabindex="0" role="group" aria-label="${esc(cap)} 전문"` : ""}>`
    + `${esc(text)}</span></div>`
    + `<button type="button" class="rvmore" data-expand="rv:${esc(key)}"`
    + ` aria-expanded="${open ? "true" : "false"}">`
    + `${open ? RVLESS_LABEL : RVMORE_LABEL}</button>`;
}

/* 막 뜬 백그라운드 작업의 손 위 글 — **까닭이 갈리면 문장도 갈린다**
   (DOC-20260831-005 규칙 2·6, designer 실측).

   사실은 서버에 이미 갈려 있었다: `reason == "wake"`(사람이 카드에서 ▶ 를
   누른 것)는 워처와 **별도 예산**을 쓴다. 그런데 스폰 마커(`state/auto_resume/
   <REQ>.json`)가 `{last,count,pid}` 뿐이라 그 사실을 버렸고, 화면은 둘을 한
   문장으로 부를 수밖에 없었다 — 제 손으로 누른 사람이 "자동 작업이 시작됐다"를
   읽은 자리가 그것이다. 마커에 칸 하나를 늘려 그 사실을 여기까지 나른다.

   「저절로」는 **워처 갈래에만** 선다: 사람이 누른 것에 저절로라 하면 거짓이고,
   워처가 띄운 것에 까닭을 안 적으면 "내가 안 시킨 일이 돈다"가 된다. 그래서
   워처 문장만 사건(반려)+까닭(저절로)을 함께 진다.
   모르는 갈래(옛 마커·CLI 재개)는 중립 문장이다 — 짐작해서 주어를 세우면
   틀릴 수 있고, 이 화면은 그 자리에서 이미 한 번 덴 적이 있다. */
const SPAWN_TAIL = " — 이 요청을 이어받기까지 잠시 걸립니다";
function spawnTell(r){
  const age = r.live_age;
  switch (r.spawn_reason) {
    case "wake":
      return `「${WAKE_LABEL}」를 눌러 ${age}초 전에 시작했습니다${SPAWN_TAIL}`;
    case "rework":
      return `반려되어 저절로 다시 시작됐습니다 (${age}초 전)${SPAWN_TAIL}`;
    default:
      return `${age}초 전에 다시 시작됐습니다${SPAWN_TAIL}`;
  }
}

function cardHTML(r){
  const isReq = r.type === "request";
  // "무엇을 기다리는가" 한 줄 (REQ-20260826-009). blocked 전용이 아니다 —
  // open/in-progress 카드도 안 끝난 선행을 가질 수 있고, 사용자가 알고 싶었던
  // 것이 바로 그 경우다. 카드에선 선행 1건 제목 + 외 N건까지만; 전부와 이동
  // 경로는 문서 뷰가 맡는다.
  const bl = isReq ? liveBlockers(r) : [];
  /* 멈춤은 **서버가 재고 화면은 읽는다** (REQ-20260828-036). 여기서 다시 재면
     CLI(`s9 stalled`)와 화면이 다른 말을 하게 된다 — 이번 사고가 정확히 그것이다.
     그래서 이 화면 어디에도 "몇 분 지났나"를 판정하는 자리는 없고, 판정은
     stallState 한 곳만 지난다 (REQ-20260828-041 2차: 카드가 자기 몫의 조건을
     따로 가지면 문서 화면과 갈라진다 — 실제로 갈라져 있었다). */
  const st = stallState(r);
  /* **일하는 중인데 아직 남긴 기록이 없다** (REQ-20260831-005).

     사용자: "지금 열심히 동작중인데 카드에는 멈춤으로 나온다. 워커 입장에서는
     많이 억울할 상황이네."

     이 화면이 아는 얼굴은 둘뿐이었다: 기록이 나가는 중(초록 채운 점)이거나,
     진전이 없는 것(정지 사각). 그 사이에 실제로 가장 흔한 얼굴이 빠져 있다 —
     **붙어서 돌고는 있는데 아직 문서에 안 적힌 것.** 리드가 한 턴 안에서 20분
     동안 도구만 부르는 동안이 그렇고, 위임된 작업자가 붙어 일하는 동안이
     그렇다. 그 얼굴이 없으니 화면은 있는 얼굴 중 가까운 것으로 떨어졌고, 그게
     「멈춤」이었다. 마크 하나가 없어서 일하는 손을 멎었다고 그린 것이다.

     **판정은 여기서 짓지 않는다** — 서버가 실어 준 한 벌(stall_verdict)을 읽어
     얼굴만 고른다. 화면이 자기 시계를 대기 시작하면 CLI(`s9 stalled`)와 다른
     말을 하게 된다 (REQ-20260828-036). 두 문이다:

       ① `stall_state === "attached"` — 서버가 "무언가 이 요청에 붙어 있다"고
          판정한 자리 전부다(위임된 작업자 · 지명 등록된 손 · 도는 긴 잡 ·
          다른 곳에서 온 손길 · 긴 턴을 도는 세션). 이 자리들은 정의상
          `stalled_mins` 를 안 싣는데 점의 사다리에 갈 곳이 없어 **`.off`(모름)**
          으로 떨어지고 있었다 — 붙어 있는 줄 알면서 모른다고 그리던 자리다.
       ② 서버는 "움직인다"(live)고 하는데 문서만 오래 조용한 것. 잣대는 새로
          짓지 않고 「오래 걸림」이 이미 쓰는 SLOW_WIN 을 그대로 쓴다(서버
          STALLED_WIN 과 같은 수, tests/test_stall_pair.py 가 대조). 그 미만은
          정상이라 ● 그대로다.

     **문장은 하나다.** 서버가 판정과 함께 사람이 읽는 한 문장(`stall_why`)을
     실어 주고 CLI 도 그것을 쓴다 — 화면이 자기 문장을 지어 덧붙이면 같은 사실이
     툴팁 안에서 두 번 말해진다(서버 문장이 이미 「문서에는 N분째 새 기록이
     없습니다」로 끝난다). 있으면 그대로 쓰고, 없을 때만 화면이 채운다.

     **술어를 따로 세우지 않은 이유**: 이 판정을 먹는 자리는 점 하나뿐이다.
     이 파일이 술어를 함수로 올리는 것은 부르는 자리가 둘 이상일 때다
     (stallState 는 점·줄·손잡이·열 머리 수·정렬 다섯이 먹는다) — 그래야
     갈라질 자리가 없어진다. 자리가 하나인 판정을 함수로 올리면 갈라짐은 안
     막으면서 이름만 늘어난다. 둘째 자리(문서 화면 따위)가 생기는 날 함수로
     올리고, 그때 tests/test_stall_pair.py 의 render() 조각 목록에 그 이름을
     함께 얹어라 — 그 목록이 화면 조각을 이어 붙이는 자리다. */
  const bzq = r.quiet_mins == null ? null : +r.quiet_mins;
  const bz = (isReq && r.status === "in-progress" && !st && !r.stopped
              && (r.stall_state === "attached"
                  || (r.live && bzq != null && bzq >= SLOW_WIN / 60)))
    ? {quiet: bzq,
       tell: r.stall_why || ("지금 이 요청을 맡아 일하고 있습니다"
         + (bzq == null ? "" : ` — 문서에는 ${bzq}분째 새 기록이 없습니다`))}
    : null;
  // 펼쳐 둔 확인 요청/대기 사유는 다시 그려도 살아남는다 (REQ-20260829-009 반려) —
  // 이 화면이 이미 쓰는 기억(expanded)에 얹는다. 15초 폴링이 접지 않는다.
  const rvOpen = expanded.has("rv:" + r.id);
  const dep = bl.length
    ? `<div class="rvpt dep" title="${esc(bl.map(b => shortId(b.id) + " " + b.title).join(" · "))}">`
      + `<span class="rvcap">선행 대기</span>${esc(bl[0].title || shortId(bl[0].id))}`
      + (bl.length > 1 ? `<span class="depmore"> 외 ${bl.length - 1}건</span>` : "") + `</div>`
    : "";
  // 판정 카드: 배경 → 판단 요구 → 행동 (DOC-20260826-015). 요약 한 줄이 없으면
  // 제목만으로 무슨 건인지 떠오르지 않은 채 결론부터 읽게 된다 — 그래서 확인
  // 포인트 "위에" 요약을 놓는다. 이 블록(판정 카드)에만 붙인다.
  /* 판정 큐 줄은 **관계 축의 사다리 아래**다 (REQ-20260831-015). 선행 대기가
     서 있으면 이 줄은 안 선다: blocked_by 는 진짜 막힘이고 이쪽은 경고-only 라,
     둘을 나란히 세우면 카드가 한 축에 두 줄을 쓰면서 무게 순서까지 흐린다
     (s9-design 「카드 사실 줄」: 축마다 한 줄). */
  const queue = bl.length ? "" : judgeQueueHTML(r);
  const acts = isReq && r.status === "review"
    ? `<div class="judge">${queue}${r.summary ? `<div class="rvpt what"><span class="rvcap">무엇을</span><span class="wtx">${esc(r.summary)}</span></div>` : ""}${r.review_point ? rvClamped("확인 요청", r.review_point, r.id, rvOpen) : ""}<div class="acts"><button class="deed" data-approve="${esc(r.id)}" title="승인하면 done 상태가 됩니다">${rvLabel("done")}</button><button class="deed" data-reject="${esc(r.id)}" title="반려하면 in-progress 상태로 돌아갑니다">${rvLabel("in-progress")}</button></div></div>`
    // 선행이 잡히면 구조화된 대기 줄이 이긴다 — 같은 사실을 두 줄로 말하지 않는다.
    // 관계가 없는 과거 문서만 note 본문의 대기 사유로 폴백 (DOC-20260826-001 규칙 7).
    : isReq && r.status === "blocked" && r.block_reason && !bl.length
    ? rvClamped("대기 사유", r.block_reason, r.id, rvOpen)
    : "";
  /* 멈춤 한 줄. **선행 대기가 있어도 손잡이를 뺏지 않는다** (REQ-20260828-041
     2차 반려로 뒤집음).

     전에는 선행 대기 줄이 이겼다 — 근거는 "같은 사실을 두 줄로 말하지 않는다"
     (DOC-20260826-001 규칙 7)였고, 문장에 대해서는 지금도 옳다. 그러나 그 관문이
     지운 것은 문장 하나가 아니라 **행동 하나**였다. 게다가 이 관문은 카드에만
     있었다: 같은 요청이 카드에선 못 깨우고 문서에선 깨워졌다 — 판정 단추가 세 번
     반려된 그 결함(REQ-20260828-007)과 같은 모양이다.

     사실로 봐도 둘은 다른 축이다. 선행 대기는 **관계**(무엇이 안 끝났나),
     멈춤은 **시계**(여기 아무도 안 적고 있다)다. 선행이 안 끝났는데 아무도 안
     붙어 있는 요청이야말로 사람이 깨워야 하는 것이다. 두 줄은 각각 한 줄이라
     문장 벽도 아니다. */
  /* 글자와 손잡이는 **조각 둘, 그리고 각각 한 곳**이다 (REQ-20260828-041 ·
     REQ-20260830-040). 문서 화면이 같은 두 함수를 부르므로 갈라질 자리가 없다:
     `stallHTML` 이 진행 축의 글자 줄 하나를, `deedBeltHTML` 이 손잡이 벨트를
     짓는다. 안 멈춘·안 도는 행에는 둘 다 빈 문자열이 온다.
     벨트가 카드에서 서는 자리는 사실 줄이 아니라 **id 줄**이다 — 그 줄은 모든
     카드에 이미 있어서, 손잡이가 카드마다 다른 데 서던 것이 여기서 멎는다. */
  const stall = stallHTML(r);
  const belt = deedBeltHTML(r);
  /* 신원 한 문장이 두 채널로 나간다. 낭독기·검색에는 시각적 숨김 글자(`vh`),
     손에는 식별자의 손 위 글(`tell`). **벨트에 걸지 않는 이유**는 둘이다:
     ① 벨트의 상자는 글리프와 2px 틈이 전부라 손이 닿는 곳은 늘 버튼이고, 그
     버튼에는 자기 툴팁(무엇을 세우는가)이 이미 있다. ② 손잡이가 없는 카드
     (그냥 조용한 것)에서 벨트가 통째로 사라지는데, 하필 그 카드가 가장 말이
     없어 신원이 가장 필요한 카드다. id 는 모든 카드에 있다. */
  const tell = holdTell(r), vh = holdTellHTML(r);
  /* 점의 사다리. **멈춤이 초록보다 먼저 걸린다** (REQ-20260828-036).
     전에는 r.live 가 맨 위에 있어서, 문서가 한 시간째 안 움직인 요청도 그것을
     잡아 둔 세션이 살아 있기만 하면 초록으로 뛰었다 — 점이 재던 것은 "이
     요청의 진전"이 아니라 "이 요청을 잡고 있는 세션의 맥박"이었다. 그 상태로
     아래에 "멈춤" 줄만 붙이면 같은 카드가 점으로는 돈다고, 글자로는 멈췄다고
     말한다. 둘이 어긋나면 사람은 **둘 다** 안 믿는다.
     멎은 작업(dot-stopped)은 더 구체적인 근거를 가지므로 위에 그대로 둔다. */
  /* **정지 마크는 서버의 멈춤 판정이 받쳐 줄 때만 선다** (REQ-20260828-041 반려).

     사용자가 겪은 화면: 카드에 정지 마크가 붙어 "멈췄다"고 말하는데 깨울
     손잡이가 없다. 두 신호가 다른 시계를 봤기 때문이다 — 마크는 색인에 굳은
     작업자 판정(어제 22:36 의 기록이 오늘도 켜져 있었다)에서 오고, 손잡이는
     서버가 지금 다시 잰 `stalled_mins` 에서 온다.

     화면은 **분을 다시 재지 않는다**(REQ-20260828-036). 대신 순서를 세운다:
     작업자가 죽었다는 기록이 있어도 그 뒤로 **문서가 움직였으면**(서버가
     stalled_mins 를 안 준다) 그 기록은 낡은 것이니 마크를 세우지 않고 아래
     사다리로 내려간다. 이렇게 하면 "멈췄다고 그려 놓고 할 일은 안 주는 카드"가
     구조적으로 생길 수 없다 — 마크가 서는 조건이 손잡이가 서는 조건의
     부분집합이다.

     2차 반려에서 **부분집합을 같은 집합으로** 좁혔다. 종전에는 손잡이가 선
     카드 중 작업자 기록이 없는 것들이 `.livedot.off`(속 빈 회색 링)로 그려졌다 —
     그 마크는 "in-progress 인데 스트림이 조용하다"는 **모름**의 자리에도 쓰인다.
     그래서 점만 훑는 눈에는 "45분째 멈춰 깨울 수 있는 것"과 "그냥 조용한 것"이
     같은 마크였고, 열 머리의 `멈춤 N` 과도 세는 대상이 어긋나 보였다. 이제
     stallState 가 연 문을 지난 행은 전부 사각(정지)으로 그린다: 죽음이 기록된
     것은 채운 사각, 아니면 속 빈 사각. */
  /* 다른 컴퓨터가 쥔 요청의 점은 **모름(○)** 이다 (REQ-20260902-021).

     새 얼굴을 만들지 않는다 — 일곱 얼굴은 두 축(모양 = 무엇이 붙어 있나 ·
     채움 = 문서에 기록이 나가나)의 조합이고, 이 자리에서 참인 것은 정확히
     「이 컴퓨터는 모른다」다: 저쪽 pid·경로는 여기서 뜻이 없고 벽시계만 읽힌다.
     그래서 마크는 사다리 끝의 ○ 그대로 두고 **문장만** 참으로 바꾼다. 아래
     사각(멈춤·죽음)으로 떨어지면 안 된다 — 저쪽에서는 돌고 있는데 여기서
     멎었다고 그리는 것이라, 점과 줄이 서로 다른 말을 하기 시작한다. */
  const elsewDot = leaseElsewhere(r);
  const liveDot = r.status === "in-progress"
    ? (elsewDot
         ? `<span class="livedot off" title="${esc(elsewDot.machine)} 에서 ${
              elsewDot.mins < 1 ? "방금" : elsewDot.mins + "분 전"}까지 움직였습니다 — 이 컴퓨터에서는 진행을 볼 수 없습니다"></span>`
       : st && st.face === "dead"
         ? `<span class="livedot dot-stopped" title="이 요청을 맡았던 일이 도중에 멎었습니다 — ${esc(st.reason||"까닭은 남아 있지 않습니다")}"></span>`
       : st
         ? `<span class="livedot dot-stopped mild" title="지금 이 요청을 담당하는 것이 없습니다 — 문서도 ${st.mins}분째 그대로입니다${esc(st.reason ? " — " + st.reason : "")}${r.live ? " — 이 요청을 만든 창은 아직 움직이고 있습니다" : ""}"></span>`
       /* 사람이 중단해 둔 것은 **모름이 아니다** (REQ-20260829-024 라운드4).
          이 갈래가 없으면 사다리 끝의 `.off`(속 빈 회색 원 = "in-progress 인데
          스트림이 조용함, 모름")로 떨어져, 카드가 왜 조용한지 알면서도 모른다고
          그린다 — 점이 서는 조건과 손잡이가 서는 조건을 다시 어긋내는 자리다
          (REQ-20260828-041 2차 반려가 지운 그 조합). 마크는 이미 있는 것을
          쓴다: 멈춤과 같은 속 빈 사각이되, 까닭은 툴팁이 갈라 말한다. */
       : r.stopped
         /* 「누군가」를 걷었다 (DOC-20260831-005 사전) — 이 화면에서 중단하는
            것은 사람뿐이라 모호할 이유가 없다. 모르는 주어는 "내가 안 한 일이
            일어났다"로 읽힌다. */
         ? `<span class="livedot dot-held" title="이 요청을 사람이 ${r.stopped && r.stopped.age >= 60 ? Math.floor(r.stopped.age / 60) + "분 전에 " : "방금 "}중단해 두었습니다 — 지금은 아무것도 돌고 있지 않습니다"></span>`
       /* **일하는 중, 기록은 아직** — ◎ (REQ-20260831-005). 초록 점멸보다
          먼저 걸린다: 이 갈래에 해당하는 카드는 대부분 `r.live` 도 참이라,
          아래에 두면 영영 안 그려지고 ● 가 "기록도 나가는 중"이라는 거짓을
          계속 말한다. 멈춤·중단보다는 뒤다 — 멎은 것이 도는 것을 이긴다. */
       : bz
         ? `<span class="livedot busy" title="${esc(bz.tell)}"></span>`
       : r.live
         ? `<span class="livedot on" title="지금 이 요청을 맡아 일하고 있습니다 — ${r.live_age}초 전에 움직였습니다"></span>`
       : r.live_kind === "session"
         ? `<span class="livedot sess" title="이 요청을 만든 창이 ${r.live_age}초 전까지 움직였습니다 — 다만 이 요청을 맡고 있지는 않습니다"></span>`
       : r.live_kind === "spawned"
         ? `<span class="livedot spawn" title="${esc(spawnTell(r))}"></span>`
         : `<span class="livedot off" title="${esc(r.stall_why || "진행 중으로 되어 있는데 도는 기색이 없습니다 — 지금 이 요청을 담당하는 것이 없을 수 있습니다")}"></span>`)
    : "";
  return `<div class="card" ${isReq ? 'draggable="true"' : ""} tabindex="0" role="button" style="--sc:${SCOLOR[r.status]||"var(--muted)"}" data-doc="${esc(r.id)}" data-status="${esc(r.status)}">
    <button type="button" class="pickdoc" data-pick="${esc(r.id)}"
      aria-label="${esc(shortId(r.id))} 에 이어 말하기">이어 말하기</button>
    <div class="id">${liveDot}<span class="idn"${tell ? ` title="${esc(tell)}"` : ""}>${esc(shortId(r.id))}</span>${vh}<span class="pkst" title="이어 말할 대상으로 골라 둔 카드입니다 — 「이어 말하기」를 다시 누르면 놓습니다">${PICKED_MARK}</span>${belt}</div>
    <div class="t">${esc(r.title)}</div>
    <div class="m">
      ${ownerBadgeHTML(r)}${lineageChip(r)}
      ${prioHTML(r)}
      ${r.size ? `<span class="size">${esc(r.size)}</span>` : ""}
      ${r.tdd ? `<span class="tdd${r.tdd.passed===r.tdd.total?" full":""}" title="TDD 시나리오 ${r.tdd.passed}/${r.tdd.total} 통과">TDD ${r.tdd.passed}/${r.tdd.total}</span>` : ""}
      ${(r.tags||[]).filter(t=>!SYS_TAGS.has(t)).slice(0,2).map(t=>`<span class="tag" style="--th:${tagHue(t)}">#${esc(t)}</span>`).join("")}
    </div>${acts}${dep}${stall}
    ${r.status_since ? `<span class="elapsed" data-since="${esc(r.status_since)}" title="현재 상태(${esc(r.status)}) 시작 이후 경과">${fmtElapsed(r.status_since)}</span>` : ""}</div>`;
}

// 반려: 사유 필수. Board·문서 뷰어 공용 (REQ-20260827-071 로 제품 대화상자 사용).
// 빈 값에 두 번째 창을 띄우던 흐름은 없앴다 — 그건 벌주는 흐름이고, 한 창 안에서
// 확인이 안 눌리는 것으로 족하다.
/* 판정 창의 머리(주소)와 제목을 **한 곳에서** 짓는다 (REQ-20260828-007).
   반려·승인·전이·취소가 각자 문장을 지어 쓰면 언젠가 하나만 제목을 잃는다 —
   실제로 넷 다 id 만 적고 있었다.

   제목은 카탈로그에서 찾아 낫표로 감싼다(집기 줄이 이미 쓰는 어휘 — 제목이
   동사로 끝나면 뒤에 붙는 조사와 엉켜 한 문장으로 읽히기 때문이다). 아주 긴
   제목은 60자에서 자른다: 뒤따르는 동사("반려합니다")가 잘려 나가면 무엇을
   하려는 창인지가 사라진다. 이 저장소의 제목 규약은 20자 이내라 실제로 잘릴
   일은 드물고, 60자면 창 폭(432px)에서 세 줄이다. */
/* 조사는 **계산한다** (REQ-20260828-007 4차). `을(를)` 은 이 화면에 남은 유일한
   서식 편지투다 — 제목은 동적이지만 받침 유무는 마지막 글자 하나로 정해진다.
   한글로 끝나지 않으면(문서 id 폴백·로마자 제목) 지금처럼 물러선다: 읽는 법이
   글자에 없는 것을 화면이 지어내는 것보다, 두 개를 다 적어 주는 편이 정직하다. */
function josa(word, withT, withoutT){
  const last = String(word || "").trim().slice(-1);
  const c = last ? last.charCodeAt(0) : 0;
  if (c < 0xAC00 || c > 0xD7A3) return `${withT}(${withoutT})`;
  return (c - 0xAC00) % 28 ? withT : withoutT;
}
function dlgFor(id, tail){
  const r = catFind(id);
  let t = String((r && r.title) || "").trim();
  const full = t;
  if (t.length > 60) t = t.slice(0, 60) + "…";
  const name = t ? `「${t}」` : shortId(id);
  // 조사가 무는 것은 낫표가 아니라 그 안의 마지막 글자다. 잘린 제목에서는
  // 말줄임표 앞의 글자로 정한다 — 사람이 읽는 소리를 따른다.
  return {doc: shortId(id),
          titleHtml: `${esc(name)}${josa(full, "을", "를")} ${tail}`};
}
/* 상태 이름을 문장 속에 세운다 (REQ-20260828-007 반려).

   사용자: "다른 상태에서는 open, in-progress, done인데 리뷰 단계에서만 …
   한글로 승인/반려 라고 표시된다. 용어를 통일할 필요가 있다."

   통일은 **번역**이 아니다. `done` 은 화면에만 있는 낱말이 아니라 문서 앞머리와
   CLI 출력과 커밋 메시지에 같은 글자로 박혀 있는 **이름**이고, 이름은 번역하지
   않는다 — 화면만 한글로 바꾸면 화면에서 본 말과 문서에서 읽는 말이 달라져
   "이게 그거인가"를 매번 이어 붙여야 한다. 대신 **이름은 이름처럼, 행위는
   행위처럼** 보이게 한다: 상태는 mono 식별자로, 승인·반려는 문장 속 동사로.

   그리고 조사를 피한다 — "done 으로"·"in-progress 로" 는 이름마다 갈리고 어느
   쪽으로 통일해도 절반은 틀린다. "…상태로" 를 끼우면 어느 이름에도 문장이 선다. */
const stName = to => `<span class="dlgst">${esc(to)}</span>`;
/* 판정 버튼의 글자는 **한 곳에서** 짓는다 (REQ-20260828-007 4차).

   보드 판정 카드와 문서 화면이 각자 글자를 갖고 있어서, 3차까지 한쪽만
   고쳐지는 일이 되풀이됐다. 두 화면이 같은 함수를 부르면 갈라질 수 없다.

   글리프(✓/↺)는 뺐다 — 실측: `✓ 승인 done` 은 보드 카드 폭(215px)에서 두
   줄로 감긴다. 글리프는 두 버튼을 가르려고 있던 것인데 이제 done/in-progress
   가 그보다 강하게 가른다. 축약(`in-prog`)은 쓰지 않는다 — 어디에도 없는
   글자를 만드는 순간 "화면과 문서와 CLI 가 같은 이름" 이라는 전제가 무너진다.

   키는 TRANSITIONS["review"] 의 부분집합이어야 한다 (계약: test_judge_dialog). */
const RVDEED = {done: "승인", "in-progress": "반려"};
/* 옮기기 버튼과 판정 버튼은 **같은 틀**이다 (REQ-20260828-007 5차):
   앞 칸이 행위, 뒤 칸이 도착지의 이름. 행위 칸에 기호가 서면 그냥 이동이고
   낱말이 서면 판정이다. 두 종류가 각자 함수를 가지면 5차에서 그랬듯 이름의
   생김새가 갈린다 — 한 함수가 짓게 두면 갈릴 자리가 없다. */
const actLabel = (to, judging) =>
  `${judging && RVDEED[to] ? RVDEED[to] : "→"}<span class="stn">${esc(to)}</span>`;
const rvLabel = to => RVDEED[to] ? actLabel(to, true) : "";
/* 판정은 **한 곳에서** 한다 (REQ-20260828-007 3차 반려).

   사용자: "보드 화면에서 승인을 할 때는 '승인하기'이고 문서에서 승인을 할 때에는
   '상태옮기기' 라고 나온다. 판정 이 단계만 보거나, 국소적으로 판단하지말고,
   전체적인 디자인, 흐름, 맥락을 다 챙기도록 해."

   원인은 문구가 아니라 **길이 둘이었다는 것**이다. 보드 카드는 `data-approve` 로
   승인 창을 열고, 문서 화면의 같은 `✓ 승인` 버튼은 `data-trans` 로 일반 상태
   옮기기 창을 열었다. 반려만 두 길이 한 함수를 쓰고 있었고 승인은 갈라져 있었다.

   이 저장소가 반복해 배운 것과 같다: **판정이 두 벌이면 한 벌만 고쳐진다.**

   행동의 이름은 **어디서 왔는가**로 정해진다. review 에서 나가는 것만 판정이다 —
   `in-progress → done` 은 일을 끝낸 것이지 승인이 아니다. */
async function judgeAct(id, to, from){
  const judging = from === "review";
  if (judging && to === "done"){
    const memo = await s9dlg({kind:"prompt", cap:"판정", attach: true,
      ...dlgFor(id, `승인해 ${stName("done")} 상태로 넘깁니다`),
      desc:"메모는 History 에 남습니다. 비워 두어도 승인됩니다. " + DLG_ATTACH_HINT,
      ok:"승인하기", cancel:"그만두기"});
    if (memo === null) return;                 // 취소
    // 화면은 사람이 쓴 **원문만** 보낸다 (REQ-20260828-007 4차). 앞서는 여기서
    // 접두어를 이어 붙였다 — 의미를 문자열에 실어 보내면 서버가 그 한글 두
    // 글자를 파싱하게 되고,
    // 화면 낱말 하나를 고치는 순간 승인 메모 인계가 소리 없이 죽는다.
    // 접두어는 (from,to) 를 아는 do_transition 이 짓는다.
    postStatus(id, "done", memo.text, memo.atts);
    return;
  }
  if (judging && to === "in-progress"){
    const why = await s9dlg({kind:"prompt", cap:"판정", attach: true,
      ...dlgFor(id, `반려해 ${stName("in-progress")} 상태로 돌려보냅니다`),
      desc:"사유는 History 에 그대로 남습니다. 무엇이 부족한지 한 줄이면 됩니다. "
         + DLG_ATTACH_HINT,
      required:true, ok:"반려하기", cancel:"그만두기"});
    if (why === null) return;                  // 취소
    postStatus(id, "in-progress", why.text, why.atts);   // 접두어는 서버가 짓는다
    return;
  }
  // 판정이 아닌 이동 — 사람이 상태를 직접 옮기는 자리다.
  /* 창 머리도 어디서 왔는가로 정해진다 (REQ-20260828-007 4차). 넷 다 `판정`
     이라 `in-progress → done` 창이 스스로를 판정이라 부르면서 버튼은 `상태
     옮기기` 라고 말하고 있었다. review 에서 나가는 것만 판정이다. */
  if (to === "cancelled" && !await s9dlg({kind:"confirm", cap:"상태 옮기기",
        ...dlgFor(id, `${stName("cancelled")} 상태로 옮깁니다`),
        desc:"취소한 요청은 보드에서 내려갑니다. 되돌리려면 다시 옮기면 됩니다.",
        ok:"취소하기", cancel:"그만두기"})) return;
  const note = await s9dlg({kind:"prompt", cap:"상태 옮기기", attach: true,
    ...dlgFor(id, `${stName(to)} 상태로 옮깁니다`),
    desc:"메모는 History 에 남습니다. 비워 두어도 됩니다. " + DLG_ATTACH_HINT,
    ok:"상태 옮기기", cancel:"그만두기"});
  if (note === null) return;
  postStatus(id, to, note.text, note.atts);
}
const rejectWithReason = id => judgeAct(id, "in-progress", "review");

async function postStatus(id, to, note, atts){
  /* **붙이기와 전이가 한 번에 간다** (REQ-20260829-015 반려 재작업).

     1차에서는 화면이 두 번 두드렸다 — `/api/note` 로 사유+파일을 붙이고
     `/api/status` 로 옮겼다. 그래서 순서("파일이 먼저")와 실패 처리("못 붙이면
     옮기지 않는다")를 화면이 손으로 엮어야 했고, 앞이 되고 뒤가 안 되면
     근거만 남고 상태는 안 옮겨진 어중간한 자리가 생겼다. 그 둘을 서버가
     한 몸으로 가져갔다(`/api/status` 가 `atts` 를 받는다) — 이제 화면은
     **한 번 보내고 결과만 읽는다.**

     표기(`[Image:]`·`[File:]`)도 더 이상 화면이 짓지 않는다. 그림이냐 아니냐는
     파일의 성질이지 화면의 취향이 아니고, 화면 둘이 각자 확장자 표를 들면
     영상에 `[Image:]` 가 붙어 문서에 깨진 칸이 남는다(서버 `asset_mark`).

     라벨은 `response` 다. 앞서는 `/api/note` 가 `ask` 로 박아 두어 **반려 근거가
     문서에 질문으로 적혔다** — 나중에 읽는 사람이 답해야 할 질문과 판정의
     근거를 구별할 수 없었다. */
  try{
    const r = await fetch("/api/status", {method: "POST",
      headers: {"Content-Type": "application/json"},
      // actor 는 서버 whoami 파생 — 화면이 실어 보내지 않는다
      body: JSON.stringify(withAs({id, to, note, atts: atts || [],
                                   label: "response"}))});
    const d = await r.json();
    if (!d.ok){
      /* `거부` 는 사람이 판정에서 거절했다는 말로 읽힌다 — 실제로는 서버가
         받지 못한 것이다 (REQ-20260828-007 4차).

         파일을 함께 보냈다면 **모르는 것을 아는 척 말하지 않는다.** 붙이기가
         먼저이므로 갈래가 둘이다: 파일에서 막혔으면 아무것도 안 남았고, 전이에서
         막혔으면(흔한 쪽이다 — "review 에서 done 으로는 갈 수 없다") 파일은
         이미 문서에 있다. 어느 쪽이든 사람이 할 일은 같으니 그 하나를 말한다. */
      s9dlg({kind:"alert", cap:"실패", title:"상태를 바꾸지 못했습니다",
        desc: String(d.error || "")
          + (atts && atts.length
             ? " 붙인 파일이 문서에 남았는지는 문서를 열어 확인해 주세요." : ""),
        ok:"닫기"});
      return;
    }
    refreshCatalog(true);
  }catch(e){
    s9dlg({kind:"alert", cap:"연결", title:"서버에 닿지 못했습니다",
      desc:"잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.", ok:"닫기"});
  }
}

/* 열려 있는 판이 그 문서면 다시 그린다 — 부르는 자리가 둘(담당 바꾸기·가져오기)
   이라 한 곳에 둔다. 다른 문서를 보고 있으면 아무 일도 하지 않는다. */
function reloadShowing(id){
  const v = document.getElementById("viewer");
  if (v && v.dataset.showing === id) loadDoc(id, true, true);
}
/* ---- 담당 후보는 그 프로젝트의 사람이다 (REQ-20260902-064) ----------------

   프로젝트에 참여하지 않은 사람까지 목록에 서던 것을 고친다. 판정은 한 줄이다 —
   **담당 후보 = 그 프로젝트의 활성 멤버 중 관찰 계정이 아닌 사람.** 서버의
   `do_assign` 이 같은 판정으로 거절하고, 화면은 그 거절이 뻔한 선택지를 손에
   쥐여 주지 않을 뿐이다 (이 파일이 관찰 계정에 대해 이미 하던 그 일 — 판정을
   새로 짓는 것이 아니라 서버가 이미 보낸 사실을 읽는다).

   프로젝트가 **없는** 문서는 금지가 아니라 정책 부재다: 서버의 `project_can` 이
   「미등록 프로젝트 = 정책 부재 → 강제 안 함」으로 세운 그 선을 그대로 따라
   등록 사용자 전부가 후보다. 여기서 거꾸로 잠그면 프로젝트에 안 매인 요청은
   아무도 못 맡는 문서가 된다.

   시스템 admin 도 멤버가 아니면 후보가 아니다. admin 우회는 **바꾸는 사람**의
   축(누가 담당을 옮길 수 있나)이지 **맡는 사람**의 축이 아니다 — 둘을 섞으면
   "프로젝트에 없는 사람이 목록에 뜬다"가 관리자 얼굴로 그대로 돌아온다.

   만료 판정도 화면이 다시 재지 않는다: `/api/projects` 가 멤버마다 실어 보내는
   `active`(서버의 `member_active`)를 읽기만 한다. 날짜를 두 벌로 재면 어느 날
   화면만 만료를 다르게 센다. */
function assignPick(row){
  const cur = String((row && row.user) || "");
  const pool = (window.__users || [])
    .filter(u => u.role !== "viewer");    // 관찰 계정은 담당을 맡지 않는다
  const slug = String((row && row.project) || "").trim();
  const pr = slug ? (window.__projects || []).find(
    p => p.slug === slug || p.id === slug) : null;
  let users = pool, desc = "";
  let empty = "담당을 맡을 수 있는 계정이 없습니다 — Settings 에서 계정을 더하면 여기에 뜹니다.";
  if (slug){
    const name = pr ? (pr.title || slug) : slug;
    /* 목록이 짧은 까닭을 창이 스스로 말한다 — 없는 이름을 찾다가 고장으로
       읽는 자리다. 자리는 설명 줄(.dlgs)이지 라벨(.dlgsub)이 아니다:
       라벨은 대문자로 눕는 자리라 프로젝트 이름을 일그러뜨린다(Section9 →
       SECTION9). 이름을 담는 글자는 본문체로 선다. */
    desc = `「${name}」 멤버만 담당을 맡습니다.`;
    if (pr){
      const mem = new Set((pr.members || [])
        .filter(m => m.active).map(m => m.user));
      users = pool.filter(u => mem.has(u.name));
      empty = `「${name}」에 멤버가 없습니다 — Projects 탭에서 멤버를 더하면 여기에 뜹니다.`;
    }else{
      /* 목록을 못 받은 것과 멤버가 없는 것은 다른 화면이다 — 못 받은 자리에
         「멤버가 없습니다」를 적으면 사람은 없는 사실을 고치러 간다. */
      users = [];
      empty = "프로젝트 목록을 받지 못했습니다 — 헤더의 다시 받기를 눌러 보세요.";
    }
  }
  const items = users.map(u => ({key: u.name, label: u.name, cur: u.name === cur,
                                 tag: u.display || "",
                                 note: u.name === cur ? "지금 이것" : ""}));
  /* 지금 맡은 사람은 멤버가 아니어도 목록에 남는다 (옛 문서·멤버에서 빠진 뒤).
     창이 「지금 이것」을 두고 거짓말하면 누가 쥐고 있는지 알 길이 없다 —
     골라 봐야 값이 안 바뀌므로 확인은 잠긴 채다(s9choose 의 idle). */
  if (cur && !items.some(it => it.cur)){
    const u = (window.__users || []).find(x => x.name === cur) || {};
    items.unshift({key: cur, label: cur, cur: true,
                   tag: u.display || "", note: "지금 이것"});
  }
  return {items, empty, desc};
}
/* ---- 담당을 바꾼다 (REQ-20260902-021) ------------------------------------

   **판정도 문구도 서버 한 곳이다.** 화면은 고를 수 없는 것만 목록에서 뺀다
   (관찰 계정·프로젝트 밖 — 서버가 어차피 거절하는 선택지를 손에 쥐여 주지
   않는다: 위 `assignPick`). 권한은
   화면이 재지 않는다: 손잡이는 누구에게나 서고, 못 하는 사람에게는 서버가 왜
   못 하는지 한 문장으로 말한다. 여기서 권한 표를 한 벌 더 들면 서버와 갈리는
   날 화면만 조용히 틀린 말을 하게 된다.

   **되돌릴 수 있다.** 담당은 다시 바꾸면 되므로 확인 창을 겹쳐 세우지 않는다 —
   한 창 안에서 고르고, 까닭 한 줄을 적어야 확인이 눌린다(빈 값은 벌주지 않고
   버튼이 안 눌릴 뿐이다). 까닭은 문서 History 에 그대로 남는다. */
async function assignDoc(id){
  const r = catFind(id) || {};
  const cur = String(r.user || "");
  const {items, empty, desc} = assignPick(r);
  const picked = await s9choose({cap: "담당",
    ...dlgFor(id, "맡을 사람을 바꿉니다"),
    sub: "누가 맡습니까", desc, items, empty,
    reason: {label: "바꾸는 까닭", required: true,
             placeholder: "한 줄이면 됩니다 — 문서 History 에 그대로 남습니다"},
    pickNote: "맡을 사람",
    confirm: {ok: "담당 바꾸기",
              idle: "지금 맡은 사람 그대로입니다.",
              say: it => `${it.key} 에게 넘깁니다. 이 컴퓨터가 쥐고 있던 진행도 함께 놓습니다.`},
    cancel: "그만두기"});
  if (!picked || !picked.key || picked.key === cur) return;
  try{
    const res = await fetch("/api/assign", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id, user: picked.key, why: picked.why || ""}))});
    const d = await res.json();
    // 서버의 거부 문장을 **그대로** 옮긴다 — 문구를 두 벌로 만들지 않는다.
    if (!d.ok){
      s9dlg({kind: "alert", cap: "담당", doc: shortId(id),
        title: "담당을 바꾸지 못했습니다", desc: String(d.error || ""), ok: "닫기"});
      return;
    }
    refreshCatalog(true);
    // 열려 있는 그 문서면 판도 함께 갱신한다 — 목록만 고치면 문서 머리의
    // 「맡은 사람」이 옛 이름을 그대로 들고 있다 (boot.js·app.js 가 쓰는 그 길).
    reloadShowing(id);
  }catch(e){
    s9dlg({kind: "alert", cap: "연결", title: "서버에 닿지 못했습니다",
      desc: "잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.", ok: "닫기"});
  }
}
/* ---- 진행을 이 컴퓨터로 (REQ-20260902-021 · D1 이관 경로 (b)) --------------

   **성공에는 창을 세우지 않는다** (REQ-20260830-049 가 세운 규칙): 줄이 사라지고
   카드가 이 컴퓨터의 것이 되는 것이 곧 답이다. 그 위에 판을 하나 더 세우면
   창이 자기가 가리키는 카드를 가린다. 거절될 때만 서버의 사유를 그대로 옮긴다. */
async function takeoverDoc(id){
  try{
    const res = await fetch("/api/claim_takeover", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(withAs({id}))});
    const d = await res.json();
    if (!d.ok){
      s9dlg({kind: "alert", cap: "가져오지 않음", stop: false, doc: shortId(id),
        title: "이 컴퓨터로 가져오지 못했습니다",
        desc: String(d.error || ""), ok: "닫기"});
      return;
    }
    refreshCatalog(true);
    // 열려 있는 그 문서면 판도 함께 갱신한다 — 목록만 고치면 문서 머리의
    // 「맡은 사람」이 옛 이름을 그대로 들고 있다 (boot.js·app.js 가 쓰는 그 길).
    reloadShowing(id);
  }catch(e){
    s9dlg({kind: "alert", cap: "연결", title: "서버에 닿지 못했습니다",
      desc: "잠시 뒤 다시 시도해 주세요. 서버가 재기동 중일 수 있습니다.", ok: "닫기"});
  }
}

// 빈 상태는 안내가 아니라 다음 행동을 주는 자리다 (s9-design 완성도 기준 3)
// 다섯 컬럼이 똑같이 "비어 있음"이면 어느 칸이 빈 것인지 눈이 다시 위를 훑어야
// 한다. 각 칸이 비었다는 사실의 뜻을 한 줄로 말한다 (REQ-20260825-081).
const EMPTY_COL = {
  open: '<div class="colempty">착수를 기다리는 요청 없음</div>',
  "in-progress": '<div class="colempty">진행 중인 요청 없음</div>',
  blocked: '<div class="colempty">막혀 있는 요청 없음</div>',
  review: '<div class="colempty">판정을 기다리는 요청 없음</div>',
  done: '<div class="colempty">완료된 요청 없음</div>',
};

// 끝난 컬럼이 접혀 있을 때 하는 말 — "몇 개 더"가 아니라 **왜 안 보이는지**를 말한다
// (REQ-20260827-057). 숫자만 있는 버튼은 목록이 잘렸다는 뜻으로 읽히지만, 여기서
// 가려진 것은 잘린 것이 아니라 하루가 지난 것이다.
const TERM_WORD = {done: "완료", cancelled: "취소"};

/* 이 열이 지금 담고 있는 것 — 끝난 열은 하루가 지난 것을 내린다
   (REQ-20260827-057). 판이 "이 열을 세울까"를 묻는 자리(colStanding)와 열이
   "무엇을 그릴까"를 묻는 자리(colHTML)가 같은 답을 봐야 한다: 두 벌이면 열이
   섰는데 안이 비거나, 안에 있는데 열이 안 서는 조합이 생긴다. */
const colLive = (key, grp) => TERMINAL.has(key)
  ? grp.filter(r => termAt(r) >= Date.now() - TERMINAL_WINDOW_MS) : grp;
/* 판에서 한 칸을 받을 열인가 (REQ-20260829-031).

   사용자: "이걸 보여줄 필요가 있나?" — 취소 열이 `하루 안에 취소된 요청 없음`
   한 줄만 담은 채 한 칸을 통째로 쓰고 있었다.

   이 파일이 이미 적어 둔 규칙이 있다(아래 colHTML): "0건이면 아예 안 나온다 —
   매번 참인 문장은 곧 안 읽히고, 없는 것을 굳이 말하는 자리가 늘면 있는 것이
   묻힌다." 취소 열이 그 규칙의 예외로 남아 있었다.

   **다른 열과 가르는 근거는 '비어 있음이 정보인가'다.** open·in-progress·
   review·blocked 는 비어 있음 자체가 사람이 확인하러 오는 값이다("판정 대기
   0"). done 은 "오늘 무엇을 끝냈나"라 매일 보는 값이라 비어도 선다. 취소는
   예외적 사건이라 **비어 있는 것이 기본값**이고, 기본값을 매일 한 칸으로
   말할 이유가 없다.

   감추는 것이지 잃는 것이 아니다: 취소된 것이 생긴 날에는 그대로 서고(그 열의
   접기·개수도 그대로다), 하루가 지나 내려간 것은 done 과 똑같이 Docs 에 있다.
   딸려 오는 값 하나 — 열이 없는 날에는 **끌어다 취소하는 자리도 없다.** 취소는
   문서 화면의 `→ cancelled` 로 늘 갈 수 있고 되돌릴 수도 있어서, 매일 한 칸을
   내주고 지킬 만큼의 지름길은 아니라고 봤다. */
const COL_ALWAYS = ["open", "in-progress", "review", "done"];
const colStanding = (key, grp) => key === "cancelled"
  ? colLive(key, grp).length > 0
  : (grp.length > 0 || COL_ALWAYS.includes(key));

function colHTML(key, label, color, grp){
  const term = TERMINAL.has(key);
  const word = TERM_WORD[key] || "완료";
  // ① 내린다 — 하루가 지난 끝난 요청은 이 열에 없다. 접은 안쪽에도 없다.
  const live = colLive(key, grp);
  const cut = grp.length - live.length;
  // ② 남은 것에 원래 접기를 그대로 — 끝난 열 3건, 나머지 7건.
  const limit = term ? COL_LIMIT_TERMINAL : COL_LIMIT;
  const open = expanded.has("col:"+key);
  const shown = open ? live : live.slice(0, limit);
  const hidden = live.length - shown.length;
  // 하루 안에 끝난 것이 없는데 "완료된 요청 없음"이라고만 하면, 322건이 어디
  // 갔는지 답하지 않는 셈이다 — 어느 하루를 말하는지 밝힌다.
  const body = live.length ? shown.map(cardHTML).join("")
    : (cut ? `<div class="colempty">하루 안에 ${word}된 요청 없음</div>`
           : (EMPTY_COL[key] || ""));
  // 내린 것을 설명하는 문구는 두지 않는다 (2026-08-27 사용자 지시 "이런건 문구로
  // 남기지마라"). 하루가 지난 것이 안 보이는 건 **이 화면이 늘 도는 규칙**이지
  // 사고가 아니다 — 규칙을 매번 변명하는 줄은 자리만 먹고 곧 안 읽힌다.
  // (사용자가 건 조건 때문에 안 보이는 경우는 다르다. 그건 원인을 짚어 줘야
  //  풀 수 있어서 Graph 빈 화면이 이름으로 말한다 — REQ-20260827-054.)
  /* 열 머리가 **멈춘 건수**를 함께 센다 (REQ-20260828-036). 사용자가 물은 것은
     "진행 중 몇 건인가"가 아니라 "그중 진짜 도는 게 몇 건인가"였다. 그 답은
     세는 대상 바로 위, 이미 총량을 말하는 그 줄에 있어야 한다 — 새 띠를 얹으면
     헤더의 경고 띠와 층위가 겹쳐 둘 다 안 읽힌다.
     0건이면 아예 안 나온다: "멈춤 0"은 매번 참인 문장이라 곧 안 읽히고, 없는
     것을 굳이 말하는 자리가 늘면 있는 것이 묻힌다. */
  // 세는 술어도 카드가 쓰는 그 하나다 (REQ-20260828-041 2차) — 배지가 세는 수와
  // 손잡이가 선 카드 수가 어긋나면, 사용자는 배지를 세다 말고 카드를 센다.
  const stalls = key === "in-progress"
    ? live.filter(r => stallState(r)).length : 0;
  // 컬럼은 이제 전부 request 상태다 (REQ-20260825-084로 etc 컬럼 제거) — 드롭 대상 표시 상시
  return `<div class="col" style="--sc:${color}" data-colstatus="${key}"><h2><span class="cdot"></span>${label}<span class="n">${live.length}</span>${stalls ? `<span class="stn" title="이 열의 ${live.length}건 중 ${stalls}건은 문서에 오래 새 기록이 없습니다">멈춤 ${stalls}</span>` : ""}</h2>
    <div class="cards">${body}
    ${hidden>0 ? `<button class="more" data-expand="col:${key}">${hidden}개 더 보기</button>`
      : (open && live.length>limit ? `<button class="more" data-expand="col:${key}">접기</button>` : "")}
    </div></div>`;
}

// Board는 요청의 상태 흐름만 다룬다 — knowledge/session 컬럼 제거 (REQ-20260825-084).
// 그 컬럼이 하던 일("지식·세션 문서에 도달한다")은 Docs 목록 최상단의 타입바가 받는다.
function renderBoard(rows){
  const reqs = rows.filter(r => r.type === "request");
  /* **상단 상태 띠를 내렸다** (REQ-20260827-070 2차 — 사용자 물음에 대한 답).

     사용자: "컬럼 헤더랑 동일한 기능인데 굳이 보여줘야 하는게 맞나?"
     아니다. 세어 보고 눌러 보고 내린 결론이다.

     ① 1차에서 띠의 셈을 열에 맞춘 뒤로 **두 줄이 같은 집합을 같은 낱말로 두 번
        센다.** 숫자가 다르면 고장으로 읽히고, 같으면 자리만 먹는다.
     ② 분포를 한눈에 보는 일도 열 머리가 그대로 한다 — 여섯 열 머리는 이미 같은
        높이에 가로로 늘어서 있어, 띠는 그 줄을 40px 위에서 되풀이하고 있었다.
        게다가 띠는 0건인 상태의 칩을 아예 뺐다 — 열은 비어도 자리를 지키는데.
        같은 화면이 같은 질문에 두 가지로 답하고 있었던 셈이다.
     ③ 띠의 필터는 **보드에서 할 일이 없었다.** 눌러도 그 열만 남는 것이 아니라
        나머지 네 열이 "…없음" 으로 비어, 걸기 전보다 나쁜 화면이 된다. 상태로
        가르는 일은 열이 이미 한다 — 칸반에 상태 필터를 겹쳐 놓은 셈이었다.
        게다가 걸린 줄은 작은 밑줄 하나로만 표시돼 빠져나오는 길이 흐렸다.
     ④ 열을 깊이 보는 일은 `+ N개 더 보기` 가 이미 맡고 있다.

     그래서 열 머리 하나만 남긴다 — **한 숫자는 한 곳에만.** CSS(.stats/.stat)는
     지우지 않고 둔다: 열 스킨 블록에 흩어져 있어 되돌리는 값이 크고, 이 판단이
     뒤집히면 이 자리 한 줄로 돌아온다. */
  let html = "";
  // 병목 한 줄 (REQ-20260826-009 2차): 카드마다 "선행 대기" 줄은 이미 있다 —
  // 카드가 말할 수 없는 것, 즉 "한 선행이 여러 건을 붙잡고 있다"일 때만 띄운다.
  // 그 외에는 같은 사실을 두 번 말하는 것이라 보드를 그대로 둔다.
  const dbk = depBoard(reqs);
  if (dbk.top && dbk.top[1] > 1){
    const b = catFind(dbk.top[0]);
    if (b) html += `<div class="bneck"><span class="bcap">병목</span> `
      + `${dlink(b.id, esc(shortId(b.id)))} `
      + `<b>${esc(b.title)}</b> 이(가) ${dbk.top[1]}건을 붙잡고 있다 · `
      + `전체 ${dbk.groups.length}건이 선행을 기다린다`
      + `<button class="bgo" data-goto="graph">선행 대기 현황 →</button></div>`;
  }
  html += `<div class="board">`;
  for (const st of STATUSES){
    let grp = reqs.filter(r => r.status === st);
    // 끝난 컬럼은 우선순위로 세우지 않는다 (REQ-20260827-016).
    // 우선순위는 "다음에 무엇을 할 것인가"에 답하는 축이다 — 이미 끝난 일에는
    // 그 질문이 없다. done 286건이 가중치 계단으로 묶여 있으면 방금 끝난 것을
    // 찾으려고 계단마다 훑어야 한다.
    //
    // 세우는 기준은 **카드가 실제로 보여주는 시각**이다 — `status_since`,
    // 즉 그 상태가 된 때. `updated` 로 세웠다가 반려를 받았다(1차): 그 필드는
    // 노트·링크·인덱스 작업으로 계속 밀려서, 21시간 전에 끝난 문서가 "방금
    // 갱신"으로 맨 위에 왔다. 화면의 시계와 정렬의 자가 다르면 사용자에게는
    // 정렬이 안 된 것으로 보인다 — 그리고 그 말이 맞다.
    if (TERMINAL.has(st))
      grp = [...grp].sort((a, b) => (b.status_since || b.updated || b.created || "")
        .localeCompare(a.status_since || a.updated || a.created || ""));
    /* in-progress 열은 **오래 멈춘 순 → 도는 중 순** (REQ-20260828-036).
       이 열이 답하는 질문은 "무엇부터 손대야 하나"이고, 그 답은 가장 오래
       조용한 것이다. 기본 정렬(우선순위 → 최근 갱신)은 그 반대로 세운다 —
       방금 움직인 것이 위로 오니, 손 뗀 지 한 시간 된 요청이 접힌 아래로
       내려가 사용자가 스크롤해야 찾는 자리에 있었다.
       멈추지 않은 것들끼리는 기존 차례를 그대로 둔다(안정 정렬). */
    if (st === "in-progress")
      grp = [...grp].sort((a, b) => {
        const x = stallState(a), y = stallState(b);
        return (y ? y.mins : -1) - (x ? x.mins : -1);
      });
    /* review 열은 **판정 큐**다 (REQ-20260831-015, DOC-20260831-002 규칙 2).
       이 열이 답하는 질문은 "무엇부터 판정할 것인가"이고, 그 답은 우선순위도
       최근 갱신도 아니다 — **먼저 지은 것이 먼저다.** 연관된 것들이 흩어져
       서면 사용자가 후행을 먼저 판정하고, 뒤이어 선행을 반려하는 순간 방금
       내린 판정이 무효가 된다(이 요청을 낳은 그 사고다).
       키 하나로 둘을 동시에 얻는다: `review_order` 로 오름차순 정렬하면 같은
       묶음이 붙어 서고 그 안에서 선행이 위에 온다 — 화면이 묶음을 다시 계산할
       일이 없다(서버 review_family 한 곳이 안다). in-progress 열이 기본 정렬을
       통째로 대체하는 것과 같은 규칙이다: 열마다 자기 질문이 있다. */
    if (st === "review")
      grp = [...grp].sort((a, b) => reviewKey(a).localeCompare(reviewKey(b)));
    // 주요 컬럼은 비어도 자리를 지킨다 — 드롭 대상이자 상태 안내 자리(ux-craft)
    // 필터가 사라졌으니 "걸러서 빈 것"과 "원래 빈 것"을 가를 일도 없다
    // (REQ-20260827-070 2차) — 주요 네 열은 비어도 자리를 지킨다.
    // 취소 열만 잣대가 다르다 — 판정은 colStanding 한 곳에 있다 (REQ-20260829-031).
    if (!colStanding(st, grp)) continue;
    html += colHTML(st, st, SCOLOR[st], grp);
  }
  html += `</div>`;
  $("#view").innerHTML = html;
  markPicked();   // 집어 둔 카드 표시 복원 (REQ-20260827-064)
  // 세 줄에서 잘린 카드에만 "전문 보기"를 연다 — 잘림은 재서 안다 (REQ-20260829-009).
  // 그림이 붙은 다음 프레임에 잰다: innerHTML 직후에는 아직 레이아웃이 없다.
  requestAnimationFrame(() => markClamped($("#view")));
  elapsedTimer = setInterval(tickElapsed, 1000);  // 카드 경과시간 실시간 갱신
}

/* 잘렸는지는 **재서** 안다 (REQ-20260829-009). 글자 수로 짐작하면 스킨마다
   틀린다 — 열 폭(210~252px)·글꼴·줄간·밀도가 열 벌 넘는 스킨에서 다 달라서,
   같은 문장이 한 스킨에선 세 줄, 다른 스킨에선 네 줄이다. 짐작이 빗나가면
   둘 중 하나가 된다: 안 잘린 카드에 손잡이가 붙는 소음이거나, 잘린 채로
   아무 말도 없는 화면이거나. 후자가 이 요청의 원인이다.

   재는 자리가 둘인 이유: 베이스는 본문 span(.rvtx)에 클램프를 걸고, calm 은
   캡션을 인라인으로 눕히므로 블록(.rvpt) 전체에 건다. 실제로 넘친 쪽을 잡는다.
   1px 여유는 소수점 줄 높이의 반올림 때문이다 — 없으면 안 잘린 글도 잘렸다고
   말한다. 계약: tests/test_review_clamp.py */
function markClamped(root){
  (root || document).querySelectorAll(".rvpt.clampy").forEach(el => {
    const tx = el.querySelector(".rvtx");
    const box = tx && tx.clientHeight ? tx : el;
    /* 문턱은 px 상수가 아니라 **줄 높이**다. 클램프가 자르면 최소 한 줄이
       남으므로 넘침은 늘 한 줄 이상이다 — 그보다 작은 차이는 레이아웃
       반올림이지 잘림이 아니다. 상수 1px 로 쟀다가 실제로 틀렸다: 넓은
       창에서 딱 세 줄로 끝난 대기 사유가(말줄임표도 없이) 잘렸다고
       보고돼 손잡이가 붙었다. 반 줄을 문턱으로 둔다. */
    const lh = parseFloat(getComputedStyle(box).lineHeight) || 16;
    el.classList.toggle("iscut", box.scrollHeight - box.clientHeight > lh * 0.5);
  });
}
// 열 폭이 바뀌면 몇 줄인지도 바뀐다 — 창을 줄였는데 손잡이가 그대로면 거짓말이다.
let clampResizeT;
function markClampedSoon(){ clearTimeout(clampResizeT); clampResizeT = setTimeout(markClamped, 60); }
window.addEventListener("resize", markClampedSoon);

/* ---------------- docs ---------------- */
function hl(text, q){
  let out = esc(text);
  for (const t of q.split(/\s+/).filter(Boolean)){
    const re = new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    out = out.replace(re, m => `<b>${m}</b>`);
  }
  return out;
}

/* 못 박은 줄의 머리글과 그 손잡이의 낱말 (REQ-20260829-012). 문구는 ux-writer
   몫이라 한 곳에만 둔다 — 다만 머리글은 **타입 이름처럼 보이면 안 된다**
   (request·knowledge 옆에 또 하나의 덩어리로 읽힌다). */
