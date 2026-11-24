// 음성 안내 (휴대폰 기본 한국어 음성, Web Speech API)
//   voice.say(text, tag)  : 순서대로 읽고, 다 읽으면 onFinished(tag, 끝난 시각)을 부른다
//   voice.interrupt(tag)  : 그 tag 문장을 읽는 중이거나 기다리는 중이면 끊는다
// 파이썬 output/tts.py의 say_async / poll_finished / interrupt와 같은 역할.
const now = () => performance.now() / 1000;

export class Voice {
  constructor(onFinished) {
    this.onFinished = onFinished || (() => {});
    this.queue = [];
    this.current = null;
    this.rate = 1.0;
    this.voice = null;
    this.synth = window.speechSynthesis || null;
    this._pickVoice();
    if (this.synth) this.synth.onvoiceschanged = () => this._pickVoice();
  }

  _pickVoice() {
    if (!this.synth) return;
    const voices = this.synth.getVoices().filter((v) => v.lang && v.lang.toLowerCase().startsWith("ko"));
    this.voice = voices.find((v) => /google|natural|online/i.test(v.name)) || voices[0] || null;
  }

  // 휴대폰 브라우저는 사용자가 화면을 누른 뒤에만 소리를 낼 수 있어서, 시작 버튼에서 한 번 부른다.
  unlock() {
    if (!this.synth) return;
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    this.synth.speak(u);
  }

  busy() {
    return this.current !== null || this.queue.length > 0;
  }

  say(text, tag = null) {
    this.queue.push({ text, tag });
    if (!this.current) this._next();
  }

  interrupt(tag) {
    this.queue = this.queue.filter((q) => q.tag !== tag);
    if (this.current && this.current.tag === tag) {
      const item = this.current;
      item.stopped = true;
      if (this.synth) this.synth.cancel();
      this._done(item);
    }
  }

  stopAll() {
    this.queue = [];
    if (this.current) this.current.stopped = true;
    this.current = null;
    if (this.synth) this.synth.cancel();
  }

  _next() {
    const item = this.queue.shift();
    if (!item) {
      this.current = null;
      return;
    }
    this.current = item;
    // 음성이 없거나 끝 신호가 오지 않는 기기를 위해, 글자 수로 잡은 시간이 지나면 끝난 것으로 본다
    const estimate = (1.2 + item.text.length * 0.16) / this.rate;
    item.timer = setTimeout(() => this._done(item), (estimate + 2.5) * 1000);
    if (!this.synth) return;
    const u = new SpeechSynthesisUtterance(item.text);
    u.lang = "ko-KR";
    u.rate = this.rate;
    if (this.voice) u.voice = this.voice;
    u.onend = () => this._done(item);
    u.onerror = () => this._done(item);
    item.utterance = u;            // 일부 브라우저는 참조가 없으면 onend 전에 지워 버린다
    this.synth.speak(u);
  }

  _done(item) {
    if (item.finished) return;
    item.finished = true;
    clearTimeout(item.timer);
    this.onFinished(item.tag, now());
    if (this.current === item) {
      this.current = null;
      this._next();
    }
  }
}
