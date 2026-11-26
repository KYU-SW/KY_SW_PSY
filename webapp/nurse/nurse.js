// OpticCall 간호사실 앱: 침상 상태 · 호출 알람 · 확인 보내기 · 오늘 기록
import { cleanKey, createLink, linkSettings, saveLinkSettings } from "../core/link.js?v=20261126l";

const $ = (id) => document.getElementById(id);
const KEY = "opticcall.nurse.v1";
const OFFLINE_SEC = 15;        // 환자 앱 상태가 이만큼 안 오면 '연결 끊김'

// ── 저장 (이 기기에만) ─────────────────────────
function load() {
  try {
    return { name: "", soundOn: true, log: [], ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { name: "", soundOn: true, log: [] };
  }
}
const data = load();
function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    /* 저장이 막힌 브라우저 */
  }
}
function addLog(kind, bed, text) {
  data.log.unshift({ at: Date.now(), kind, bed, text });
  data.log = data.log.slice(0, 300);
  save();
}

// ── 알람 소리 · 진동 ──────────────────────────
let audio = null;
let alarmTimer = null;
function beep(freq, start, dur) {
  const o = audio.createOscillator();
  const g = audio.createGain();
  o.type = "sine";
  o.frequency.value = freq;
  g.gain.setValueAtTime(0.0001, audio.currentTime + start);
  g.gain.exponentialRampToValueAtTime(0.35, audio.currentTime + start + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + dur);
  o.connect(g).connect(audio.destination);
  o.start(audio.currentTime + start);
  o.stop(audio.currentTime + start + dur + 0.05);
}
// 확인 안 된 호출이 하나라도 있으면 계속 울린다. 재호출이 있으면 더 높고 빠른 소리.
function ringOnce(urgent) {
  if (audio && data.soundOn) {
    if (urgent) {
      [0, 0.16, 0.32, 0.48, 0.64].forEach((t, i) => beep(i % 2 ? 1175 : 1480, t, 0.12));
    } else {
      beep(880, 0, 0.22);
      beep(660, 0.28, 0.22);
      beep(880, 0.56, 0.22);
    }
  }
  if (navigator.vibrate) navigator.vibrate(urgent ? [200, 80, 200, 80, 200, 80, 200] : [300, 150, 300]);
}
let ringing = null;            // null | "normal" | "urgent"
function setRinging(mode) {
  if (mode === ringing) return;
  clearInterval(alarmTimer);
  alarmTimer = null;
  ringing = mode;
  if (!mode) {
    if (navigator.vibrate) navigator.vibrate(0);
    return;
  }
  ringOnce(mode === "urgent");
  alarmTimer = setInterval(() => ringOnce(mode === "urgent"), mode === "urgent" ? 1100 : 1600);
}

// ── 침상 상태 ─────────────────────────────────
// bed 이름 -> { bed, patient, lastSeen, state: idle|calling|acked, call: {id, at, count}, who, ackSec, ackAt }
const beds = new Map();
const silenced = new Set();    // '알람만 끄기'를 누른 호출 id

function bedOf(name) {
  if (!beds.has(name)) beds.set(name, { bed: name, patient: "", lastSeen: 0, state: "idle" });
  return beds.get(name);
}

// ── 등록된 침상 (침상 관리) ─────────────────────
let roster = {};                          // { 침상키: { bed, patient, at } }
const regOf = (bed) => roster[cleanKey(bed)];
// 환자 이름은 간호사가 등록한 것을 우선한다 (환자 휴대폰에서 보낸 이름보다)
const patientOf = (b) => (regOf(b.bed) ? regOf(b.bed).patient : b.patient);
function onRoster(r) {
  roster = r || {};
  for (const e of Object.values(roster)) if (e?.bed) bedOf(e.bed);
  // 지운 침상: 호출 중이 아니고 연결도 끊긴 카드는 치운다
  for (const [name, b] of beds) {
    if (!regOf(name) && b.state === "idle" && Date.now() - b.lastSeen > OFFLINE_SEC * 1000) beds.delete(name);
  }
  renderRoster();
  render();
}

let link = createLink();
let linkState = link.state;

function wire() {
  link.onState((s) => {
    linkState = s;
    render();
  });
  link.onStatus(onStatus);
  link.onCall(onCall);
  link.onAck(onAck);
}

function onStatus(m) {
  const b = bedOf(m.bed || "침상");
  b.patient = m.patient || b.patient;
  b.lastSeen = Math.min(Date.now(), m.at || Date.now());   // 보낸 시각 기준 (예전 상태가 '연결됨'으로 보이지 않게)
  b.patientState = m.state;
  render();
}

function onCall(m) {
  const b = bedOf(m.bed || "침상");
  b.patient = m.patient || b.patient;
  b.lastSeen = Date.now();
  // 아직 확인 안 된 상태에서 또 부르면(재호출) 처음 부른 시각부터 기다린 시간을 센다
  const at = m.at || Date.now();
  b.firstAt = b.state === "calling" && b.firstAt ? Math.min(b.firstAt, at) : at;
  b.state = "calling";
  b.call = { id: m.id, at, count: m.count || 1 };
  const who = patientOf(b);
  addLog("call", b.bed, `${regOf(b.bed) ? "" : "미등록 침상 · "}${who ? who + " · " : ""}${b.call.count > 1 ? `재호출 (${b.call.count}번째)` : "호출"}`);
  notify(b);
  render();
}

// 다른 의료진 기기에서 먼저 확인한 경우도 반영한다
function onAck(m) {
  for (const b of beds.values()) {
    if (b.state === "calling" && b.call?.id === m.id) markAcked(b, m.who, m.at, false);
  }
}
wire();

function markAcked(b, who, at = Date.now(), mine = true) {
  b.state = "acked";
  b.who = who;
  b.ackAt = at;
  b.ackSec = Math.max(0, Math.round((at - (b.firstAt || b.call.at)) / 1000));
  addLog("ack", b.bed, `${who || "간호사"} 확인 · ${b.ackSec}초`);
  if (mine) link.sendAck(b.call.id, who);
  render();
}

function notify(b) {
  // 앱이 뒤에 있을 때를 위한 알림 (허용한 경우만)
  try {
    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      new Notification(`🚨 ${b.bed} 호출`, { body: patientOf(b) ? `${patientOf(b)} 님이 부르고 있어요` : "환자가 부르고 있어요", tag: b.call.id, requireInteraction: true });
    }
  } catch {
    /* 알림을 지원하지 않는 브라우저 */
  }
}

// ── 알람 화면: 대기 중인 호출 전체 ─────────────
// 순서: 재호출(여러 번 부름)이 먼저, 같은 경우 많이 부른 순, 그다음 오래 기다린 순
function sortPending(list) {
  return [...list].sort(
    (a, b) => (b.call.count > 1) - (a.call.count > 1) || b.call.count - a.call.count || (a.firstAt || a.call.at) - (b.firstAt || b.call.at)
  );
}
const pending = () => sortPending([...beds.values()].filter((b) => b.state === "calling"));
const waitText = (b) => {
  const sec = Math.max(0, Math.round((Date.now() - (b.firstAt || b.call.at)) / 1000));
  return sec < 5 ? "방금 호출" : `${elapsed(sec)} 기다리는 중`;
};

function renderAlarm() {
  const list = pending();
  const loud = list.filter((b) => !silenced.has(b.call.id));
  // 끄지 않은 호출이 있으면 알람 화면과 소리를 유지한다
  if (!loud.length || $("main").hidden) {
    $("alarm").hidden = true;
    setRinging(null);
    return;
  }
  setRinging(loud.some((b) => b.call.count > 1) ? "urgent" : "normal");
  const top = list[0];
  const alarm = $("alarm");
  alarm.hidden = false;
  alarm.classList.toggle("urgent", top.call.count > 1);
  $("alarmCount").textContent = list.length > 1 ? `호출 ${list.length}건 대기 중` : "간호 호출";
  $("alarmKind").textContent = top.call.count > 1 ? `재호출 · ${top.call.count}번째` : list.length > 1 ? "가장 오래 기다린 호출" : "새 호출";
  $("alarmBed").textContent = top.bed;
  const topWho = patientOf(top);
  $("alarmWho").textContent = `${topWho ? `${topWho} 님이 부르고 있어요` : "환자가 부르고 있어요"}${regOf(top.bed) ? "" : " · 미등록 침상"}`;
  $("alarmTime").textContent = waitText(top);
  $("btnAck").dataset.bed = top.bed;

  const ul = $("alarmList");
  ul.innerHTML = "";
  for (const b of list.slice(1)) {
    const li = document.createElement("li");
    li.className = b.call.count > 1 ? "recall" : "";
    li.innerHTML = '<div class="q-main"><b></b><span></span></div><div class="q-sub"></div><button class="btn q-ack">확인</button>';
    li.querySelector("b").textContent = b.bed;
    const who = patientOf(b);
    li.querySelector(".q-main span").textContent = b.call.count > 1 ? `재호출 ${b.call.count}번째` : who || "";
    li.querySelector(".q-sub").textContent = `${regOf(b.bed) ? "" : "미등록 침상 · "}${who && b.call.count > 1 ? who + " · " : ""}${waitText(b)}`;
    li.querySelector("button").addEventListener("click", () => markAcked(b, data.name));
    ul.appendChild(li);
  }
  ul.hidden = list.length < 2;
}
$("btnAck").addEventListener("click", () => {
  const b = beds.get($("btnAck").dataset.bed);
  if (b && b.state === "calling") markAcked(b, data.name);
});
$("btnLater").addEventListener("click", () => {
  for (const b of pending()) silenced.add(b.call.id);   // 지금 울리는 호출만 끈다 (새 호출이 오면 다시 울림)
  renderAlarm();
});

// ── 화면 ─────────────────────────────────────
function elapsed(sec) {
  if (sec < 60) return `${sec}초`;
  const m = Math.floor(sec / 60);
  return m < 60 ? `${m}분 ${sec % 60}초` : `${Math.floor(m / 60)}시간 ${m % 60}분`;
}
const hhmm = (ms) => {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const PATIENT_STATE = { IDLE: "대기 중", ASKING: "질문 듣는 중", WAITING: "대답 기다리는 중", COOLDOWN: "안내 중" };

function render() {
  const now = Date.now();
  // 호출 중인 침상은 알람 화면과 같은 순서(재호출 → 오래 기다린 순), 나머지는 이름순
  const calling = sortPending([...beds.values()].filter((b) => b.state === "calling"));
  // 등록 안 된(지운) 침상은 카드로 보이지 않는다. 다만 호출했으면 응급일 수 있으니 '미등록'으로 보여 준다
  const others = [...beds.values()].filter((b) => b.state !== "calling" && (regOf(b.bed) || b.state === "acked"));
  const list = [...calling, ...others.sort((a, b) => a.bed.localeCompare(b.bed, "ko", { numeric: true }))];
  const wrap = $("beds");
  wrap.querySelectorAll(".bed").forEach((el) => el.remove());
  $("bedsEmpty").hidden = list.length > 0;
  let online = 0;
  for (const b of list) {
    const alive = now - b.lastSeen < OFFLINE_SEC * 1000;
    online += alive;
    const el = document.createElement("article");
    el.className = `bed ${b.state === "calling" ? "calling" : b.state === "acked" ? "acked" : alive ? "idle" : "offline"}`;
    const head = document.createElement("div");
    head.className = "bed-head";
    head.innerHTML = '<span class="bed-name"></span><span class="bed-patient"></span>';
    head.children[0].textContent = b.bed;
    const reg = regOf(b.bed);
    head.children[1].textContent = reg ? reg.patient || "빈 침상" : b.patient;
    if (!reg) {
      const tag = document.createElement("span");
      tag.className = "tag-unreg";
      tag.textContent = "미등록";
      head.children[0].appendChild(tag);
    }
    const state = document.createElement("div");
    state.className = "bed-state";
    const meta = document.createElement("div");
    meta.className = "bed-meta";
    if (b.state === "calling") {
      state.textContent = `🚨 호출 중${b.call.count > 1 ? ` (${b.call.count}번째)` : ""}`;
      meta.textContent = `${hhmm(b.firstAt || b.call.at)} · ${elapsed(Math.round((now - (b.firstAt || b.call.at)) / 1000))} 기다리는 중`;
    } else if (b.state === "acked") {
      state.textContent = `✅ ${b.who || "간호사"} 확인`;
      meta.textContent = `${hhmm(b.firstAt || b.call.at)} 호출 · ${b.ackSec}초 만에 확인`;
    } else {
      const empty = reg && !reg.patient;
      state.textContent = alive ? "대기 중" : empty ? "빈 침상" : b.lastSeen ? "연결 끊김" : "휴대폰 연결 전";
      meta.textContent = alive
        ? `환자 앱: ${PATIENT_STATE[b.patientState] || "켜짐"}`
        : b.lastSeen ? `마지막 연결 ${hhmm(b.lastSeen)}` : empty ? "" : "환자 휴대폰 설정에서 이 침상을 고르면 연결돼요";
    }
    el.append(head, state, meta);
    if (b.state === "calling") {
      const btn = document.createElement("button");
      btn.className = "btn go";
      btn.textContent = "확인 · 지금 갈게요";
      btn.addEventListener("click", () => markAcked(b, data.name));
      el.append(btn);
    } else if (b.state === "acked") {
      const btn = document.createElement("button");
      btn.className = "btn small";
      btn.textContent = "처리 완료";
      btn.addEventListener("click", () => {
        b.state = "idle";
        render();
      });
      el.append(btn);
    }
    wrap.appendChild(el);
  }

  const conn = $("conn");
  const net = link.kind === "firebase" ? (linkState.online ? "" : linkState.error ? " · 서버 연결 안 됨" : " · 서버 연결 중") : " · 이 브라우저 안에서만";
  conn.textContent = `병동 ${link.ward} · ${online ? `침상 ${online}개 연결됨` : "침상 기다리는 중"}${net}`;
  conn.classList.toggle("on", online > 0 && (link.kind !== "firebase" || linkState.online));

  const today = new Date().toDateString();
  const todays = data.log.filter((l) => new Date(l.at).toDateString() === today);
  const active = list.filter((b) => b.state === "calling").length;
  $("stActive").textContent = active;
  $("stActive").classList.toggle("hot", active > 0);
  $("stToday").textContent = todays.filter((l) => l.kind === "call").length;
  const secs = todays.filter((l) => l.kind === "ack").map((l) => parseInt(l.text.match(/(\d+)초/)?.[1] || "", 10)).filter((n) => !isNaN(n));
  $("stAvg").textContent = secs.length ? `${Math.round(secs.reduce((a, b) => a + b, 0) / secs.length)}초` : "-";

  const ul = $("log");
  ul.innerHTML = "";
  for (const l of todays.slice(0, 30)) {
    const li = document.createElement("li");
    li.innerHTML = '<span class="t"></span><div><span></span><span class="muted"></span></div>';
    li.children[0].textContent = hhmm(l.at);
    const [what, detail] = li.children[1].children;
    what.textContent = `${{ call: "🚨", ack: "✅" }[l.kind] || "📋"} ${l.bed}`;
    what.className = `ev-${l.kind}`;
    detail.textContent = l.text;
    ul.appendChild(li);
  }
  if (!todays.length) ul.innerHTML = '<li class="muted">아직 기록이 없어요</li>';
  $("me").textContent = data.name || "이름 없음";
  $("btnSound").textContent = data.soundOn ? "🔔 소리 켬" : "🔕 소리 끔";
  renderAlarm();
}

// ── 침상 관리: 등록 · 환자 바꾸기(입원) · 퇴원 · 삭제 ──
let editingKey = null;                     // 환자 이름을 고치는 중인 침상
function rosterMsg(text, bad) {
  const el = $("rosterMsg");
  el.textContent = text;
  el.classList.toggle("bad", !!bad);
}
// 병동 안에서 겹치지 않는 4자리 연결 코드
function newCode() {
  const used = new Set(Object.values(roster).map((e) => e?.code));
  let code;
  do code = String(Math.floor(1000 + Math.random() * 9000));
  while (used.has(code));
  return code;
}
async function saveRoster(bed, patient, logText, code = regOf(bed)?.code || newCode()) {
  const ok = await link.setRoster(bed, patient, code);
  if (!ok) return rosterMsg("저장하지 못했어요. 인터넷 연결을 확인해 주세요", true);
  addLog("roster", bed, logText);
  rosterMsg(`${bed}: ${logText}`);
  render();
}
function renderRoster() {
  const ul = $("rosterList");
  ul.innerHTML = "";
  const list = Object.values(roster).filter((e) => e?.bed).sort((a, b) => a.bed.localeCompare(b.bed, "ko", { numeric: true }));
  if (!list.length) ul.innerHTML = '<li class="muted">아직 등록한 침상이 없어요</li>';
  for (const e of list) {
    const key = cleanKey(e.bed);
    const li = document.createElement("li");
    const name = document.createElement("b");
    name.textContent = e.bed;
    li.appendChild(name);
    if (editingKey === key) {
      const input = document.createElement("input");
      input.value = e.patient;
      input.maxLength = 20;
      input.placeholder = "새 환자 이름";
      const ok = button("저장", "primary", () => {
        const p = input.value.trim();
        editingKey = null;
        if (p === e.patient) return renderRoster();
        saveRoster(e.bed, p, p ? `환자 ${p} 등록${e.patient ? ` (이전: ${e.patient})` : ""}` : "빈 침상으로 바꿈");
      });
      const cancel = button("취소", "ghost", () => {
        editingKey = null;
        renderRoster();
      });
      input.addEventListener("keydown", (ev) => ev.key === "Enter" && ok.click());
      li.append(input, ok, cancel);
      ul.appendChild(li);
      setTimeout(() => input.focus(), 0);
      continue;
    }
    const who = document.createElement("span");
    who.className = e.patient ? "" : "muted";
    who.textContent = e.patient || "빈 침상";
    const code = document.createElement("span");
    code.className = `code${e.code ? "" : " none"}`;
    code.title = "환자 휴대폰 설정에 넣는 연결 코드";
    code.textContent = e.code ? `코드 ${e.code}` : "코드 없음";
    const acts = document.createElement("span");
    acts.className = "acts";
    acts.append(
      button(e.patient ? "환자 바꾸기" : "입원 등록", "", () => {
        editingKey = key;
        renderRoster();
      })
    );
    if (e.patient) {
      acts.append(
        button("퇴원", "ghost", () => {
          if (confirm(`${e.bed} ${e.patient} 님을 퇴원 처리할까요?
침상은 남고 빈 침상이 돼요.`)) saveRoster(e.bed, "", `${e.patient} 퇴원`);
        })
      );
    }
    acts.append(
      button(e.code ? "새 코드" : "코드 만들기", "ghost", () => {
        if (e.code && !confirm(`${e.bed}의 연결 코드를 새로 만들까요?\n지금 연결된 환자 휴대폰은 새 코드를 넣어야 다시 연결돼요.`)) return;
        saveRoster(e.bed, e.patient, "연결 코드 새로 만듦", newCode());
      }),
      button("삭제", "ghost danger", async () => {
        if (beds.get(e.bed)?.state === "calling") return rosterMsg("호출 중인 침상은 지울 수 없어요. 먼저 확인해 주세요", true);
        if (!confirm(`${e.bed} 침상을 목록에서 지울까요?`)) return;
        const ok = await link.removeRoster(e.bed);
        if (!ok) return rosterMsg("지우지 못했어요. 인터넷 연결을 확인해 주세요", true);
        addLog("roster", e.bed, "침상 삭제");
        rosterMsg(`${e.bed}: 침상 삭제`);
        render();
      })
    );
    li.append(who, code, acts);
    ul.appendChild(li);
  }
}
function button(text, cls, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `btn small ${cls}`.trim();
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}
$("rosterForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const bed = $("rBed").value.trim();
  const patient = $("rPatient").value.trim();
  if (!bed) return rosterMsg("침상 이름을 넣어 주세요", true);
  const old = regOf(bed);
  if (old && !confirm(`${bed}은(는) 이미 등록돼 있어요 (${old.patient || "빈 침상"}).
${patient || "빈 침상"}(으)로 바꿀까요?`)) return;
  $("rBed").value = "";
  $("rPatient").value = "";
  saveRoster(bed, patient, patient ? `환자 ${patient} 등록` : "빈 침상 등록");
});

// ── 시작 ─────────────────────────────────────
let wakeLock = null;
let watching = false;
async function begin() {
  data.name = $("nurseName").value.trim() || data.name || "간호사";
  save();
  const ward = $("ward").value.trim() || "ward1";
  if (ward !== link.ward) {
    saveLinkSettings({ ward });
    link.close();
    link = createLink();
    beds.clear();
    wire();
    watching = false;
  }
  if (!watching) {
    roster = {};
    link.watchAll();
    link.watchRoster(onRoster);
    watching = true;
  }
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    await audio.resume();
  } catch {
    audio = null;
  }
  try {
    if ("Notification" in window && Notification.permission === "default") await Notification.requestPermission();
  } catch {
    /* 알림 권한을 물을 수 없는 환경 */
  }
  try {
    if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen");
  } catch {
    /* 화면 꺼짐 방지 미지원 */
  }
  $("start").hidden = true;
  $("main").hidden = false;
  render();
}
$("nurseName").value = data.name;
$("ward").value = linkSettings().ward;
$("btnBegin").addEventListener("click", begin);
$("btnSound").addEventListener("click", () => {
  data.soundOn = !data.soundOn;
  save();
  render();
});
$("btnRename").addEventListener("click", () => {
  $("main").hidden = true;
  $("start").hidden = false;
});
document.addEventListener("visibilitychange", async () => {
  if (!document.hidden && $("start").hidden && "wakeLock" in navigator) {
    try {
      wakeLock = await navigator.wakeLock.request("screen");
    } catch {
      /* 무시 */
    }
  }
});
setInterval(() => {
  if (!$("main").hidden) render();
  else renderAlarm();
}, 1000);
