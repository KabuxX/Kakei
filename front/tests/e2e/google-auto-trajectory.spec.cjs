const {test,expect}=require('@playwright/test');
async function seed(page,date,labels=['A','B','C']){
 await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
 for(const label of labels){const response=await page.request.post('/api/transactions',{headers:{Origin:'http://127.0.0.1:8767'},data:{title:`合成店舗${label}`,merchant:`合成店舗${label}`,date:`${date}T12:00`,type:'expense',category:'食費',amount:100,paymentMethod:'cash'}});expect(response.ok()).toBeTruthy();}
}
async function send(page,text){await page.getByRole('textbox',{name:'メッセージ',exact:true}).fill(text);const response=page.waitForResponse(r=>r.url().endsWith('/messages')&&r.request().method()==='POST');await page.getByRole('button',{name:'送信',exact:true}).click();return (await response).json();}
for(const [width,height,date] of [[1440,900,'2027-04-01'],[390,844,'2027-04-02']]){
 test(`direct creation and reload at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height});await seed(page,date);await page.goto('/#agent');
  const outgoing=page.waitForRequest(r=>r.url().endsWith('/messages')&&r.method()==='POST');
  const reply=await send(page,`${date}の取引記録によって、軌跡を作って`);
  const request=await outgoing;const replay=await page.request.post(request.url(),{headers:{Origin:'http://127.0.0.1:8767'},data:request.postDataJSON()});expect(await replay.json()).toEqual(reply);
  expect(reply.trajectoryCreation.counts).toEqual({saved:2,existing:0,excluded:1});
  await expect(page.getByText('2件保存 · 0件作成済み · 1件除外')).toBeVisible();await expect(page.getByText(/同名の候補が複数/)).toBeVisible();await expect(page.getByRole('button',{name:'確認して保存'})).toHaveCount(0);
  // Reload persisted results, then send a new same-day instruction.
  const messages=await page.request.get('/api/agent/threads');const thread=(await messages.json()).threads[0];
  await page.reload();if(width<600)await page.getByRole('button',{name:'会話履歴を開く'}).click();await page.getByRole('button',{name:thread.title,exact:true}).click();await expect(page.getByText(/2件保存 ·/)).toBeVisible();
  const again=await send(page,`${date}の軌跡を作って`);expect(again.trajectoryCreation.counts).toEqual({saved:0,existing:2,excluded:1});
  await page.getByRole('link',{name:`${date}の軌跡を開く`}).last().click();await expect(page.getByRole('combobox',{name:'表示する日付'})).toHaveValue(date);await expect(page.getByRole('heading',{name:'時系列'})).toBeVisible();await expect(page.getByText('2地点', {exact:true})).toBeVisible();await expect(page.getByText(/ブラウザ用キー/)).toBeVisible();
  await page.screenshot({path:`../docs/verification/2026-10-04-google-auto-trajectory/timeline-${width}.png`,fullPage:true,animations:'disabled'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 });
}
test('all excluded leaves existing dates and pending edits usable',async({page})=>{
 await seed(page,'2027-04-03',['C']);await page.goto('/#agent');await send(page,'給与を追加して');await expect(page.getByRole('button',{name:'確認して保存'})).toBeVisible();
 const before=await (await page.request.get('/api/trajectory')).json();const reply=await send(page,'2027-04-03の軌跡を作って');expect(reply.trajectoryCreation.counts).toEqual({saved:0,existing:0,excluded:1});
 expect(await (await page.request.get('/api/trajectory')).json()).toEqual(before);await expect(page.getByText('0件保存 · 0件作成済み · 1件除外')).toBeVisible();await expect(page.getByRole('button',{name:'確認して保存'})).toBeVisible();
});

test('Google map combines legacy visits and survives old proposal approval',async({page})=>{
 const date='2027-04-04',headers={Origin:'http://127.0.0.1:8767'};await seed(page,date,['A','B']);
 for(const data of [{kind:'place',id:'manual-google-mix',data:{name:'手動の訪問',address:null,coordinates:[139.7,35.6],sourceUrl:null,placeEvidence:'user'}},{kind:'day',date,data:{events:[{id:'manual-google-mix',placeId:'manual-google-mix',time:'11:00',timeEvidence:'exact'}],legs:[]}}])expect((await page.request.post('/api/trajectory',{headers,data})).ok()).toBeTruthy();
 await page.goto('/#agent');const pending=await send(page,'給与を追加して');const reply=await send(page,date+'の軌跡を作って');expect(reply.trajectoryCreation.counts.saved).toBe(2);
 expect((await page.request.post('/api/agent/proposals/'+pending.proposal.id+'/approve',{headers,data:{revision:1}})).ok()).toBeTruthy();
 const saved=await (await page.request.get('/api/trajectory/'+date)).json();expect(saved.days[0].events).toHaveLength(3);expect(Object.values(saved.places).filter(p=>p.provider==='google')).toHaveLength(2);
 await page.route('**/api/map-config',r=>r.fulfill({json:{googleMapsBrowserKey:'synthetic-browser-key',googleMapId:'DEMO_MAP_ID'}}));
 await page.route('https://maps.googleapis.com/maps/api/js?**',route=>{
  const callback=new URL(route.request().url()).searchParams.get('callback');return route.fulfill({contentType:'text/javascript',body:`window.google={maps:{Map:class{constructor(el){this.el=el;}fitBounds(){}setCenter(){}setZoom(){}},Polyline:class{setMap(){}},marker:{AdvancedMarkerElement:class{constructor(opts){Object.assign(this,opts);opts.map.el.append(opts.content);}}}}};window[${JSON.stringify(callback)}]();`});
 });
 await page.getByRole('link',{name:date+'の軌跡を開く'}).click();await expect(page.getByRole('button',{name:'1. 手動の訪問',exact:true})).toBeVisible();await page.getByRole('button',{name:/^[23]\. 合成店舗A$/}).focus();await page.keyboard.press('Enter');await expect(page.locator('.trajectory-event[aria-pressed="true"]')).toContainText('合成店舗A');
});
