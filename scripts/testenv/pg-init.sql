-- Test database owned by a NON-superuser role: superusers bypass Row Level
-- Security, so tests must connect as this role for RLS to be exercised.
CREATE ROLE truebind_app LOGIN PASSWORD 'truebind-test-only' NOSUPERUSER NOCREATEROLE;
CREATE DATABASE truebind_test OWNER truebind_app;
-- Separate database for the migration round-trip check (fresh, never shared).
CREATE DATABASE truebind_migrations OWNER truebind_app;
-- Separate database for the Playwright end-to-end run.
CREATE DATABASE truebind_e2e OWNER truebind_app;
