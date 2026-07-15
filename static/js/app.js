// ===== ToneUp client app.js =====

let mediaRecorder = null;
let audioChunks = [];
let recordedBlob = null;
let timerInterval = null;
let recordStartTime = 0;

const recordBtn = document.getElementById("recordBtn");
const recLabel = recordBtn.querySelector(".rec-label");
const recordTimer = document.getElementById("recordTimer");
const transcriptEl = document.getElementById("transcript");
const feedbackList = document.getElementById("feedbackList");

const pronFill = document.getElementById("pronFill");
const pronValue = document.getElementById("pronValue");
const speedFill = document.getElementById("speedFill");
const speedValue = document.getElementById("speedValue");
const speedLabel = document.getElementById("speedLabel");

const statDuration = document.getElementById("statDuration");
const statWords = document.getElementById("statWords");
const statPauses = document.getElementById("statPauses");
const statPauseRatio = document.getElementById("statPauseRatio");

const statPitchMean = document.getElementById("statPitchMean");
const statPitchRange = document.getElementById("statPitchRange");
const statVolume = document.getElementById("statVolume");
const statVolumeCons = document.getElementById("statVolumeCons");
const statEmotion = document.getElementById("statEmotion");
const statEnergy = document.getElementById("statEnergy");

const overallFill = document.getElementById("overallFill");
const overallValue = document.getElementById("overallValue");
const overallGrade = document.getElementById("overallGrade");
const segmentsCard = document.getElementById("segmentsCard");
const segmentsList = document.getElementById("segmentsList");
const resultAudio = document.getElementById("resultAudio");
const readDiff = document.getElementById("readDiff");

const habitBody = document.getElementById("habitBody");
const downloadClientBtn = document.getElementById("downloadClient");
const downloadServerBtn = document.getElementById("downloadServer");
const downloadReportBtn = document.getElementById("downloadReport");

const aiCoaching = document.getElementById("aiCoaching");
const aiCoachingText = document.getElementById("aiCoachingText");
const aiImproved = document.getElementById("aiImproved");
const aiImprovedText = document.getElementById("aiImprovedText");
const historyList = document.getElementById("historyList");
const themeToggle = document.getElementById("themeToggle");

const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const dropOverlay = document.getElementById("dropOverlay");

const modeTabs = document.getElementById("modeTabs");
const promptText = document.getElementById("promptText");
const promptHint = document.getElementById("promptHint");
const newPromptBtn = document.getElementById("newPromptBtn");
const accuracyBox = document.getElementById("accuracyBox");
const accuracyValue = document.getElementById("accuracyValue");

const detailModal = document.getElementById("detailModal");
const modalTitle = document.getElementById("modalTitle");
const modalBody = document.getElementById("modalBody");

const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    try {
      await fetch("/api/logout", { method: "POST" });
    } catch (err) {
      console.error("logout error:", err);
    }
    window.location.href = "/login";
  });
}

// ====== 테마 전환 ======
let trendChart = null;
let lastHistoryRows = [];
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  if (themeToggle) themeToggle.textContent = t === "dark" ? "☀️" : "🌙";
  localStorage.setItem("toneup-theme", t);
  if (trendChart) renderTrend(lastHistoryRows); // 차트 색상 갱신
  // 녹음 중이 아니면 파형 캔버스 기준선도 테마에 맞춰 갱신
  if (
    typeof drawIdleBaseline === "function" &&
    !(mediaRecorder && mediaRecorder.state === "recording")
  ) {
    drawIdleBaseline();
  }
}
applyTheme(document.documentElement.dataset.theme || "light");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

// ====== 결과 등장 애니메이션 ======
function revealResults() {
  const cards = document.querySelectorAll(
    ".left-col .card:not(:first-child), .right-col .card"
  );
  cards.forEach((el) => {
    el.classList.remove("fade-in");
    void el.offsetWidth; // 리플로우로 애니메이션 재시작
    el.classList.add("fade-in");
  });
}

// ====== 타이머 ======
function startTimer() {
  recordStartTime = Date.now();
  recordTimer.style.display = "block";
  recordTimer.textContent = "00:00";
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - recordStartTime) / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    recordTimer.textContent = `${mm}:${ss}`;
  }, 250);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}

// ====== 분석 중 로딩 상태 ======
let analyzeInterval = null;
function setAnalyzing(on) {
  if (on) {
    recordBtn.disabled = true;
    if (uploadBtn) uploadBtn.disabled = true;
    const started = Date.now();
    transcriptEl.innerHTML =
      '<div class="analyzing"><span class="spinner"></span>' +
      '<span>음성을 분석하고 있어요… <b id="analyzeElapsed">0초</b></span></div>';
    const el = document.getElementById("analyzeElapsed");
    analyzeInterval = setInterval(() => {
      if (el) el.textContent = `${Math.floor((Date.now() - started) / 1000)}초`;
    }, 500);
  } else {
    recordBtn.disabled = false;
    if (uploadBtn) uploadBtn.disabled = false;
    clearInterval(analyzeInterval);
    analyzeInterval = null;
  }
}

// ====== 녹음 시작/종료 ======
recordBtn.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    recLabel.textContent = "녹음 시작";
    recordBtn.classList.remove("recording");
    stopVisualizer();
    stopTimer();
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    alert("마이크 권한이 필요합니다. 브라우저 설정을 확인해주세요.");
    console.error(err);
    return;
  }

  startVisualizer(stream);
  startTimer();

  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];

  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    // 마이크 트랙 해제
    stream.getTracks().forEach((t) => t.stop());

    recordedBlob = new Blob(audioChunks, {
      type: audioChunks[0] ? audioChunks[0].type : "audio/webm",
    });
    downloadClientBtn.style.display = "inline-block";

    let ext = "webm";
    if (recordedBlob.type.includes("wav")) ext = "wav";
    else if (recordedBlob.type.includes("ogg")) ext = "ogg";
    else if (recordedBlob.type.includes("mp4")) ext = "mp4";

    const fd = new FormData();
    fd.append("audio", recordedBlob, `input.${ext}`);
    analyzeForm(fd);
  };

  mediaRecorder.start();
  recLabel.textContent = "녹음 종료";
  recordBtn.classList.add("recording");
});

// ====== 공통 fetch (세션 만료 시 로그인으로) ======
async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = "/login"; // 세션 만료
    throw new Error("unauthenticated");
  }
  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    /* 413/프록시 에러 등 비JSON 응답 */
  }
  return { res, data };
}

// ====== 공통 분석 요청 (녹음·업로드 공용) ======
async function analyzeForm(fd) {
  fd.append("mode", currentMode);
  fd.append("context", currentMode === "free" ? "" : currentTarget || "");
  setAnalyzing(true);
  try {
    const { res, data } = await fetchJSON("/process_audio", { method: "POST", body: fd });
    if (!res.ok || !data || data.error) {
      const fallback =
        res.status === 413 ? "파일이 너무 큽니다. 더 작은 파일로 시도해보세요." : "분석 실패";
      transcriptEl.textContent = "❌ " + ((data && data.error) || fallback);
      console.error("analyze failed:", res.status, data);
      return;
    }
    applyResult(data);
    loadHistory();
    loadStats();
  } catch (err) {
    console.error("Analyze error:", err);
    if (err.message !== "unauthenticated") {
      transcriptEl.textContent = "❌ 업로드 중 오류가 발생했습니다. 네트워크를 확인해주세요.";
    }
  } finally {
    setAnalyzing(false);
  }
}

// ====== 파일 업로드 / 드래그&드롭 ======
function analyzeFile(file) {
  if (!file) return;
  recordedBlob = file; // 브라우저 다운로드용
  downloadClientBtn.style.display = "inline-block";
  const fd = new FormData();
  fd.append("audio", file, file.name || "upload");
  analyzeForm(fd);
}

if (uploadBtn && fileInput) {
  uploadBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    analyzeFile(e.target.files[0]);
    fileInput.value = "";
  });
}

function _dragHasFiles(e) {
  return e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
}
let _dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (!_dragHasFiles(e)) return;
  _dragDepth++;
  dropOverlay.style.display = "flex";
});
window.addEventListener("dragover", (e) => {
  if (_dragHasFiles(e)) e.preventDefault();
});
window.addEventListener("dragleave", () => {
  _dragDepth = Math.max(0, _dragDepth - 1);
  if (_dragDepth === 0) dropOverlay.style.display = "none";
});
window.addEventListener("drop", (e) => {
  if (!_dragHasFiles(e)) return;
  e.preventDefault();
  _dragDepth = 0;
  dropOverlay.style.display = "none";
  analyzeFile(e.dataTransfer.files[0]);
});

// ====== 종합 점수 게이지 ======
function gradeOf(s) {
  return s >= 90 ? "A+" : s >= 80 ? "A" : s >= 70 ? "B" : s >= 60 ? "C" : "D";
}
function scoreColor(s) {
  return s >= 80 ? "#10b981" : s >= 60 ? "#f59e0b" : "#ef4444";
}
function renderOverall(score) {
  if (!overallFill) return;
  if (!Number.isFinite(score)) {
    overallValue.textContent = "--";
    overallGrade.textContent = "";
    overallFill.style.background = "";
    return;
  }
  const c = scoreColor(score);
  overallFill.style.background = `conic-gradient(${c} ${score}%, var(--track) ${score}%)`;
  overallValue.innerHTML = `${score}<small>점</small>`;
  overallGrade.textContent = `등급 ${gradeOf(score)}`;
  overallGrade.style.color = c;
}

// ====== 문장별 분석 ======
function segBadge(cls, label) {
  return `<span class="seg-badge ${cls}">${label}</span>`;
}
function renderSegments(segments) {
  if (!segmentsCard) return;
  if (!Array.isArray(segments) || segments.length < 2) {
    segmentsCard.style.display = "none"; // 문장이 하나뿐이면 전체 지표와 중복
    return;
  }
  const clarities = segments.filter((s) => s.clarity != null).map((s) => s.clarity);
  const worstClarity = clarities.length ? Math.min(...clarities) : null;

  segmentsList.innerHTML = "";
  segments.forEach((s) => {
    const speedCls = s.sps > 5.5 || s.sps < 2.0 ? "mid" : "good";
    const speedLabel = s.sps > 5.5 ? `빠름 ${s.sps}` : s.sps < 2.0 ? `느림 ${s.sps}` : `${s.sps} 음절/초`;
    let clarityHtml = "";
    if (s.clarity != null) {
      const cls = s.clarity >= 75 ? "good" : s.clarity >= 60 ? "mid" : "low";
      clarityHtml = segBadge(cls, `명료도 ${s.clarity}`);
    }
    const isWorst =
      worstClarity != null && s.clarity === worstClarity && worstClarity < 65 && segments.length > 1;
    const div = document.createElement("div");
    div.className = "segment-item" + (isWorst ? " worst" : "");
    div.innerHTML =
      `<div class="seg-text">${escapeHtml(s.text)}</div>` +
      `<div class="seg-meta"><span class="seg-time">${s.start}s–${s.end}s</span>` +
      segBadge(speedCls, speedLabel) + clarityHtml +
      (isWorst ? '<span class="seg-worst-tag">가장 흐림</span>' : "") +
      `</div>`;
    segmentsList.appendChild(div);
  });
  segmentsCard.style.display = "block";
}

// ====== 녹음 다시 듣기 ======
function showAudio(el, wavFile) {
  if (!el) return;
  if (!wavFile) {
    el.style.display = "none";
    el.removeAttribute("src");
    return;
  }
  el.src = `/audio/${wavFile}`;
  el.style.display = "block";
  el.onerror = () => { el.style.display = "none"; }; // TTL 만료 등으로 파일이 없으면 숨김
}

// ====== 분석 결과 반영 ======
function applyResult(data) {
  renderTranscript(data.text, data.habits);
  updateAccuracy(data.text);

  feedbackList.innerHTML = "";
  (data.feedback || []).forEach((msg) => {
    const d = document.createElement("div");
    d.className = "fb";
    d.textContent = msg;
    feedbackList.appendChild(d);
  });

  // 종합 점수 · 문장별 분석 · 다시 듣기
  renderOverall(data.overall_score);
  renderSegments(data.segments);
  showAudio(resultAudio, data.wav_file);

  // 발음 점수 게이지
  const pron = Number.isFinite(data.pron_score) ? data.pron_score : 0;
  const pronPct = Math.min(100, Math.max(0, pron));
  pronFill.style.background = `conic-gradient(#10b981 ${pronPct}%, var(--track) ${pronPct}%)`;
  pronValue.innerHTML = `${pron}<small>점</small>`;

  // 말 속도 게이지 (SPS 기준: 4.5 SPS를 가득 참으로)
  const sps = data.sps || 0;
  const speedPct = Math.min(100, Math.round((sps / 4.5) * 100));
  speedFill.style.background = `conic-gradient(#6366f1 ${speedPct}%, var(--track) ${speedPct}%)`;
  speedValue.innerHTML = `${sps}<small>음절/초</small>`;
  speedLabel.textContent = `${data.speed_label || ""} · ${data.wpm || 0} WPM`;

  // 통계
  statDuration.textContent = `${data.duration ?? "--"}초`;
  statWords.textContent = `${data.word_count ?? "--"}개`;
  statPauses.textContent = `${data.pause_count ?? "--"}회`;
  statPauseRatio.textContent = `${data.pause_ratio ?? "--"}%`;

  // 음성 특성
  statPitchMean.textContent = data.pitch_mean ? `${data.pitch_mean} Hz` : "--";
  statPitchRange.textContent = `${data.pitch_range ?? "--"}반음 (${data.pitch_label ?? ""})`;
  statVolume.textContent = `${data.volume_db ?? "--"}dB (${data.volume_label ?? ""})`;
  statVolumeCons.textContent = `${data.volume_consistency ?? "--"}점`;
  statEmotion.textContent = data.emotion_label ?? "--";
  statEnergy.textContent = data.energy != null ? `${data.energy}/100` : "--";

  // 습관어
  habitBody.innerHTML = "";
  (data.habits || []).forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${item.word}</td><td>${item.count}회</td>`;
    if (item.count > 0) row.classList.add("habit-hit");
    habitBody.appendChild(row);
  });

  // AI 코칭
  if (data.ai_coaching) {
    aiCoaching.style.display = "block";
    aiCoachingText.textContent = data.ai_coaching;
  } else {
    aiCoaching.style.display = "none";
  }

  // AI 말투 개선
  if (data.ai_improved) {
    aiImproved.style.display = "block";
    aiImprovedText.textContent = data.ai_improved;
  } else {
    aiImproved.style.display = "none";
  }

  if (data.server_file_url) {
    downloadServerBtn.style.display = "inline-block";
    downloadServerBtn.onclick = () => {
      window.location.href = data.server_file_url;
    };
  } else {
    downloadServerBtn.style.display = "none";
  }

  // PDF 리포트
  if (data.record_id) {
    downloadReportBtn.style.display = "inline-block";
    downloadReportBtn.onclick = () => {
      window.location.href = `/report/${data.record_id}`;
    };
  } else {
    downloadReportBtn.style.display = "none";
  }

  revealResults();
}

// ====== 히스토리 ======
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function loadHistory() {
  try {
    const { data: rows } = await fetchJSON("/history");
    lastHistoryRows = Array.isArray(rows) ? rows : [];
    renderTrend(lastHistoryRows);

    if (!Array.isArray(rows) || rows.length === 0) {
      historyList.textContent = "(아직 기록이 없습니다)";
      return;
    }
    historyList.innerHTML = "";
    rows.forEach((r) => {
      const item = document.createElement("div");
      item.className = "history-item";
      const when = (r.created_at || "").replace("T", " ");
      const preview = escapeHtml((r.text || "(텍스트 없음)").slice(0, 40));
      item.innerHTML =
        `<button class="hi-del" title="삭제" data-id="${r.id}">×</button>` +
        `<div class="hi-link" data-id="${r.id}">` +
        `<div class="hi-top"><b>#${r.id}</b><span>${when}</span></div>` +
        `<div class="hi-text">${preview}</div>` +
        `<div class="hi-meta">` +
        (r.overall_score != null ? `종합 ${r.overall_score}점 · ` : "") +
        `발음 ${r.pron_score ?? "--"}점 · ${r.sps ?? "--"} 음절/초 · ` +
        `${r.speed_label ?? ""} · 습관어 ${r.total_habits ?? 0}회</div>` +
        `</div>`;
      historyList.appendChild(item);
    });
  } catch (err) {
    console.error("history error:", err);
  }
}

// 삭제 / 상세보기 (이벤트 위임)
historyList.addEventListener("click", async (e) => {
  const del = e.target.closest(".hi-del");
  if (del) {
    e.preventDefault();
    if (!confirm(`기록 #${del.dataset.id}을 삭제할까요?`)) return;
    try {
      await fetchJSON(`/history/${del.dataset.id}`, { method: "DELETE" });
      loadHistory();
      loadStats(); // 삭제 후 성장 요약도 갱신
    } catch (err) {
      console.error("delete error:", err);
    }
    return;
  }
  const link = e.target.closest(".hi-link");
  if (link) openDetail(link.dataset.id);
});

// ====== 성장 추이 차트 ======
function renderTrend(rows) {
  const canvas = document.getElementById("trendChart");
  if (!canvas || typeof Chart === "undefined") return;

  const dark = document.documentElement.dataset.theme === "dark";
  const tickColor = dark ? "#a1a1aa" : "#52525b";
  const gridColor = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.06)";

  // 오래된 → 최신 순으로
  const data = (rows || []).slice().reverse();
  const labels = data.map((r) => `#${r.id}`);

  const cfg = {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "종합 점수",
          data: data.map((r) => r.overall_score),
          borderColor: "#8b5cf6",
          backgroundColor: "rgba(139,92,246,0.1)",
          yAxisID: "y",
          tension: 0.3,
        },
        {
          label: "발음 점수",
          data: data.map((r) => r.pron_score),
          borderColor: "#10b981",
          backgroundColor: "rgba(16,185,129,0.1)",
          yAxisID: "y",
          tension: 0.3,
        },
        {
          label: "말속도(SPS)",
          data: data.map((r) => r.sps),
          borderColor: "#6366f1",
          backgroundColor: "rgba(99,102,241,0.1)",
          yAxisID: "y1",
          tension: 0.3,
        },
        {
          label: "억양 변화폭(반음)",
          data: data.map((r) => r.pitch_range),
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245,158,11,0.1)",
          yAxisID: "y1",
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: tickColor } } },
      scales: {
        x: { ticks: { color: tickColor }, grid: { color: gridColor } },
        y: { type: "linear", position: "left", min: 0, max: 100,
             title: { display: true, text: "발음 점수", color: tickColor },
             ticks: { color: tickColor }, grid: { color: gridColor } },
        y1: { type: "linear", position: "right", min: 0,
              title: { display: true, text: "SPS / 반음", color: tickColor },
              ticks: { color: tickColor }, grid: { drawOnChartArea: false } },
      },
    },
  };

  // 테마 색상이 옵션에 반영되도록 재생성
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(canvas, cfg);
}

// 페이지 로드 시 히스토리 표시
loadHistory();

// ====== 브라우저 원본 다운로드 ======
downloadClientBtn.addEventListener("click", () => {
  if (!recordedBlob) {
    alert("녹음 파일이 없습니다.");
    return;
  }
  const url = URL.createObjectURL(recordedBlob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "toneup_recording.webm";
  a.click();
  URL.revokeObjectURL(url);
});

// ====== 인식 텍스트 하이라이트 (습관어 강조) ======
function renderTranscript(text, habits) {
  if (!text) {
    transcriptEl.textContent = "(인식된 텍스트 없음)";
    return;
  }
  const set = new Set((habits || []).map((h) => h.word));
  const parts = text.split(/(\s+)/);
  transcriptEl.innerHTML = parts
    .map((tok) => {
      if (tok === "" || /^\s+$/.test(tok)) return tok;
      const stripped = tok.replace(/[^가-힣a-zA-Z0-9]/g, "");
      const safe = escapeHtml(tok);
      return set.has(stripped) ? `<mark class="filler">${safe}</mark>` : safe;
    })
    .join("");
}

// ====== 연습 모드 (자유 / 읽기 / 면접 / 발표) ======
const PRACTICE_SENTENCES = [
  "간장 공장 공장장은 강 공장장이고 된장 공장 공장장은 장 공장장이다.",
  "저기 계신 저 분이 박 법학박사이고 이 분이 백 법학박사이다.",
  "내가 그린 기린 그림은 잘 그린 기린 그림이다.",
  "경찰청 철창살은 외철창살이고 검찰청 철창살은 쌍철창살이다.",
  "차분하고 또렷한 목소리로 핵심을 전달하는 연습을 합니다.",
  "작은 차이가 명품을 만든다는 말을 늘 마음에 새깁니다.",
];
const INTERVIEW_QUESTIONS = [
  "자기소개를 1분 동안 해주세요.",
  "본인의 가장 큰 강점과 약점은 무엇인가요?",
  "지원 동기와 입사 후 포부를 말씀해주세요.",
  "팀에서 갈등을 겪었던 경험과 해결 방법을 설명해주세요.",
  "가장 도전적이었던 프로젝트와 거기서 배운 점은 무엇인가요?",
  "5년 후 본인의 모습을 어떻게 그리고 있나요?",
];
const PRESENTATION_TOPICS = [
  "최근 읽은 책이나 본 영화를 1분간 소개해보세요.",
  "우리 팀에 새 도구 도입을 제안하는 발표를 해보세요.",
  "프로젝트 진행 현황을 보고하는 발표를 해보세요.",
  "신제품의 핵심 가치를 청중에게 설득해보세요.",
  "자신의 하루 루틴을 발표하듯 설명해보세요.",
];

const MODE_INFO = {
  free: { hint: "어떤 말이든 분석해 코칭해 드립니다.", showBtn: false },
  reading: { hint: "이 문장을 또박또박 읽고 녹음해 발음·정확도를 확인해보세요.", showBtn: true, pool: PRACTICE_SENTENCES, btn: "🔀 다른 문장" },
  interview: { hint: "질문에 답하듯 녹음하면 면접관 관점으로 코칭합니다.", showBtn: true, pool: INTERVIEW_QUESTIONS, btn: "🔀 다른 질문" },
  presentation: { hint: "주제로 발표하듯 녹음하면 전달력을 코칭합니다.", showBtn: true, pool: PRESENTATION_TOPICS, btn: "🔀 다른 주제" },
};

let currentMode = "free";
let currentTarget = "";

function _pick(pool, exclude) {
  let next = exclude;
  while (next === exclude && pool.length > 1) {
    next = pool[Math.floor(Math.random() * pool.length)];
  }
  return next;
}

function newPrompt() {
  const info = MODE_INFO[currentMode];
  if (!info.pool) return;
  currentTarget = _pick(info.pool, currentTarget);
  promptText.textContent = currentTarget;
  accuracyBox.style.display = "none";
}

function setMode(mode) {
  currentMode = mode;
  currentTarget = "";
  const info = MODE_INFO[mode];
  [...modeTabs.querySelectorAll(".mode-tab")].forEach((t) =>
    t.classList.toggle("active", t.dataset.mode === mode)
  );
  promptHint.textContent = info.hint;
  accuracyBox.style.display = "none";
  newPromptBtn.style.display = info.showBtn ? "inline-block" : "none";
  if (info.showBtn) {
    newPromptBtn.textContent = info.btn;
    newPrompt();
  } else {
    promptText.textContent = "자유롭게 말하고 녹음 버튼을 눌러보세요.";
  }
}

if (modeTabs) {
  modeTabs.addEventListener("click", (e) => {
    const tab = e.target.closest(".mode-tab");
    if (tab) setMode(tab.dataset.mode);
  });
}
if (newPromptBtn) newPromptBtn.addEventListener("click", newPrompt);
setMode("free");

// 읽기 모드에서만 목표 문장 대비 정확도 측정
function _normalize(s) {
  return (s || "").replace(/[^가-힣a-zA-Z0-9]/g, "").toLowerCase();
}
function _levenshtein(a, b) {
  const m = a.length, n = b.length;
  if (!m) return n;
  if (!n) return m;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  let cur = new Array(n + 1);
  for (let i = 1; i <= m; i++) {
    cur[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, cur] = [cur, prev];
  }
  return prev[n];
}
// 목표 문장을 단어 단위로 정렬해 틀리게 읽은 단어를 표시한다.
function renderReadingDiff(target, recognized) {
  const tWords = (target || "").split(/\s+/).filter(Boolean);
  const rNorm = (recognized || "").split(/\s+/).map(_normalize).filter(Boolean);
  const tNorm = tWords.map(_normalize);
  const m = tNorm.length, n = rNorm.length;

  // 단어 단위 편집거리 DP + 역추적으로 '정확히 일치한' 목표 단어 표시
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = tNorm[i - 1] === rNorm[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  const ok = new Array(m).fill(false);
  let i = m, j = n;
  while (i > 0 && j > 0) {
    if (tNorm[i - 1] === rNorm[j - 1] && dp[i][j] === dp[i - 1][j - 1]) {
      ok[i - 1] = true; i--; j--;
    } else if (dp[i][j] === dp[i - 1][j - 1] + 1) { i--; j--; }
    else if (dp[i][j] === dp[i - 1][j] + 1) { i--; }
    else { j--; }
  }
  const missed = ok.filter((v) => !v).length;
  const html = tWords
    .map((w, k) => (ok[k] ? escapeHtml(w) : `<mark class="miss">${escapeHtml(w)}</mark>`))
    .join(" ");
  return { html, missed };
}

function updateAccuracy(recognized) {
  if (!accuracyBox || currentMode !== "reading" || !currentTarget) return;
  const a = _normalize(currentTarget);
  const b = _normalize(recognized);
  if (!a || !b) {
    accuracyBox.style.display = "none";
    return;
  }
  const sim = 1 - _levenshtein(a, b) / Math.max(a.length, b.length);
  const pct = Math.max(0, Math.round(sim * 100));
  accuracyValue.textContent = `${pct}%`;
  accuracyBox.className =
    "accuracy-box " + (pct >= 80 ? "good" : pct >= 50 ? "mid" : "low");

  // 틀리게 읽은 단어 하이라이트
  if (readDiff) {
    const diff = renderReadingDiff(currentTarget, recognized);
    if (diff.missed > 0) {
      readDiff.innerHTML =
        `<span class="read-diff-label">다시 읽어볼 단어</span> ${diff.html}`;
      readDiff.style.display = "block";
    } else {
      readDiff.style.display = "none";
    }
  }
  accuracyBox.style.display = "block";
}

// ====== 성장 요약 ======
async function loadStats() {
  try {
    const { data: s } = await fetchJSON("/stats");
    const set = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.textContent = v;
    };
    if (!s || !s.sessions) {
      set("gSessions", "0"); set("gStreak", "--"); set("gAvgOverall", "--");
      set("gAvgPron", "--"); set("gBestPron", "--");
      set("gAvgSps", "--"); set("gImprove", "--");
      return;
    }
    const imp = s.improvement;
    set("gSessions", `${s.sessions}회`);
    set("gStreak", s.streak > 0 ? `🔥 ${s.streak}일` : "0일");
    set("gAvgOverall", s.avg_overall != null ? `${s.avg_overall}점` : "--");
    set("gAvgPron", `${s.avg_pron}점`);
    set("gBestPron", `${s.best_pron}점`);
    set("gAvgSps", `${s.avg_sps}`);
    set("gImprove", `${imp > 0 ? "▲ +" : imp < 0 ? "▼ " : ""}${imp}점`);
    const gi = document.getElementById("gImprove");
    if (gi) gi.style.color = imp > 0 ? "var(--green)" : imp < 0 ? "var(--red)" : "var(--text)";
  } catch (err) {
    console.error("stats error:", err);
  }
}
loadStats();

// ====== 기록 상세 모달 ======
function showModal() {
  if (detailModal) detailModal.style.display = "flex";
}
function hideModal() {
  if (detailModal) detailModal.style.display = "none";
}
async function openDetail(id) {
  try {
    const { res, data: r } = await fetchJSON(`/history/${id}`);
    if (!res.ok || !r) return;
    modalTitle.textContent = `기록 #${r.id}`;
    modalBody.innerHTML = renderDetail(r);
    showModal();
  } catch (err) {
    console.error("detail error:", err);
  }
}
function renderDetail(r) {
  const habits =
    (r.habits || [])
      .filter((h) => h.count > 0)
      .map((h) => `${h.word}(${h.count})`)
      .join(", ") || "없음";
  const fb = (r.feedback || []).map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  const ai = r.ai_coaching
    ? `<div class="ai-coaching"><h5>✦ AI 코칭</h5><p>${escapeHtml(r.ai_coaching)}</p></div>`
    : "";
  const audio = r.wav_file
    ? `<audio controls preload="none" style="width:100%;margin:10px 0;" src="/audio/${encodeURIComponent(r.wav_file)}" onerror="this.style.display='none'"></audio>`
    : "";
  const segs =
    Array.isArray(r.segments) && r.segments.length >= 2
      ? `<h4 class="card-title">문장별 분석</h4><div class="segments-list">` +
        r.segments
          .map(
            (s) =>
              `<div class="segment-item"><div class="seg-text">${escapeHtml(s.text)}</div>` +
              `<div class="seg-meta"><span class="seg-time">${s.start}s–${s.end}s</span>` +
              `<span class="seg-badge good">${s.sps} 음절/초</span>` +
              (s.clarity != null ? `<span class="seg-badge ${s.clarity >= 75 ? "good" : s.clarity >= 60 ? "mid" : "low"}">명료도 ${s.clarity}</span>` : "") +
              `</div></div>`
          )
          .join("") +
        `</div>`
      : "";
  return (
    `<p class="modal-date">${(r.created_at || "").replace("T", " ")}</p>` +
    audio +
    `<div class="modal-transcript">${escapeHtml(r.text || "(텍스트 없음)")}</div>` +
    `<ul class="stat-list">` +
    (r.overall_score != null
      ? `<li><span>종합 점수</span><b style="color:${scoreColor(r.overall_score)}">${r.overall_score}점 (${gradeOf(r.overall_score)})</b></li>`
      : "") +
    `<li><span>발음 점수</span><b>${r.pron_score ?? "--"}점</b></li>` +
    `<li><span>말 속도</span><b>${r.sps ?? "--"} 음절/초 (${r.speed_label ?? ""})</b></li>` +
    `<li><span>녹음 길이</span><b>${r.duration ?? "--"}초</b></li>` +
    `<li><span>휴지</span><b>${r.pause_count ?? "--"}회 / ${r.pause_ratio ?? "--"}%</b></li>` +
    `<li><span>억양</span><b>${r.pitch_range ?? "--"}반음 (${r.pitch_label ?? ""})</b></li>` +
    `<li><span>음량</span><b>${r.volume_db ?? "--"}dB (${r.volume_label ?? ""})</b></li>` +
    `<li><span>습관어</span><b>${escapeHtml(habits)}</b></li>` +
    `</ul>` +
    segs +
    `<h4 class="card-title">코칭 피드백</h4><ul class="modal-feedback">${fb}</ul>` +
    ai +
    `<div class="file-actions"><a class="btn primary" href="/report/${r.id}">📄 PDF 리포트 다운로드</a></div>`
  );
}
if (detailModal) {
  detailModal.addEventListener("click", (e) => {
    if (e.target.hasAttribute("data-close")) hideModal();
  });
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") hideModal();
});
