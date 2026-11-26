// 휴대폰 앞면 카메라 + MediaPipe 얼굴 랜드마크 (파이썬 input/camera_stream.py + vision/face_landmarker.py 역할)
import { FaceLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";
import { makeFace } from "./features.js";

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL = new URL("../models/face_landmarker.task", import.meta.url).href;

const VIRTUAL = /droidcam|virtual|obs|studio effects|snap camera|manycam|ndi/i;
let landmarkerPromise = null;

async function createLandmarker() {
  const files = await FilesetResolver.forVisionTasks(WASM);
  const options = (delegate) => ({
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO",
    numFaces: 1,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
  });
  try {
    return await FaceLandmarker.createFromOptions(files, options("GPU"));
  } catch {
    return await FaceLandmarker.createFromOptions(files, options("CPU"));
  }
}

export class Camera {
  constructor(video) {
    this.video = video;
    this.stream = null;
    this.landmarker = null;
    this.lastTs = 0;
    this.lastVideoTime = -1;
  }

  // deviceId: 설정에서 고른 카메라 (없으면 앞면 카메라, PC면 가상 카메라가 아닌 실제 카메라)
  async start(deviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("이 브라우저에서는 카메라를 쓸 수 없어요. 주소가 https://로 시작하는지 확인해 주세요.");
    }
    landmarkerPromise = landmarkerPromise || createLandmarker();
    if (this.stream && deviceId && this.deviceId !== deviceId) this.stop();
    if (!this.stream) {
      const open = (id) =>
        navigator.mediaDevices.getUserMedia({
          video: id
            ? { deviceId: { exact: id }, width: { ideal: 1280 }, height: { ideal: 720 } }
            : { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
      try {
        this.stream = await open(deviceId);
      } catch (err) {
        if (!deviceId || err.name === "NotAllowedError") throw err;
        this.stream = await open(null);          // 고른 카메라가 없어졌으면 기본 카메라로
      }
      // 고른 카메라가 없을 때 DroidCam·OBS 같은 가상 카메라가 잡혔으면 실제 카메라로 바꾼다
      const label = this.stream.getVideoTracks()[0]?.label || "";
      if (!deviceId && VIRTUAL.test(label)) {
        const real = (await Camera.list()).find((d) => !VIRTUAL.test(d.label));
        if (real) {
          this.stop();
          this.stream = await open(real.deviceId);
        }
      }
      this.deviceId = this.stream.getVideoTracks()[0]?.getSettings().deviceId || deviceId || null;
      this.label = this.stream.getVideoTracks()[0]?.label || "";
    }
    if (this.video.srcObject !== this.stream) {      // 화면(영상 요소)이 바뀌었으면 다시 연결
      this.video.srcObject = this.stream;
      this.lastVideoTime = -1;
    }
    await this.video.play();
    this.landmarker = await landmarkerPromise;
  }

  static async list() {
    const all = await navigator.mediaDevices.enumerateDevices();
    return all.filter((d) => d.kind === "videoinput");
  }

  // 영상이 들어오는데 거의 새까만지 (연결 안 된 가상 카메라 등)
  isDark() {
    if (!this.ready) return false;
    const c = (this._probe = this._probe || document.createElement("canvas"));
    c.width = 32;
    c.height = 24;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(this.video, 0, 0, 32, 24);
    const d = ctx.getImageData(0, 0, 32, 24).data;
    let sum = 0;
    for (let i = 0; i < d.length; i += 4) sum += d[i] + d[i + 1] + d[i + 2];
    return sum / (d.length / 4) / 3 < 12;
  }

  stop() {
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.lastVideoTime = -1;
    this.video.srcObject = null;
  }

  get ready() {
    return !!(this.landmarker && this.stream && this.video.readyState >= 2);
  }

  // 새 프레임이 있으면 { face(없으면 null), landmarks } , 없으면 undefined
  detect() {
    if (!this.ready || this.video.currentTime === this.lastVideoTime) return undefined;
    this.lastVideoTime = this.video.currentTime;
    const ts = Math.max(Math.round(performance.now()), this.lastTs + 1);
    this.lastTs = ts;
    const r = this.landmarker.detectForVideo(this.video, ts);
    if (!r.faceLandmarks?.length) return { face: null, landmarks: null };
    const bs = {};
    for (const c of r.faceBlendshapes?.[0]?.categories || []) bs[c.categoryName] = c.score;
    const matrix = r.facialTransformationMatrixes?.[0] || null;
    const lm = r.faceLandmarks[0];
    return { face: makeFace(lm, bs, matrix, this.video.videoWidth, this.video.videoHeight), landmarks: lm };
  }
}
