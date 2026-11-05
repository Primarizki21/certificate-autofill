#!/bin/sh
# Backup PostgreSQL terjadwal (RPO 1 jam) dengan retensi 48 jam, 14 harian,
# 12 bulanan. Jalankan sebagai service compose atau cron host.
set -eu

: "${PGHOST:=postgres}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=certautofill}"
: "${PGUSER:=cert_backup}"
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_INTERVAL_SECONDS:=3600}"
: "${BACKUP_OFFSITE_DIR:=}"
: "${BACKUP_ONCE:=0}"

if [ -z "${PGPASSWORD:-}" ] && [ -n "${BACKUP_DB_PASSWORD:-}" ]; then
    PGPASSWORD=$BACKUP_DB_PASSWORD
    export PGPASSWORD
fi

export PGHOST PGPORT PGDATABASE PGUSER

mkdir -p "$BACKUP_DIR/hourly" "$BACKUP_DIR/daily" "$BACKUP_DIR/monthly"

prune() {
    find "$BACKUP_DIR/hourly" -maxdepth 1 -name '*.dump' -mmin +2880 -delete
    find "$BACKUP_DIR/daily" -maxdepth 1 -name '*.dump' -mtime +14 -delete
    find "$BACKUP_DIR/monthly" -maxdepth 1 -name '*.dump' -mtime +365 -delete
}

while true; do
    stamp=$(date -u +%Y%m%d-%H)
    day=$(date -u +%Y%m%d)
    month=$(date -u +%Y%m)
    target="$BACKUP_DIR/hourly/certautofill-$stamp.dump"

    if pg_dump --format=custom --no-owner --no-privileges --file="$target.part"; then
        if pg_restore --list "$target.part" >/dev/null; then
            mv "$target.part" "$target"
            echo "$(date -u +%FT%TZ) backup ok: $target"
        else
            rm -f "$target.part"
            echo "$(date -u +%FT%TZ) backup FAILED: dump tidak bisa dibaca" >&2
        fi
    else
        rm -f "$target.part"
        echo "$(date -u +%FT%TZ) backup FAILED: pg_dump error" >&2
    fi

    if [ -f "$target" ]; then
        if [ "$(date -u +%H)" = "00" ]; then
            ln -f "$target" "$BACKUP_DIR/daily/certautofill-$day.dump"
        fi
        if [ "$(date -u +%d)" = "01" ] && [ "$(date -u +%H)" = "00" ]; then
            ln -f "$target" "$BACKUP_DIR/monthly/certautofill-$month.dump"
        fi
        if [ -n "$BACKUP_OFFSITE_DIR" ]; then
            mkdir -p "$BACKUP_OFFSITE_DIR"
            cp "$target" "$BACKUP_OFFSITE_DIR/" || echo "salinan offsite gagal" >&2
        fi
    fi

    prune

    if [ "$BACKUP_ONCE" = "1" ]; then
        break
    fi
    sleep "$BACKUP_INTERVAL_SECONDS"
done
