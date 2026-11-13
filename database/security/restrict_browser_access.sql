-- REVIEW BEFORE APPLYING. Run only with an administrative Supabase connection.
-- The application uses a server-only service_role key; browsers call Flask.
-- This script has NOT been applied to the live database by the security review.
BEGIN;
DO $$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT n.nspname, c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND c.relname IN ('users','bookings','service_avails','booking_payments',
        'service_payments','resort_transfer_references','resort_password_resets',
        'resort_email_outbox','resort_notifications','rooms','services','reviews')
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', item.nspname, item.relname);
    EXECUTE format('REVOKE ALL ON TABLE %I.%I FROM PUBLIC, anon, authenticated', item.nspname, item.relname);
    EXECUTE format('GRANT ALL ON TABLE %I.%I TO service_role', item.nspname, item.relname);
  END LOOP;
  FOR item IN
    SELECT p.oid::regprocedure AS signature FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.prokind = 'f' AND left(p.proname, 7) = 'resort_'
  LOOP
    EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, anon, authenticated', item.signature);
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', item.signature);
  END LOOP;
END $$;
COMMIT;
