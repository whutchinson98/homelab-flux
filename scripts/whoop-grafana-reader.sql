-- Run by configure-whoop-grafana.py as the local CNPG administrator, inside
-- a transaction. No table ownership changes, blanket SELECT or default grants.
DO $reader$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'whoop_grafana') THEN
        CREATE ROLE whoop_grafana LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
    IF EXISTS (
        SELECT FROM pg_roles WHERE rolname = 'whoop_grafana'
        AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) OR EXISTS (
        SELECT FROM pg_auth_members WHERE member = 'whoop_grafana'::regrole
    ) THEN
        RAISE EXCEPTION 'Existing whoop_grafana role has unexpected elevated privileges';
    END IF;
    IF EXISTS (
        SELECT FROM pg_class WHERE relnamespace = 'public'::regnamespace
        AND relowner = 'whoop_grafana'::regrole
    ) THEN
        RAISE EXCEPTION 'Dashboard reader must not own database objects';
    END IF;
END
$reader$;

ALTER ROLE whoop_grafana LOGIN NOINHERIT CONNECTION LIMIT 5;
ALTER ROLE whoop_grafana SET default_transaction_read_only = on;
ALTER ROLE whoop_grafana SET statement_timeout = '30s';
ALTER ROLE whoop_grafana SET search_path = pg_catalog, public;
GRANT CONNECT ON DATABASE whoop TO whoop_grafana;
GRANT USAGE ON SCHEMA public TO whoop_grafana;
GRANT SELECT ON public.whoop_cycle_metrics, public.whoop_cycle_metric_values,
    public.whoop_weight_observations TO whoop_grafana;

DO $permissions$
DECLARE
    object record;
BEGIN
    IF has_database_privilege('whoop_grafana', 'whoop', 'CREATE')
        OR has_schema_privilege('whoop_grafana', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'Dashboard reader unexpectedly has CREATE privileges';
    END IF;
    FOR object IN
        SELECT oid, relname FROM pg_class
        WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        IF has_table_privilege('whoop_grafana', object.oid,
                'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            OR has_any_column_privilege('whoop_grafana', object.oid, 'INSERT,UPDATE,REFERENCES') THEN
            RAISE EXCEPTION 'Unexpected write privileges on %', object.relname;
        END IF;
        IF object.relname NOT IN ('whoop_cycle_metrics', 'whoop_cycle_metric_values',
            'whoop_weight_observations')
            AND (has_table_privilege('whoop_grafana', object.oid, 'SELECT')
                OR has_any_column_privilege('whoop_grafana', object.oid, 'SELECT')) THEN
            RAISE EXCEPTION 'Unexpected read privileges on %', object.relname;
        END IF;
    END LOOP;
END
$permissions$;
