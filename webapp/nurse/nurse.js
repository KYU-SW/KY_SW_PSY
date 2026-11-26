// OpticCall 간호사실 앱: 침상 상태 · 호출 알람 · 확인 보내기 · 오늘 기록
import { createLink } from "../core/link.js";

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
function startAlarm() {
  stopAlarm();
  const once = () => {
    if (audio && data.soundOn) {
      beep(880, 0, 0.22);
      beep(660, 0.28, 0.22);
      beep(880, 0.56, 0.22);
    }
    if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
  };
  once();
  alarmTimer = setInterval(once, 1600);
}
function stopAlarm() {
  clearInterval(alarmTimer);
  alarmTimer = null;
  if (navigator.vibrate) navigator.vibrate(0);
}

// ── 침상 상태 ─────────────────────────────────
// bed 이름 -> { bed, patient, lastSeen, state: idle|calling|acked, call: {id, at, count}, who, ackSec, ackAt }
const beds = new Map();
let alarmBed = null;           // 알람 화면에 띄운 침상
const silenced = new Set();    // '알람만 끄기'를 누른 호출 id

function bedOf(name) {
  if (!beds.has(name)) beds.set(name, { bed: name, patient: "", lastSeen: 0, state: "idle" });
  return beds.get(name);
}

const link = createLink();

link.onStatus((m) => {
  const b = bedOf(m.bed || "침상");
  b.patient = m.patient || b.patient;
  b.lastSeen = Date.now();
  b.patientState = m.state;
  render();
});

link.onCall((m) => {
  const b = bedOf(m.bed || "침상");
  b.patient = m.patient || b.patient;
  b.lastSeen = Date.now();
  b.state = "calling";
  b.call = { id: m.id, at: m.at || Date.now(), count: m.count || 1 };
  addLog("call", b.bed, `${b.patient ? b.patient + " · " : ""}${b.call.count > 1 ? `재호출 (${b.call.count}번째)` : "호출"}`);
  notify(b);
  showAlarm(b);
  render();
});

// 다른 의료진 기기에서 먼저 확인한 경우도 반영한다
link.onAck((m) => {
  for (const b of beds.values()) {
    if (b.state === "calling" && b.call?.id === m.id) markAcked(b, m.who, m.at, false);
  }
});

function markAcked(b, who, at = Date.now(), mine = true) {
  b.state = "acked";
  b.who = who;
  b.ackAt = at;
  b.ackSec = Math.max(0, Math.round((at - b.call.at) / 1000));
  addLog("ack", b.bed, `${who || "간호사"} 확인 · ${b.ackSec}초`);
  if (mine) link.sendAck(b.call.id, who);
  if (alarmBed === b.bed) nextAlarm();
  render();
}

function notify(b) {
  // 앱이 뒤에 있을 때를 위한 알림 (허용한 경우만)
  try {
    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      new Notification(`🚨 ${b.bed} 호출`, { body: b.patient ? `${b.patient} 님이 부르고 있어요` : "환자가 부르고 있어요", tag: b.call.id, requireInteraction: true });
    }
  } catch {
    /* 알림을 지원하지 않는 브라우저 */
  }
}

// ── 알람 화면 ─────────────────────────────────
function showAlarm(b) {
  alarmBed = b.bed;
  $("alarmKind").textContent = b.call.count > 1 ? `재호출 · ${b.call.count}번째` : "간호 호출";
  $("alarmBed").textContent = b.bed;
  $("alarmWho").textContent = b.patient ? `${b.patient} 님이 부르고 있어요` : "환자가 부르고 있어요";
  $("alarm").hidden = false;
  startAlarm();
  tickAlarm();
}
function tickAlarm() {
  const b = beds.get(alarmBed);
  if (!b || $("alarm").hidden) return;
  const sec = Math.round((Date.now() - b.call.at) / 1000);
  $("alarmTime").textContent = sec < 5 ? "방금" : `${elapsed(sec)} 전 호출`;
}
function nextAlarm() {
  $("alarm").hidden = true;
  stopAlarm();
  alarmBed = null;
  const waiting = [...beds.values()].find((x) => x.state === "calling" && !silenced.has(x.call.id));
  if (waiting) showAlarm(waiting);
}
$("btnAck").addEventListener("click", () => {
  const b = beds.get(alarmBed);
  if (b && b.state === "calling") markAcked(b, data.name);
  else nextAlarm();
});
$("btnLater").addEventListener("click", () => {
  const b = beds.get(alarmBed);
  if (b?.call) silenced.add(b.call.id);
  nextAlarm();
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
  const list = [...beds.values()].sort((a, b) => (b.state === "calling") - (a.state === "calling") || a.bed.localeCompare(b.bed));
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
    head.children[1].textContent = b.patient;
    const state = document.createElement("div");
    state.className = "bed-state";
    const meta = document.createElement("div");
    meta.className = "bed-meta";
    if (b.state === "calling") {
      state.textContent = `🚨 호출 중${b.call.count > 1 ? ` (${b.call.count}번째)` : ""}`;
      meta.textContent = `${hhmm(b.call.at)} · ${elapsed(Math.round((now - b.call.at) / 1000))} 지남`;
    } else if (b.state === "acked") {
      state.textContent = `✅ ${b.who || "간호사"} 확인`;
      meta.textContent = `${hhmm(b.call.at)} 호출 · ${b.ackSec}초 만에 확인`;
    } else {
      state.textContent = alive ? "대기 중" : "연결 끊김";
      meta.textContent = alive ? `환자 앱: ${PATIENT_STATE[b.patientState] || "켜짐"}` : b.lastSeen ? `마지막 연결 ${hhmm(b.lastSeen)}` : "";
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
  conn.textContent = link.kind === "none" ? "연결 안 됨" : online ? `침상 ${online}개 연결됨` : "침상 연결 기다리는 중";
  conn.classList.toggle("on", online > 0);

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
    what.textContent = l.kind === "call" ? `🚨 ${l.bed}` : `✅ ${l.bed}`;
    what.className = l.kind === "call" ? "ev-call" : "ev-ack";
    detail.textContent = l.text;
    ul.appendChild(li);
  }
  if (!todays.length) ul.innerHTML = '<li class="muted">아직 기록이 없어요</li>';
  $("me").textContent = data.name || "이름 없음";
  $("btnSound").textContent = data.soundOn ? "🔔 소리 켬" : "🔕 소리 끔";
}

// ── 시작 ─────────────────────────────────────
let wakeLock = null;
async function begin() {
  data.name = $("nurseName").value.trim() || data.name || "간호사";
  save();
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
  tickAlarm();
}, 1000);
