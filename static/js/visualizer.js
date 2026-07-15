/* visualizer.js — 실시간 파형 */
const visCanvas = document.getElementById('visualizer');
const visCtx = visCanvas ? visCanvas.getContext('2d') : null;

let audioCtx, analyser, dataArray, sourceNode;
let rafId = null;       // 애니메이션 프레임 id (정지 시 취소)
let running = false;    // 그리기 루프 동작 여부

function _sizeCanvas() {
  // 고해상도(레티나) 대응: devicePixelRatio 만큼 백버퍼를 키우고 좌표계를 스케일.
  const dpr = window.devicePixelRatio || 1;
  const w = visCanvas.clientWidth;
  const h = visCanvas.clientHeight;
  visCanvas.width = Math.round(w * dpr);
  visCanvas.height = Math.round(h * dpr);
  visCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w, h };
}

function _isDark() {
  return document.documentElement.dataset.theme === 'dark';
}

function _clear(w, h) {
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--canvas-bg').trim();
  visCtx.fillStyle = bg || (_isDark() ? '#131318' : '#fafafb');
  visCtx.fillRect(0, 0, w, h);
}

function startVisualizer(stream) {
  if (!visCanvas || !visCtx) return;

  const { w, h } = _sizeCanvas();

  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;

  sourceNode = audioCtx.createMediaStreamSource(stream);
  sourceNode.connect(analyser);
  const bufferLength = analyser.frequencyBinCount;
  dataArray = new Uint8Array(bufferLength);

  running = true;

  function draw() {
    // 정지됐거나 컨텍스트가 닫혔으면 루프 종료
    if (!running || !audioCtx || audioCtx.state === 'closed') return;
    rafId = requestAnimationFrame(draw);

    analyser.getByteTimeDomainData(dataArray);
    _clear(w, h);

    visCtx.lineWidth = 2;
    visCtx.strokeStyle = '#6366f1';
    visCtx.beginPath();

    const sliceWidth = w / bufferLength;
    let x = 0;
    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0;   // 128 = 무음(중앙)
      const y = (v * h) / 2;
      if (i === 0) visCtx.moveTo(x, y);
      else visCtx.lineTo(x, y);
      x += sliceWidth;
    }
    visCtx.stroke();
  }
  draw();
}

function drawIdleBaseline() {
  // 대기 상태(녹음 전/종료 후)의 중앙 기준선
  if (!visCanvas || !visCtx) return;
  const { w, h } = _sizeCanvas();
  _clear(w, h);
  visCtx.lineWidth = 2;
  visCtx.strokeStyle = _isDark() ? '#3f3f46' : '#e0e0e5';
  visCtx.beginPath();
  visCtx.moveTo(0, h / 2);
  visCtx.lineTo(w, h / 2);
  visCtx.stroke();
}

function stopVisualizer() {
  running = false;
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  if (audioCtx && audioCtx.state !== 'closed') {
    audioCtx.close();
  }
  // 정지 시 중앙 기준선을 그려 깔끔하게 마무리
  drawIdleBaseline();
}

// 페이지 로드 시에도 대기 기준선을 표시
drawIdleBaseline();
