const API_BASE = window.location.port === '5173' ? 'http://127.0.0.1:8000' : '';

const state = {
  options: {},
  currentDocumentId: null,
  pollTimer: null,
  objectUrl: null,
};

const fieldIds = [
  'tahun_akademik',
  'bukti_fisik',
  'kelompok_kegiatan',
  'jenis_kegiatan',
  'tingkat',
  'prestasi_partisipasi_jabatan',
  'nama_kegiatan_sertifikasi',
  'waktu_mulai_pelaksanaan',
  'waktu_selesai_pelaksanaan',
  'jenis_penyelenggara',
  'penyelenggara_kegiatan',
  'nomor_bukti_fisik_nomor_sertifikasi',
];

const selectOptionMap = {
  tahun_akademik: 'tahun_akademik',
  bukti_fisik: 'bukti_fisik',
  kelompok_kegiatan: 'kelompok_kegiatan',
  jenis_kegiatan: 'jenis_kegiatan',
  tingkat: 'tingkat',
  prestasi_partisipasi_jabatan: 'prestasi_partisipasi_jabatan',
  jenis_penyelenggara: 'jenis_penyelenggara',
};

function el(id) { return document.getElementById(id); }

async function init() {
  bindEvents();
  await loadOptions();
  setInitialDefaults();
  await restoreLastSession();
}

function bindEvents() {
  el('khpForm').addEventListener('submit', uploadAndParse);
  el('resetBtn').addEventListener('click', resetPage);
  el('saveBtn').addEventListener('click', () => {
    setStatus('Prototype: data form sudah siap dikirim ke backend utama Sistem Informasi.');
  });

  el('upload_bukti').addEventListener('change', () => {
    const file = el('upload_bukti').files?.[0];
    if (!file) return;
    showPdfPreview(file);
    setStatus('PDF dipilih. Klik PROSES PDF untuk parsing dan autofill.');
  });

  el('tingkat').addEventListener('change', applyStrictOrganizerRuleFromLevel);
}

function applyStrictOrganizerRuleFromLevel() {
  const tingkat = el('tingkat').value;
  if (['Fakultas', 'Departemen/Program Studi', 'UKM'].includes(tingkat)) {
    ensureOptionAndSet(el('jenis_penyelenggara'), 'PTN di Indonesia');
  } else if (tingkat === 'Internasional') {
    ensureOptionAndSet(el('jenis_penyelenggara'), 'PT di luar negeri');
  }
}

async function loadOptions() {
  const response = await fetch(`${API_BASE}/api/options`);
  if (!response.ok) throw new Error('Gagal mengambil master option dari backend.');
  const data = await response.json();
  state.options = data.options || {};

  Object.entries(selectOptionMap).forEach(([selectId, optionKey]) => {
    fillSelect(selectId, state.options[optionKey] || []);
  });
}

function fillSelect(selectId, values, selectedValue = '') {
  const select = el(selectId);
  if (!select) return;
  select.innerHTML = '';
  values.forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  if (selectedValue) ensureOptionAndSet(select, selectedValue);
}

function setInitialDefaults() {
  ensureOptionAndSet(el('tahun_akademik'), '2035/2036 - Genap');
  ensureOptionAndSet(el('bukti_fisik'), 'Sertifikat');
}

async function uploadAndParse(event) {
  event.preventDefault();
  const file = el('upload_bukti').files?.[0];
  if (!file) {
    setStatus('Pilih file PDF terlebih dahulu.');
    return;
  }
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    setStatus('File wajib PDF.');
    return;
  }

  showPdfPreview(file);
  showAfterUploadSection();
  setLoading(true);
  setStatus('Mengupload PDF ke PostgreSQL dan memulai parsing...');

  const formData = new FormData();
  formData.append('tahun_akademik', el('tahun_akademik').value);
  formData.append('bukti_fisik', el('bukti_fisik').value || 'Sertifikat');
  formData.append('file', file);

  try {
    const response = await fetch(`${API_BASE}/api/documents`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await safeJson(response);
      throw new Error(err.detail || `Upload gagal. HTTP ${response.status}`);
    }

    const uploaded = await response.json();
    state.currentDocumentId = uploaded.document_id;
    try {
      localStorage.setItem('cert_last_document_id', uploaded.document_id);
    } catch (e) {}
    setStatus('PDF berhasil diupload. Menunggu hasil parsing extraction...');
    pollResult(uploaded.document_id);
  } catch (error) {
    setLoading(false);
    setStatus(error.message || String(error));
  }
}

function showAfterUploadSection() {
  el('afterUploadSection').classList.remove('hidden');
}

function showPdfPreview(file) {
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.objectUrl = URL.createObjectURL(file);
  el('pdfPreview').src = state.objectUrl;
}

function pollResult(documentId) {
  if (state.pollTimer) clearInterval(state.pollTimer);

  state.pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/documents/${documentId}/result`);
      if (!response.ok) throw new Error(`Gagal mengambil hasil parsing. HTTP ${response.status}`);
      const data = await response.json();

      if (data.status === 'failed') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        setLoading(false);
        setStatus('Parsing gagal. Cek terminal backend untuk detail error.');
        return;
      }

      if (['completed', 'needs_review'].includes(data.status)) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        applyResult(data);
        applyStrictOrganizerRuleFromLevel();
        if (data.has_preview) {
          el('pdfPreview').src = `${API_BASE}/api/documents/${documentId}/preview`;
        }
        setLoading(false);
        const engineTag = data.parser_engine ? ` [${data.parser_engine}]` : '';
        setStatus(data.needs_review ? `Parsing selesai${engineTag}. Form sudah terisi, tetapi beberapa field perlu dicek ulang.` : `Parsing selesai${engineTag}. Form sudah terisi otomatis.`);
      } else {
        setStatus(`Status parsing: ${data.status}. Menunggu...`);
      }
    } catch (error) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      setLoading(false);
      setStatus(error.message || String(error));
    }
  }, 1200);
}

function applyResult(data) {
  const fields = data.fields || {};
  fieldIds.forEach(fieldId => {
    const item = fields[fieldId];
    if (!item) return;
    const element = el(fieldId);
    if (!element) return;
    const value = normalizeDateForDisplay(fieldId, item.value || '');
    if (element.tagName === 'SELECT') ensureOptionAndSet(element, value);
    else element.value = value;
  });
}

function normalizeDateForDisplay(fieldId, value) {
  if (!['waktu_mulai_pelaksanaan', 'waktu_selesai_pelaksanaan'].includes(fieldId)) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

function ensureOptionAndSet(select, value) {
  if (!select || !value) return;
  const exists = Array.from(select.options).some(option => option.value === value);
  if (!exists) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
  select.value = value;
}

function renderDebug(data) {
  // Debug panel intentionally disabled for production-style frontend.
}

function resetPage() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  state.currentDocumentId = null;
  try {
    localStorage.removeItem('cert_last_document_id');
  } catch (e) {}
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.objectUrl = null;

  el('khpForm').reset();
  setInitialDefaults();
  el('afterUploadSection').classList.add('hidden');
  el('pdfPreview').src = '';
  setLoading(false);
  setStatus('Upload PDF untuk melakukan parsing extraction.');
}

async function restoreLastSession() {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const docId = urlParams.get('doc') || localStorage.getItem('cert_last_document_id');
    if (!docId) return;

    const response = await fetch(`${API_BASE}/api/documents/${docId}/result`);
    if (!response.ok) {
      try { localStorage.removeItem('cert_last_document_id'); } catch (e) {}
      return;
    }
    const data = await response.json();
    if (['completed', 'needs_review'].includes(data.status)) {
      state.currentDocumentId = docId;
      showAfterUploadSection();
      applyResult(data);
      applyStrictOrganizerRuleFromLevel();
      if (data.has_preview) {
        el('pdfPreview').src = `${API_BASE}/api/documents/${docId}/preview`;
      }
      const engineTag = data.parser_engine ? ` [${data.parser_engine}]` : '';
      setStatus(data.needs_review ? `Hasil sebelumnya berhasil dimuat ulang${engineTag}. Beberapa field perlu dicek ulang.` : `Hasil sebelumnya berhasil dimuat ulang${engineTag}. Form sudah terisi otomatis.`);
    }
  } catch (err) {
    console.warn('Gagal memulihkan dokumen sebelumnya:', err);
  }
}

function setLoading(isLoading) {
  el('parseBtn').disabled = isLoading;
  el('parseBtn').textContent = isLoading ? 'MEMPROSES...' : 'PROSES PDF';
}

function setStatus(text) {
  el('statusText').textContent = text;
}

async function safeJson(response) {
  try { return await response.json(); }
  catch { return {}; }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

init().catch(error => setStatus(`Frontend gagal inisialisasi: ${error.message || error}`));
