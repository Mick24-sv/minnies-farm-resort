-- Adds nullable clock times to existing date-based room bookings.
-- Existing reservations are left unchanged; pricing/availability remain per night.
BEGIN;
ALTER TABLE public.bookings
  ADD COLUMN IF NOT EXISTS check_in_time time without time zone,
  ADD COLUMN IF NOT EXISTS check_out_time time without time zone;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'bookings_selected_times_valid'
                 AND conrelid = 'public.bookings'::regclass) THEN
    ALTER TABLE public.bookings ADD CONSTRAINT bookings_selected_times_valid CHECK (
      (check_in_time IS NULL AND check_out_time IS NULL) OR
      (check_in_time IS NOT NULL AND check_out_time IS NOT NULL
       AND check_in_time < time '24:00' AND check_out_time < time '24:00'
       AND (check_in + check_in_time) < (check_out + check_out_time))
    );
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.resort_create_booking_with_times(p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp
AS $$
DECLARE
  v_result jsonb;
  v_booking public.bookings%ROWTYPE;
  v_arrival time;
  v_departure time;
BEGIN
  IF jsonb_typeof(p_payload) <> 'object'
     OR COALESCE(p_payload->>'p_check_in_time', '') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
     OR COALESCE(p_payload->>'p_check_out_time', '') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' THEN
    RAISE EXCEPTION 'BOOKING_INVALID';
  END IF;
  v_arrival := (p_payload->>'p_check_in_time')::time;
  v_departure := (p_payload->>'p_check_out_time')::time;
  IF (p_payload->>'p_check_out')::date <= (p_payload->>'p_check_in')::date THEN
    RAISE EXCEPTION 'BOOKING_INVALID';
  END IF;
  IF p_payload->>'p_source' = 'online'
     AND (((p_payload->>'p_check_in')::date + v_arrival) AT TIME ZONE 'Asia/Manila') <= now() THEN
    RAISE EXCEPTION 'BOOKING_INVALID';
  END IF;

  -- Serialize time-aware reservations for this room.
  PERFORM 1 FROM public.rooms WHERE id = (p_payload->>'p_room_id')::bigint FOR UPDATE;
  -- Call the existing transactional booking/payment function; do not duplicate pricing,
  -- stock/availability, actor checks, deposits, walk-in payments or retry-key behavior.
  SELECT to_jsonb(public.resort_create_booking(
    p_actor_id => (p_payload->>'p_actor_id')::bigint,
    p_room_id => (p_payload->>'p_room_id')::bigint,
    p_check_in => (p_payload->>'p_check_in')::date,
    p_check_out => (p_payload->>'p_check_out')::date,
    p_guests => (p_payload->>'p_guests')::integer,
    p_source => p_payload->>'p_source',
    p_guest_name => p_payload->>'p_guest_name',
    p_guest_phone => p_payload->>'p_guest_phone',
    p_request_key => p_payload->>'p_request_key',
    p_method => p_payload->>'p_method',
    p_reference => p_payload->>'p_reference',
    p_expected_total => (p_payload->>'p_expected_total')::numeric
  )) INTO v_result;

  IF COALESCE(v_result->>'id', '') !~ '^[0-9]+$' THEN
    RAISE EXCEPTION 'BOOKING_INVALID';
  END IF;
  SELECT * INTO STRICT v_booking FROM public.bookings
    WHERE id = (v_result->>'id')::bigint FOR UPDATE;
  IF (v_booking.check_in_time IS NOT NULL AND v_booking.check_in_time <> v_arrival)
     OR (v_booking.check_out_time IS NOT NULL AND v_booking.check_out_time <> v_departure) THEN
    RAISE EXCEPTION 'BOOKING_KEY_CONFLICT';
  END IF;
  -- Protect same-day turnovers. Legacy bookings reserve their boundary days
  -- conservatively until the resort has supplied their real clock times.
  IF EXISTS (
    SELECT 1 FROM public.bookings other
    WHERE other.room_id = v_booking.room_id AND other.id <> v_booking.id
      AND other.status IN ('pending', 'confirmed')
      AND tsrange(other.check_in + COALESCE(other.check_in_time, time '00:00'),
                  other.check_out + COALESCE(other.check_out_time, time '23:59:59.999999'), '[)')
          && tsrange(v_booking.check_in + v_arrival, v_booking.check_out + v_departure, '[)')
  ) THEN
    RAISE EXCEPTION 'BOOKING_ROOM_UNAVAILABLE';
  END IF;
  UPDATE public.bookings SET check_in_time = v_arrival, check_out_time = v_departure
    WHERE id = v_booking.id RETURNING * INTO v_booking;
  RETURN to_jsonb(v_booking);
END $$;

REVOKE ALL ON FUNCTION public.resort_create_booking_with_times(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.resort_create_booking_with_times(jsonb) TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
