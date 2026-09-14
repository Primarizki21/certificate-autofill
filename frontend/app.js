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
  el('kelompok_kegiatan')?.addEventListener('change', onKelompokKegiatanChange);
  el('jenis_kegiatan')?.addEventListener('change', onJenisKegiatanChange);

  // Modal Master Kegiatan
  el('masterKegiatanBtn')?.addEventListener('click', openMasterModal);
  el('closeModalBtn')?.addEventListener('click', closeMasterModal);
  el('closeModalBtn2')?.addEventListener('click', closeMasterModal);
  el('masterModal')?.addEventListener('click', (e) => {
    if (e.target === el('masterModal')) closeMasterModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMasterModal();
  });
  el('modalSearchInput')?.addEventListener('input', filterAndRenderModalTable);
  el('modalGroupFilter')?.addEventListener('change', filterAndRenderModalTable);
}
function applyStrictOrganizerRuleFromLevel() {
  const tingkat = selectedOptionLabel(el('tingkat'));
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
    const isMasterOption = value && typeof value === 'object';
    if (isMasterOption && value.active === false) return;
    const label = isMasterOption ? String(value.label || '') : String(value);
    if (!label) return;
    const option = document.createElement('option');
    option.value = isMasterOption ? String(value.id) : label;
    option.textContent = label;
    option.dataset.label = label;
    if (isMasterOption && value.group_id != null) {
      option.dataset.groupId = String(value.group_id);
    }
    select.appendChild(option);
  });
  if (selectedValue) ensureOptionAndSet(select, selectedValue);
}

function onKelompokKegiatanChange() {
  const selectedGroup = el('kelompok_kegiatan').value;
  const currentJenisVal = el('jenis_kegiatan').value;
  filterJenisKegiatanByGroup(selectedGroup, currentJenisVal);
}

function filterJenisKegiatanByGroup(groupId, preserveValue = '') {
  const jenisSelect = el('jenis_kegiatan');
  if (!jenisSelect) return;
  const allActivities = state.options.jenis_kegiatan || [];
  let filtered = allActivities;
  if (groupId && groupId !== '--' && groupId !== '') {
    filtered = allActivities.filter(item => {
      if (typeof item === 'object' && item.group_id != null) {
        return String(item.group_id) === String(groupId);
      }
      return true;
    });
  }
  fillSelect('jenis_kegiatan', filtered, preserveValue);
}

function onJenisKegiatanChange() {
  const jenisSelect = el('jenis_kegiatan');
  const selectedOption = jenisSelect?.selectedOptions?.[0];
  const groupId = selectedOption?.dataset?.groupId;
  if (groupId) {
    const kelompokSelect = el('kelompok_kegiatan');
    if (kelompokSelect && kelompokSelect.value !== String(groupId)) {
      ensureOptionAndSet(kelompokSelect, String(groupId));
      filterJenisKegiatanByGroup(groupId, jenisSelect.value);
    }
  }
}

function selectedOptionLabel(select) {
  const selected = select?.selectedOptions?.[0];
  return selected?.dataset?.label || selected?.textContent || select?.value || '';
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
  const masterFields = data.master_resolution?.fields || {};

  // 1. Set kelompok_kegiatan first
  const kelItem = fields['kelompok_kegiatan'];
  const kelMaster = masterFields['kelompok_kegiatan'];
  const kelVal = kelMaster?.id ?? kelItem?.value ?? '';
  if (kelVal) {
    ensureOptionAndSet(el('kelompok_kegiatan'), kelVal);
  }

  // 2. Filter jenis_kegiatan based on kelompok_kegiatan, then set it
  const jenItem = fields['jenis_kegiatan'];
  const jenMaster = masterFields['jenis_kegiatan'];
  const jenVal = jenMaster?.id ?? jenItem?.value ?? '';
  filterJenisKegiatanByGroup(kelVal, jenVal);
  if (jenVal) {
    ensureOptionAndSet(el('jenis_kegiatan'), jenVal);
  }

  // 3. Set remaining fields
  fieldIds.forEach(fieldId => {
    if (['kelompok_kegiatan', 'jenis_kegiatan'].includes(fieldId)) return;
    const item = fields[fieldId];
    if (!item) return;
    const element = el(fieldId);
    if (!element) return;
    const masterField = masterFields[fieldId];
    const selectedValue = masterField?.id ?? item.value ?? '';
    const value = normalizeDateForDisplay(
      fieldId,
      element.tagName === 'SELECT' ? selectedValue : item.value || '',
    );
    if (element.tagName === 'SELECT') ensureOptionAndSet(element, value);
    else element.value = value;
  });

  // 4. Render AUCC resolution and evidence panel
  renderAuccResolution(data.master_resolution, selectedOptionLabel(el('bukti_fisik')));
}

function renderAuccResolution(masterResolution, currentBuktiFisik) {
  const panel = el('auccResolutionSection');
  if (!panel) return;
  if (!masterResolution) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');

  const badge = el('auccStatusBadge');
  const idTag = el('auccIdTag');
  const masterSummary = el('auccMasterSummary');
  const evidenceSummary = el('auccEvidenceSummary');
  const reasonsRow = el('auccReasonsRow');
  const reasonsChips = el('auccReasonsChips');

  const status = masterResolution.status || 'unknown';
  const idKegiatan2 = masterResolution.id_kegiatan_2;
  const rule = masterResolution.master_rule;
  const evidenceStatus = masterResolution.evidence_status || 'not_checked';
  const reasons = masterResolution.reasons || [];

  // 1. Badge & Tag
  badge.className = 'aucc-badge';
  if (status === 'resolved') {
    badge.classList.add('resolved');
    badge.textContent = '✓ Terverifikasi AUCC';
  } else if (status === 'needs_review') {
    badge.classList.add('review');
    badge.textContent = '⚠ Perlu Review Form';
  } else {
    badge.classList.add('awaiting');
    badge.textContent = 'ℹ Menunggu Lookup';
  }

  idTag.textContent = idKegiatan2 ? `ID Kegiatan 2: ${idKegiatan2}` : 'ID Kegiatan 2: Belum Terpetakan';

  // 2. Master Summary
  const mf = masterResolution.fields || {};
  const kelompokText = mf.kelompok_kegiatan?.label || selectedOptionLabel(el('kelompok_kegiatan')) || '-';
  const jenisText = mf.jenis_kegiatan?.label || selectedOptionLabel(el('jenis_kegiatan')) || '-';
  const tingkatText = mf.tingkat?.label || selectedOptionLabel(el('tingkat')) || '-';
  const roleText = mf.prestasi_partisipasi_jabatan?.label || selectedOptionLabel(el('prestasi_partisipasi_jabatan')) || '-';

  masterSummary.innerHTML = `<strong>${jenisText}</strong> (${kelompokText}) &bull; Tingkat: <strong>${tingkatText}</strong> &bull; Peran: <strong>${roleText}</strong>`;

  // 3. Evidence Status
  if (rule && rule.dasar_penilaian) {
    const dasar = rule.dasar_penilaian;
    const bukti = currentBuktiFisik || selectedOptionLabel(el('bukti_fisik')) || 'Sertifikat';
    if (evidenceStatus === 'matched') {
      evidenceSummary.innerHTML = `<span style="color:#12753a; font-weight:600;">✓ Sesuai Aturan:</span> Bukti fisik "<em>${bukti}</em>" memenuhi syarat aturan resmi [<strong>${dasar}</strong>].`;
    } else if (evidenceStatus === 'not_allowed') {
      evidenceSummary.innerHTML = `<span style="color:#b26a00; font-weight:600;">⚠ Peringatan Aturan:</span> Bukti fisik "<em>${bukti}</em>" tidak memenuhi ketentuan aturan resmi [<strong>${dasar}</strong>].`;
    } else if (evidenceStatus === 'missing') {
      evidenceSummary.innerHTML = `<span style="color:#b3261e; font-weight:600;">⚠ Bukti Kosong:</span> Aturan resmi mensyaratkan bukti [<strong>${dasar}</strong>].`;
    } else {
      evidenceSummary.innerHTML = `Syarat aturan resmi: [<strong>${dasar}</strong>] (status: ${evidenceStatus}).`;
    }
  } else {
    evidenceSummary.textContent = 'Kombinasi kegiatan_2 ini tidak memiliki batasan master rule khusus.';
  }

  // 4. Reasons Chips
  if (reasons && reasons.length > 0) {
    reasonsRow.classList.remove('hidden');
    reasonsChips.innerHTML = '';
    reasons.forEach(r => {
      const chip = document.createElement('span');
      chip.className = 'aucc-chip warn';
      chip.textContent = humanizeReason(r);
      reasonsChips.appendChild(chip);
    });
  } else {
    reasonsRow.classList.add('hidden');
  }
}

function humanizeReason(key) {
  const map = {
    'bukti_fisik_not_allowed': 'Bukti fisik tidak sesuai aturan penilaian',
    'bukti_fisik_missing': 'Bukti fisik belum dipilih',
    'kegiatan_2_not_found': 'Kombinasi kegiatan, tingkat, dan peran belum ada di master',
    'kegiatan_2_ambiguous': 'Kombinasi kegiatan ambigu pada master data',
    'master_rule_ambiguous': 'Aturan penilaian ganda pada master',
    'ambiguous_master_label': 'Label kegiatan terdeteksi ganda',
    'ambiguous_structural_anchor': 'Struktur teks ambigu',
    'level_conflicts_with_raw_ocr': 'Tingkat perlu dicek ulang terhadap teks sertifikat',
    'khp_master_resolution_pending': 'Verifikasi master KHP masih pending',
  };
  return map[key] || key;
}

function openMasterModal() {
  const modal = el('masterModal');
  if (!modal) return;
  modal.classList.remove('hidden');

  const groupFilter = el('modalGroupFilter');
  if (groupFilter && groupFilter.options.length <= 1) {
    const groups = state.options.kelompok_kegiatan || [];
    groups.forEach(g => {
      const opt = document.createElement('option');
      opt.value = typeof g === 'object' ? String(g.id) : String(g);
      opt.textContent = typeof g === 'object' ? String(g.label) : String(g);
      groupFilter.appendChild(opt);
    });
  }

  filterAndRenderModalTable();
  el('modalSearchInput')?.focus();
}

function closeMasterModal() {
  const modal = el('masterModal');
  if (modal) modal.classList.add('hidden');
}

function filterAndRenderModalTable() {
  const tbody = el('modalTableBody');
  const countEl = el('modalItemCount');
  if (!tbody) return;

  const searchQuery = (el('modalSearchInput')?.value || '').toLowerCase().trim();
  const groupFilter = el('modalGroupFilter')?.value || '';

  const allActivities = state.options.jenis_kegiatan || [];
  const groups = state.options.kelompok_kegiatan || [];
  const groupMap = {};
  groups.forEach(g => {
    if (typeof g === 'object') groupMap[g.id] = g.label;
  });

  const filtered = allActivities.filter(act => {
    const isObj = typeof act === 'object';
    const id = isObj ? String(act.id) : '';
    const label = isObj ? String(act.label || '') : String(act);
    const groupId = isObj && act.group_id != null ? String(act.group_id) : '';

    if (groupFilter && groupId !== groupFilter) return false;
    if (searchQuery) {
      const matchText = `${id} ${label}`.toLowerCase();
      if (!matchText.includes(searchQuery)) return false;
    }
    return true;
  });

  tbody.innerHTML = '';
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#829ab1; padding:18px;">Tidak ada kegiatan yang cocok dengan pencarian.</td></tr>';
  } else {
    filtered.forEach(act => {
      const isObj = typeof act === 'object';
      const id = isObj ? act.id : '-';
      const label = isObj ? act.label : String(act);
      const groupId = isObj ? act.group_id : '';
      const groupName = groupMap[groupId] || (groupId ? `Kelompok ${groupId}` : '-');

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:monospace; font-weight:700; color:#1d5280;">${id}</td>
        <td style="color:#486581; font-size:11px;">${groupName}</td>
        <td style="color:#102a43; font-weight:500;">${label}</td>
        <td style="text-align:center;">
          <button type="button" class="btn-select" data-id="${id}" data-group-id="${groupId}">PILIH</button>
        </td>
      `;
      tr.querySelector('.btn-select').addEventListener('click', () => {
        selectActivityFromModal(id, groupId);
      });
      tbody.appendChild(tr);
    });
  }

  if (countEl) {
    countEl.textContent = `Menampilkan ${filtered.length} dari ${allActivities.length} kegiatan`;
  }
}

function selectActivityFromModal(activityId, groupId) {
  if (groupId) {
    ensureOptionAndSet(el('kelompok_kegiatan'), String(groupId));
    filterJenisKegiatanByGroup(groupId, String(activityId));
  } else {
    ensureOptionAndSet(el('jenis_kegiatan'), String(activityId));
  }
  ensureOptionAndSet(el('jenis_kegiatan'), String(activityId));
  closeMasterModal();
  el('jenis_kegiatan')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function normalizeDateForDisplay(fieldId, value) {
  if (!['waktu_mulai_pelaksanaan', 'waktu_selesai_pelaksanaan'].includes(fieldId)) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

function ensureOptionAndSet(select, value) {
  if (!select || value === null || value === undefined || value === '') return;
  const target = String(value);
  const exists = Array.from(select.options).some(option => option.value === target);
  if (!exists) {
    const option = document.createElement('option');
    option.value = target;
    option.textContent = target;
    option.dataset.label = target;
    select.appendChild(option);
  }
  select.value = target;
}

function renderDebug(data) {
  // Debug panel intentionally disabled for production-style frontend.
}

function resetPage() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  state.currentDocumentId = null;
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.objectUrl = null;

  el('khpForm').reset();
  setInitialDefaults();
  filterJenisKegiatanByGroup('', '');
  renderAuccResolution(null);
  el('afterUploadSection').classList.add('hidden');
  el('pdfPreview').src = '';
  setLoading(false);
  setStatus('Upload PDF untuk melakukan parsing extraction.');
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
