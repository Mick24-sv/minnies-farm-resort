BEGIN;
CREATE TABLE public.customer_history_visibility (
  user_id bigint NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  entity_kind text NOT NULL CHECK (entity_kind IN ('booking','service')),
  entity_id bigint NOT NULL,
  hidden_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id,entity_kind,entity_id)
);
ALTER TABLE public.customer_history_visibility ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.customer_history_visibility FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.customer_history_visibility TO service_role;

CREATE FUNCTION public.resort_set_history_visibility(p_actor_id bigint,p_kind text,p_entity_id bigint,p_hidden boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp
AS $$
DECLARE owner_id bigint; current_status text;
BEGIN
  IF p_hidden IS NULL OR p_kind IS NULL OR p_kind NOT IN ('booking','service') THEN RAISE EXCEPTION 'BOOKING_INVALID'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.users WHERE id=p_actor_id AND role='guest') THEN RAISE EXCEPTION 'BOOKING_FORBIDDEN'; END IF;
  IF p_kind='booking' THEN
    SELECT user_id,status INTO owner_id,current_status FROM public.bookings WHERE id=p_entity_id FOR UPDATE;
  ELSE
    SELECT user_id,status INTO owner_id,current_status FROM public.service_avails WHERE id=p_entity_id FOR UPDATE;
  END IF;
  IF NOT FOUND THEN RAISE EXCEPTION 'BOOKING_NOT_FOUND'; END IF;
  IF owner_id IS DISTINCT FROM p_actor_id THEN RAISE EXCEPTION 'BOOKING_FORBIDDEN'; END IF;
  IF p_hidden AND (current_status IS NULL OR current_status NOT IN ('completed','cancelled')) THEN RAISE EXCEPTION 'HISTORY_ACTIVE'; END IF;
  IF p_hidden THEN
    INSERT INTO public.customer_history_visibility(user_id,entity_kind,entity_id)
      VALUES(p_actor_id,p_kind,p_entity_id) ON CONFLICT DO NOTHING;
  ELSE
    DELETE FROM public.customer_history_visibility WHERE user_id=p_actor_id AND entity_kind=p_kind AND entity_id=p_entity_id;
  END IF;
  RETURN jsonb_build_object('hidden',p_hidden);
END $$;
REVOKE ALL ON FUNCTION public.resort_set_history_visibility(bigint,text,bigint,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.resort_set_history_visibility(bigint,text,bigint,boolean) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
