-- Role backup read-only. Jalankan dengan password dari secret manager:
--   psql -U postgres -d certautofill -v backup_password="$(cat /run/secrets/db_backup)" \
--        -f scripts/sql/create_backup_role.sql
\set ON_ERROR_STOP on

SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cert_backup') AS role_exists \gset
\if :role_exists
\echo 'role cert_backup sudah ada, password tidak diubah'
\else
CREATE ROLE cert_backup LOGIN PASSWORD :'backup_password';
\endif

GRANT CONNECT ON DATABASE certautofill TO cert_backup;
GRANT USAGE ON SCHEMA public TO cert_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cert_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO cert_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO cert_backup;
