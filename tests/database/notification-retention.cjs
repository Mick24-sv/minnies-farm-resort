// Isolated SQL test; pg_cron scheduling is verified separately on Supabase.
const {PGlite}=require(process.env.PGLITE_PATH || '@electric-sql/pglite');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const db=new PGlite();try{
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated;
    CREATE TABLE public.resort_notifications(id bigint PRIMARY KEY,user_id bigint,entity_kind text,entity_id bigint,event text,title text,message text,created_at timestamptz,read_at timestamptz);
    CREATE TABLE public.test_delivery(notification_id bigint REFERENCES public.resort_notifications(id) ON DELETE SET NULL);
    INSERT INTO public.resort_notifications(id,user_id,created_at,read_at) VALUES
    (1,7,now()-interval '6 months',NULL),(2,7,now()-interval '1 month',NULL),
    (3,7,now()-interval '2 months',now()),(4,8,now()-interval '1 month',NULL),
    (5,7,((now() AT TIME ZONE 'Asia/Manila'-interval '5 months') AT TIME ZONE 'Asia/Manila'),NULL);
    INSERT INTO public.test_delivery VALUES(1);`);
  const sql=fs.readFileSync(path.resolve(__dirname,'../../database/migrations/20261114_notification_retention.sql'),'utf8');
  await db.exec(sql.split('-- Scheduled cleanup:')[0]+'COMMIT;');
  const inbox=(await db.query('SELECT public.resort_list_notifications(7) AS inbox')).rows[0].inbox;
  assert.deepEqual(inbox.notifications.map(n=>n.id),[3,2]);assert.equal(inbox.unread_count,1);
  const older=(await db.query('SELECT public.resort_list_notifications(7,3) AS inbox')).rows[0].inbox;
  assert.deepEqual(older.notifications.map(n=>n.id),[2]);assert.equal(older.unread_count,1);
  assert.equal((await db.query('SELECT public.resort_purge_old_notifications() AS removed')).rows[0].removed,2);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.resort_notifications')).rows[0].n,3);
  assert.equal((await db.query('SELECT notification_id FROM public.test_delivery')).rows[0].notification_id,null);
  assert.equal((await db.query("SELECT has_function_privilege('anon','public.resort_purge_old_notifications()','EXECUTE') AS allowed")).rows[0].allowed,false);
  console.log('PASS: five-calendar-month boundary, unread count, ownership, pagination, purge, delivery preservation and permissions.');
}finally{await db.close()}})().catch(e=>{console.error(e.message);process.exitCode=1});
