// OpticCall 환자 앱: 홈 · 호출 대기(시선 추적) · 눈 맞추기 · 설정
import { Camera } from "../core/camera.js";
import { CallController, COOLDOWN_APP, buildPhrases, secondsText, IDLE, ASKING, WAITING, COOLDOWN } from "../core/controller.js";
import { FeatureExtractor, buildCalibration, rawFeatures } from "../core/features.js";
import { cleanKey, createLink, deviceId, linkSettings, saveLinkSettings } from "../core/link.js?v=20261126l";
import { store } from "../core/store.js?v=20261126l";
import { Voice } from "../core/voice.js";

const $ = (id) => document.getElementById(id);
const clock = () => performance.now() / 1000;
const RING = 326.7;
const EYE_OUTLINE = {
  right: [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
  left: [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466],
};
const EVENT_TEXT = { CALL: "호출", CANCEL: "취소", TIMEOUT: "응답 없음", ACK: "간호사 확인", ASK: "질문" };

// ── 화면 전환 ─────────────────────────────────
function show(id) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === id));
  document.querySelector('meta[name="theme-color"]').content = id === "home" || id === "settings" || id === "pair" ? "#f3f8fa" : "#0f3b4c";
}

let toastTimer = null;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 2600);
}

function timeText(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// ── 홈 ───────────────────────────────────────
// ── 간호사 앱에 등록된 침상 ───────────────────
let roster = null;                 // null: 아직 못 받음 (인터넷 안 됨 등)
let bedStates = {};                // 침상별 최근 상태 (다른 휴대폰이 쓰는지 확인)
const myReg = () => (roster && store.data.bed ? roster[cleanKey(store.data.bed)] : undefined);
// 연결 코드가 지금도 맞는지 (간호사가 [새 코드]를 누르면 끊긴다)
const paired = () => !!(myReg() && myReg().code && myReg().code === store.data.pairCode);
// 지금 환자 이름: 간호사가 등록한 이름 (빈 침상이면 "")
const currentPatient = () => (paired() ? myReg().patient : store.data.current);
// 다른 휴대폰이 최근(15초) 이 침상을 쓰고 있는지
function usedByOther(bed) {
  const s = bedStates[cleanKey(bed)];
  return !!(s && s.device && s.device !== deviceId() && Date.now() - (s.at || 0) < 15000);
}
// 침상 등록 문제 (없으면 "")
function bedProblem() {
  if (!store.data.bed) return "침상 연결 안 됨 · 연결 코드를 넣어 주세요";
  if (roster && !myReg()) return "간호사 앱에서 지워진 침상";
  if (roster && !paired()) return "연결 코드가 바뀌었어요 · 새 코드를 넣어 주세요";
  if (myReg() && !myReg().patient) return "빈 침상 (환자 없음)";
  if (usedByOther(store.data.bed)) return "다른 휴대폰도 이 침상 사용 중";
  return "";
}
function onRoster(r) {
  roster = r || {};
  // 간호사 앱에서 이 침상을 지웠으면 연결을 끊고 코드 화면으로 (Firebase 목록 기준일 때만)
  if (store.data.pairCode && link.kind === "firebase" && !myReg()) {
    store.data.bed = "";
    store.data.pairCode = "";
    store.save();
    if ($("track").classList.contains("active")) stopTracking();
    show("pair");
    toast("간호사 앱에서 이 침상을 지워 연결이 끊겼어요. 새 연결 코드를 넣어 주세요");
    return;
  }
  const reg = paired() ? myReg() : null;
  // 간호사가 이 침상의 환자를 바꾸면 따라 바꾼다 (응시 시간·눈 맞추기는 환자마다 따로)
  if (reg && reg.patient && reg.patient !== store.data.current) {
    const isNew = !store.data.patients[reg.patient];
    store.addPatient(reg.patient);
    toast(`환자가 ${reg.patient} 님으로 바뀌었어요${isNew ? ". 눈 맞추기를 해 주세요" : ""}`);
  }
  refresh();
}
function refresh() {
  if ($("home").classList.contains("active")) renderHome();
  if ($("settings").classList.contains("active")) fillBedSelect();
}

function renderHome() {
  $("homeBed").textContent = store.data.bed || "침상 연결 안 됨";
  $("homePatient").textContent = store.data.bed ? currentPatient() || "없음" : "-";
  const problem = bedProblem();
  $("chipBed").hidden = !problem;
  $("chipBed").textContent = problem;
  // 연결한 뒤 간호사가 코드를 새로 만들었거나 침상을 지웠으면 홈 맨 위에 코드 입력칸을 띄운다
  // (처음 연결은 따로 '침상 연결' 화면에서 한다)
  const needCode = !!store.data.pairCode && !!roster && !paired();
  $("homePair").hidden = !needCode;
  if (needCode) $("chipBed").hidden = true;            // 위의 연결 칸이 같은 내용을 보여 준다
  if (needCode) {
    $("homePairTitle").textContent = !store.data.bed ? "침상 연결" : !myReg() ? "침상이 지워졌어요" : "연결 코드가 바뀌었어요";
    $("homePairSub").textContent = !store.data.bed
      ? "간호사 앱 [침상 관리]에 있는 4자리 연결 코드를 넣어 주세요."
      : "간호사에게 새 연결 코드를 받아 넣어 주세요.";
    $("homeWard").textContent = `병동 코드: ${link.ward} (다르면 설정에서 바꿔요)`;
  }

  const p = store.patient;
  $("chipCalib").textContent = p.calib ? "눈 맞추기 완료" : "눈 맞추기 안 함 (공통 기준)";
  $("chipCalib").classList.toggle("on", !!p.calib);
  const d = p.dwell;
  $("chipDwell").textContent = `응시 ${secondsText(d.first_gaze_sec)} · 확정 ${secondsText(d.confirm_gaze_sec)} · 취소 ${secondsText(d.cancel_close_sec)}`;
  const today = new Date().toDateString();
  const items = store.data.history.filter((h) => new Date(h.at).toDateString() === today && h.event !== "ASK");
  const calls = items.filter((h) => h.event === "CALL").length;
  $("histCount").textContent = `오늘 호출 ${calls}번`;
  const ul = $("histList");
  ul.innerHTML = "";
  for (const h of items.slice(0, 5)) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="ev-${h.event}"></span><span class="muted"></span>`;
    li.children[0].textContent = `${EVENT_TEXT[h.event] || h.event}${h.detail ? " · " + h.detail : ""}`;
    li.children[1].textContent = `${h.patient} · ${timeText(h.at)}`;
    ul.appendChild(li);
  }
  if (!items.length) ul.innerHTML = '<li><span class="muted">오늘은 아직 기록이 없어요</span></li>';
}


// ── 음성 · 연결 ───────────────────────────────
const voice = new Voice((tag, at) => session && session.onVoiceDone(tag, at));
voice.rate = store.data.voiceRate;
const link = createLink();
link.onAck((m) => session && session.onAck(m));
link.watchAcks();
// 인터넷 없이 같은 브라우저 안에서 시연할 때만 탭끼리 등록 목록을 받는다.
// Firebase를 쓸 때는 10초마다 읽는 전체 목록만 믿는다 (탭끼리 오는 일부 변경만 보고 '침상이 지워졌다'고 오해하지 않게)
if (link.kind !== "firebase") link.watchRoster(onRoster, { live: false });
// 등록 목록(환자 바뀜)과 같은 침상을 쓰는 다른 휴대폰: 설정을 열 때와 10초마다 한 번씩 읽는다
// (실시간 연결은 '간호사 확인' 하나만 열어 둔다)
async function checkBeds() {
  const [r, b] = await Promise.all([link.readRoster(), link.readBeds()]);
  bedStates = b;
  if (r) onRoster(r);
  else refresh();
}
checkBeds();
setInterval(() => {
  if (!document.hidden) checkBeds();
}, 10000);
function showLinkState(s = link.state) {
  const chip = $("chipLink");
  if (!chip) return;
  const ok = link.kind === "firebase" ? s.online : link.kind === "local";
  chip.textContent = link.kind === "firebase"
    ? `의료진 연결 ${s.online ? "됨" : s.error ? "안 됨" : "확인 중"} · 병동 ${link.ward}`
    : `의료진 연결: 이 브라우저 안에서만 · 병동 ${link.ward}`;
  chip.classList.toggle("on", ok);
  chip.classList.toggle("bad", link.kind === "firebase" && !s.online && !!s.error);
}
link.onState(showLinkState);
// 시작하자마자 연결을 확인한다 (침상 상태를 한 번 보낸다)
// 연결 코드로 연결된 휴대폰만 침상 상태를 보낸다 (예전에 침상 이름만 쳐 넣은 휴대폰이 침상처럼 보이지 않게)
if (store.data.pairCode && store.data.bed) link.sendStatus({ bed: store.data.bed, patient: currentPatient(), state: "HOME" });

let wakeLock = null;
async function keepAwake(on) {
  try {
    if (on && "wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen");
    else if (!on && wakeLock) {
      await wakeLock.release();
      wakeLock = null;
    }
  } catch {
    /* 화면 꺼짐 방지를 지원하지 않는 브라우저 */
  }
}

// ── 카메라 ───────────────────────────────────
const camera = new Camera($("video"));
let session = null;

async function openCamera(deviceId = store.data.cameraId) {
  await camera.start(deviceId);
  if (camera.deviceId && camera.deviceId !== store.data.cameraId) {
    store.data.cameraId = camera.deviceId;      // 다음에도 같은 카메라로
    store.save();
  }
}

async function switchCamera() {
  const list = await Camera.list();
  if (list.length < 2) return toast("다른 카메라가 없어요");
  const i = list.findIndex((d) => d.deviceId === camera.deviceId);
  const next = list[(i + 1) % list.length];
  camera.stop();
  try {
    await openCamera(next.deviceId);
    toast(`카메라: ${camera.label || next.label || "다음 카메라"}`);
  } catch (err) {
    toast(`이 카메라는 열 수 없어요 (${err.name})`);
  }
  if (session) session.extractor.reset();
}

$("btnSwitchCam").addEventListener("click", switchCamera);
$("btnCalSwitch").addEventListener("click", switchCamera);

// ── 호출 대기 (시선 추적) ──────────────────────

class Session {
  constructor() {
    const p = store.patient;
    this.dwell = { ...p.dwell };
    this.phrases = buildPhrases(this.dwell);
    this.controller = new CallController(this.dwell, { ...COOLDOWN_APP, CALL: store.data.callCooldownSec ?? COOLDOWN_APP.CALL });
    this.extractor = new FeatureExtractor(p.calib || undefined);
    this.lastResult = null;
    this.callId = null;
    this.callAt = 0;
    this.callCount = 0;
    this.cardTimer = null;
    this.running = true;
    this.canvas = $("overlay");
    this.ctx = this.canvas.getContext("2d");
  }

  onVoiceDone(tag, at) {
    if (tag === "ASK") this.controller.questionFinished(at);
    else if (["CALL", "CANCEL", "TIMEOUT"].includes(tag)) this.controller.announcementFinished(at);
  }

  onEvent(ev, now) {
    if (ev === "READY") return;
    store.log(ev, ev === "CALL" && this.callCount ? `${this.callCount + 1}회째` : "");
    if (ev === "CANCEL") voice.interrupt("ASK");
    if (this.phrases[ev]) voice.say(this.phrases[ev], ev);
    if (ev === "CALL") {
      this.callCount = this.callAt && Date.now() - this.callAt < 300000 ? this.callCount + 1 : 1;
      this.callAt = Date.now();
      this.callId = link.sendCall({ bed: store.data.bed || "침상 미선택", patient: currentPatient(), count: this.callCount });
      this.showCard("call", "간호사를 불렀어요", this.callCount > 1 ? `다시 불렀어요 (${this.callCount}번째)` : "잠시만 기다려 주세요", "🔔");
    } else if (ev === "CANCEL") {
      this.showCard("cancel", "호출을 취소했어요", "필요하면 언제든 다시 바라보세요", "↩️", 3500);
    }
  }

  onAck(m) {
    if (!this.callId || m.id !== this.callId) return;
    const sec = Math.round((Date.now() - this.callAt) / 1000);
    store.log("ACK", `${m.who || "간호사"} · ${sec}초`);
    voice.say(this.phrases.ACK, "ACK");
    this.callId = null;
    this.showCard("ack", "간호사가 확인했어요", `${m.who || "간호사"}님이 곧 도착해요`, "✅", 12000);
  }

  showCard(kind, title, sub, icon, hideAfter = 0) {
    const card = $("callCard");
    card.className = `callcard ${kind === "call" ? "" : kind}`;
    $("callTitle").textContent = title;
    $("callSub").textContent = sub;
    $("callIcon").textContent = icon;
    card.hidden = false;
    clearTimeout(this.cardTimer);
    if (hideAfter) this.cardTimer = setTimeout(() => (card.hidden = true), hideAfter);
  }

  tick() {
    if (!this.running) return;
    // 의료진 앱에 '이 침상 앱이 켜져 있다'를 알린다 (3초마다)
    if (Date.now() - (this.lastStatus || 0) > 3000) {
      this.lastStatus = Date.now();
      if (store.data.pairCode && store.data.bed) link.sendStatus({ bed: store.data.bed, patient: currentPatient(), state: this.controller.state });
    }
    const r = camera.detect();
    if (r !== undefined) {
      const now = clock();
      // 1초에 몇 장 분석하는지 재서 끊김 허용치를 맞춘다
      if (this.lastFrame) {
        const dt = now - this.lastFrame;
        this.frameDt = this.frameDt ? this.frameDt * 0.9 + dt * 0.1 : dt;
        this.controller.setFrameInterval(this.frameDt);
      }
      this.lastFrame = now;
      const eye = this.extractor.update(r.face);
      for (const ev of this.controller.update(eye, now)) this.onEvent(ev, now);
      // 호출 화면은 의료진이 확인하기 전까지 두되, 환자가 다시 질문을 받으면 추적 화면으로 돌아온다
      if (this.controller.state === ASKING) $("callCard").hidden = true;
      this.landmarks = r.landmarks;
      this.render(eye, r.landmarks, now);
    }
    requestAnimationFrame(() => this.tick());
  }

  render(eye, landmarks, now) {
    const c = this.controller;
    const d = this.dwell;
    const p = c.progress(now);
    const ring = $("ring");
    ring.style.strokeDashoffset = String(RING * (1 - p.value));
    ring.classList.toggle("confirm", p.kind === "confirm");
    ring.classList.toggle("close", p.kind === "close");
    const target = $("targetEye");
    target.classList.toggle("gazing", !!eye?.gazing && c.state !== ASKING && c.state !== WAITING);
    target.classList.toggle("asking", c.state === ASKING || c.state === WAITING);

    let head, sub, label = "여기를 바라보세요";
    if (!eye && c.state !== COOLDOWN) {
      head = "얼굴이 보이지 않아요";
      sub = /droidcam|virtual/i.test(camera.label)
        ? "가상 카메라가 켜져 있어요. 아래 [카메라 바꾸기]를 눌러 주세요"
        : "휴대폰 화면 쪽으로 얼굴을 돌려 주세요";
    } else if (c.state === IDLE) {
      head = p.value > 0 ? `조금만 더 바라보세요` : "부르고 싶으면 바라보세요";
      sub = p.value > 0 ? `${Math.max(0, d.first_gaze_sec * (1 - p.value)).toFixed(1)}초 남았어요` : `눈 모양을 ${secondsText(d.first_gaze_sec)} 보면 호출할지 물어봐요`;
    } else if (c.state === ASKING) {
      head = "호출할까요?";
      sub = p.kind === "close" ? "눈을 계속 감고 있으면 취소돼요" : "질문을 듣고 대답해 주세요";
      label = "질문 중";
    } else if (c.state === WAITING) {
      head = "호출할까요?";
      sub = p.kind === "close" && p.value > 0
        ? `눈을 감고 있어요 · ${Math.max(0, d.cancel_close_sec * (1 - p.value)).toFixed(1)}초 뒤 취소`
        : p.value > 0
          ? `바라보는 중 · ${Math.max(0, d.confirm_gaze_sec * (1 - p.value)).toFixed(1)}초 뒤 호출`
          : `계속 바라보면 호출, 눈을 감으면 취소 (${Math.ceil(p.remain)}초)`;
      label = "대답해 주세요";
    } else if (p.kind === "rest") {
      head = c.lastResult === "CALL" ? "간호사를 부른 뒤 쉬는 중이에요" : "잠시 쉬는 중이에요";
      sub = `${Math.ceil(p.remain)}초 뒤에 다시 부를 수 있어요`;
      label = `${Math.ceil(p.remain)}초`;
    } else {
      head = p.kind === "lookaway" ? "잠시 다른 곳을 봐 주세요" : "안내를 듣고 있어요";
      sub = p.kind === "lookaway" ? "다시 부르려면 눈을 뗐다가 다시 바라보세요" : "";
    }
    $("headline").textContent = head;
    $("sub").textContent = sub;
    $("targetLabel").textContent = label;

    const set = (id, cls, text) => {
      const b = $(id);
      b.className = `badge ${cls}`;
      b.textContent = text;
    };
    set("bFace", eye ? "on" : "bad", eye ? "얼굴 ✓" : "얼굴 없음");
    set("bGaze", eye?.gazing ? "on" : "", eye?.gazing ? "바라보는 중" : "시선 밖");
    set("bEye", eye?.eyesClosed ? "warn" : eye ? "on" : "", eye?.eyesClosed ? "눈 감음" : "눈 뜸");
    const ro = $("readout");
    ro.hidden = !store.data.showReadout;
    if (store.data.showReadout) {
      const k = this.extractor.calib;
      const t = this.extractor.tol;
      const ok = (name) => (eye.checks[name] ? "✓" : "✗");
      ro.textContent = eye
        ? `눈 열림 ${eye.ear.toFixed(3)} (≤${k.ear_closed.toFixed(3)} 감음) · 감김 ${eye.blink.toFixed(2)} (≥${k.blink_closed.toFixed(2)} 감음)\n` +
          `${ok("iris_h")} 홍채 가로 ${eye.iris_h.toFixed(3)} (기준 ${k.iris_h_center.toFixed(3)}±${t.iris_h.toFixed(3)})\n` +
          `${ok("iris_v")} 홍채 세로 ${eye.iris_v.toFixed(3)} (기준 ${k.iris_v_center.toFixed(3)}±${t.iris_v.toFixed(3)})\n` +
          `${ok("yaw")} 고개 좌우 ${eye.yaw.toFixed(1)}° (기준 ${k.yaw_center.toFixed(1)}±${t.yaw.toFixed(0)}) · ` +
          `${ok("pitch")} 상하 ${eye.pitch.toFixed(1)}°\n` +
          `${store.patient.calib ? "눈 맞추기 적용됨" : "눈 맞추기 안 함 (공통 기준)"}\n` +
          this.cameraLine()
        : `얼굴 없음\n${this.cameraLine()}`;
    }
    this.drawEyes(eye, landmarks);
  }

  // 카메라 · 처리 속도 · 눈 크기 (인식이 약할 때 원인을 찾는 용도)
  cameraLine() {
    const v = $("video");
    const fps = this.frameDt ? (1 / this.frameDt).toFixed(0) : "-";
    let eyePx = "-";
    const lm = this.landmarks;
    if (lm) eyePx = Math.round(Math.hypot((lm[33].x - lm[133].x) * v.videoWidth, (lm[33].y - lm[133].y) * v.videoHeight));
    const warn = [];
    if (this.frameDt && 1 / this.frameDt < 10) warn.push("처리 느림");
    if (eyePx !== "-" && eyePx < 28) warn.push("눈이 작게 찍힘: 더 가까이");
    return `영상 ${v.videoWidth}×${v.videoHeight} · ${fps}장/초 · 눈 너비 ${eyePx}px${warn.length ? " · ⚠ " + warn.join(", ") : ""}`;
  }

  drawEyes(eye, lm) {
    const v = $("video");
    const cv = this.canvas;
    if (cv.width !== v.videoWidth) {
      cv.width = v.videoWidth;
      cv.height = v.videoHeight;
    }
    const ctx = this.ctx;
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (!lm || !store.data.showCamera) return;
    const color = eye?.eyesClosed ? "#f2b23a" : eye?.gazing ? "#8fd9c4" : "#ffffff";
    const pt = (i) => [lm[i].x * cv.width, lm[i].y * cv.height];
    ctx.lineWidth = Math.max(2, cv.width / 260);
    ctx.strokeStyle = color;
    for (const idx of Object.values(EYE_OUTLINE)) {
      ctx.beginPath();
      idx.forEach((i, k) => (k ? ctx.lineTo(...pt(i)) : ctx.moveTo(...pt(i))));
      ctx.closePath();
      ctx.stroke();
    }
    if (!eye?.eyesClosed) {
      for (const [c, e1, e2] of [[468, 469, 471], [473, 474, 476]]) {
        const [x, y] = pt(c);
        const r = Math.hypot(pt(e1)[0] - pt(e2)[0], pt(e1)[1] - pt(e2)[1]) / 2;
        ctx.beginPath();
        ctx.arc(x, y, Math.max(2, r), 0, Math.PI * 2);
        ctx.fillStyle = color + "55";
        ctx.fill();
        ctx.stroke();
      }
    }
  }

  stop() {
    this.running = false;
    clearTimeout(this.cardTimer);
  }
}

async function startTracking() {
  // 침상을 고르지 않았으면 먼저 고르게 한다 (등록 문제는 경고만 하고 시작은 막지 않음: 응급일 수 있음)
  if (!store.data.pairCode) {
    toast("간호사 앱의 연결 코드를 먼저 넣어 주세요");
    show("pair");
    return;
  }
  voice.unlock();
  show("track");
  $("callCard").hidden = true;
  $("camBox").classList.toggle("hidden-cam", !store.data.showCamera);
  $("trackWho").textContent = `${store.data.bed} · ${currentPatient() || "환자 없음"}`;
  $("headline").textContent = "카메라를 준비하고 있어요";
  $("sub").textContent = "처음에는 10초쯤 걸릴 수 있어요";
  camera.video = $("video");
  try {
    await openCamera();
  } catch (err) {
    $("headline").textContent = "카메라를 켤 수 없어요";
    $("sub").textContent = err.name === "NotAllowedError" ? "브라우저에서 카메라 사용을 허용해 주세요" : err.message || String(err);
    return;
  }
  keepAwake(true);
  session = new Session();
  voice.say(session.phrases.START, "START");
  session.tick();
}

function stopTracking() {
  if (session) session.stop();
  session = null;
  voice.stopAll();
  camera.stop();
  keepAwake(false);
  show("home");
  renderHome();
}

$("btnStart").addEventListener("click", startTracking);
$("btnStop").addEventListener("click", stopTracking);
$("callCard").addEventListener("click", () => ($("callCard").hidden = true));

// ── 눈 맞추기 ─────────────────────────────────
let calibRunning = false;

function setStep(n) {
  ["st1", "st2", "st3"].forEach((id, i) => {
    $(id).className = `step ${i + 1 === n ? "on" : i + 1 < n ? "done" : ""}`;
  });
}

async function collect(seconds, ringId, keep) {
  const out = [];
  const end = clock() + seconds;
  const ring = $(ringId);
  return new Promise((resolve) => {
    const loop = () => {
      const left = end - clock();
      ring.style.strokeDashoffset = String(RING * Math.max(0, left / seconds));
      const r = camera.detect();
      if (r?.face) {
        const f = rawFeatures(r.face);
        if (keep(f)) out.push(f);
      }
      if (left <= 0 || !calibRunning) resolve(out);
      else requestAnimationFrame(loop);
    };
    loop();
  });
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const sayAndWait = (text) =>
  new Promise((resolve) => {
    const prev = voice.onFinished;
    voice.onFinished = (tag, at) => {
      if (tag === "CAL") {
        voice.onFinished = prev;
        resolve();
      } else prev(tag, at);
    };
    voice.say(text, "CAL");
  });

async function openCalib() {
  voice.unlock();
  show("calib");
  setStep(0);
  $("calRing").style.strokeDashoffset = String(RING);
  $("calHead").textContent = "눈 맞추기";
  $("calSub").textContent = "휴대폰을 얼굴 옆쪽 위(눈만 돌리면 보이는 곳)에 고정하고, 환자가 편하게 누운 자세에서 시작해 주세요";
  $("btnCalGo").hidden = false;
  $("btnCalGo").textContent = "시작";
  camera.video = $("calVideo");
  try {
    await openCamera();
  } catch (err) {
    $("calHead").textContent = "카메라를 켤 수 없어요";
    $("calSub").textContent = err.message || String(err);
  }
}

async function runCalib() {
  if (!camera.ready) {
    toast("카메라가 아직 준비되지 않았어요");
    return;
  }
  calibRunning = true;
  $("btnCalGo").hidden = true;
  setStep(1);
  $("calHead").textContent = "눈만 돌려 눈 모양을 바라보세요";
  $("calSub").textContent = "고개는 그대로 두고, 링이 다 줄어들 때까지 계속 바라봐 주세요";
  await sayAndWait("고개는 그대로 두고, 눈만 돌려 카메라 옆의 눈 모양을 바라봐 주세요.");
  const look = await collect(3, "calRing", (f) => f.blink < 0.5);
  if (!calibRunning) return;
  setStep(2);
  $("calHead").textContent = "눈을 감아 주세요";
  $("calSub").textContent = "소리가 날 때까지 감고 있어 주세요";
  await sayAndWait("이번에는 눈을 감아 주세요.");
  await wait(600);
  const closed = await collect(2.5, "calRing", () => true);
  if (!calibRunning) return;
  if (look.length < 15) {
    voice.say("얼굴을 잘 찾지 못했습니다. 다시 해 주세요.");
    $("calHead").textContent = "얼굴을 잘 찾지 못했어요";
    $("calSub").textContent = "휴대폰 위치와 밝기를 확인하고 다시 해 주세요";
    $("btnCalGo").hidden = false;
    $("btnCalGo").textContent = "다시 하기";
    setStep(0);
    calibRunning = false;
    return;
  }
  store.patient.calib = { ...buildCalibration(look, closed), at: Date.now() };
  store.save();
  setStep(3);
  voice.say("눈을 떠 주세요. 눈 맞추기가 끝났습니다.");
  $("calHead").textContent = "눈 맞추기 완료";
  $("calSub").textContent = `${currentPatient() || store.data.current} 님 기준으로 저장했어요`;
  $("btnCalGo").hidden = false;
  $("btnCalGo").textContent = "호출 대기 시작";
  $("btnCalGo").dataset.next = "track";
  calibRunning = false;
}

$("btnCalib").addEventListener("click", openCalib);
$("btnCalGo").addEventListener("click", () => {
  if ($("btnCalGo").dataset.next === "track") {
    delete $("btnCalGo").dataset.next;
    camera.stop();
    startTracking();
  } else runCalib();
});
$("btnCalBack").addEventListener("click", () => {
  calibRunning = false;
  voice.stopAll();
  camera.stop();
  delete $("btnCalGo").dataset.next;
  show("home");
  renderHome();
});

// ── 설정 ─────────────────────────────────────
function renderSettings() {
  fillBedSelect();
  $("dwellFor").textContent = `· ${currentPatient() || store.data.current}`;
  document.querySelectorAll(".slider[data-key]").forEach((s) => {
    const v = store.patient.dwell[s.dataset.key];
    s.querySelector("input").value = v;
    s.querySelector(".val").textContent = secondsText(v);
  });
  const rate = $("rateSlider");
  rate.querySelector("input").value = store.data.voiceRate;
  rate.querySelector(".val").textContent = `${store.data.voiceRate.toFixed(1)}배`;
  $("setShowCam").checked = store.data.showCamera;
  $("setReadout").checked = !!store.data.showReadout;
  $("setWard").value = linkSettings().ward;
  const cd = $("cooldownSlider");
  cd.querySelector("input").value = store.data.callCooldownSec ?? 30;
  cd.querySelector(".val").textContent = `${store.data.callCooldownSec ?? 30}초`;
  fillCameraSelect();
  const c = store.patient.calib;
  $("calibInfo").textContent = c ? `눈 맞추기: ${new Date(c.at).toLocaleDateString()} ${timeText(c.at)}` : "눈 맞추기 안 함 (공통 기준)";
}

$("btnSettings").addEventListener("click", () => {
  renderSettings();
  checkBeds();
  show("settings");
});
$("btnSetBack").addEventListener("click", () => {
  show("home");
  renderHome();
});
$("setWard").addEventListener("change", (e) => {
  const ward = e.target.value.trim() || "ward1";
  if (ward === linkSettings().ward) return;
  saveLinkSettings({ ward });
  toast("병동 코드를 바꿨어요. 다시 연결할게요");
  setTimeout(() => location.reload(), 900);
});
// 침상 연결: 간호사 앱이 알려 준 4자리 연결 코드로
function fillBedSelect() {
  const now = $("pairNow");
  if (store.data.bed) {
    now.innerHTML = '<div class="muted">지금 연결된 침상</div><b></b><div></div>';
    now.children[1].textContent = store.data.bed;
    now.children[2].textContent = `환자: ${currentPatient() || "없음"}${store.data.pairCode ? ` · 코드 ${store.data.pairCode}` : ""}`;
  } else {
    now.innerHTML = '<b>아직 침상에 연결하지 않았어요</b><div class="muted">간호사 앱 [침상 관리]에서 침상을 등록하면 연결 코드가 나와요.</div>';
  }
  const info = $("setBedInfo");
  const problem = store.data.bed ? bedProblem() : "";
  info.textContent = problem ? `⚠ ${problem}` : roster === null && link.kind === "firebase" ? "등록 목록을 불러오는 중…" : "";
  info.style.color = problem ? "var(--call)" : "";
}
async function pairWithCode(input = $("setCode")) {
  const code = input.value.trim();
  if (!/^\d{4}$/.test(code)) return toast("4자리 숫자를 넣어 주세요");
  const fresh = await link.readRoster();          // 방금 만든 코드도 바로 찾을 수 있게 새로 읽는다
  if (fresh) roster = fresh;
  const e = Object.values(roster || {}).find((x) => x?.code === code);
  if (!e) return toast("맞는 침상이 없어요. 코드와 병동 코드를 확인해 주세요");
  bedStates = await link.readBeds();
  if (e.bed !== store.data.bed && usedByOther(e.bed) && !confirm(`${e.bed}은(는) 다른 휴대폰이 쓰고 있어요. 그래도 이 휴대폰으로 연결할까요?`)) return;
  store.data.bed = e.bed;
  store.data.pairCode = code;
  if (e.patient) store.addPatient(e.patient);
  store.save();
  input.value = "";
  input.blur();
  link.sendStatus({ bed: e.bed, patient: currentPatient(), state: "HOME" });
  if ($("settings").classList.contains("active")) renderSettings();
  else {
    show("home");
    renderHome();
  }
  toast(`${e.bed}${e.patient ? ` · ${e.patient} 님` : ""}으로 연결했어요`);
}
$("btnPair").addEventListener("click", () => pairWithCode($("setCode")));
$("setCode").addEventListener("keydown", (ev) => ev.key === "Enter" && pairWithCode($("setCode")));
$("btnHomePair").addEventListener("click", () => pairWithCode($("homeCode")));
$("btnStartPair").addEventListener("click", () => pairWithCode($("startCode")));
$("startCode").addEventListener("keydown", (ev) => ev.key === "Enter" && pairWithCode($("startCode")));
$("startWard").value = linkSettings().ward;
$("startWard").addEventListener("change", (e) => {
  const ward = e.target.value.trim() || "ward1";
  if (ward === linkSettings().ward) return;
  saveLinkSettings({ ward });
  toast("병동 코드를 바꿨어요. 다시 연결할게요");
  setTimeout(() => location.reload(), 900);
});
$("homeCode").addEventListener("keydown", (ev) => ev.key === "Enter" && pairWithCode($("homeCode")));
document.querySelectorAll(".slider[data-key] input").forEach((input) => {
  input.addEventListener("input", () => {
    const s = input.closest(".slider");
    const v = store.setDwell(s.dataset.key, parseFloat(input.value));
    s.querySelector(".val").textContent = secondsText(v);
  });
});
$("rateSlider").querySelector("input").addEventListener("input", (e) => {
  store.data.voiceRate = parseFloat(e.target.value);
  voice.rate = store.data.voiceRate;
  store.save();
  $("rateSlider").querySelector(".val").textContent = `${store.data.voiceRate.toFixed(1)}배`;
});
$("cooldownSlider").querySelector("input").addEventListener("input", (e) => {
  store.data.callCooldownSec = parseInt(e.target.value, 10);
  store.save();
  $("cooldownSlider").querySelector(".val").textContent = `${store.data.callCooldownSec}초`;
});
$("btnVoiceTest").addEventListener("click", () => {
  voice.unlock();
  voice.stopAll();
  voice.say(buildPhrases(store.patient.dwell).ASK, "TEST");
});
async function fillCameraSelect() {
  const sel = $("setCamera");
  sel.innerHTML = '<option value="">자동 (앞면 · 실제 카메라)</option>';
  try {
    const list = await Camera.list();
    list.forEach((d, i) => {
      const o = document.createElement("option");
      o.value = d.deviceId;
      o.textContent = d.label || `카메라 ${i + 1} (이름은 카메라를 한 번 켠 뒤에 보여요)`;
      o.selected = d.deviceId === store.data.cameraId;
      sel.appendChild(o);
    });
  } catch {
    /* 카메라 목록을 못 읽는 브라우저 */
  }
}
$("setCamera").addEventListener("change", (e) => {
  store.data.cameraId = e.target.value || null;
  store.save();
  camera.stop();
});
$("setReadout").addEventListener("change", (e) => {
  store.data.showReadout = e.target.checked;
  store.save();
});
$("setShowCam").addEventListener("change", (e) => {
  store.data.showCamera = e.target.checked;
  store.save();
});
$("btnCalibReset").addEventListener("click", () => {
  store.patient.calib = null;
  store.save();
  renderSettings();
  toast("공통 기준으로 돌아갔어요");
});

renderHome();
showLinkState();
// 연결 코드를 아직 안 넣었으면 (예전에 침상 이름만 쳐 넣은 휴대폰 포함) 코드 화면부터
if (!store.data.pairCode) show("pair");

// 가로로 돌렸을 때 앞면 카메라가 어느 쪽에 있는지 (표적을 카메라 쪽에 두려고)
// 반시계로 돌리면(90°) 카메라가 왼쪽, 시계로 돌리면(270°) 오른쪽
function updateCamSide() {
  const angle = screen.orientation?.angle ?? window.orientation ?? 0;
  document.body.dataset.camSide = angle === 90 ? "left" : "right";
}
updateCamSide();
screen.orientation?.addEventListener?.("change", updateCamSide);
window.addEventListener("orientationchange", updateCamSide);
