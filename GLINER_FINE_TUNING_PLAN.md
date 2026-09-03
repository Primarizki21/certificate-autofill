# Fine-Tuning GLiNER dan GLiNER2.5 dengan Paritas Benchmark Encoder

## Context
Melatih `urchade/gliner_multi-v2.1` dan `fastino/gliner2.5-base-v1` pada 74 teks OCR Tesseract sertifikat, lalu membandingkannya secara adil dengan encoder NER sebelumnya. Hasil wajib berupa prediksi Out-of-Fold lima fold yang dievaluasi terhadap `Ground_Truth_Sertifikat_v9.csv` melalui Matcher v2 pada lima field framework (310 sel), bukan evaluasi pada dokumen yang pernah dipakai melatih fold tersebut. Tidak ada perubahan pipeline produksi atau promosi model.

## Approach
### 1. Bangun dataset span dari sumber dan split encoder yang sama
Pertahankan `tests/benchmark_gliner.py` sebagai satu runner GLiNER; benchmark zero-shot yang ada tetap tersedia melalui `--mode zero-shot` (default), lalu tambahkan `--mode fine-tune` dan `--sanity-overfit`. Runner fine-tuned harus mengimpor `Example`, `build_examples`, `find_token_span`, dan `stratified_folds` dari `tests/benchmark_ner_encoders.py`; jangan menduplikasi pembacaan OCR, normalisasi token, atau algoritme stratifikasi.

Tambahkan `build_gliner_training_examples(examples: list[Example]) -> tuple[list[GlinerTrainingExample], dict[str, object]]`. Untuk setiap nilai GT non-kosong yang ditemukan oleh `find_token_span`, bentuk label schema yang persis sama dengan zero-shot: `nama_kegiatan_sertifikasi -> "event name"`, `nomor_bukti_fisik_nomor_sertifikasi -> "certificate number"`, `penyelenggara_kegiatan -> "organizer"`, dan kedua field waktu -> `"date"`. Simpan `(start_word, end_word_inclusive, label, field, matched_ocr_text)`; deduplikasi hanya tuple `(start_word, end_word_inclusive, label)` identik. Jangan melakukan fuzzy matching atau anotasi manual: audit awal yang dihasilkan harus menyatakan 310 field GT, 223 span cocok, dan 87 span tidak cocok pada OCR.

Tambahkan tokenizer-aware windowing `window_gliner_example(example: GlinerTrainingExample, tokenizer, max_length: int = 512, stride: int = 64) -> list[GlinerTrainingWindow]`. Hitung panjang dengan tokenizer backbone, bukan jumlah kata. Setiap window berisi paling banyak 512 subword termasuk special token, overlap minimal 64 subword, dan batas kanan digeser mundur hingga tidak pernah memotong span berlabel; kemudian rebase indeks span ke window. Setelah seluruh window terbentuk, verifikasi setiap dari 223 span cocok muncul penuh setidaknya satu kali. Ini diperlukan karena 11/74 dokumen melampaui 512 subword (maksimum 768), sementara span GT terpanjang adalah 60 token kata.

Konversi window yang sama hanya sesudah fold dokumen ditentukan: `to_gliner_v1_records(windows) -> list[dict[str, object]]` menghasilkan `{"tokenized_text": list[str], "ner": [[start, end_inclusive, label], ...]}`; GLiNER v2.1 memakai indeks akhir inklusif. `to_gliner2_examples(windows) -> list[InputExample]` menghasilkan `InputExample(text=window.text, entities={label: [matched_ocr_text, ...]})`; panggil `.validate()` dan jadikan error sebagai kegagalan pra-latih, bukan sanitasi yang menghapus label. Semua window turunan satu sertifikat selalu berada pada fold yang sama; tidak boleh ada window held-out dalam data train.

### 2. Kunci manifest paritas yang dapat diaudit
Tuliskan `config.json` sebelum training di `tests/benchmark_runs/gliner_ft_{model_slug}_{timestamp}/`. Manifest wajib mencatat revision checkpoint, versi `gliner`/`gliner2`/`transformers`/`torch`, GT `Ground_Truth_Sertifikat_v9.csv`, korpus `tesseract_primary_v4/extracted_texts`, dan statistik alignment/windowing di atas.

Tetapkan parameter lintas-arsitektur persis seperti run pembanding `tests/benchmark_runs/ner_encoder_treamyracle_indobert_ner_gold_20260903_183549/config.json`: `folds=5`, fold `stratified_folds(..., seed=42)`, seed model `42 + fold_index`, `epochs=10`, `batch_size=1`, `gradient_accumulation_steps=8`, effective batch `8`, `max_length=512`, `stride=64`, `encoder_learning_rate=2e-5`, `task_learning_rate=2e-5`, `weight_decay=0.01`, `max_grad_norm=1.0`, linear scheduler, warmup ratio `0.1`, `dataloader_num_workers=0`, `eval_strategy="no"`, dan tanpa early stopping. Muat ulang checkpoint awal per fold, jalankan fold serial, gunakan `model.float()` untuk master FP32, dan aktifkan BF16 autocast hanya bila CUDA mendukungnya; bila tidak, pakai FP32 penuh. LoRA harus `False`.

Rekam perbedaan yang tidak dapat disamakan secara jujur dalam `config.json` dan laporan: baseline token classifier memakai Adafactor serta weighted cross-entropy sqrt-inverse-frequency; GLiNER v2.1 memakai Adafactor (`optim="adafactor"`) dengan focal/span loss native (`focal_loss_alpha=-1`, `focal_loss_gamma=0`, `negatives=1.0`, `masking="none"`, `loss_reduction="sum"`); GLiNER2.5 `ExtractorTrainer` mengunci full fine-tune pada AdamW dua kelompok dengan boundary/proposal loss native. Untuk GLiNER2.5 gunakan native `AdamW`, `encoder_lr=task_lr=2e-5`, bukan subclass optimizer atau LoRA; itu menjaga prosedur pelatihan resmi dan satu-satunya perbedaan optimizer dinyatakan sebagai batas validitas perbandingan.

### 3. Jalankan GLiNER v2.1 sebagai lima model out-of-fold
Tambahkan `run_gliner_v1_fold(...)` yang memuat `GLiNER.from_pretrained("urchade/gliner_multi-v2.1")` dari awal pada tiap fold. Sebelum membuat trainer, set `model.config.max_len = 512` dan `model.config.max_width = 64`: checkpoint default berkapasitas `max_len=384` dan `max_width=12`, sedangkan korpus memiliki 11 teks >512 subword dan 8 span GT >12 token (terpanjang 60); nilai 64 mencakup seluruh span label tanpa mengubah label atau data. Panggil `model.float()` serta `model.model.token_rep_layer.bert_layer.model.gradient_checkpointing_enable()`.

Bangun `gliner.training.TrainingArguments` dengan parameter di atas, lalu instansiasi `StrictGlinerTrainer(gliner.training.Trainer)` langsung memakai `model._create_data_collator()` dan tokenizer `model.data_processor.transformer_tokenizer`; jangan panggil `model.train_model`, karena trainer native mengubah OOM menjadi batch bernilai nol. `StrictGlinerTrainer.training_step(...)` mempertahankan perhitungan `compute_loss` native tetapi melempar ulang `torch.cuda.OutOfMemoryError` dan `RuntimeError` yang mengandung “out of memory”. Jalankan `trainer.train()` dengan `per_device_train_batch_size=1`, `gradient_accumulation_steps=8`, `num_train_epochs=10`, `learning_rate=2e-5`, `others_lr=2e-5`, weight decay `0.01`, Adafactor, clipping `1.0`, scheduler/warmup/precision dari manifest, dan tanpa evaluation/checkpoint selection dalam training. Simpan metrik loss dan peak VRAM per fold; setiap logits/loss non-finite atau batch OOM menghentikan run, tidak boleh diskip.

Perluas `ExtractedEntity` agar membawa `start` dan `end` karakter. Untuk held-out, `predict_gliner_v1_long(...)` menggunakan window tokenizer-aware 512/64 yang sama, menggabungkan kandidat `(label, normalized_text)` lintas-window dengan score tertinggi, lalu `gliner_entities_to_ner_entities(...)` mengubah label menjadi `EVT`/`ORG`/`NUM`/`DAT` dan memakai `tests.benchmark_ner_encoders.map_entities_to_fields` yang sama persis untuk candidate scoring, merge, dan pemilihan start/end date. Jangan gunakan heuristik “string terpanjang” pada `map_gliner_entities_to_fields` zero-shot. Hapus trainer, model, tokenizer, dan data fold lalu panggil `gc.collect()` serta `torch.cuda.empty_cache()` sebelum fold berikutnya.

### 4. Jalankan GLiNER2.5 sebagai lima model out-of-fold
Tambahkan `run_gliner2_fold(...)` yang memuat `GLiNER2.from_pretrained("fastino/gliner2.5-base-v1")` baru pada tiap fold, kemudian memanggil `model.float()`. Buat `TrainingConfig` dengan `num_epochs=10`, `batch_size=1`, `gradient_accumulation_steps=8`, `encoder_lr=2e-5`, `task_lr=2e-5`, `weight_decay=0.01`, `max_grad_norm=1.0`, `scheduler_type="linear"`, `warmup_ratio=0.1`, `max_len=512`, `gradient_checkpointing=True`, `use_lora=False`, `deterministic=False`, `eval_strategy="no"`, `save_best=False`, `num_workers=0`, `strict_training=True`, dan `allow_invalid_samples=False`. Set `bf16=True, fp16=False` jika hardware BF16-capable; bila tidak set keduanya `False` agar trainer mempertahankan FP32, bukan FP16 boundary training.

Gunakan `GLiNER2Trainer(model, config).train(train_data=fold_windows)`, dengan `InputExample` dari langkah 1. Biarkan native AdamW membagi parameter berdasarkan nama mengandung `encoder`; simpan tipe optimizer dan jumlah parameter trainable di artefak fold. Jangan gunakan `sanitize()` atau `skip_step_errors`: invalid mention, proposal-capacity overflow, non-finite loss, dan OOM adalah kegagalan eksplisit yang menghentikan model tersebut.

Untuk held-out gunakan `extract_entities_long(text, labels, threshold=0.5, chunk_size=512, chunk_overlap=64, batch_size=1, include_confidence=True, include_spans=True)`. Urai skor dan span yang dikembalikan API, deduplikasi kandidat lintas chunk berdasarkan `(label, start, end, normalized_text)` dengan confidence maksimum, ubah ke `NEREntity`, lalu gunakan `map_entities_to_fields` yang sama seperti v2.1 dan benchmark encoder. Jalankan fold serial dan kosongkan memori CUDA setelah fold seperti langkah 3.

### 5. Validasi, putuskan gate eksperimen, dan rekam hasil
Tambahkan `tests/test_gliner_experiment.py`, tanpa unduhan model, untuk membuktikan: (a) format GLiNER v2.1 menggunakan indeks akhir inklusif; (b) satu dokumen dengan dua tanggal menghasilkan dua `"date"` mention; (c) field GT yang tidak muncul di OCR tercatat `unmatched` tanpa label palsu; (d) window 512/64 yang batasnya berpotongan dengan span panjang memindahkan batas dan tetap meliput label; (e) seluruh span yang cocok terlindungi oleh audit; (f) fold deterministik, disjoint pada tingkat stem, dan menyatukan setiap stem tepat sekali; (g) manifest menyimpan seluruh parameter paritas; dan (h) hasil GLiNER2 dengan `include_confidence=True, include_spans=True` mempertahankan skor/span API.

Tambahkan mode `--sanity-overfit` yang melatih dua dokumen berlabel terbanyak pada masing-masing arsitektur selama 20 epoch memakai konfigurasi precision/optimizer yang sama. Mode ini wajib membuktikan training forward/backward finite, perubahan parameter finite, dan exact recall 100% atas span label yang ada pada dua teks train ketika diprediksi ulang pada window yang sama; kegagalan menghentikan OOF penuh.

`run_finetuned_model(...)` mengagregasi hanya 74 prediksi held-out ke `aggregate_results`, Bootstrap CI 1000 resampling seed 42, dan OOD yang sama dengan runner encoder: mutasi UNAIR/FTMM serta noise `5↔S`, `8↔B`, `0↔O`, `1↔I` sebesar 10/25/50%. OOD wajib memakai model fold yang tidak melatih stem tersebut dan `FREE_INSTITUTION_FIELDS`; tulis `results.json`, `summary_oof.json`, `folds.json`, `alignment_audit.json`, dan prediksi per-stem/field beserta source fold, latency, serta peak VRAM.

Tandai `NER-GLINER-002` PASS hanya jika kedua run menyelesaikan 74 prediksi OOF, tanpa non-finite/OOM/invalid-label, dan framework exact masing-masing tidak lebih rendah daripada baseline zero-shotnya (v2.1 35.48%; v2.5 28.71%). Regresi adalah FAIL yang tetap didokumentasikan; skor apa pun tidak mengubah pipeline produksi atau flag deployment.

### 6. Integrasikan hasil yang sudah diukur ke laporan
Setelah kedua `results.json` final ada, masukkan angka aktual—bukan estimasi—ke `scripts/generate_ner_encoder_report_xlsx.py`. Di `Ringkasan Komparasi`, tambah satu baris `5-Fold OOF Fine-Tuned` tepat setelah masing-masing baris zero-shot GLiNER; isi framework exact/fuzzy, CI, lima field, total runtime, peak VRAM, dan status eksperimen. Refactor sheet `Uji Ketahanan OOD` dari matriks kolom model menjadi tabel panjang dengan kolom `Kondisi`, `Jumlah Sel`, `Model`, `Mode`, `Akurasi Exact`, `Drop vs Clean`, dan `Catatan`; isi lima kondisi untuk GLiNER zero-shot dan fine-tuned sekaligus, serta pertahankan seri encoder/Composite yang sudah tercatat.

Tambahkan entri `NER-GLINER-002` ke `docs/experiments_ledger.md` dengan model, paritas/pengecualian native loss-optimizer, hasil OOF per-field, CI, OOD, runtime/VRAM, verdict gate, dan penegasan zero blast radius produksi. Regenerasi `docs/report/runs_summary.md` melalui `uv run python scripts/generate_runs_summary.py`; generator sudah mengklasifikasikan prefix `gliner_` sebagai `ner_encoder`. Buat `docs/handoff_v49.md` yang merangkum komparasi GLiNER zero-shot/fine-tuned terhadap IndoBERT/XLM-R/DeBERTa, empat lapis bukti, file artefak, dan open frontier, dengan supersession note untuk `docs/handoff_v48.md`.
## Critical files & anchors
- `tests/benchmark_gliner.py` — runner zero-shot, extractor, mapping field, Bootstrap, dan OOD yang harus diperluas menjadi runner OOF tanpa mengubah benchmark zero-shot.
- `tests/benchmark_ner_encoders.py:build_examples`, `stratified_folds`, `run_model` — kontrak dataset, fold, artefak, dan evaluasi yang harus dipakai ulang untuk paritas.
- `.venv/lib/python3.11/site-packages/gliner/model.py:1846-2004` — API native GLiNER v2.1 `create_training_args`/`train_model` dan parameter yang tersedia.
- `.venv/lib/python3.11/site-packages/gliner2/training/trainer.py:89-270,635-813,1324-1384` — konfigurasi dan trainer GLiNER2.5; runner eksperimen mengadaptasi API tanpa mengubah dependensi terpasang.
- `scripts/generate_ner_encoder_report_xlsx.py` — tabel komparasi dan tabel OOD yang saat ini hanya memuat zero-shot GLiNER.

## Verification
1. Dari root repo, jalankan `uv run pytest tests/test_gliner_experiment.py tests/test_ner_encoder_experiment.py -v`. Kasus konkret: teks `Sertifikat Nomor 12/ABC/2024 untuk Seminar Data pada 1 Januari 2024 sampai 2 Januari 2024 oleh Himasada` menghasilkan span GLiNER `[2, 2, "certificate number"]`, dua mention `"date"`, dan `InputExample` tervalidasi; nilai GT tidak muncul menghasilkan audit `unmatched`, bukan label palsu. Kasus dokumen 768 subword dengan span 60 kata melintasi batas awal harus tetap menghasilkan sedikitnya satu window 512/64 yang memuat seluruh span.
2. Jalankan pra-latih masing-masing model: `uv run python -m tests.benchmark_gliner --mode fine-tune --sanity-overfit --models gliner-multi-v2.1` lalu perintah yang sama untuk `gliner2.5-base`. Keduanya harus mencapai exact recall span train 100%, loss/parameter finite, dan tidak mencatat batch skip/OOM sebelum OOF dapat dimulai.
3. Jalankan benchmark penuh serial: `uv run python -m tests.benchmark_gliner --mode fine-tune --models gliner-multi-v2.1 gliner2.5-base --folds 5 --epochs 10 --batch-size 1 --gradient-accumulation-steps 8 --learning-rate 2e-5`. Setiap run harus memuat 74 prediksi OOF dari lima fold non-kosong, 310 sel framework GT v9, manifest paritas, audit 223/87 alignment, ringkasan per field, CI bootstrap 1000x, OOD clean/10/25/50%, latency, dan peak VRAM.
4. Jalankan `uv run pytest tests/ -v`; kemudian `uv run python scripts/generate_ner_encoder_report_xlsx.py` dan `uv run python scripts/generate_runs_summary.py`. Periksa workbook berisi baris zero-shot dan fine-tuned terpisah serta tabel OOD memuat semua empat seri GLiNER; ledger, run summary, dan handoff v49 harus menyebut direktori run final yang sama.

## Assumptions & contingencies
- Kedua checkpoint dan API training sudah tersedia lokal; jika cache model hilang, unduh checkpoint resmi yang sama sebelum benchmark lalu catat revision/commit checkpoint di manifest.
- Jika preflight GLiNER2.5 full fine-tune dengan native AdamW, BF16/FP32 policy, gradient checkpointing, dan batch 1 masih OOM, hentikan benchmark GLiNER2.5 sebagai `INFEASIBLE_ON_8GB` serta dokumentasikan peak VRAM dan error. Jangan mengganti ke LoRA atau custom Adafactor karena itu bukan konfigurasi fine-tuning native yang ditetapkan di plan dan akan mengubah basis perbandingan.
- Ambang keberhasilan eksperimen adalah zero-regression terhadap baseline zero-shot masing-masing serta pelaporan lengkap. Hasil tidak menjadi kandidat produksi; bahkan nilai yang mengungguli encoder lain tetap tidak mengubah `ENABLE_TESSERACT_GEMINI` maupun flag Combined v4.2 tanpa persetujuan promosi pengguna.

## Validated Preflight Audit — Binding Corrections

Audit lokal 2026-09-03 menemukan flaw berikut. Bagian plan yang bertentangan di atas
disupersede oleh kontrak ini; pipeline produksi tetap tidak disentuh.

1. **Alignment bukan langsung label training.** `find_token_span()` mengembalikan
   `(start, end_exclusive)`, serta mencari pada token yang diratakan. Audit runtime
   mengonfirmasi kontrak lama: 310 field GT, 223 kandidat ditemukan, 87 tidak ditemukan.
   Tetapi 17 dari 223 first-hit membentang/melewati batas token atau mengambil kemunculan
   pertama yang salah; 10 field tidak memiliki span whole-token yang valid, sedangkan 7
   memiliki kemunculan whole-token lain yang valid. Runner tidak boleh mengubah fungsi
   shared tersebut. Tambahkan enumerator lokal whole-token yang menerima hanya span dengan
   `normalize_token("".join(tokens[start:end])) == normalize_token(gt_value)`, lalu
   kanonisasi posisi dengan menolak token batas yang normalisasinya kosong. Probe awal 78
   ambigu menghitung `-`/tanda baca di tepi sebagai posisi kedua; enumerator kanonik
   menghapus 13 duplikasi artifisial tersebut. Dari 213 field yang memiliki span
   whole-token, 148 memiliki tepat satu posisi dan 65 benar-benar ambigu. Tanpa bukti
   konteks tambahan, runner hanya melabeli 148 field unambiguous (130 tuple
   `(stem, start, end_inclusive, label)` setelah date-dedup). Semua 65 kandidat ambigu dan
   10 boundary-unmatched ditolak serta dicatat, bukan dipilih berdasar first occurrence.
   Audit wajib merekam: `candidate_found=223`, `initial_unmatched=87`,
   `first_hit_nonexact=17`, `fields_with_valid_whole_token=213`,
   `whole_token_ambiguous=65`, `whole_token_unambiguous=148`,
   `boundary_unmatched=10`, dan `usable_label_tuples=130`. Tidak ada fallback fuzzy,
   manual, atau label dari kandidat boundary-expanded maupun ambiguous.
2. **Konvensi indeks v1.** Setiap end dari `find_token_span` dan enumerator internal bersifat
   eksklusif; `to_gliner_v1_records()` wajib menulis `end_exclusive - 1`. GLiNER v2.1
   memang memakai indeks akhir inklusif. Test harus mencakup konversi ini dan first-hit
   palsu di nomor sertifikat.
   `max_width` wajib diteruskan pada `GLiNER.from_pretrained(..., max_length=512,
   max_width=64)`, bukan dimutasi sesudah load: span-representation layer dibangun saat
   konstruksi dan tetap width 12 bila config saja diubah. Preflight harus assert
   `model.config.max_len == 512`, `model.config.max_width == 64`, dan
   `model.model.span_rep_layer.span_rep_layer.max_width == 64` sebelum training.
3. **Validasi InputExample.** `InputExample.validate()` mengembalikan `list[str]`, bukan
   melempar exception. Runner wajib mengumpulkan error non-kosong lalu melempar
   `ValueError`; tidak boleh hanya memanggil hasilnya atau memakai `sanitize()`.
4. **Checkpoint GLiNER2.5 adalah boundary.** Konfigurasi lokal
   `fastino/gliner2.5-base-v1` menyatakan `architecture="boundary"`, sementara
   `GLiNER2.from_pretrained()` span-only. Gunakan
   `AutoExtractor.from_pretrained()` dan assert `model.architecture == "boundary"` sebelum
   trainer maupun inferensi. Gunakan `ExtractorTrainer` (alias `GLiNER2Trainer` tidak
   diperlukan).
5. **Window inferensi GLiNER2 harus tokenizer-aware.** API
   `extract_entities_long(chunk_size=512, chunk_overlap=64)` memotong *word token*, bukan
   subword. Tambahkan `window_gliner_text()` berbasis tokenizer dengan batas ≤512 subword
   termasuk special token dan overlap ≥64 subword; panggil `extract_entities()` langsung
   pada tiap window dengan `max_len=512`, lalu offset span karakter ke dokumen asal sebelum
   deduplikasi. Jangan gunakan `extract_entities_long()` untuk benchmark OOF ini.
6. **Empat lapis bukti dilaporkan jujur.** Lapis 1 (OOF + bootstrap) dan Lapis 2 (OOD)
   berlaku. Lapis 3 dicatat sebagai bukti anti-leakage/alignment/window, bukan klaim
   semantic-anchor karena GLiNER tidak menambah regex anchor. Lapis 4 dicatat
   `needs_review` tidak berlaku: eksperimen tidak memanggil mapper produksi atau mengubah
   confidence. Safety net yang dibuktikan adalah zero production blast radius. OOD paritas
   mempertahankan set runner encoder yang sebenarnya: kegiatan, dua tanggal, dan nomor;
   peranan tidak berada pada lima field evaluasi dan penyelenggara dikecualikan.

7. **OOD mutation tidak boleh mengkontaminasi ground truth.** Jika teks sumber
   mengubah entitas institusi, expected field yang memuat entitas tersebut wajib diubah
   secara ekuivalen atau dikeluarkan dari metrik. Laporan memisahkan field bebas institusi
   yang dapat memakai GT asli dari field pembawa institusi; skor terhadap GT lama tidak
   boleh diklaim sebagai robustness.

**Gate pra-latih tambahan:** hentikan sebelum model load bila statistik kandidat tidak
sama, ada label non-whole-token, span window terpotong, validasi `InputExample` gagal, atau
arsitektur GLiNER2 bukan boundary. Manifest dan ledger wajib menyebut angka audit ini
bersama 223/87 historis.
