/* userform.js — 프로필+config 편집 폼 */
"use strict";
function showUserForm(u, host, isAdminEdit){
  if (!host) return;
  const cfg = u.config || {};
  /* 자리를 얻지 못한 값만 남긴다 (REQ-20260901-022).
     **자리를 얻은 키는 반드시 여기서 빠져야 한다** — 안 빼면 같은 값이 제 행과
     이 목록에 두 번 서고, 어느 쪽이 참인지 화면이 말하지 못한다. 그래서 목록을
     손으로 늘리지 않고 `WCFG_KEYS`(백그라운드 작업 판이 세우는 행의 키)와
     `wcfgMine`(그 판이 데려가는 접두사)에서 받아 온다: 그 판에 행이 늘면 이
     제외도 저절로 는다.
     **판이 넷으로 늘었다** (REQ-20260911-005) — 「외부 서비스」(`JIRA_CFG_KEYS`)와
     「저장소 → 문서 동기화」(`SYNC_CAP_KEYS`)도 제 행을 세우는데 여기서 빠지지
     않아, jira 넷이 제 행과 이 표에 **두 번 서 있었다**. 목록을 네 판에서
     모두 받아 온다. */
  const extraCfg = Object.entries(cfg).filter(([k]) =>
    !["timezone","digest_budget","ui_skin","ui_tone","ui_density",
      "stream_mirror","stream_keep_days",
      "external_secrets_path"].includes(k) && !k.startsWith("pref_")
    && !WCFG_KEYS.includes(k) && !wcfgMine(k)
    && !JIRA_CFG_KEYS.includes(k) && !SYNC_CAP_KEYS.includes(k));
  // 비밀은 **내 계정 판에서만** 다룬다. 서버의 /api/secrets 는 admin 대리(as)를
  // 받지 않아 내 키를 주는데, 넣고 지우는 쪽은 대리를 받는다 — 남의 이름표를 달고
  // 내 키 목록을 보여 주면 그 화면은 거짓말이다. 그럴 바엔 자리를 내지 않는다.
  const mySecrets = !isAdminEdit && !asUser && u.name === getMe();
  // 회사 이메일: emails[] 우선, 비어 있으면 legacy email 단수를 시드(저장 시 emails로 이관)
  const seedEmails = (u.emails && u.emails.length) ? u.emails : (u.email ? [u.email] : []);
  const emRowHTML = val => `<div class="emrow">
      <input class="uf em-val" value="${esc(val)}" placeholder="name@company.com">
      <button type="button" class="em-rm" title="이 이메일 행 삭제">− 삭제</button></div>`;
  const reqhint = `<span class="reqhint">권장 — 미기재</span>`;
  host.innerHTML = `
    <div class="path">users/${esc(u.name)}/profile.md · 등록 ${esc((u.registered||"?").slice(0,16))} @ ${esc(u.registered_on||"?")}</div>
    <h1 style="margin:6px 0 14px">@${esc(u.name)}</h1>
    <table class="metatbl">
      <!-- 사람을 부르는 이름 (REQ-20260915-029-62x6, 주인 지적 2026-09-15 16:47:
           「설치할 때는 성·이름을 받는데 정작 settings 에는 구분이 없다」).
           세 칸의 관계: display 는 **사람이 직접 쓴 표기**라 있으면 그것이 이기고,
           비어 있으면 성·이름을 그 사람의 말 순서로 이어 부른다(서버의
           user_full_name 한 함수). 그래서 성·이름 칸은 display 바로 아래 선다 —
           (이 주석에 백틱을 쓰지 마라: 이 자리는 템플릿 문자열 안이라 백틱 하나가
           문자열을 끊어 이 파일이 통째로 SyntaxError 로 죽는다 — 실측 2026-09-15.)
           무엇이 무엇을 대신하는지가 위아래로 읽힌다. -->
      <tr><td>display</td><td><input class="uf" id="uf-display" value="${esc(u.display)}"
        placeholder="비우면 성·이름으로 부릅니다"></td></tr>
      <tr><td>성</td><td><input class="uf" id="uf-last" value="${esc(u.last_name||"")}"
        placeholder="예: 박"></td></tr>
      <tr><td>이름</td><td><input class="uf" id="uf-first" value="${esc(u.first_name||"")}"
        placeholder="예: 성진"></td></tr>
      <tr><td>부르는 이름</td><td><span class="path" id="uf-full">${esc(u.full || "—")}</span>
        <span class="path">— 카드와 목록에 이 이름이 섭니다. 비면 id(@${esc(u.name)})로 섭니다</span></td></tr>
      <tr><td>회사 이메일</td><td id="uf-emails">
        ${seedEmails.map(em => emRowHTML(em)).join("")}
        <button type="button" class="em-add" id="uf-em-add">+ 이메일 추가</button>${seedEmails.length ? "" : reqhint}
        <div class="path">회사 이메일 N개 — 빈 행은 저장 시 제외됩니다</div></td></tr>
      <tr><td>github (개인)</td><td><input class="uf" id="uf-github" value="${esc(u.github||"")}" placeholder="개인 GitHub 계정명">${u.github ? "" : reqhint}</td></tr>
      <tr><td>github (조직)</td><td><input class="uf" id="uf-github-org" value="${esc(u.github_org||"")}" placeholder="조직 GitHub 계정/org (선택)"></td></tr>
      <tr><td>role</td><td><select class="uf" id="uf-role">
        ${["admin","member","viewer"].map(r => `<option${r===u.role?" selected":""}>${r}</option>`).join("")}
      </select> <span class="path">변경은 admin만</span></td></tr>
    </table>
    <div class="acts"><button id="uf-save">프로필 저장</button><span class="ferr" id="uf-err"></span></div>
    ${machineHistoryHTML(u)}
    <div class="cfg-h">개인화 설정 — config/settings.json</div>
    <table class="metatbl">
      <tr><td>digest_budget</td><td><input class="uf" id="cf-digest_budget" placeholder="2500" value="${esc(cfg.digest_budget||"")}"></td></tr>
      <tr><td><input class="uf" id="cf-key" placeholder="임의 키" style="width:130px"></td>
          <td><input class="uf" id="cf-val" placeholder="값 (빈 값=삭제)"></td></tr>
    </table>
    <div class="acts"><button id="cf-save">설정 저장</button></div>
    <div class="cfg-h">시간대</div>
    <div class="path secnote">문서와 기록의 시각을 이 시간대로 적습니다 — config/settings.json 의 <b>timezone</b>. 이름을 쳐서 좁히고 골라 주세요. <b>고르면 바로 저장됩니다.</b></div>
    <div class="tzline">
      <div class="tzc">
        <input class="uf tzin" id="tz-in" role="combobox" aria-expanded="false"
               aria-controls="tz-pop" aria-autocomplete="list" aria-label="시간대"
               autocomplete="off" spellcheck="false" placeholder="설정 안 함"
               value="${esc(cfg.timezone || "")}">
        <span class="tzcar">${mk("unfold")}</span>
      </div>
      <span class="tznow" id="tz-now" aria-live="polite"></span>
    </div>
    <div class="secmsg" id="tz-msg"></div>
    <div class="cfg-h">대화 기록 — Stream 탭</div>
    <div class="path secnote">세션 대화를 이 저장소에 남길지 정합니다. 끄면 Stream 탭과 문서 안의 대화 보기가 함께 사라지고, 이미 남은 기록은 지우지 않습니다. <b>바꾸면 바로 저장됩니다.</b></div>
    <table class="metatbl">
      <tr><td>기록 남기기</td><td>
        <select class="uf" id="cf-stream" style="width:auto">
          <option value="on"${String(cfg.stream_mirror ?? "on").toLowerCase() === "off" ? "" : " selected"}>켬 — 대화를 남깁니다</option>
          <option value="off"${String(cfg.stream_mirror ?? "on").toLowerCase() === "off" ? " selected" : ""}>끔 — 남기지 않습니다</option>
        </select></td></tr>
      <tr id="cf-daysrow"><td>보관 기간</td><td>
        <input class="uf" id="cf-streamdays" style="width:80px" inputmode="numeric"
               placeholder="7" value="${esc(cfg.stream_keep_days ?? "")}"> 일
        <span class="path" style="display:inline;margin-left:8px">비우면 7일 · 0 이면 지우지 않습니다</span></td></tr>
    </table>
    <div class="secmsg" id="cf-stream-msg"></div>
    ${mySecrets ? `
    <div class="cfg-h">시크릿 — 값은 이 화면에 나오지 않습니다</div>
    <div class="path secnote">API 키처럼 남이 보면 안 되는 값입니다. <b>키 이름만 보입니다.</b> 넣은 값은 저장한 뒤 다시 볼 수 없으니, 잊었으면 새 값으로 덮어쓰세요.</div>
    <div id="sec-list" class="secempty">불러오는 중…</div>
    <div class="secform">
      <input class="uf" id="sec-key" style="width:210px" autocomplete="off" spellcheck="false"
             aria-label="키 이름" placeholder="키 이름 (예: OPENAI_API_KEY)">
      <input class="uf" id="sec-val" type="password" autocomplete="new-password"
             aria-label="값" placeholder="값 — 저장 뒤 다시 볼 수 없습니다">
    </div>
    <div class="secwlab" id="sec-wlab">어디에 넣을까요</div>
    <div class="secwhere" id="sec-where" role="radiogroup" aria-labelledby="sec-wlab">
      <label class="wopt on" data-w="internal">
        <input type="radio" name="sec-w" value="internal" checked>
        <span class="wm" aria-hidden="true">●</span><span class="wn">저장소 안</span>
        <span class="wp" id="sec-wp-in">users/…/secrets</span></label>
      <label class="wopt" data-w="external">
        <input type="radio" name="sec-w" value="external">
        <span class="wm" aria-hidden="true">○</span><span class="wn">저장소 밖</span>
        <span class="wp" id="sec-wp-ex">불러오는 중…</span></label>
    </div>
    <div class="secwhy" id="sec-why"></div>
    <div class="secform">
      <button type="button" id="sec-add">+ 저장소 안에 넣기</button>
    </div>
    <div class="secmsg" id="sec-msg"></div>
    <div class="secsub">바깥 폴더 — 저장소 밖에 둘 시크릿의 자리</div>
    <div class="path secnote">저장소는 다른 사람과 공유됩니다. 그래서 저장소 밖 폴더 하나를 더 쓸 수 있습니다 — <b>없는 폴더는 저장할 때 만들어 드립니다</b>(나만 읽을 수 있게). 경로를 정하면 <b>위의 넣기에서 “저장소 밖”을 고를 수 있습니다</b> — 정하기 전에는 그 칸이 잠겨 있습니다. 이미 그 폴더에 둔 파일도 함께 읽습니다: <b>파일 이름이 곧 키 이름</b>입니다.</div>
    <div class="secform">
      <input class="uf" id="sec-ext" style="width:330px" autocomplete="off" spellcheck="false"
             aria-label="바깥 폴더 경로" placeholder="예: ~/.s9-secrets (비우면 쓰지 않습니다)"
             value="${esc(cfg.external_secrets_path || "")}">
      <button type="button" id="sec-ext-save">경로 저장</button>
    </div>
    <div class="secstate" id="sec-ext-state" aria-live="polite">불러오는 중…</div>` : ""}
    ${extraCfg.length ? `<div class="cfg-h">그 밖의 값</div>
    <div class="path secnote">화면이 아직 뜻을 모르는 값입니다 — 이름과 값은 그대로 쓰이고 있습니다. <b>빈 값으로 저장하면 지워집니다.</b></div>
    <table class="metatbl" id="xc-table">
      ${extraCfg.map(([k, val]) => `<tr data-xc="${esc(k)}">
        <td>${esc(k)}</td>
        <td><input class="uf xc-val" value="${esc(String(val))}" placeholder="비우고 저장 = 삭제"></td>
      </tr>`).join("")}
    </table>
    <div class="acts"><button id="xc-save">값 저장</button></div>` : ""}
    ${isAdminEdit ? `<div class="cfg-h">백그라운드 작업</div>${workerCfgHTML(u)}` : ""}
    <div class="path" style="margin-top:16px">변경은 profile.md Notes에 audit + git 동기화. 본인 또는 admin만 수정.</div>`;
  /* admin 이 남의 백그라운드 작업 설정을 만지는 자리 (REQ-20260901-022) — 내 판과
     **같은 부품 한 벌**이다. 서버가 대리를 받으므로(POST /api/user/config)
     가능하고, 확인 창과 사실 줄은 그 계정 이름을 말한다(REQ-20260901-017). */
  if (isAdminEdit) wireWorkerCfg(host, u);
  // 이메일 행 추가/삭제 — DOM만 조작(재렌더 없음 → 다른 입력값 보존)
  host.querySelector("#uf-emails").addEventListener("click", e => {
    // 지우기 버튼의 **글자**를 누르면 target 이 텍스트 노드다 — 거기엔
    // classList 도 closest 도 없다 (REQ-20260830-010). 경로를 한 번만 지난다.
    const el = evEl(e.target);
    if (el?.classList.contains("em-rm")) el.closest(".emrow")?.remove();
  });
  host.querySelector("#uf-em-add").addEventListener("click", () => {
    host.querySelector("#uf-em-add").insertAdjacentHTML("beforebegin", emRowHTML(""));
    const rows = host.querySelectorAll("#uf-emails .em-val");
    rows[rows.length - 1].focus();
  });
  host.querySelector("#uf-save").addEventListener("click", async () => {
    const errEl = host.querySelector("#uf-err");
    errEl.textContent = "";
    const emails = [...host.querySelectorAll("#uf-emails .em-val")]
      .map(i => i.value.trim()).filter(Boolean);
    const body = {name: u.name, display: host.querySelector("#uf-display").value.trim(),
                  last_name: host.querySelector("#uf-last").value.trim(),
                  first_name: host.querySelector("#uf-first").value.trim(),
                  emails,  // legacy email 단수는 더 보내지 않음 — 서버는 미전달 필드 무변경
                  github: host.querySelector("#uf-github").value.trim(),
                  github_org: host.querySelector("#uf-github-org").value.trim()};
    const nr = host.querySelector("#uf-role").value;
    if (nr !== u.role) body.role = nr;
    const res = await postJSONRaw("/api/user/update", body);
    if (!res.ok){ errEl.textContent = "✕ " + res.error; return; }  // 인라인 — 팝업 금지
    renderSettings();
  });
  host.querySelector("#cf-save").addEventListener("click", async () => {
    // timezone 은 여기서 저장하지 않는다 (REQ-20260828-029) — 자기 자리에서
    // 고른 즉시 저장된다. 이 목록에 남겨 두면 **렌더 시점의 낡은 값**이
    // 방금 고른 값을 덮어쓴다(이 폼은 재렌더 없이 살아 있다).
    const sets = [["digest_budget", $("#cf-digest_budget").value.trim()]];
    const ck = $("#cf-key").value.trim();
    if (ck) sets.push([ck, $("#cf-val").value.trim()]);
    let ok = true;
    for (const [k, val] of sets){
      if (val === String(cfg[k] ?? "")) continue;
      ok = (await postJSON("/api/user/config", {name: u.name, key: k, value: val})) && ok;
    }
    if (ok) renderSettings();
  });
  /* ------- 대화 기록 스위치 (REQ-20260828-013) -------
     **바꾸면 바로 저장된다.** 저장 버튼을 따로 두면 "켰는데 왜 안 켜지지"가 생기고,
     디스플레이 설정이 이미 같은 손버릇을 쓴다(고른 즉시 반영). 저장 뒤에는 신원을
     다시 받아 Stream 탭을 그 자리에서 올리거나 내린다 — 껐는데 탭이 남아 있으면
     설정이 안 먹은 것으로 읽힌다. */
  const smSel = host.querySelector("#cf-stream");
  const smDays = host.querySelector("#cf-streamdays");
  const smMsg = host.querySelector("#cf-stream-msg");
  const smSyncDays = () => {
    if (!smDays) return;
    const off = smSel.value === "off";
    smDays.disabled = off;
    const row = host.querySelector("#cf-daysrow");
    if (row) row.classList.toggle("rowoff", off);
  };
  async function saveStream(key, val, said){
    smMsg.className = "secmsg";
    smMsg.textContent = "저장하는 중…";
    const res = await postJSONRaw("/api/user/config", {name: u.name, key, value: val});
    if (!res.ok){ smMsg.className = "secmsg bad"; smMsg.textContent = "✕ " + res.error; return; }
    smMsg.textContent = said;
    await loadWhoami();
    applyStreamVisibility();
  }
  if (smSel){
    smSyncDays();
    smSel.addEventListener("change", () => { smSyncDays();
      saveStream("stream_mirror", smSel.value,
        smSel.value === "off" ? "껐습니다 — Stream 탭이 내려갔습니다. 이미 남은 기록은 그대로입니다."
                              : "켰습니다 — Stream 탭에서 대화를 볼 수 있습니다."); });
    smDays.addEventListener("change", () => {
      const raw = smDays.value.trim();
      if (raw && !/^\d+$/.test(raw)){
        smMsg.className = "secmsg bad";
        smMsg.textContent = "✕ 날짜 수만 적어 주세요. 예: 7";
        return;
      }
      saveStream("stream_keep_days", raw,
        !raw ? "기본값(7일)으로 되돌렸습니다."
             : raw === "0" ? "지우지 않고 계속 보관합니다."
                           : `${raw}일이 지난 기록부터 지웁니다.`);
    });
  }
  tzWire(host, u);
  /* ------- 비밀 키 (REQ-20260828-012) -------
     **값을 그리지 않는다.** 목록은 키 이름과 어디에 있는지뿐이고, 넣은 값은 저장
     즉시 입력칸에서도 지운다 — 화면에 남아 있으면 캡처·화면 공유·어깨너머로
     따라간다. 서버도 값을 응답에 담지 않으므로 화면이 다시 보여 줄 방법 자체가
     없다. 그래서 "잊었으면 덮어쓰세요"라고 미리 말해 둔다. */
  const secList = host.querySelector("#sec-list");
  /* ------- 바깥 폴더 (REQ-20260828-017) -------
     `external_secret_dir()` 은 폴더가 없으면 **아무 말 없이** "" 로 떨어진다.
     경로만 적어 두고 폴더를 안 만든 사람에게는 "적었는데 아무 일도 안 일어난다"
     로만 보인다 — 그 침묵을 이 한 줄이 깬다.
     **판정은 서버가 한다.** 브라우저는 폴더가 있는지 볼 수 없고, 둘이 따로 재면
     언젠가 답이 갈린다. 화면은 서버가 준 낱말 하나를 사람 말로 옮길 뿐이다. */
  const extIn = host.querySelector("#sec-ext");
  const extState = host.querySelector("#sec-ext-state");
  const EXTSAY = {
    ok:      ["on",   "읽는 중",
              "이 폴더의 파일도 시크릿으로 함께 읽고 있고, 위의 넣기에서 여기에 넣을 수 있습니다."],
    missing: ["warn", "폴더 없음",
              "지워졌거나 연결이 끊긴 것 같습니다. 지금은 저장소 안의 시크릿만 씁니다 — 경로 저장을 다시 누르면 만듭니다."],
    inrepo:  ["bad",  "쓰면 안 됩니다",
              "이 저장소 안의 폴더입니다. 저장소는 다른 사람과 공유되니 밖에 두는 뜻이 없습니다 — 저장소 밖 경로로 바꿔 주세요."],
    unset:   ["",     "정하지 않음",
              "저장소 안에 둔 시크릿만 씁니다."],
    unknown: ["",     "확인 못 함",
              "지금 이 폴더를 읽고 있는지 알아내지 못했습니다."],
  };
  function extSay(state, saved){
    if (!extState) return;
    if (!state){ extState.className = "secstate"; extState.textContent = "확인하는 중…"; return; }
    const [cls, mark, why] = EXTSAY[state] || EXTSAY.unset;
    extState.className = "secstate" + (cls ? " " + cls : "");
    // 손잡이를 더 두지 않는다 — 폴더가 사라졌을 때 할 일도 '경로 저장' 하나다
    // (다시 만들고, 만든 뒤 판정을 다시 받는 것까지 그 버튼이 한다).
    extState.innerHTML = `<span class="sm">${mark}</span>${why}`;
    // 저장된 값이 화면의 진실이다 — 손이 칸에 올라가 있을 때만 건드리지 않는다
    if (extIn && saved !== undefined && document.activeElement !== extIn)
      extIn.value = saved;
  }
  function extBad(msg){
    if (!extState) return;
    extState.className = "secstate bad";
    extState.innerHTML = `<span class="sm">저장 못 함</span>${esc(msg)}`;
  }
  /* ------- 어디에 넣을까 (REQ-20260828-017) -------
     사용자: "internal 항목이랑 좌우 형태로 같이 등록될 수 있으면 좋겠는데."
     넣는 폼을 두 벌 세우는 대신 **둘 곳을 좌우 두 칸으로** 세웠다 — 값은 한 번만
     치고 목적지만 고른다(마음이 바뀌어도 값을 다시 치지 않는다).
     **바깥을 못 쓰는 상태면 그 칸이 잠긴다.** 조용히 저장소 안으로 떨어뜨리지
     않는다: 사용자는 밖에 넣은 줄 아는데 값은 안에 들어가 있는 상태가 제일 나쁘다.
     판정(external_state)은 여기서도 서버가 낸 것 하나를 읽는다. */
  const whereBox = host.querySelector("#sec-where");
  const whyBox = host.querySelector("#sec-why");
  const WHERE_KO = {internal: "저장소 안", external: "저장소 밖"};
  /* 칸 안에는 **짧은 상태 이름**, 아래 줄에는 문장과 다음 행동. 같은 말을 두 번
     하면 칸이 설명문이 되고, 왼쪽 칸의 경로 줄과 짝이 맞지 않는다. */
  const EXTWHY = {
    unset:   ["경로 미설정",      "바깥 폴더를 아직 정하지 않았습니다."],
    missing: ["폴더 없음",        "적어 둔 바깥 폴더가 지금 없습니다."],
    inrepo:  ["저장소 안을 가리킴", "바깥 폴더가 저장소 안을 가리킵니다."],
    unknown: ["확인 못 함",       "바깥 폴더를 쓸 수 있는지 알아내지 못했습니다."],
  };
  let secWhere = "internal", secData = null;
  function paintWhere(){
    if (!whereBox) return;
    const st = (secData && secData.external_state) || (secData ? "unset" : "unknown");
    const canExt = st === "ok";
    const ks = (secData && secData.keys) || [];
    // 바깥 키 수에는 **가려진 것도 센다** — 목록에서 안 보인다고 없는 것이 아니다
    const nIn = ks.filter(k => k.where === "internal").length;
    const nEx = ks.filter(k => k.where === "external").length
              + ks.filter(k => k.shadowed).length;
    if (!canExt) secWhere = "internal";
    const wIn = host.querySelector("#sec-wp-in"), wEx = host.querySelector("#sec-wp-ex");
    if (wIn) wIn.textContent = ((secData && secData.internal) || "users/…/secrets")
      + " · 키 " + nIn + "개";
    const why = EXTWHY[st] || EXTWHY.unknown;
    if (wEx) wEx.textContent = canExt
      ? ((secData.external_path || "(경로 없음)") + " · 키 " + nEx + "개")
      : why[0];
    whereBox.querySelectorAll(".wopt").forEach(el => {
      const on = el.dataset.w === secWhere, off = el.dataset.w === "external" && !canExt;
      el.classList.toggle("on", on);
      el.classList.toggle("off", off);
      el.querySelector(".wm").textContent = on ? "●" : "○";
      const r = el.querySelector("input");
      r.checked = on;
      r.disabled = off;
    });
    if (whyBox) whyBox.innerHTML = canExt ? "" :
      `${esc(why[1])} 저장소 밖에 넣으려면 아래에서 경로부터 정해 주세요.
       <button type="button" class="gefix" id="sec-gopath">경로 정하기</button>`;
    const ab = host.querySelector("#sec-add");
    if (ab) ab.textContent = `+ ${WHERE_KO[secWhere]}에 넣기`;
  }
  if (whereBox){
    whereBox.addEventListener("change", e => {
      const r = evEl(e.target)?.closest("input[type=radio]");
      if (!r || r.disabled) return;
      secWhere = r.value;
      paintWhere();
    });
    // 잠긴 칸을 눌렀는데 아무 일도 안 일어나면 고장으로 읽힌다 — 아래 줄을 한 번
    // 깜빡여 눈을 그리로 보낸다(움직임을 줄여 달라고 한 사람에게는 하지 않는다).
    whereBox.addEventListener("click", e => {
      if (!evEl(e.target)?.closest(".wopt.off")) return;
      e.preventDefault();
      const w = host.querySelector("#sec-why");
      if (w && w.animate
          && !matchMedia("(prefers-reduced-motion: reduce)").matches)
        w.animate([{opacity: .25}, {opacity: 1}], {duration: 180, easing: "ease-out"});
    });
  }
  if (whyBox) whyBox.addEventListener("click", e => {
    if (!evEl(e.target)?.closest("#sec-gopath")) return;
    const box = host.querySelector("#sec-ext");
    if (!box) return;
    box.scrollIntoView({block: "center", behavior: "smooth"});
    box.focus();
  });
  async function loadSecrets(){
    if (!secList) return;
    secList.className = "secempty";
    secList.textContent = "불러오는 중…";
    extSay(null);
    let d = null;
    try{ d = await (await s9Fetch("/api/secrets")).json(); }catch(e){}
    if (!d || !Array.isArray(d.keys)){
      secList.className = "secempty";
      secList.innerHTML = `시크릿 목록을 받아오지 못했습니다.
        <button type="button" class="gefix" id="sec-retry">다시 받기</button>`;
      const rt = host.querySelector("#sec-retry");
      if (rt) rt.addEventListener("click", loadSecrets);
      extSay("unknown");
      secData = null;
      paintWhere();
      return;
    }
    secData = d;
    paintWhere();
    // 바깥 폴더 칸은 목록과 한 호흡이다 — 목록이 갱신될 때마다 그 판정도 같이
    // 새로 받는다. 빈 목록에서 먼저 return 하기 전에 그린다.
    extSay(d.external_state || "unset", d.external_path || "");
    if (!d.keys.length){
      secList.className = "secempty";
      secList.textContent = "아직 넣은 시크릿이 없습니다 — 아래에 키 이름과 값을 넣으면 여기에 줄이 쌓입니다.";
      return;
    }
    secList.className = "mhwrap";
    secList.innerHTML = `<table class="mhtbl sectbl">
      <tr><th>키 이름</th><th>둔 곳</th><th></th></tr>
      ${d.keys.map(k => `<tr>
        <td class="sk">${esc(k.key)}</td>
        <td>${k.where === "external" ? "저장소 밖" : "저장소 안"}${
          k.shadowed ? `<span class="shad">밖의 같은 이름은 가려짐 — 안의 값이 쓰입니다</span>` : ""}</td>
        <td><button type="button" class="secrm" data-k="${esc(k.key)}"
             data-w="${esc(k.where)}" data-both="${k.shadowed ? 1 : 0}">지우기</button></td>
      </tr>`).join("")}
    </table>
    <div class="path">저장소 안 = <code>${esc(d.internal || "")}</code>${
      d.external ? " · 저장소 밖 = 아래 <b>바깥 폴더</b>에 적어 둔 경로" : ""}</div>`;
  }
  const secMsg = host.querySelector("#sec-msg");
  function secSay(text, bad){
    if (!secMsg) return;
    // bad === true 는 실패, 문자열이면 등급 이름("warn") — 넣기는 성공했는데
    // 그 값이 쓰이지 않는 경우가 있어 둘 사이에 한 급이 필요하다
    secMsg.className = "secmsg" + (bad === true ? " bad" : bad ? " " + bad : "");
    secMsg.textContent = text;
  }
  if (secList){
    loadSecrets();
    const kIn = host.querySelector("#sec-key"), vIn = host.querySelector("#sec-val");
    const addBtn = host.querySelector("#sec-add");
    addBtn.addEventListener("click", async () => {
      const key = kIn.value.trim();
      if (!key){ secSay("키 이름을 적어 주세요. 예: OPENAI_API_KEY", true); kIn.focus(); return; }
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)){
        secSay("키 이름은 영문·숫자·밑줄만 씁니다. 예: OPENAI_API_KEY", true); kIn.focus(); return; }
      if (!vIn.value){ secSay("값을 넣어 주세요. 빈 값은 저장하지 않습니다.", true); vIn.focus(); return; }
      /* 같은 이름이 저장소 안에 있으면 **안의 값이 이긴다**(secret_keys 가 그렇게
         정해져 있다). 밖에 넣어 놓고 안 쓰이는 것을 모르는 상태가 이 기능에서
         가장 나쁜 결말이라, 넣기 전에 그 사실부터 말한다. */
      if (secWhere === "external"
          && ((secData && secData.keys) || []).some(
               k => k.key === key && k.where === "internal")
          && !await s9dlg({kind: "confirm", cap: "가려짐",
               titleHtml: `<code>${esc(key)}</code> 는 저장소 안에도 있습니다`,
               desc: "같은 이름이면 저장소 안의 값이 쓰입니다 — 지금 밖에 넣는 값은 쓰이지 않습니다. 밖의 값을 쓰려면 안의 것을 먼저 지워야 합니다.",
               ok: "그래도 넣기", cancel: "그만두기"})) return;
      addBtn.disabled = true;
      secSay("저장하는 중…");
      const res = await postJSONRaw("/api/secret/set",
        {key, value: vIn.value, where: secWhere});
      // 성공이든 실패든 값은 화면에서 지운다 — 실패했다고 남겨 두면 그대로 방치된다
      vIn.value = "";
      addBtn.disabled = false;
      if (!res.ok){ secSay("✕ " + res.error, true); return; }
      kIn.value = "";
      const put = WHERE_KO[res.where] || WHERE_KO[secWhere];
      secSay(`${key} 를 ${put}에 넣었습니다. 값은 다시 보이지 않습니다.`
             + (res.shadowed ? " 다만 저장소 안에 같은 이름이 있어 이 값은 쓰이지 않습니다." : ""),
             res.shadowed ? "warn" : "");
      loadSecrets();
    });
    // 엔터로도 넣는다 — 값 칸에서 손을 떼지 않고 끝낼 수 있게
    [kIn, vIn].forEach(el => el.addEventListener("keydown", e => {
      if (e.key === "Enter"){ e.preventDefault(); addBtn.click(); }
    }));
    /* 바깥 폴더 경로 저장 — 값이 아니라 **경로**다. 다른 설정과 같은 길
       (/api/user/config)로 보내고, 저장 뒤에는 목록까지 다시 받는다: 경로가
       살아나면 그 폴더의 키들이 목록에 새로 나타나야 하고, 죽으면 사라져야
       한다. 저장만 하고 목록을 그대로 두면 화면이 옛말을 한다.
       비우고 저장하면 설정이 지워진다 — 서버가 빈 값을 삭제로 받는다. */
    const extBtn = host.querySelector("#sec-ext-save");
    if (extBtn && extIn){
      const saveExt = async () => {
        extBtn.disabled = true;
        extState.className = "secstate";
        extState.textContent = "저장하는 중…";
        const res = await postJSONRaw("/api/user/config",
          {name: u.name, key: "external_secrets_path", value: extIn.value.trim()});
        extBtn.disabled = false;
        if (!res.ok){ extBad(res.error); return; }
        loadSecrets();
      };
      extBtn.addEventListener("click", saveExt);
      extIn.addEventListener("keydown", e => {
        if (e.key === "Enter"){ e.preventDefault(); saveExt(); }
      });
    }
    /* 지우기는 **되돌릴 수 없다** — 값이 어디에도 남지 않으므로 "실행 취소"를 줄
       방법이 없다. 되돌릴 수 없을 때만 확인 창을 쓴다는 규칙이 정확히 이 자리다. */
    secList.addEventListener("click", async e => {
      const b = evEl(e.target)?.closest(".secrm");
      if (!b) return;
      const key = b.dataset.k, w = b.dataset.w;
      // 같은 이름이 양쪽에 있으면 줄은 하나지만 파일은 둘이다 — 무엇이 사라지는지
      // 묻기 전에 말한다.
      const both = b.dataset.both === "1";
      const place = both ? "저장소 안과 밖 양쪽" : (WHERE_KO[w] || "저장소 안");
      // 되살릴 수 없는 창이라 맨 Enter 는 「그만두기」에 닿는다
      // (REQ-20260830-008 — 계정 자리 지우기가 이미 서 있는 그 자리).
      if (!await s9dlg({kind: "confirm", cap: "삭제", safe: true,
            titleHtml: `<code>${esc(key)}</code> 를 지울까요?`,
            desc: `${place}에 있는 파일을 지웁니다. 지운 값은 되살릴 수 없습니다. 이 키를 쓰는 도구는 다음 실행부터 멈춥니다.`,
            ok: "지우기", cancel: "그만두기"})) return;
      secSay("지우는 중…");
      const res = await postJSONRaw("/api/secret/rm",
        both ? {key} : {key, where: w});
      if (!res.ok){ secSay("✕ " + res.error, true); return; }
      const gone = (res.places || []).map(x => WHERE_KO[x] || x).join(" · ");
      secSay(`${key} 를 지웠습니다 — ${gone || place}.`);
      loadSecrets();
    });
  }
  /* ?stdbg=off|on — **스위치를 손 없이 눌러 본다.** 이 자리의 계약은 "화면에서
     끄고 켤 수 있다" 인데, select 에 값이 들어 있는 것만으로는 그걸 못 말한다.
     실제로 바꿔서 서버에 저장되고 Stream 탭이 따라 내려가는지까지 봐야 한다.
     되돌리기를 함께 태운다 — 진단이 사용자의 설정을 바꿔 놓고 끝나면 안 된다. */
  if (smSel && /[?&]stdbg=/.test(location.search) && !window.__stdbgArmed){
    window.__stdbgArmed = 1;
    const want = /[?&]stdbg=off/.test(location.search) ? "off" : "on";
    const was = smSel.value;
    const tabOn = () => { const b = document.querySelector('[data-tab="stream"]');
                          return b ? !b.hidden : null; };
    setTimeout(async () => {
      const t0 = tabOn();
      smSel.value = want;
      smSel.dispatchEvent(new Event("change", {bubbles: true}));
      await new Promise(r => setTimeout(r, 1200));
      const line = [`기록 남기기 ${was} → ${smSel.value}`,
                    `Stream 탭 ${t0 ? "보임" : "숨김"} → ${tabOn() ? "보임" : "숨김"}`,
                    `보관 기간 칸 ${smDays.disabled ? "잠김" : "쓸 수 있음"}`,
                    `알림 "${smMsg.textContent}"`];
      // 되돌린다 — 진단이 사용자의 설정을 바꿔 놓고 끝나지 않는다
      if (was !== want){
        smSel.value = was;
        smSel.dispatchEvent(new Event("change", {bubbles: true}));
        await new Promise(r => setTimeout(r, 1200));
        line.push(`되돌림 → ${smSel.value} · Stream 탭 ${tabOn() ? "보임" : "숨김"}`);
      }
      const box = document.createElement("pre");
      box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
        + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
        + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
      box.textContent = line.join("\n");
      document.body.appendChild(box);
    }, 600);
  }
  /* ?secdbg[=rm] — **손 없이 넣고 지워 본다** (헤드리스 검증용, ?gdbl 과 동형).
     이 자리의 계약은 "값이 화면 어디에도 안 나온다" 인데, 코드를 읽어 그걸
     확인했다고 말할 수는 없다 — 실제로 넣어 보고 판을 뒤져야 한다.
     **S9DBG_ 로 시작하는 키만 건드린다.** 진단이 진짜 비밀을 지울 수 있으면
     그건 진단이 아니라 사고다. 지우는 쪽도 확인 창을 그대로 지난다. */
  if (secList && /[?&]secdbg/.test(location.search) && !window.__secdbgArmed){
    window.__secdbgArmed = 1;
    const K = "S9DBG_TEST", V = "not-a-real-secret-0000";
    const say = lines => {
      const box = document.createElement("pre");
      box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
        + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
        + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
      box.textContent = lines.join("\n");
      document.body.appendChild(box);
    };
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const keys = () => [...host.querySelectorAll(".sectbl .sk")].map(e => e.textContent);
    /* 값이 샜는지는 **이 판을 통째로 뒤져서** 본다 — 입력칸만 보면 목록·툴팁·
       title 로 새는 길을 놓친다. 문서 전체(body.innerHTML)를 뒤지면 이 진단
       코드에 적힌 글자까지 걸려 늘 "샜다"가 되므로, 판(host)으로 좁힌다. */
    const inPanel = () => host.innerHTML.includes(V)
      || [...host.querySelectorAll("input")].some(i => i.value.includes(V));
    const stuck = () => host.querySelector("#sec-val").value !== "";
    setTimeout(async () => {
      const kIn = host.querySelector("#sec-key"), vIn = host.querySelector("#sec-val");
      kIn.value = K; vIn.value = V;
      host.querySelector("#sec-add").click();
      await wait(900);
      const out = [`넣기: ${K}`, `목록 ${keys().join(" · ") || "(없음)"}`,
                   `값이 판에 남았나: ${inPanel() ? "예 ✕" : "아니오"}`,
                   `값 칸이 비었나: ${stuck() ? "아니오 ✕" : "예"}`,
                   `알림 "${(host.querySelector("#sec-msg") || {}).textContent || ""}"`];
      if (/[?&]secdbg=rm/.test(location.search)){
        const b = [...host.querySelectorAll(".secrm")].find(x => x.dataset.k === K);
        out.push(`지우기 버튼: ${b ? "있음" : "없음 ✕"}`);
        if (b){
          b.click();
          await wait(250);
          const yes = dlg.hidden ? null : dlg.querySelector(".dlgyes");
          out.push(`확인 창: ${yes ? "떴다" : "안 떴다 ✕"}`);
          if (yes) yes.click();
          await wait(900);
          out.push(`지운 뒤 목록 ${keys().join(" · ") || "(없음)"}`,
                   `알림 "${(host.querySelector("#sec-msg") || {}).textContent || ""}"`);
        }
      }
      say(out);
    }, 600);
  }
  /* ?secview — 비밀 판은 설정 판 **안쪽 스크롤** 아래에 있다. 헤드리스 캡처는
     스크롤을 못 하므로 아래쪽이 통째로 안 잡힌다 — 검증하려면 보여야 한다. */
  if (secList && /[?&]sec(view|wdbg)/.test(location.search))
    setTimeout(() => {
      const w = host.querySelector("#sec-where");
      if (w) w.scrollIntoView({block: "center"});
    }, 500);
  /* ?secwdbg[=shadow] — **둘 곳 고르기를 손 없이 눌러 본다** (REQ-20260828-017).
     이 자리의 계약은 넷이다: 바깥이 열려 있으면 고를 수 있다 · **고른 곳이 곧
     값이 가는 곳이다** · 못 고를 때는 그 이유가 화면에 있다 · **가려질 값은
     넣기 전에 말한다**. 칸이 그려져 있다는 것만으로는 하나도 못 말한다.
     `=shadow` 는 같은 이름을 안쪽에 먼저 심어 그 경고를 실제로 띄워 본다.
     S9DBG_ 로 시작하는 키만 건드리고, 넣은 것은 지우고 끝낸다. */
  if (secList && /[?&]secwdbg/.test(location.search) && !window.__secwdbgArmed){
    window.__secwdbgArmed = 1;
    const K = "S9DBG_WHERE", V = "not-a-real-secret-1111";
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const cell = w => host.querySelector(`.wopt[data-w="${w}"]`);
    const label = () => (host.querySelector("#sec-add").textContent || "").trim();
    const msg = () => ((host.querySelector("#sec-msg") || {}).textContent || "").trim();
    const rows = () => [...host.querySelectorAll(".sectbl tr")]
      .map(r => r.textContent.replace(/\s+/g, " ").trim());
    const pick = w => { const r = cell(w).querySelector("input");
      r.checked = true; r.dispatchEvent(new Event("change", {bubbles: true})); };
    // 진짜 버튼을 누르고, 확인 창이 뜨면 그 문구를 적어 두고 지나간다
    const add = async () => {
      host.querySelector("#sec-key").value = K;
      host.querySelector("#sec-val").value = V;
      host.querySelector("#sec-add").click();
      await wait(300);
      let asked = "(안 물음)";
      const yes = dlg.hidden ? null : dlg.querySelector(".dlgyes");
      if (yes){
        asked = dlg.textContent.replace(/\s+/g, " ").trim().slice(0, 100);
        yes.click();
      }
      await wait(1100);
      return asked;
    };
    setTimeout(async () => {
      const line = [
        `바깥 칸: ${cell("external").classList.contains("off") ? "잠김" : "열림"}`,
        `이유: ${(host.querySelector("#sec-why").textContent || "(없음)").trim()}`,
        `버튼 "${label()}"`];
      const ex = cell("external").querySelector("input");
      if (!ex.disabled){
        const wantShadow = /[?&]secwdbg=shadow/.test(location.search);
        if (wantShadow){
          pick("internal");
          line.push(`먼저 안쪽에: ${await add() === "(안 물음)" ? "안 물음(맞음)" : "물었다 ✕"}`);
        }
        pick("external");
        await wait(150);
        line.push(`밖을 고른 뒤 버튼 "${label()}"`);
        const asked = await add();
        line.push(`넣기 전에 물었나: ${asked}`,
                  `목록: ${rows().filter(r => r.includes(K)).join(" | ") || "(없음) ✕"}`,
                  `알림 "${msg()}"`,
                  `값이 판에 남았나: ${host.innerHTML.includes(V) ? "예 ✕" : "아니오"}`);
        const b = [...host.querySelectorAll(".secrm")].find(x => x.dataset.k === K);
        if (b){
          b.click();
          await wait(300);
          const yes = dlg.hidden ? null : dlg.querySelector(".dlgyes");
          line.push(`지우기 확인: ${yes
            ? dlg.textContent.replace(/\s+/g, " ").trim().slice(0, 90) : "안 떴다 ✕"}`);
          if (yes) yes.click();
          await wait(1100);
          line.push(`되돌림: ${rows().some(r => r.includes(K)) ? "실패 ✕" : "지웠다"}`,
                    `알림 "${msg()}"`);
        }
        pick("internal");
      }
      const box = document.createElement("pre");
      box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
        + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
        + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
      box.textContent = line.join("\n");
      document.body.appendChild(box);
      const w = host.querySelector("#sec-where");
      if (w) w.scrollIntoView({block: "center"});
    }, 900);
  }
  /* ?extdbg — **바깥 폴더 칸을 손 없이 눌러 본다** (REQ-20260828-017).
     이 자리의 계약은 셋이다: 화면에서 경로를 정할 수 있다 · 없는 폴더는 저장할
     때 만들어진다 · 만들지 못하면 그 사유가 화면에 뜬다. 칸에 글자가 들어 있는
     것만으로는 셋 다 못 말한다 — 실제로 눌러 봐야 한다.
     끝나면 원래 값으로 되돌린다 — 진단이 사용자의 설정을 바꿔 놓고 끝나면 안 된다.
     (만들어 본 폴더는 비어 있고, 지우는 것은 사람 몫이다 — 화면에는 폴더를
     지우는 손잡이가 없고, 진단이 몰래 지우게 만들 이유는 더 없다.) */
  if (extIn && /[?&]extdbg/.test(location.search) && !window.__extdbgArmed){
    window.__extdbgArmed = 1;
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const verdict = () => (extState.textContent || "").trim();
    const save = async v => { extIn.value = v;
      host.querySelector("#sec-ext-save").click(); await wait(1300); };
    setTimeout(async () => {
      const was = extIn.value;
      const line = [`처음 "${was || "(비어 있음)"}" · ${verdict()}`];
      // ① 만들 수 없는 자리 — 사유가 화면에 떠야 한다
      await save("/nope/s9-extdbg/deeper");
      line.push(`못 만드는 경로 → ${verdict()}`,
                `사유가 떴나: ${verdict().startsWith("저장 못 함") ? "예" : "아니오 ✕"}`);
      // ② 만들 수 있는 자리 — 저장만으로 폴더가 생겨 바로 읽히는 상태가 된다
      await save("~/.s9-extdbg-tmp");
      line.push(`없던 폴더 → "${extIn.value}" · ${verdict()}`,
                `저장만으로 만들어졌나: ${verdict().startsWith("읽는 중") ? "예" : "아니오 ✕"}`);
      await save(was);
      line.push(`되돌림 "${extIn.value}" · ${verdict()}`);
      const box = document.createElement("pre");
      box.style.cssText = "position:fixed;left:10px;top:10px;z-index:99;margin:0;"
        + "padding:8px 12px;font:11px/1.6 ui-monospace,monospace;white-space:pre;"
        + "background:var(--panel);border:1px solid var(--text);color:var(--text)";
      box.textContent = line.join("\n");
      document.body.appendChild(box);
    }, 700);
  }
  /* 그 밖의 값 (REQ-20260901-022) — 개인 선호 표와 **같은 부품·같은 손버릇**이다.
     JSON 한 줄을 행으로 편 것이 전부고, 새로 만든 것은 없다. 아는 키가 늘면
     이 목록에서 조용히 빠져 제 자리로 올라간다. */
  const xcSave = host.querySelector("#xc-save");
  if (xcSave) xcSave.addEventListener("click", async () => {
    const sets = [];
    host.querySelectorAll("#xc-table tr[data-xc]").forEach(tr => {
      const k = tr.dataset.xc, val = tr.querySelector(".xc-val").value.trim();
      if (val !== String(cfg[k] ?? "")) sets.push([k, val]);   // 빈 값 = 서버가 삭제
    });
    let ok = true;
    for (const [k, val] of sets)
      ok = (await postJSON("/api/user/config", {name: u.name, key: k, value: val})) && ok;
    if (ok && sets.length) renderSettings();
  });
}


/* ===== 개인 선호 — Settings 레일의 제 판 (REQ-20260915-052-62x6) =====
   종전에는 「내 계정」 판의 아홉째 덩이였다: 세로 2,120px 아래, 창 높이 900px 이면
   세 번째 화면. 「백그라운드 작업」을 같은 판에서 뽑아낸 근거(덩이 여덟·1,400px)를
   같은 자로 재면 여기가 더 깊다. 묶음은 여전히 「나」 안이라 「디스플레이」 다음·
   「백그라운드 작업」 앞이다 — 나는 누구인가 → 어떻게 보이나 → 리드가 나를 어떻게
   대하나 → 내가 없을 때.

   값 칸이 `textarea` 인 것은 취향이 아니라 **데이터 유실의 처방**이다
   (REQ-20260915-054-62x6): 한 줄짜리 `input` 은 브라우저가 값에서 줄바꿈을 지우고,
   지워진 값은 저장값과 달라 보이므로 **열고 저장만 눌러도** 원본이 한 줄로 덮여
   썼다. 이 자리에 `input` 을 되돌리지 마라. */

function prefsOf(u){
  return Object.entries((u && u.config) || {}).filter(([k]) => k.startsWith("pref_"));
}

/* 부제가 상태를 겸한다 (repoNavSub·workerNavSub 의 손버릇) — 레일만 봐도 몇 개인지 보인다. */
function prefNavSub(u){
  const ps = prefsOf(u);
  if (!ps.length) return "아직 저장한 값이 없습니다";
  const first = ps[0][0].slice(5);
  return ps.length > 1 ? `${ps.length}개 — ${first} 외 ${ps.length - 1}개`
                       : `1개 — ${first}`;
}

/* 보낼 것만 고른다 — 화면 없이도 재는 **순수 함수**다 (REQ-20260915-054-62x6).
   줄바꿈이 든 값을 열고 아무것도 고치지 않은 채 저장하면 여기서 **빈 목록**이
   나와야 한다: 하나라도 나오면 그 POST 가 원본을 덮어쓴다. 비교는 양쪽을 같은
   자로 — 앞뒤 공백만 다른 값을 「고쳤다」로 보지 않는다. */
function prefSets(rows, cfg, newKey, newVal){
  const sets = [];
  for (const r of rows){
    const val = r.removed ? "" : String(r.value ?? "").trim();
    if (val !== String(cfg[r.key] ?? "").trim()) sets.push([r.key, val]);
  }
  const nk = String(newKey || "").trim();
  if (nk) sets.push(["pref_" + nk.replace(/^pref_/, ""), String(newVal || "").trim()]);
  return sets;
}

function showPrefForm(u, host){
  if (!host) return;
  const cfg = u.config || {};
  const prefs = prefsOf(u);
  const row = ([k, v]) => `<tr data-pref="${esc(k)}">
      <td>${esc(k.slice(5))}</td>
      <td><textarea class="uf pf-val" rows="2" spellcheck="false"
            aria-label="${esc(k.slice(5))} — 선호 내용">${esc(String(v))}</textarea></td>
      <td class="pfrm"><button type="button" class="em-rm pf-rm">지우기</button></td></tr>`;
  host.innerHTML = `<h1 style="margin:0 0 4px">개인 선호</h1>
    <div class="path">말투나 보고 형식처럼 지켜 주었으면 하는 것을 적어 두는 자리입니다. 대화를 시작할 때마다 자동으로 전달되며, 이 계정으로 어디서 접속해도 따라옵니다.</div>
    <div class="path">이 저장소를 보는 사람도 함께 읽을 수 있습니다 — 비밀번호나 키는 「내 계정」의 시크릿에 넣습니다.</div>
    ${prefs.length ? "" : `<p class="empty">아직 저장한 개인 선호가 없습니다.<br>
      말투나 답변 형식처럼 대화마다 지켜야 할 것을 적어 보세요 — 예: 주제 <b>말투</b>, 내용 <b>짧게 답하고 칭찬은 빼 주세요</b>.</p>`}
    <table class="metatbl pftbl" id="pf-table">
      ${prefs.map(row).join("")}
      <tr id="pf-newrow">
        <td><input class="uf" id="pf-key" aria-label="새 개인 선호 주제"
              placeholder="주제 (예: 말투)"></td>
        <td><textarea class="uf pf-val" id="pf-new" rows="2" spellcheck="false"
              aria-label="새 개인 선호 내용" placeholder="내용 (예: 짧게 답하고 칭찬은 빼 주세요)"></textarea></td>
        <td class="pfrm"></td></tr>
    </table>
    <div class="secmsg" id="pf-gone"></div>
    <div class="acts"><button id="pf-save">저장하기</button></div>
    <div class="secmsg" id="pf-msg" aria-live="polite"></div>`;

  /* 값이 잘리면 「온전히 읽는다」가 거짓말이 된다 — 칸을 내용에 맞춰 편다
     (실측: 세 줄짜리 값이 rows=2 상자에서 셋째 줄이 반쯤 잘렸다). 상한 240px 을
     넘으면 그 안에서 스크롤한다. 8의 배수만 쓴다(비정수 배율에서 위아래가 다르게
     반올림되지 않게). */
  const fit = ta => {
    ta.style.height = "auto";
    ta.style.height = Math.min(Math.max(ta.scrollHeight, 48), 240) + "px";
  };
  host.querySelectorAll(".pf-val").forEach(ta => {
    fit(ta);
    ta.addEventListener("input", () => fit(ta));
  });

  const goneLine = () => {
    const n = host.querySelectorAll("#pf-table tr.pfgone").length;
    host.querySelector("#pf-gone").textContent =
      n ? "지운 행은 저장을 눌러야 실제로 사라집니다." : "";
  };
  /* 지우기는 **저장 전까지 되돌릴 수 있다** — 확인 창 대신 되돌리기(s9-design 4절).
     누른 글자가 텍스트 노드로 잡히는 자리라 evEl 로 한 번 올라간다. */
  host.querySelector("#pf-table").addEventListener("click", e => {
    const el = evEl(e.target);
    if (!el || !el.classList.contains("pf-rm")) return;
    const tr = el.closest("tr[data-pref]");
    if (!tr) return;
    const gone = tr.classList.toggle("pfgone");
    tr.querySelector(".pf-val").disabled = gone;
    el.textContent = gone ? "되돌리기" : "지우기";
    goneLine();
  });

  host.querySelector("#pf-save").addEventListener("click", async () => {
    const msg = host.querySelector("#pf-msg");
    const rows = [...host.querySelectorAll("#pf-table tr[data-pref]")].map(tr => ({
      key: tr.dataset.pref,
      value: tr.querySelector(".pf-val").value,
      removed: tr.classList.contains("pfgone")}));
    const sets = prefSets(rows, cfg, host.querySelector("#pf-key").value,
                          host.querySelector("#pf-new").value);
    msg.className = "secmsg";
    if (!sets.length){ msg.textContent = "바뀐 것이 없습니다."; return; }
    msg.textContent = "저장하는 중…";
    for (const [k, val] of sets){
      const res = await postJSONRaw("/api/user/config", {name: u.name, key: k, value: val});
      if (!res.ok){
        msg.className = "secmsg bad";
        msg.textContent = "저장하지 못했습니다 — " + res.error;
        return;
      }
    }
    const said = "저장했습니다.";
    await renderSettings();   // 레일 부제(개수)까지 같이 고쳐 그린다
    const after = document.querySelector("#pf-msg");
    if (after) after.textContent = said;
  });
}
