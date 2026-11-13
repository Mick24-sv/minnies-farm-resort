// Disposable PostgreSQL test. The original booking RPC is a stub: this checks the
// new wrapper/constraints/rollback/permissions, not production pricing or triggers.
const { PGlite } = require(process.env.PGLITE_PATH || '@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const db = new PGlite();
  try {
    await db.exec(`
      CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
      CREATE TABLE public.rooms(id bigint PRIMARY KEY);
      INSERT INTO public.rooms VALUES (1);
      CREATE TABLE public.bookings(id bigserial PRIMARY KEY, room_id bigint NOT NULL,
        user_id bigint, check_in date NOT NULL, check_out date NOT NULL, guest_count integer,
        status text DEFAULT 'pending', request_key text UNIQUE, total_price numeric DEFAULT 2000);
      CREATE TABLE public.test_receipts(booking_id bigint, amount numeric);
      INSERT INTO public.bookings(room_id,user_id,check_in,check_out,status,request_key)
        VALUES (1,7,'2035-05-01','2035-05-03','confirmed','legacy');
      CREATE FUNCTION public.resort_create_booking(p_actor_id bigint,p_room_id bigint,
        p_check_in date,p_check_out date,p_guests integer,p_source text,p_guest_name text,
        p_guest_phone text,p_request_key text,p_method text DEFAULT NULL,
        p_reference text DEFAULT NULL,p_expected_total numeric DEFAULT NULL)
      RETURNS jsonb LANGUAGE plpgsql AS $$
      DECLARE result public.bookings%ROWTYPE;
      BEGIN
        SELECT * INTO result FROM public.bookings WHERE request_key=p_request_key;
        IF FOUND THEN RETURN to_jsonb(result); END IF;
        INSERT INTO public.bookings(room_id,user_id,check_in,check_out,guest_count,request_key)
          VALUES(p_room_id,p_actor_id,p_check_in,p_check_out,p_guests,p_request_key)
          RETURNING * INTO result;
        IF p_source='walk_in' THEN INSERT INTO public.test_receipts VALUES(result.id,2000); END IF;
        RETURN to_jsonb(result);
      END $$;
    `);
    const migration = fs.readFileSync(path.resolve(__dirname, '../../database/migrations/20261114_booking_times.sql'), 'utf8');
    await db.exec(migration);
    const old = (await db.query("SELECT check_in_time,check_out_time FROM public.bookings WHERE request_key='legacy'")).rows[0];
    assert.equal(old.check_in_time, null); assert.equal(old.check_out_time, null);
    const payload = {p_actor_id:7,p_room_id:1,p_check_in:'2035-06-01',p_check_out:'2035-06-02',p_guests:2,
      p_source:'online',p_guest_name:'QA',p_guest_phone:'',p_request_key:'times-1',p_check_in_time:'14:30',p_check_out_time:'09:15'};
    const create = async body => (await db.query('SELECT public.resort_create_booking_with_times($1::jsonb) AS booking',[JSON.stringify(body)])).rows[0].booking;
    const created = await create(payload);
    assert.equal(created.check_in_time, '14:30:00'); assert.equal(created.check_out_time, '09:15:00');
    assert.equal(created.total_price, 2000);
    assert.equal((await create(payload)).id, created.id);
    await assert.rejects(create({...payload,p_check_in_time:'15:30'}), /BOOKING_KEY_CONFLICT/);
    await assert.rejects(create({...payload,p_request_key:'bad-clock',p_check_in_time:'24:00'}), /BOOKING_INVALID/);
    const before = (await db.query('SELECT count(*)::int AS count FROM public.bookings')).rows[0].count;
    await assert.rejects(create({...payload,p_source:'walk_in',p_request_key:'overlap',p_check_in:'2035-06-02',p_check_out:'2035-06-03',p_check_in_time:'08:30'}), /BOOKING_ROOM_UNAVAILABLE/);
    assert.equal((await db.query('SELECT count(*)::int AS count FROM public.bookings')).rows[0].count,before);
    assert.equal((await db.query('SELECT count(*)::int AS count FROM public.test_receipts')).rows[0].count,0);
    await create({...payload,p_request_key:'adjacent',p_check_in:'2035-06-02',p_check_out:'2035-06-03',p_check_in_time:'09:15'});
    await assert.rejects(create({...payload,p_request_key:'legacy-boundary',p_check_in:'2035-05-03',p_check_out:'2035-05-04'}), /BOOKING_ROOM_UNAVAILABLE/);
    const privileges = (await db.query("SELECT has_function_privilege('anon','public.resort_create_booking_with_times(jsonb)','EXECUTE') AS anon,has_function_privilege('authenticated','public.resort_create_booking_with_times(jsonb)','EXECUTE') AS authenticated,has_function_privilege('service_role','public.resort_create_booking_with_times(jsonb)','EXECUTE') AS server")).rows[0];
    assert.equal(privileges.anon,false); assert.equal(privileges.authenticated,false); assert.equal(privileges.server,true);
    await db.exec(migration);
    console.log('PASS: migration executes and reapplies; legacy rows preserved; times persist; retry-key conflict rejected; overlap rolls back booking/payment; exact turnover allowed; legacy boundary protected; browser roles cannot execute.');
  } finally { await db.close(); }
})().catch(error=>{console.error(error.message);process.exitCode=1});
