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
    showDocumentPreview(file);
    const isPdf = file.name.toLowerCase().endsWith('.pdf');
    setStatus(`${isPdf ? 'PDF' : 'Gambar'} dipilih. Klik PROSES DOKUMEN untuk parsing dan autofill.`);
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
  if (['kelompok_kegiatan', 'jenis_kegiatan', 'prestasi_partisipasi_jabatan'].includes(selectId)) {
    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = '-- Pilih --';
    emptyOption.dataset.label = '';
    select.appendChild(emptyOption);
  }
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

const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.webp'];

function isSupportedFile(filename) {
  const lower = (filename || '').toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

async function uploadAndParse(event) {
  event.preventDefault();
  const file = el('upload_bukti').files?.[0];
  if (!file) {
    setStatus('Pilih file dokumen (PDF/Gambar) terlebih dahulu.');
    return;
  }
  if (!isSupportedFile(file.name)) {
    setStatus('Format file tidak didukung. Harap unggah PDF, JPG, JPEG, PNG, atau WEBP.');
    return;
  }

  showDocumentPreview(file);
  showAfterUploadSection();
  setLoading(true);
  setStatus('Mengunggah dokumen dan memulai ekstraksi...');

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
      const detailMsg = err.detail || `Upload gagal. HTTP ${response.status}`;
      setLoading(false);
      setStatus(detailMsg);
      return;
    }

    const uploaded = await response.json();
    state.currentDocumentId = uploaded.document_id;
    setStatus('Dokumen berhasil diunggah. Sedang memproses ekstraksi...');
    pollResult(uploaded.document_id);
  } catch (networkError) {
    setLoading(false);
    setStatus('Terjadi kendala jaringan saat mengunggah dokumen. Silakan coba kembali.');
  }
}

function showAfterUploadSection() {
  el('afterUploadSection').classList.remove('hidden');
}

function showDocumentPreview(file) {
  if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
  state.objectUrl = URL.createObjectURL(file);
  const isPdf = file.name.toLowerCase().endsWith('.pdf');
  const pdfFrame = el('pdfPreview');
  const imgView = el('imagePreview');

  if (isPdf) {
    if (pdfFrame) {
      pdfFrame.classList.remove('hidden');
      pdfFrame.src = state.objectUrl;
    }
    if (imgView) {
      imgView.classList.add('hidden');
      imgView.src = '';
    }
  } else {
    if (pdfFrame) {
      pdfFrame.classList.add('hidden');
      pdfFrame.src = '';
    }
    if (imgView) {
      imgView.classList.remove('hidden');
      imgView.src = state.objectUrl;
    }
  }
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
        setStatus('Ekstraksi dokumen tidak berhasil. Silakan coba kembali.');
        return;
      }

      if (['completed', 'needs_review'].includes(data.status)) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        applyResult(data);
        applyStrictOrganizerRuleFromLevel();
        setLoading(false);
        setStatus(data.needs_review ? 'Pengisian form selesai otomatis. Silakan periksa kembali isian sebelum menyimpan.' : 'Pengisian form selesai otomatis.');
      } else {
        setStatus('Sedang memproses dokumen...');
      }
    } catch (error) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      setLoading(false);
      setStatus('Terjadi kendala saat memproses dokumen. Silakan coba kembali.');
    }
  }, 1200);
}

function applyResult(data) {
  const fields = data.fields || {};

  // 1. Set kelompok_kegiatan first
  const kelItem = fields['kelompok_kegiatan'];
  const kelVal = kelItem?.value ?? '';
  if (kelVal) {
    ensureOptionAndSet(el('kelompok_kegiatan'), kelVal);
  } else {
    const kelEl = el('kelompok_kegiatan');
    if (kelEl) kelEl.value = '';
  }

  // 2. Filter jenis_kegiatan based on kelompok_kegiatan, then set it
  const jenItem = fields['jenis_kegiatan'];
  const jenVal = jenItem?.value ?? '';
  const currentGroupId = el('kelompok_kegiatan')?.value || '';
  filterJenisKegiatanByGroup(currentGroupId, jenVal);
  if (jenVal) {
    ensureOptionAndSet(el('jenis_kegiatan'), jenVal);
  } else {
    const jenEl = el('jenis_kegiatan');
    if (jenEl) jenEl.value = '';
  }

  // 3. Set remaining fields
  fieldIds.forEach(fieldId => {
    if (['kelompok_kegiatan', 'jenis_kegiatan'].includes(fieldId)) return;
    const item = fields[fieldId];
    const element = el(fieldId);
    if (!element) return;
    const rawVal = item ? (item.value || '') : '';
    const value = normalizeDateForDisplay(fieldId, rawVal);
    if (element.tagName === 'SELECT') {
      if (value) {
        ensureOptionAndSet(element, value);
      } else {
        element.value = '';
      }
    } else {
      element.value = value;
    }
  });
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
  const target = String(value).trim();
  if (!target) return;

  // 1. Coba cocokkan dengan value atau label teks option yang sudah ada
  const options = Array.from(select.options);
  const matchedOpt = options.find(
    opt => opt.value === target ||
           (opt.dataset.label && opt.dataset.label.toLowerCase() === target.toLowerCase()) ||
           opt.textContent.trim().toLowerCase() === target.toLowerCase()
  );

  if (matchedOpt) {
    select.value = matchedOpt.value;
    return;
  }

  // 2. Jika belum ada, buat option baru
  const option = document.createElement('option');
  option.value = target;
  option.textContent = target;
  option.dataset.label = target;
  select.appendChild(option);
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
  el('afterUploadSection').classList.add('hidden');
  if (el('pdfPreview')) el('pdfPreview').src = '';
  if (el('imagePreview')) {
    el('imagePreview').src = '';
    el('imagePreview').classList.add('hidden');
  }
  setLoading(false);
  setStatus('Upload PDF atau gambar untuk melakukan parsing extraction.');
}

function setLoading(isLoading) {
  el('parseBtn').disabled = isLoading;
  el('parseBtn').textContent = isLoading ? 'MEMPROSES...' : 'PROSES DOKUMEN';
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

init().catch(() => setStatus('Frontend gagal memuat opsi form. Silakan refresh halaman.'));
