#!/usr/bin/env bash
# ==============================================================================
# Skrip Audit Keamanan Staging & Pre-Commit Verifier
# Memastikan tidak ada secret, kredensial, data privat, atau berkas besar ter-stage.
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

ERRORS=0

echo -e "${BLUE}=== [1/4] Memeriksa Berkas yang Ter-stage (Staged Files Audit) ===${NC}"
STAGED_FILES=$(git diff --cached --name-only)

if [ -z "$STAGED_FILES" ]; then
    echo -e "${YELLOW}ℹ Tidak ada berkas yang ter-stage saat ini.${NC}"
else
    echo "Daftar berkas ter-stage:"
    echo "$STAGED_FILES" | sed 's/^/  - /'
    echo ""

    # 1. Cek berkas terlarang (.env nyata, dataset privat, folder eksperimen internal)
    BLOCKED_PATTERNS=(
        "^\.env$"
        "^\.env\.local$"
        "^\.env\.google$"
        "^\.env\.production$"
        "^Ground_Truth.*\.csv$"
        "^Sertifikat_Ground_Truth/"
        "^certs_test/"
        "^certs_unified/"
        "^tests/bio_labels/"
        "^tests/benchmark_runs/"
        "^tests/benchmark_results\.json$"
        "^docs/handoff.*\.md$"
        "^docs/experiments_ledger.*\.md$"
        "^docs/experiments/"
        "^.*_PLAN\.md$"
        "^.*PLAN.*\.md$"
        "^CHANGELOG_RULES_.*\.md$"
        "\.xlsx$"
        "\.docx$"
        "\.pdf$"
        "\.png$"
        "\.jpg$"
        "\.jpeg$"
    )

    for file in $STAGED_FILES; do
        for pattern in "${BLOCKED_PATTERNS[@]}"; do
            if echo "$file" | grep -qE "$pattern"; then
                echo -e "${RED}[BLOCKED] Berkas sensitif/privat ter-stage: $file (cocok pola: $pattern)${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        done

        # 2. Cek ukuran file (> 5 MB)
        if [ -f "$file" ]; then
            SIZE_BYTES=$(stat -c%s "$file")
            MAX_BYTES=$((5 * 1024 * 1024))
            if [ "$SIZE_BYTES" -gt "$MAX_BYTES" ]; then
                echo -e "${RED}[BLOCKED] Berkas melebihi batas 5 MB ($SIZE_BYTES bytes): $file${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    done
fi

echo -e "\n${BLUE}=== [2/4] Memindai Pola Kunci Rahasia pada Staged Diff (Secret Patterns) ===${NC}"
SECRET_REGEX='AIza[0-9A-Za-z_-]{35}|(sk|rk)_(live|test)_[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z]{24,}|ghp_[0-9A-Za-z]{36}|gho_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{22,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH|DSA|PGP)? PRIVATE KEY-----'

MATCHED_SECRETS=$(git diff --cached -U0 | grep -E "^\+" | grep -E "$SECRET_REGEX" || true)

if [ -n "$MATCHED_SECRETS" ]; then
    echo -e "${RED}[BLOCKED] Terdeteksi pola kunci rahasia / secret token pada perubahan bertanda tambah (+):${NC}"
    echo "$MATCHED_SECRETS" | head -n 10
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✓ Bebas pola secret aktif pada staged diff.${NC}"
fi

echo -e "\n${BLUE}=== [3/4] Memeriksa Riwayat Komit Branch vs origin/main ===${NC}"
BASE_REF="origin/main"
if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    COMMITS_TO_AUDIT=$(git log "$BASE_REF..HEAD" --oneline || true)
    if [ -n "$COMMITS_TO_AUDIT" ]; then
        LOG_SECRET_HITS=$(git log -E -G"$SECRET_REGEX" "$BASE_REF..HEAD" || true)
        if [ -n "$LOG_SECRET_HITS" ]; then
            echo -e "${RED}[BLOCKED] Terdeteksi secret dalam commit riwayat branch ini vs origin/main!${NC}"
            ERRORS=$((ERRORS + 1))
        else
            echo -e "${GREEN}✓ Seluruh komit di branch ini bersih dari pola secret (${BASE_REF}..HEAD).${NC}"
        fi
    else
        echo -e "${GREEN}✓ Branch sinkron dengan $BASE_REF.${NC}"
    fi
else
    echo -e "${YELLOW}ℹ Ref $BASE_REF tidak ditemukan; melewati perbandingan commit log.${NC}"
fi

echo -e "\n${BLUE}=== [4/4] Ringkasan Status Audit ===${NC}"
if [ "$ERRORS" -gt 0 ]; then
    echo -e "${RED}✗ DITEMUKAN $ERRORS PELANGGARAN KEAMANAN! Batalkan commit dan unstage berkas bermasalah.${NC}"
    exit 1
else
    echo -e "${GREEN}✓ SEMUA PEMERIKSAAN LOLOS! Aman untuk melanjutkan commit.${NC}"
    exit 0
fi
