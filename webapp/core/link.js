// 환자 앱 ↔ 의료진 앱 연결
// 지금은 같은 기기·같은 브라우저 안에서만 전달한다 (BroadcastChannel: 노트북 한 대로 시연할 때).
// 휴대폰 두 대를 잇는 서버(Firebase 등)는 여기에 붙인다. 앱 화면 코드는 이 파일만 바뀌면 된다.
//   link.sendCall({ bed, patient, count }) -> 호출 번호
//   link.onAck((ack) => ...)              -> 의료진이 [확인]을 누르면 { id, who }
//   link.onCall((call) => ...)            -> (의료진 앱) 호출이 오면
//   link.sendAck(id, who)                 -> (의료진 앱) 확인 보내기
export function createLink() {
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("opticcall") : null;
  const handlers = { call: [], ack: [] };
  if (channel) {
    channel.onmessage = (e) => {
      const m = e.data || {};
      (handlers[m.type] || []).forEach((h) => h(m));
    };
  }
  const post = (m) => channel && channel.postMessage(m);
  return {
    kind: channel ? "local" : "none",
    sendCall(info) {
      const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
      post({ type: "call", id, at: Date.now(), ...info });
      return id;
    },
    sendAck(id, who) {
      post({ type: "ack", id, who, at: Date.now() });
    },
    onCall(h) {
      handlers.call.push(h);
    },
    onAck(h) {
      handlers.ack.push(h);
    },
  };
}
