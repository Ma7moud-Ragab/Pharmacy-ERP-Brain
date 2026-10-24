-- handover_ownership.sql (B2, D-50): ONE-TIME, run by a DBA (superuser) on a database built before D-50 by a
-- superuser migrator. Moves the Brain schemas, tables, views, functions and alembic_version to the migration owner,
-- so every later `alembic upgrade` runs as that non-superuser owner. Runtime grants and data are unchanged.
-- Usage: psql -d <db> -c "SET bb.migration_owner = '<owner login>'" -f handover_ownership.sql  (one session)
DO $do$ DECLARE r record; owner_role text := current_setting('bb.migration_owner'); BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = owner_role AND NOT rolsuper) THEN
    RAISE EXCEPTION 'bb.migration_owner must name an existing non-superuser login';
  END IF;
  -- 0007 and later revisions create public.brain_* functions; the owner needs CREATE on public (not ownership).
  EXECUTE 'GRANT USAGE, CREATE ON SCHEMA public TO ' || quote_ident(owner_role);
  FOR r IN SELECT nspname FROM pg_namespace WHERE nspname IN ('ingest','feat','intel','agent','audit') LOOP
    EXECUTE 'ALTER SCHEMA ' || quote_ident(r.nspname) || ' OWNER TO ' || quote_ident(owner_role);
  END LOOP;
  FOR r IN SELECT n.nspname, c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE (n.nspname IN ('ingest','feat','intel','agent','audit') AND c.relkind IN ('r', 'p', 'v'))
              OR (n.nspname = 'public' AND c.relname = 'alembic_version') LOOP
    EXECUTE 'ALTER ' || CASE r.relkind WHEN 'v' THEN 'VIEW ' ELSE 'TABLE ' END || quote_ident(r.nspname) || '.'
            || quote_ident(r.relname) || ' OWNER TO ' || quote_ident(owner_role);
  END LOOP;
  FOR r IN SELECT p.oid::regprocedure AS fn FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname IN ('ingest','feat','intel','agent','audit') OR (n.nspname = 'public' AND left(p.proname, 6) = 'brain_') LOOP
    EXECUTE 'ALTER FUNCTION ' || r.fn::text || ' OWNER TO ' || quote_ident(owner_role);
  END LOOP;
END $do$;
