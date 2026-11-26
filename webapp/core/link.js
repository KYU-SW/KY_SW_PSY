// 환자 앱 ↔ 의료진 앱 연결
//   - 휴대폰끼리: Firebase Realtime Database (REST로 쓰고, 실시간 스트림으로 받는다. 따로 설치할 라이브러리 없음)
//   - 같은 브라우저 탭끼리: BroadcastChannel (인터넷이 안 될 때, 노트북 한 대로 시연할 때)
// 둘 다 보내고 받는다. 같은 메시지가 두 길로 와도 id로 한 번만 처리한다.
//
// 주고받는 메시지
//   call   환자 → 의료진  { id, bed, patient, count, at }        호출 확정
//   ack    의료진 → 환자  { id, who, at }                        [확인]을 누름
//   status 환자 → 의료진  { bed, patient, state, device, at }     몇 초마다: 앱이 켜져 있는지, 지금 상태
//   roster 의료진 → 모두  { bed, patient, code, at }              침상 등록 (patient가 빈 문자열이면 빈 침상,
//                                                                code는 환자 휴대폰을 그 침상에 연결하는 4자리 숫자)
//
// Firebase 안의 위치: opticcall/{병동 코드}/calls/{id}, /beds/{침상 키}, /roster/{침상 키}
export const DB_URL = "https://opticcall-1570c-default-rtdb.asia-southeast1.firebasedatabase.app";
const LINK_KEY = "opticcall.link.v1";
const RECENT_MS = 10 * 60 * 1000;          // 의료진 앱을 켰을 때 이보다 최근의 미확인 호출만 알람

export function linkSettings() {
  try {
    return { ward: "ward1", online: true, ...JSON.parse(localStorage.getItem(LINK_KEY) || "{}") };
  } catch {
    return { ward: "ward1", online: true };
  }
}
export function saveLinkSettings(s) {
  try {
    localStorage.setItem(LINK_KEY, JSON.stringify({ ...linkSettings(), ...s }));
  } catch {
    /* 저장이 막힌 브라우저 */
  }
}

export const cleanKey = (s) => String(s || "침상").replace(/[.#$\[\]\/]/g, "_").slice(0, 60);
// 이 휴대폰을 구별하는 값 (같은 침상을 두 휴대폰이 쓰는지 알아보려고)
export function deviceId() {
  try {
    let id = localStorage.getItem("opticcall.device");
    if (!id) localStorage.setItem("opticcall.device", (id = Math.random().toString(36).slice(2, 10)));
    return id;
  } catch {
    return "nostore";
  }
}
const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

// 실시간 스트림의 put/patch를 받아 로컬 사본에 반영한다
function applyAt(root, path, data, merge) {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return merge ? { ...(root || {}), ...(data || {}) } : data;
  const copy = { ...(root || {}) };
  let node = copy;
  for (let i = 0; i < parts.length - 1; i++) {
    node[parts[i]] = { ...(node[parts[i]] || {}) };
    node = node[parts[i]];
  }
  const last = parts.at(-1);
  if (merge) node[last] = { ...(node[last] || {}), ...(data || {}) };
  else if (data === null) delete node[last];
  else node[last] = data;
  return copy;
}

export function createLink(options = {}) {
  const settings = { ...linkSettings(), ...options };
  const base = `${DB_URL}/opticcall/${cleanKey(settings.ward)}`;
  const handlers = {};
  const seen = new Set();                    // 이미 처리한 call / ack id
  const on = (type, h) => (handlers[type] = handlers[type] || []).push(h);
  const emit = (type, m) => (handlers[type] || []).forEach((h) => h(m));
  const state = { online: false, error: "" };
  const onState = [];
  const setState = (patch) => {
    Object.assign(state, patch);
    onState.forEach((h) => h({ ...state }));
  };

  function deliver(type, m) {
    const key = `${type}:${m.id || ""}`;
    if (m.id && seen.has(key)) return;
    if (m.id) seen.add(key);
    emit(type, m);
  }

  // ── 같은 브라우저 탭끼리 ──
  const channel = "BroadcastChannel" in window ? new BroadcastChannel(`opticcall-${settings.ward}`) : null;
  if (channel) channel.onmessage = (e) => e.data?.type && deliver(e.data.type, e.data);
  const local = (m) => channel && channel.postMessage(m);

  // ── Firebase ──
  const remote = settings.online && DB_URL && "fetch" in window;
  const put = (path, body) =>
    fetch(`${base}/${path}.json`, { method: "PUT", body: JSON.stringify(body) })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setState({ online: true, error: "" });
        return true;
      })
      .catch((err) => {
        setState({ online: false, error: err.message || String(err) });
        return false;
      });

  const streams = [];
  function listen(path, query, onData) {
    if (!remote || !("EventSource" in window)) return;
    let mirror = null;
    const src = new EventSource(`${base}/${path}.json${query || ""}`);
    const handle = (merge) => (e) => {
      try {
        const { path: p, data } = JSON.parse(e.data);
        mirror = applyAt(mirror, p, data, merge);
        setState({ online: true, error: "" });
        onData(mirror || {});
      } catch {
        /* keep-alive 등 */
      }
    };
    src.addEventListener("put", handle(false));
    src.addEventListener("patch", handle(true));
    src.addEventListener("cancel", () => setState({ online: false, error: "권한 없음 (데이터베이스 규칙 확인)" }));
    src.onerror = () => setState({ online: false, error: "연결 중..." });   // EventSource가 스스로 다시 연결한다
    streams.push(src);
  }

  const link = {
    kind: remote ? "firebase" : channel ? "local" : "none",
    ward: settings.ward,
    get state() {
      return { ...state };
    },
    onState: (h) => onState.push(h),
    onCall: (h) => on("call", h),
    onAck: (h) => on("ack", h),
    onStatus: (h) => on("status", h),

    sendCall(info) {
      const m = { type: "call", id: newId(), at: Date.now(), ...info };
      seen.add(`call:${m.id}`);
      local(m);
      if (remote) put(`calls/${m.id}`, { id: m.id, at: m.at, bed: m.bed || "", patient: m.patient || "", count: m.count || 1 });
      return m.id;
    },
    sendAck(id, who) {
      const m = { type: "ack", id, who: who || "", at: Date.now() };
      seen.add(`ack:${id}`);
      local(m);
      if (remote) put(`calls/${id}/ack`, { who: m.who, at: m.at });
    },
    sendStatus(info) {
      const m = { type: "status", at: Date.now(), ...info };
      local(m);
      if (remote) put(`beds/${cleanKey(info.bed)}`, { bed: info.bed || "", patient: info.patient || "", state: info.state || "", device: deviceId(), at: m.at });
    },

    // 침상 등록 (의료진 앱). patient가 ""이면 빈 침상(퇴원)
    // 저장되면 이 기기 목록에도 바로 반영한다 (같은 탭에는 BroadcastChannel이 돌아오지 않음)
    async setRoster(bed, patient, code) {
      const m = { type: "roster", bed, patient: patient || "", code: code || "", at: Date.now() };
      const ok = remote ? await put(`roster/${cleanKey(bed)}`, { bed, patient: m.patient, code: m.code, at: m.at }) : true;
      if (ok) {
        local(m);
        emit("roster", m);
      }
      return ok;
    },
    async removeRoster(bed) {
      const m = { type: "roster", bed, removed: true, at: Date.now() };
      const ok = remote
        ? await fetch(`${base}/roster/${cleanKey(bed)}.json`, { method: "DELETE" }).then((r) => r.ok).catch(() => false)
        : true;
      if (ok) {
        local(m);
        emit("roster", m);
      }
      return ok;
    },
    // 등록된 침상 목록이 바뀔 때마다 { 침상키: { bed, patient, at } } 전체를 넘긴다
    // live: false면 Firebase 실시간 연결을 열지 않는다 (환자 앱은 readRoster로 가끔 읽음)
    watchRoster(cb, { live = true } = {}) {
      let roster = {};
      on("roster", (m) => {
        roster = { ...roster };
        if (m.removed) delete roster[cleanKey(m.bed)];
        else roster[cleanKey(m.bed)] = { bed: m.bed, patient: m.patient, code: m.code || "", at: m.at };
        cb(roster);
      });
      // 같은 브라우저 안에서 나중에 연 탭이 목록을 달라고 하면 알려 준다 (인터넷 없이 시연할 때)
      on("roster-request", () => Object.values(roster).forEach((e) => local({ type: "roster", ...e })));
      if (!remote) {
        cb(roster);                            // 빈 목록에서 시작하고, 다른 탭에 목록을 달라고 한다
        local({ type: "roster-request" });
      }
      if (live) {
        listen("roster", "", (data) => {
          roster = data || {};
          cb(roster);
        });
      }
    },
    // 등록된 침상 목록을 한 번 읽는다 (못 읽으면 null)
    async readRoster() {
      if (!remote) return null;
      try {
        const r = await fetch(`${base}/roster.json`);
        return r.ok ? (await r.json()) || {} : null;
      } catch {
        return null;
      }
    },
    // 침상 상태 전체를 한 번 읽는다 (환자 앱: 같은 침상을 다른 휴대폰이 쓰는지 확인).
    // 환자 앱이 실시간 연결을 여러 개 열지 않는 이유: 브라우저는 한 서버에 연결을 6개까지만 열어 두므로,
    // 노트북 한 대에 두 앱을 띄워 시연할 때 연결이 모자라 호출 전송이 멈출 수 있다.
    async readBeds() {
      if (!remote) return {};
      try {
        const r = await fetch(`${base}/beds.json`);
        return r.ok ? (await r.json()) || {} : {};
      } catch {
        return {};
      }
    },

    // 환자 앱: 내가 보낸 호출의 '확인'만 기다린다
    watchAcks() {
      listen("calls", '?orderBy="$key"&limitToLast=20', (calls) => {
        for (const c of Object.values(calls)) {
          if (c?.ack && c.id) deliver("ack", { id: c.id, who: c.ack.who, at: c.ack.at });
        }
      });
    },
    // 의료진 앱: 호출 · 확인 · 침상 상태를 모두 받는다
    watchAll() {
      const startedAt = Date.now();
      listen("calls", '?orderBy="$key"&limitToLast=50', (calls) => {
        const list = Object.values(calls).filter((c) => c?.id).sort((a, b) => a.at - b.at);
        for (const c of list) {
          if (!seen.has(`call:${c.id}`)) {
            // 켜기 전에 이미 확인된 호출이나 오래된 호출은 알람 없이 지나간다
            if (c.ack || startedAt - c.at > RECENT_MS) seen.add(`call:${c.id}`);
            else deliver("call", { type: "call", ...c });
          }
          if (c.ack) deliver("ack", { id: c.id, who: c.ack.who, at: c.ack.at });
        }
      });
      listen("beds", "", (beds) => {
        for (const b of Object.values(beds)) if (b?.bed) emit("status", b);
      });
    },
    close() {
      streams.forEach((s) => s.close());
      if (channel) channel.close();
    },
  };
  return link;
}
