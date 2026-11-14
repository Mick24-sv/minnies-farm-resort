const {PGlite}=require(process.env.PGLITE_PATH || '@electric-sql/pglite');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const db=new PGlite();try{
await db.exec(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role;
CREATE TABLE users(id bigint PRIMARY KEY,role text);INSERT INTO users VALUES(1,'guest'),(2,'guest'),(3,'staff');
CREATE TABLE bookings(id bigint PRIMARY KEY,user_id bigint,status text);INSERT INTO bookings VALUES(1,1,'completed'),(2,1,'pending');
CREATE TABLE service_avails(id bigint PRIMARY KEY,user_id bigint,status text);INSERT INTO service_avails VALUES(1,1,'cancelled'),(2,1,'confirmed');`);
await db.exec(fs.readFileSync(path.resolve(__dirname,'../../database/migrations/20261114_customer_history_visibility.sql'),'utf8'));
const change=(actor,kind,id,hidden)=>db.query('SELECT resort_set_history_visibility($1,$2,$3,$4)',[actor,kind,id,hidden]);
for(const kind of ['booking','service']){
 await assert.rejects(change(2,kind,1,true),/BOOKING_FORBIDDEN/);
 await assert.rejects(change(3,kind,1,true),/BOOKING_FORBIDDEN/);
 await assert.rejects(change(1,kind,2,true),/HISTORY_ACTIVE/);
 await change(1,kind,1,true);await change(1,kind,1,true);
 assert.equal((await db.query('SELECT count(*)::int AS n FROM customer_history_visibility WHERE entity_kind=$1',[kind])).rows[0].n,1);
 await change(1,kind,1,false);
}
assert.equal((await db.query('SELECT count(*)::int AS n FROM customer_history_visibility')).rows[0].n,0);
assert.equal((await db.query('SELECT count(*)::int AS n FROM bookings')).rows[0].n,2);
assert.equal((await db.query('SELECT count(*)::int AS n FROM service_avails')).rows[0].n,2);
assert.equal((await db.query("SELECT has_function_privilege('anon','resort_set_history_visibility(bigint,text,bigint,boolean)','EXECUTE') AS allowed")).rows[0].allowed,false);
console.log('PASS room/service hide and restore, retry safety, ownership, staff/active rejection, original records and permissions.');
}finally{await db.close()}})().catch(e=>{console.error(e.message);process.exitCode=1});
