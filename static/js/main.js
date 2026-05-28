/* ===== STATE ===== */
let selectedFile = null;
let isAnalyzing = false;

/* ===== INIT ===== */
document.addEventListener('DOMContentLoaded', () => {
  setupDragDrop();
  setupTabs();
  document.getElementById('fileInput').addEventListener('change', onFileSelect);
  document.getElementById('removeFile').addEventListener('click', onRemoveFile);
  document.getElementById('analyzeBtn').addEventListener('click', onAnalyze);
  document.getElementById('selectFileBtn').addEventListener('click', e => {
    e.stopPropagation();
    document.getElementById('fileInput').click();
  });
});

/* ===== DRAG & DROP ===== */
function setupDragDrop() {
  const zone = document.getElementById('dropZone');

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', e => {
    if (!zone.contains(e.relatedTarget)) zone.classList.remove('drag-over');
  });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
  });

  // 파일이 없을 때만 드롭존 클릭 → 파일 선택창
  zone.addEventListener('click', e => {
    if (selectedFile) return;                           // 파일 이미 선택됨 → 무시
    if (e.target.id === 'selectFileBtn') return;        // 버튼 자체 클릭은 버튼 핸들러가 처리
    if (e.target.closest('#filePreview')) return;       // 미리보기 영역 클릭 → 무시
    document.getElementById('fileInput').click();
  });
}

function onFileSelect(e) {
  const file = e.target.files[0];
  if (file) setFile(file);
  // value 초기화 → 같은 파일 재선택 가능하게
  e.target.value = '';
}

function setFile(file) {
  selectedFile = file;
  document.getElementById('fileName').textContent = file.name;
  document.getElementById('filePreview').hidden = false;
  document.getElementById('dropContent').hidden = true;
  document.getElementById('dropZone').classList.add('has-file');
  document.getElementById('analyzeBtn').disabled = false;
  hideError();
}

function onRemoveFile(e) {
  e.stopPropagation();
  selectedFile = null;
  document.getElementById('fileInput').value = '';
  document.getElementById('filePreview').hidden = true;
  document.getElementById('dropContent').hidden = false;
  document.getElementById('dropZone').classList.remove('has-file');
  document.getElementById('analyzeBtn').disabled = true;
}

/* ===== TABS ===== */
function setupTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });
}

/* ===== ANALYZE ===== */
async function onAnalyze() {
  if (!selectedFile || isAnalyzing) return;

  isAnalyzing = true;
  hideError();
  showLoading();

  const formData = new FormData();
  formData.append('file', selectedFile);
  formData.append('context', document.getElementById('contextInput').value);

  try {
    const res = await fetch('/analyze', { method: 'POST', body: formData });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `서버 오류 (${res.status})`);
    }

    // SSE 스트림 읽기
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let gotResult = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop();

      for (const chunk of parts) {
        if (!chunk.trim()) continue;
        const lines = chunk.split('\n');
        const evtLine = lines.find(l => l.startsWith('event:'));
        const dataLine = lines.find(l => l.startsWith('data:'));
        if (!evtLine || !dataLine) continue;

        const eventType = evtLine.slice(6).trim();
        let data;
        try {
          data = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue;
        }

        if (eventType === 'progress') {
          window._currentMsg = data.message;
          updateLoadingStep(data.step);
          updateLoadingMessage(data.message);
        } else if (eventType === 'done') {
          gotResult = true;
          hideLoading();
          renderResults(data.result);
          return;
        } else if (eventType === 'error') {
          throw new Error(data.message);
        }
      }
    }

    if (!gotResult) {
      throw new Error('분석 결과를 받지 못했습니다. 파일을 확인 후 다시 시도해주세요.');
    }

  } catch (err) {
    hideLoading();
    showError(err.message);
  } finally {
    isAnalyzing = false;
  }
}

function updateLoadingStep(step) {
  // step은 1~4, 현재 step만 active, 이전 step은 done
  ['step1', 'step2', 'step3', 'step4'].forEach((id, i) => {
    const el = document.getElementById(id);
    el.classList.remove('active', 'done');
    if (i < step - 1)      el.classList.add('done');
    else if (i === step - 1) el.classList.add('active');
  });
  // 메시지도 업데이트
  const stepEl = document.getElementById('step' + step);
  if (stepEl && window._currentMsg) {
    stepEl.dataset.msg = window._currentMsg;
  }
}

/* ===== LOADING ===== */
function showLoading() {
  document.getElementById('loadingOverlay').hidden = false;
  document.getElementById('resultsSection').hidden = true;
  document.getElementById('analyzeBtn').disabled = true;
  document.getElementById('step1').classList.add('active');
  document.getElementById('loadingMsg').textContent = '파일 읽는 중...';
}

function updateLoadingMessage(msg) {
  const el = document.getElementById('loadingMsg');
  if (el) el.textContent = msg;
}

function hideLoading() {
  document.getElementById('loadingOverlay').hidden = true;
  ['step1', 'step2', 'step3', 'step4'].forEach(id => {
    document.getElementById(id).classList.remove('active', 'done');
  });
  document.getElementById('analyzeBtn').disabled = !selectedFile;
}

/* ===== ERROR BANNER ===== */
function showError(msg) {
  const banner = document.getElementById('errorBanner');
  document.getElementById('errorBannerMsg').textContent = msg;
  banner.hidden = false;
  banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideError() {
  document.getElementById('errorBanner').hidden = true;
}

/* ===== RENDER RESULTS ===== */
function renderResults(r) {
  const s = r.summary || {};

  const riskMap = { '낮음': 'risk-low', '보통': 'risk-medium', '높음': 'risk-high', '매우높음': 'risk-very-high' };
  const riskEl = document.getElementById('summaryRisk');
  riskEl.className = 'summary-card ' + (riskMap[s.risk_level] || '');
  document.getElementById('riskLevel').textContent = s.risk_level || '-';

  document.getElementById('totalQuoted').textContent = s.total_quoted ? formatWon(s.total_quoted) : '불명확';
  document.getElementById('totalFair').textContent = s.total_fair ? formatWon(s.total_fair) : '-';

  const rate = s.overprice_rate;
  const opEl = document.getElementById('summaryOverprice');
  if (rate != null) {
    document.getElementById('overpriceRate').textContent = (rate > 0 ? '+' : '') + rate + '%';
    opEl.className = 'summary-card ' + (rate <= 5 ? 'overprice-ok' : rate <= 20 ? 'overprice-warn' : 'overprice-danger');
  } else {
    document.getElementById('overpriceRate').textContent = '-';
    opEl.className = 'summary-card';
  }

  document.getElementById('oneLine').textContent = s.one_line || '';

  renderItems(r.items || [], r.missing_items || []);
  renderRedFlags(r.red_flags || []);
  renderNegotiation(r.negotiation || {});
  renderChecklist(r.contract_checklist || []);
  document.getElementById('overallAdvice').textContent = r.overall_advice || '';

  document.getElementById('resultsSection').hidden = false;
  document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });

  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === 0));
  document.querySelectorAll('.tab-content').forEach((c, i) => c.classList.toggle('active', i === 0));
}

function renderItems(items, missing) {
  const tbody = document.getElementById('itemsBody');
  tbody.innerHTML = '';

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:24px">항목 정보를 추출할 수 없습니다.</td></tr>`;
    return;
  }

  items.forEach(item => {
    const tr = document.createElement('tr');
    const fairRange = (item.fair_price_min && item.fair_price_max)
      ? `${formatWon(item.fair_price_min)} ~ ${formatWon(item.fair_price_max)}`
      : '-';
    tr.innerHTML = `
      <td style="font-weight:600">${esc(item.name)}</td>
      <td>${item.quoted_price ? formatWon(item.quoted_price) : '-'}</td>
      <td>${fairRange}</td>
      <td><span class="status-badge status-${esc(item.status)}">${esc(item.status)}</span></td>
      <td style="color:var(--text-muted);font-size:.83rem">${esc(item.note || '')}</td>
    `;
    tbody.appendChild(tr);
  });

  const missingEl = document.getElementById('missingItems');
  if (missing.length) {
    document.getElementById('missingList').innerHTML = missing.map(m => `<li>${esc(m)}</li>`).join('');
    missingEl.hidden = false;
  } else {
    missingEl.hidden = true;
  }
}

function renderRedFlags(flags) {
  const container = document.getElementById('redFlagsContainer');
  if (!flags.length) {
    container.innerHTML = `<div class="card"><div class="empty-state"><div class="empty-icon">✅</div><p>특별한 위험 신호가 발견되지 않았습니다.</p></div></div>`;
    return;
  }
  container.innerHTML = flags.map(f => `
    <div class="redflag-card redflag-${esc(f.severity)}">
      <div class="redflag-header">
        <span class="redflag-severity">${esc(f.severity)}</span>
        <span class="redflag-title">${esc(f.title)}</span>
      </div>
      <p class="redflag-desc">${esc(f.description)}</p>
      <div class="redflag-action"><strong>권고 조치:</strong> ${esc(f.action)}</div>
    </div>
  `).join('');
}

function renderNegotiation(neg) {
  document.getElementById('targetPrice').textContent = neg.target_price ? formatWon(neg.target_price) : '-';
  document.getElementById('walkawayprice').textContent = neg.walkaway_price ? formatWon(neg.walkaway_price) : '-';
  document.getElementById('strategyText').textContent = neg.strategy || '';

  const scripts = neg.scripts || [];
  const container = document.getElementById('scriptsContainer');
  if (!scripts.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">💬</div><p>협상 스크립트 정보가 없습니다.</p></div>`;
    return;
  }
  container.innerHTML = scripts.map((s, i) => `
    <div class="script-card">
      <div class="script-topic">${esc(s.topic)}</div>
      <div class="script-body">
        ${esc(s.script)}
        <button class="script-copy-btn" onclick="copyScript(this, ${i})">📋 복사</button>
      </div>
    </div>
  `).join('');
  window._scripts = scripts;
}

function copyScript(btn, idx) {
  const text = window._scripts[idx]?.script || '';
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = '✅ 복사됨';
    setTimeout(() => { btn.textContent = '📋 복사'; }, 2000);
  }).catch(() => {
    btn.textContent = '복사 실패';
  });
}

function renderChecklist(items) {
  const container = document.getElementById('checklistContainer');
  if (!items.length) {
    container.innerHTML = `<div class="empty-state"><p>체크리스트 정보가 없습니다.</p></div>`;
    return;
  }
  container.innerHTML = items.map(c => `
    <div class="check-item">
      <span class="check-icon">${c.required ? '🔴' : '🟡'}</span>
      <div class="check-body">
        <div class="check-name">
          ${esc(c.item)}
          ${c.required ? '<span class="check-required">필수</span>' : ''}
        </div>
        <div class="check-tip">${esc(c.tip || '')}</div>
      </div>
    </div>
  `).join('');
}

/* ===== UTILS ===== */
function formatWon(num) {
  if (num == null) return '-';
  num = Math.round(Number(num));
  if (num >= 100000000) {
    const uk = Math.floor(num / 100000000);
    const man = Math.round((num % 100000000) / 10000);
    return man > 0 ? `${uk}억 ${man.toLocaleString()}만원` : `${uk}억원`;
  }
  if (num >= 10000) return Math.round(num / 10000).toLocaleString() + '만원';
  return num.toLocaleString() + '원';
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/\n/g, '<br>');
}

function resetForm() {
  onRemoveFile({ stopPropagation: () => {} });
  document.getElementById('contextInput').value = '';
  document.getElementById('resultsSection').hidden = true;
  hideError();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
