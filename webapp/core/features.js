// 카메라 응시 여부 · 눈 감김 판정 (파이썬 vision/features.py를 그대로 옮김)
// MediaPipe 얼굴 랜드마크 478점에서 EAR, 홍채 위치, 고개 각도를 구하고 보정값과 비교한다.

// 환자 본인 기준 좌/우. EAR 6점: [눈꼬리 A, 위1, 위2, 눈꼬리 B, 아래2, 아래1]
export const RIGHT_EYE = [33, 160, 158, 133, 153, 144];
export const LEFT_EYE = [362, 385, 387, 263, 373, 380];
export const RIGHT_IRIS = [468, 469, 470, 471, 472];
export const LEFT_IRIS = [473, 474, 475, 476, 477];

// 공통 기준 (파이썬 config.DEFAULT_CALIBRATION과 같음). 앱의 '눈 맞추기'로 사람·거치 위치마다 다시 잡는다.
export const DEFAULT_CALIBRATION = {
  ear_closed: 0.15,
  blink_closed: 0.45,
  iris_h_center: 0.5,
  iris_v_center: -0.07,
  yaw_center: 0.0,
  pitch_center: 0.0,
};
export const GAZE_TOLERANCE = { iris_h: 0.06, iris_v: 0.05, yaw: 5.0, pitch: 30.0 };
export const SMOOTHING = 0.5;

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

export function makeFace(landmarks, blendshapes, matrix, width, height) {
  return {
    blendshapes: blendshapes || {},
    matrix: matrix || null,
    px: (i) => [landmarks[i].x * width, landmarks[i].y * height],
  };
}

export function eyeAspectRatio(face, idx) {
  const p = idx.map((i) => face.px(i));
  const width = dist(p[0], p[3]);
  if (width === 0) return 0;
  return (dist(p[1], p[5]) + dist(p[2], p[4])) / (2 * width);
}

export function irisPosition(face, eyeIdx, irisIdx) {
  const a = face.px(eyeIdx[0]);
  const b = face.px(eyeIdx[3]);
  const c = face.px(irisIdx[0]);
  const axis = [b[0] - a[0], b[1] - a[1]];
  const len2 = axis[0] * axis[0] + axis[1] * axis[1];
  if (len2 === 0) return [0.5, 0];
  const h = ((c[0] - a[0]) * axis[0] + (c[1] - a[1]) * axis[1]) / len2;
  const normal = [-axis[1], axis[0]];
  const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const v = ((c[0] - mid[0]) * normal[0] + (c[1] - mid[1]) * normal[1]) / len2;
  return [h, v];
}

// MediaPipe 4x4 변환 행렬 -> (yaw, pitch) 도 단위.
// 웹 버전은 data가 16칸 배열이라 행 우선/열 우선을 이동값 위치로 알아낸다 (이동값의 z가 가장 크다).
export function headAngles(matrix) {
  if (!matrix) return [0, 0];
  const d = matrix.data || matrix;
  const colMajor = Math.abs(d[14]) > Math.abs(d[11]);
  const r = (row, col) => (colMajor ? d[col * 4 + row] : d[row * 4 + col]);
  const yaw = (Math.asin(Math.max(-1, Math.min(1, -r(2, 0)))) * 180) / Math.PI;
  const pitch = (Math.atan2(r(2, 1), r(2, 2)) * 180) / Math.PI;
  return [yaw, pitch];
}

export function rawFeatures(face) {
  const ear = (eyeAspectRatio(face, RIGHT_EYE) + eyeAspectRatio(face, LEFT_EYE)) / 2;
  const bs = face.blendshapes;
  const blink = ((bs.eyeBlinkLeft || 0) + (bs.eyeBlinkRight || 0)) / 2;
  const [rh, rv] = irisPosition(face, RIGHT_EYE, RIGHT_IRIS);
  const [lh, lv] = irisPosition(face, LEFT_EYE, LEFT_IRIS);
  const [yaw, pitch] = headAngles(face.matrix);
  return { ear, blink, iris_h: (rh + lh) / 2, iris_v: (rv + lv) / 2, yaw, pitch };
}

export function judge(f, calib, tol) {
  const eyesClosed = f.ear <= calib.ear_closed || f.blink >= calib.blink_closed;
  // 항목별 통과 여부 (화면의 '판정 숫자 보기'에서 무엇 때문에 응시가 아닌지 보여 준다)
  const checks = {
    iris_h: Math.abs(f.iris_h - calib.iris_h_center) <= tol.iris_h,
    iris_v: Math.abs(f.iris_v - calib.iris_v_center) <= tol.iris_v,
    yaw: Math.abs(f.yaw - calib.yaw_center) <= tol.yaw,
    pitch: Math.abs(f.pitch - calib.pitch_center) <= tol.pitch,
  };
  const gazing = !eyesClosed && checks.iris_h && checks.iris_v && checks.yaw && checks.pitch;
  return { eyesClosed, gazing, checks };
}

export class FeatureExtractor {
  constructor(calibration, tolerance) {
    this.calib = { ...DEFAULT_CALIBRATION, ...(calibration || {}) };
    this.tol = { ...GAZE_TOLERANCE, ...(this.calib.tolerance || {}), ...(tolerance || {}) };
    this.smoothed = null;
  }

  reset() {
    this.smoothed = null;
  }

  // 얼굴이 없으면 null, 있으면 { ...특징값, eyesClosed, gazing }
  update(face) {
    if (!face) {
      this.reset();
      return null;
    }
    const raw = rawFeatures(face);
    if (!this.smoothed) this.smoothed = raw;
    else {
      const a = SMOOTHING;
      for (const k in raw) this.smoothed[k] = a * raw[k] + (1 - a) * this.smoothed[k];
    }
    const f = { ...this.smoothed };
    return { ...f, ...judge(f, this.calib, this.tol), raw };
  }
}

// '눈 맞추기' 결과로 보정값을 만든다.
//   look: 화면의 눈 표시를 볼 때 모은 특징값들, closed: 눈을 감았을 때 모은 특징값들
export function buildCalibration(look, closed) {
  const median = (xs) => {
    const s = [...xs].sort((a, b) => a - b);
    const m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const calib = { ...DEFAULT_CALIBRATION };
  if (look.length) {
    calib.iris_h_center = median(look.map((f) => f.iris_h));
    calib.iris_v_center = median(look.map((f) => f.iris_v));
    calib.yaw_center = median(look.map((f) => f.yaw));
    calib.pitch_center = median(look.map((f) => f.pitch));
    // 허용 범위: 바라보는 동안 값이 흔들린 만큼 넓힌다 (중앙값에서 벗어난 정도의 90% 지점 × 1.5).
    // 눈만 옆으로 돌려 보거나 얼굴이 비스듬히 잡히면 공통 기준(홍채 0.06, 고개 5°)보다 많이 흔들린다.
    const spread = (key, center) => {
      const dev = look.map((f) => Math.abs(f[key] - center)).sort((a, b) => a - b);
      return dev[Math.min(dev.length - 1, Math.floor(dev.length * 0.9))] * 1.5;
    };
    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    calib.tolerance = {
      iris_h: clamp(spread("iris_h", calib.iris_h_center), GAZE_TOLERANCE.iris_h, 0.12),
      iris_v: clamp(spread("iris_v", calib.iris_v_center), GAZE_TOLERANCE.iris_v, 0.1),
      yaw: clamp(spread("yaw", calib.yaw_center), 8, 15),
      pitch: GAZE_TOLERANCE.pitch,
    };
  }
  if (look.length && closed.length) {
    // 눈을 감았을 때 값이 뜬 눈과 충분히 달라야만 기준을 바꾼다 (덜 감았거나 얼굴을 놓쳤으면 공통 기준 유지)
    const open = median(look.map((f) => f.ear));
    const shut = median(closed.map((f) => f.ear));
    if (open - shut > 0.05) calib.ear_closed = Math.min(0.25, Math.max(0.1, shut + (open - shut) * 0.4));
    // 감김 점수: 사람마다 감았을 때 0.3~0.9로 달라서, 뜬 눈과 감은 눈의 중간으로 잡는다
    const bOpen = median(look.map((f) => f.blink));
    const bShut = median(closed.map((f) => f.blink));
    if (bShut - bOpen > 0.15) calib.blink_closed = Math.min(0.6, Math.max(0.25, bOpen + (bShut - bOpen) * 0.5));
  }
  return calib;
}
