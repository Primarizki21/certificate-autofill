#!/usr/bin/env bash
# Audit keamanan staging & pre-commit verifier.
# Memastikan bebas dari secret, berkas kredensial, data privat, dan artefak berukuran > 5 MB.
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VERBOSE=false
for arg in "$@"; do
    case "$arg" in
        -v|--verbose) VERBOSE=true ;;
        *) ;;
    esac
done

VIOLATIONS=()
STAGED_FILES=$(git diff --cached --name-only --diff-filter=d)

# Pola berkas terlarang: kredensial, dataset privat mahasiswa, dokumen internal, dan artefak uji
BLOCKED_PATTERNS=(
    # Kredensial dan environment (kecuali berkas template .example)
    '(^|/)\.env(\..+)?$'
    '\.(pem|key|pkcs12|pfx|p12|keystore)$'
    '(^|/)(id_rsa|id_ed25519|id_ecdsa|id_dsa)(\.pub)?$'
    '(^|/)[^/]*(credential|credentials|secret|service_account)[^/]*\.json$'
    '(^|/)(token|auth)\.json$'
    'scripts/\.paper_search_state\.json$'

    # Dataset privat & benchmark internal
    '(^|/)Ground_Truth.*\.csv$'
    '(^|/)Sertifikat_Ground_Truth/'
    '(^|/)certs_test/'
    '(^|/)certs_unified/'
    '(^|/)tests/bio_labels/'
    '(^|/)tests/benchmark_runs/'
    '(^|/)tests/benchmark_results\.json$'
    '(^|/)data/'
    '(^|/)\.cache/'

    # Memori proyek internal, planning, dan aturan internal
    '(^|/)AGENTS\.md$'
    '(^|/)docs/handoff.*\.md$'
    '(^|/)docs/experiments_ledger.*\.md$'
    '(^|/)docs/experiments/'
    '(^|/)docs/screenshots/'
    '(^|/)docs/stress_test/'
    '(^|/)docs/security.*/'
    '(^|/)docs/pipeline_pr_3/'
    '(^|/)old_docs/'
    '(^|/)project_source/'
    '(^|/)docs/ADMIN_GUIDE\.md$'
    '(^|/)ADMIN_GUIDE\.md$'
    '.*_PLAN\.md$'
    '.*PLAN.*\.md$'
    '(^|/)CHANGELOG_RULES_.*\.md$'

    # Artefak eksternal & model biner besar
    '(^|/)tests/ner_model/'
    '(^|/)papers/'
    '(^|/)input_marker_paper/'
    '(^|/)output_marker/'
    '(^|/)cloudflared.*'
    '.*\.tunnel\.log$'
    '(^|/)graphify-out/'
    '(^|/)\.graphify_.*'
    '(^|/)laporan_pkl/'

    # Berkas uji coba temporer / scratch
    '(^|/)tmp_.*'
    '(^|/)test_.*_temp\.py$'
    '.*\.bak$'
    '.*\.tmp$'
    '.*\.orig$'
    '.*:Zone\.Identifier$'

    # Format biner / raster visual
    '\.(pdf|png|jpg|jpeg)$'
)

# Pola regex token dan kunci rahasia aktif
SECRET_REGEX='AIza[0-9A-Za-z_-]{35}|(sk|rk)_(live|test)_[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{24,}|ghp_[0-9A-Za-z]{36}|gho_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,}|AKIA[0-9A-Z]{16}|hf_[0-9A-Za-z]{34,}|ya29\.[0-9A-Za-z_-]+|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|xox[baprs]-[0-9A-Za-z]{10,}|-----BEGIN (RSA|EC|OPENSSH|DSA|PGP)? PRIVATE KEY-----'

STAGED_COUNT=0

if [ -n "$STAGED_FILES" ]; then
    while IFS= read -r file; do
        [ -z "$file" ] && continue
        STAGED_COUNT=$((STAGED_COUNT + 1))

        # Abaikan berkas template / dokumentasi contoh
        if echo "$file" | grep -qE '\.example$'; then
            continue
        fi

        # Pengecekan pola terlarang
        for pattern in "${BLOCKED_PATTERNS[@]}"; do
            if echo "$file" | grep -qE "$pattern"; then
                VIOLATIONS+=("[BLOCKED FILE] $file (pola: $pattern)")
                break
            fi
        done

        # Khusus .xlsx & .docx: blokir kecuali daftar whitelist resmi
        if echo "$file" | grep -qE '\.(xlsx|docx)$'; then
            WHITELIST_DOCS='^docs/report/(technical_report_tesseract_ocr\.docx|production_input_matrix\.docx|gt_review\.xlsx|raw_vs_pipeline_tesseract\.xlsx|komparasi_ner_encoder_dan_pipeline\.xlsx|production_input_matrix\.xlsx)$'
            if ! echo "$file" | grep -qE "$WHITELIST_DOCS"; then
                VIOLATIONS+=("[BLOCKED DOC] $file (.xlsx/.docx di luar whitelist resmi)")
            fi
        fi

        # Khusus direktori khp/ (kecuali aucc.sql.example)
        if echo "$file" | grep -qE '^khp/' && [ "$file" != "khp/aucc.sql.example" ]; then
            VIOLATIONS+=("[BLOCKED KHP] $file (direktori khp bersifat privat)")
        fi

        # Pengecekan batas ukuran berkas (maksimal 5 MB)
        if [ -f "$file" ]; then
            SIZE_BYTES=$(stat -c%s "$file")
            MAX_BYTES=$((5 * 1024 * 1024))
            if [ "$SIZE_BYTES" -gt "$MAX_BYTES" ]; then
                VIOLATIONS+=("[OVERSIZE] $file ($SIZE_BYTES bytes > 5 MB)")
            fi
        fi

        # Pemindaian pola secret pada baris tambah staged diff (+, abaikan header +++)
        DIFF_HITS=$(git diff --cached -U0 -- "$file" | grep -E "^\+[^+]" | grep -E "$SECRET_REGEX" || true)
        if [ -n "$DIFF_HITS" ]; then
            SNIPPET=$(echo "$DIFF_HITS" | head -n 1 | cut -c 1-60)
            VIOLATIONS+=("[SECRET IN DIFF] $file (snippet: $SNIPPET...)")
        fi
    done <<< "$STAGED_FILES"
fi

# Audit riwayat komit branch lokal terhadap origin/main
BASE_REF="origin/main"
BRANCH_STATUS="branch clean vs $BASE_REF"
if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    COMMITS_TO_AUDIT=$(git log "$BASE_REF..HEAD" --oneline || true)
    if [ -n "$COMMITS_TO_AUDIT" ]; then
        LOG_SECRET_HITS=$(git log -E -G"$SECRET_REGEX" "$BASE_REF..HEAD" -n 1 --oneline || true)
        if [ -n "$LOG_SECRET_HITS" ]; then
            VIOLATIONS+=("[SECRET IN LOG] Komit di $BASE_REF..HEAD memuat secret: $LOG_SECRET_HITS")
            BRANCH_STATUS="secret leak vs $BASE_REF"
        else
            COMMIT_COUNT=$(echo "$COMMITS_TO_AUDIT" | wc -l | tr -d ' ')
            BRANCH_STATUS="$COMMIT_COUNT commit(s) clean vs $BASE_REF"
        fi
    else
        BRANCH_STATUS="in sync with $BASE_REF"
    fi
else
    BRANCH_STATUS="ref $BASE_REF not found"
fi

# Cetak hasil audit
if [ "${#VIOLATIONS[@]}" -gt 0 ]; then
    echo -e "${RED}✗ [AUDIT FAILED] ${#VIOLATIONS[@]} pelanggaran keamanan terdeteksi:${NC}"
    for v in "${VIOLATIONS[@]}"; do
        echo -e "${RED}  - $v${NC}"
    done
    echo -e "${YELLOW}Batalkan commit dan bersihkan berkas bermasalah.${NC}"
    exit 1
fi

if [ "$VERBOSE" = true ]; then
    echo -e "${BLUE}=== Ringkasan Audit Keamanan Staging ===${NC}"
    echo -e "${GREEN}✓ Status: SEMUA PEMERIKSAAN LOLOS${NC}"
    echo -e "  - Berkas ter-stage: $STAGED_COUNT berkas"
    echo -e "  - Pola rahasia diff: 0 terdeteksi"
    echo -e "  - Status branch: $BRANCH_STATUS"
else
    echo -e "${GREEN}✓ [AUDIT OK] $STAGED_COUNT staged file(s) | 0 blocked | 0 secrets | $BRANCH_STATUS${NC}"
fi

exit 0
