#!/bin/sh
# Membuat catatan rilis dari Conventional Commits antara tag sebelumnya dan tag
# ini. Hasil ditulis ke stdout; workflow meneruskannya ke `gh release create`.
#
#   scripts/generate_release_notes.sh v0.2.0            # tag sebelumnya otomatis
#   scripts/generate_release_notes.sh v0.2.0 v0.1.0     # rentang eksplisit
#
# Sorotan manual per versi ditulis di docs/releases/<tag>.md (opsional). Isi
# berkas itu ditempatkan paling atas, diikuti daftar perubahan otomatis.
set -eu

TAG=${1:-}
if [ -z "$TAG" ]; then
    echo "usage: scripts/generate_release_notes.sh <tag> [previous-tag]" >&2
    exit 2
fi
PREV=${2:-}

if [ -z "$PREV" ]; then
    PREV=$(git describe --tags --abbrev=0 "${TAG}^" 2>/dev/null || true)
fi

if [ -n "$PREV" ]; then
    RANGE="${PREV}..${TAG}"
    COMPARE_REF="${PREV}...${TAG}"
else
    RANGE="${TAG}"
    COMPARE_REF=""
fi

REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
REPO=${GITHUB_REPOSITORY:-$(printf '%s' "$REMOTE_URL" | sed -E 's#.*github\.com[:/]([^/]+/[^/.]+)(\.git)?$#\1#')}

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

: > "$WORKDIR/breaking"
: > "$WORKDIR/feat"
: > "$WORKDIR/fix"
: > "$WORKDIR/perf"
: > "$WORKDIR/refactor"
: > "$WORKDIR/docs"
: > "$WORKDIR/test"
: > "$WORKDIR/internal"
: > "$WORKDIR/other"

git log --no-merges --pretty=format:'%s' "$RANGE" |
{
    cat
    printf '\n'
} |
while IFS= read -r subject; do
    [ -z "$subject" ] && continue
    case "$subject" in
        "Merge "*) continue ;;
    esac

    type=$(printf '%s' "$subject" | sed -nE 's/^([a-zA-Z]+)(\([^)]*\))?(!)?: .*/\1/p')
    scope=$(printf '%s' "$subject" | sed -nE 's/^[a-zA-Z]+\(([^)]*)\)(!)?: .*/\1/p')
    desc=$(printf '%s' "$subject" | sed -E 's/^[a-zA-Z]+(\([^)]*\))?!?: //')
    item="- ${desc}"
    if [ -n "$scope" ]; then
        item="- **${scope}:** ${desc}"
    fi

    case "$subject" in
        *"!:"*) printf '%s\n' "$item" >> "$WORKDIR/breaking" ;;
    esac

    case "$type" in
        feat) printf '%s\n' "$item" >> "$WORKDIR/feat" ;;
        fix) printf '%s\n' "$item" >> "$WORKDIR/fix" ;;
        perf) printf '%s\n' "$item" >> "$WORKDIR/perf" ;;
        refactor) printf '%s\n' "$item" >> "$WORKDIR/refactor" ;;
        docs) printf '%s\n' "$item" >> "$WORKDIR/docs" ;;
        test) printf '%s\n' "$item" >> "$WORKDIR/test" ;;
        build|ci|chore|style) printf '%s\n' "$item" >> "$WORKDIR/internal" ;;
        *) printf '%s\n' "$item" >> "$WORKDIR/other" ;;
    esac
done

emit() {
    title=$1
    file=$2
    [ -s "$file" ] || return 0
    printf '## %s\n\n' "$title"
    cat "$file"
    printf '\n'
}

printf '# %s\n\n' "$TAG"
printf 'Tanggal: %s\n' "$(date -u +%Y-%m-%d)"
if [ -n "$COMPARE_REF" ] && [ -n "$REPO" ]; then
    printf 'Perbandingan lengkap: https://github.com/%s/%s\n' "$REPO" "compare/${COMPARE_REF}"
fi
printf '\n'

MANUAL="docs/releases/${TAG}.md"
if [ -f "$MANUAL" ]; then
    cat "$MANUAL"
    printf '\n'
fi

emit "Perubahan breaking" "$WORKDIR/breaking"
emit "Fitur" "$WORKDIR/feat"
emit "Perbaikan" "$WORKDIR/fix"
emit "Performa" "$WORKDIR/perf"
emit "Refaktor" "$WORKDIR/refactor"
emit "Dokumentasi" "$WORKDIR/docs"
emit "Pengujian" "$WORKDIR/test"
emit "Internal" "$WORKDIR/internal"
emit "Lainnya" "$WORKDIR/other"

printf '## Deploy\n\n'
printf '```bash\n'
printf 'scripts/build_release.sh %s\n' "$TAG"
printf 'docker load < cert-autofill-images-%s.tar.gz\n' "$TAG"
printf 'BACKEND_IMAGE=cert-autofill-backend:%s \\\n' "$TAG"
printf '  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d\n'
printf '```\n'
