v1 「검은 타일」 — 잉크 사각 타일 위에 렌즈(테·돔 음영·반사)와 잉크 점 셋

주인이 2026-09-14 11:02 에 채택한 판이다(REQ-20260914-001-62x6). 타일이 잉크라
어느 배경에서도 렌즈가 또렷하지만, 그 검은 사각이 밝은 배경과 어울리지 않는다는
지적에서 v2 가 갈라져 나왔다.

  · 렌즈 r=24(64 눈금) · 테 = 반지름의 4.2% · 돔 음영 #fdfcf8 → #c6c4ba
  · 점 셋 = 렌즈 지름의 12.5%, 무리 중심이 14.2% 아래 (탭 새김)
  · logo.svg 타일과 큰 PNG 는 큰 새김(점 지름 8%, 15.2% 아래)

다시 구우려면: python3 build.py install <web/assets 경로> · python3 build.py pages

되돌리기(명령이 아니라 절차 한 줄):
  cp web/assets/mark/v1/{mark.svg,favicon.svg,logo.svg,favicon.ico,icon-192.png,icon-512.png,apple-touch-icon.png} web/assets/
  그리고 web/index.html 의 `<svg class="mark">…</svg>` 한 덩어리를 이 폴더의 header.svg 로 바꾼다.
