#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=rest_password="$POSTGREST_DB_PASSWORD" --set=freqtrade_password="$FREQTRADE_DB_PASSWORD" <<'SQL'
CREATE ROLE service_role NOLOGIN BYPASSRLS;
CREATE ROLE authenticator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'rest_password';
GRANT service_role TO authenticator;
CREATE ROLE freqtrade_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'freqtrade_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
