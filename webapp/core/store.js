// 이 휴대폰에만 저장하는 설정 (침상 이름, 환자별 응시 시간·눈 맞추기 값, 호출 기록)
import { DWELL_DEFAULTS, DWELL_MAX_SEC, DWELL_MIN_SEC, DWELL_STEP_SEC } from "./controller.js";

const KEY = "opticcall.patient.v1";
const DEFAULT = {
  bed: "",                      // 간호사 앱이 알려 준 연결 코드로 정한다
  pairCode: "",
  current: "기본",
  patients: { 기본: { dwell: { ...DWELL_DEFAULTS }, calib: null } },
  voiceRate: 1.0,
  showCamera: true,
  cameraId: null,
  callCooldownSec: 30,          // 호출 후 다시 질문하지 않는 시간
  history: [],
};

function read() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "null");
    return saved ? { ...structuredClone(DEFAULT), ...saved } : structuredClone(DEFAULT);
  } catch {
    return structuredClone(DEFAULT);
  }
}

export const store = {
  data: read(),

  save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.data));
    } catch {
      /* 저장이 막힌 브라우저(사생활 보호 모드 등)에서는 이번 실행 동안만 유지 */
    }
  },

  get patient() {
    const d = this.data;
    if (!d.patients[d.current]) d.current = Object.keys(d.patients)[0] || "기본";
    if (!d.patients[d.current]) d.patients[d.current] = { dwell: { ...DWELL_DEFAULTS }, calib: null };
    return d.patients[d.current];
  },

  setDwell(key, value) {
    const v = Math.round(Math.min(DWELL_MAX_SEC, Math.max(DWELL_MIN_SEC, value)) / DWELL_STEP_SEC) * DWELL_STEP_SEC;
    this.patient.dwell[key] = v;
    this.save();
    return v;
  },

  addPatient(name) {
    name = name.trim();
    if (!name) return false;
    if (!this.data.patients[name]) this.data.patients[name] = { dwell: { ...DWELL_DEFAULTS }, calib: null };
    this.data.current = name;
    this.save();
    return true;
  },

  removePatient(name) {
    if (Object.keys(this.data.patients).length <= 1) return false;
    delete this.data.patients[name];
    if (this.data.current === name) this.data.current = Object.keys(this.data.patients)[0];
    this.save();
    return true;
  },

  log(event, detail = "") {
    this.data.history.unshift({ at: Date.now(), event, detail, patient: this.data.current });
    this.data.history = this.data.history.slice(0, 200);
    this.save();
  },
};
