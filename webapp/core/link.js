// 환자 앱 ↔ 의료진 앱 연결
// 지금은 같은 기기·같은 브라우저 안에서만 전달한다 (BroadcastChannel: 노트북 한 대로 시연할 때).
// 휴대폰 두 대를 잇는 서버(Firebase 등)는 여기에 붙인다. 앱 화면 코드는 이 파일만 바뀌면 된다.
//
// 주고받는 메시지
//   call   환자 → 의료진  { id, bed, patient, count, at }        호출 확정
//   ack    의료진 → 환자  { id, who, at }                        [확인]을 누름
//   status 환자 → 의료진  { bed, patient, state, at }             몇 초마다: 앱이 켜져 있는지, 지금 상태
export function createLink() {
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("opticcall") : null;
  const handlers = {};
  if (channel) {
    channel.onmessage = (e) => {
      const m = e.data || {};
      (handlers[m.type] || []).forEach((h) => h(m));
    };
  }
  const post = (m) => channel && channel.postMessage({ ...m, at: m.at || Date.now() });
  const on = (type, h) => (handlers[type] = handlers[type] || []).push(h);
  return {
    kind: channel ? "local" : "none",
    sendCall(info) {
      const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
      post({ type: "call", id, ...info });
      return id;
    },
    sendAck(id, who) {
      post({ type: "ack", id, who });
    },
    sendStatus(info) {
      post({ type: "status", ...info });
    },
    onCall: (h) => on("call", h),
    onAck: (h) => on("ack", h),
    onStatus: (h) => on("status", h),
  };
}
