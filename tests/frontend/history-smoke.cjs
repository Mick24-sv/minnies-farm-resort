const{chromium}=require(process.env.PLAYWRIGHT_PATH || 'playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
const flags={booking:false,service:false};let fail=false;const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>sessionStorage.setItem('token','qa'));
await page.route('**/api/**',route=>{
 const req=route.request(),url=new URL(req.url());let status=200,data={rooms:[],services:[],avails:[],bookings:[],notifications:[],accounts:[],configured:true};
 if(url.pathname.endsWith('/me'))data={user:{id:7,name:'QA guest',role:'guest'}};
 else if(url.pathname.startsWith('/api/history/')){
  const kind=url.pathname.split('/')[3];
  if(fail){status=503;data={error:'Test save failure'};}else{flags[kind]=req.postDataJSON().hidden;data={hidden:flags[kind]};}
 }else if(url.pathname==='/api/bookings')data={bookings:[{id:1,user_id:7,room_id:1,room_name:'Garden Room',status:'completed',check_in:'2026-11-01',check_out:'2026-11-02',guest_count:1,total_price:2200,hidden_from_history:flags.booking}]};
 else if(url.pathname==='/api/services/avails')data={avails:[{id:1,user_id:7,service_name:'Day visit',status:'completed',quantity:1,total_price:200,hidden_from_history:flags.service},{id:2,user_id:7,service_name:'Active service',status:'pending',quantity:1,total_price:100}]};
 return route.fulfill({status,json:data});
});
await page.goto('http://127.0.0.1:5000');
await page.evaluate(()=>__app._container._vnode.component.proxy.navigate('dashboard'));
const reservations=page.locator('.guest-tabs[aria-label="Reservation history"]');
await reservations.getByRole('button',{name:/Past/}).tap();
await page.locator('.guest-booking .history-visibility-button').tap();assert.equal(flags.booking,true);
assert.equal(await page.locator('.guest-booking').count(),0);
await reservations.getByRole('button',{name:/Hidden/}).tap();
await page.locator('.guest-booking').waitFor();
await page.evaluate(()=>__app._container._vnode.component.proxy.fetchUserBookings());
assert.equal(await page.locator('.guest-booking').count(),1,'hidden preference survives fetch');
await page.locator('.guest-booking').getByRole('button',{name:'Restore to history',exact:true}).tap();assert.equal(flags.booking,false);
await reservations.getByRole('button',{name:/Past/}).tap();await page.locator('.guest-booking').waitFor();
const services=page.locator('.guest-services');
assert.equal(await services.locator('.history-visibility-button').count(),1,'active request has no hide action');
fail=true;await services.getByRole('button',{name:'Hide from history',exact:true}).tap();
await page.getByText('Test save failure',{exact:true}).waitFor();assert.equal(await services.locator('.guest-service-record').count(),2);
fail=false;await services.getByRole('button',{name:'Hide from history',exact:true}).tap();assert.equal(flags.service,true);
assert.equal(await services.locator('.guest-service-record').count(),1);
await services.getByRole('button',{name:/Hidden/}).tap();
assert.equal(await services.locator('.guest-service-record').count(),1);
assert.equal(await services.getByRole('button',{name:'Payment history',exact:true}).count(),1,'receipt access remains available');
await services.getByRole('button',{name:'Restore to history',exact:true}).tap();assert.equal(flags.service,false);
await services.getByRole('button',{name:/Requests/}).tap();assert.equal(await services.locator('.guest-service-record').count(),2);
assert.deepEqual(errors,[]);console.log('PASS mobile room and service hide/restore, persisted state, active request protection, failed-save recovery, and retained payment access.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
