BEGIN;
CREATE INDEX IF NOT EXISTS resort_notifications_created_at_idx
  ON public.resort_notifications (created_at);

CREATE OR REPLACE FUNCTION public.resort_list_notifications(p_actor_id bigint, p_before bigint DEFAULT NULL)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
  SELECT jsonb_build_object('notifications', coalesce((
    SELECT jsonb_agg(to_jsonb(inbox) ORDER BY inbox.id DESC) FROM (
      SELECT id,entity_kind,entity_id,event,title,message,created_at,read_at
      FROM public.resort_notifications
      WHERE user_id=p_actor_id AND (p_before IS NULL OR id<p_before)
        AND created_at > ((now() AT TIME ZONE 'Asia/Manila' - interval '5 months') AT TIME ZONE 'Asia/Manila')
      ORDER BY id DESC LIMIT 50
    ) inbox), '[]'::jsonb),
    'unread_count', (SELECT count(*) FROM public.resort_notifications
      WHERE user_id=p_actor_id AND read_at IS NULL
        AND created_at > ((now() AT TIME ZONE 'Asia/Manila' - interval '5 months') AT TIME ZONE 'Asia/Manila')));
$$;

CREATE OR REPLACE FUNCTION public.resort_purge_old_notifications()
RETURNS bigint LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp
AS $$
DECLARE removed bigint;
BEGIN
  DELETE FROM public.resort_notifications
  WHERE created_at <= ((now() AT TIME ZONE 'Asia/Manila' - interval '5 months') AT TIME ZONE 'Asia/Manila');
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END;
$$;
REVOKE ALL ON FUNCTION public.resort_purge_old_notifications() FROM PUBLIC, anon, authenticated;

-- Scheduled cleanup: 03:00 Philippine time, daily (19:00 UTC).
CREATE EXTENSION IF NOT EXISTS pg_cron;
SELECT cron.schedule('resort_notification_retention', '0 19 * * *',
  'SELECT public.resort_purge_old_notifications();');
SELECT public.resort_purge_old_notifications();
NOTIFY pgrst, 'reload schema';
COMMIT;
