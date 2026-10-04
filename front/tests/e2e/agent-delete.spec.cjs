const {test,expect}=require('@playwright/test');
const shots=process.env.KAKEI_E2E_ARTIFACT_DIR||'../docs/verification/2026-10-04-agent-delete';

for (const [kind,date,message,heading] of [
 ['event','2027-02-01','訪問を削除','訪問を削除'],
 ['leg','2027-02-02','移動区間を削除','移動区間を削除'],
 ['day','2027-02-03','一日の軌跡を削除','一日の軌跡を削除'],
]) {
 test(`${kind} deletion reviews scope and refreshes saved trajectory`,async({page,baseURL})=>{
  test.skip(baseURL!=='http://127.0.0.1:8767','disposable browser runner only');
  await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  const headers={Origin:baseURL};
  const prefix=`delete-${kind}`;
  for (const [id,name] of [['a','出発店'],['b','削除する店'],['c','到着店']]) {
   const response=await page.request.post('/api/trajectory',{headers,data:{kind:'place',id:`${prefix}-${id}`,data:{name,address:null,coordinates:[139.7,35.6],sourceUrl:null,placeEvidence:'user'}}});
   expect(response.ok()).toBe(true);
  }
  const data={events:['a','b','c'].map((id,i)=>({id:`${prefix}-${id}`,placeId:`${prefix}-${id}`,time:`${9+i}:00`.padStart(5,'0'),timeEvidence:'exact'})),legs:[['a','b'],['b','c']].map(([a,b])=>({fromEventId:`${prefix}-${a}`,toEventId:`${prefix}-${b}`,modeEvidence:'inferred',modeEvidenceNote:'検証用の概算'}))};
  const created=await page.request.post('/api/trajectory',{headers,data:{kind:'day',date,data}});
  expect(created.ok()).toBe(true);
  await page.goto('/#agent');
  await page.getByRole('textbox',{name:'メッセージ',exact:true}).fill(`${date} ${message}（削除の動作確認）`);
  await page.getByRole('button',{name:'送信',exact:true}).click();
  const card=page.getByRole('article',{name:'変更案'});
  await expect(card.getByRole('heading',{name:heading,exact:true})).toBeVisible();
  const unchanged=await (await page.request.get(`/api/trajectory/${date}`)).json();
  expect(unchanged.days[0].events).toHaveLength(3);expect(unchanged.days[0].legs).toHaveLength(2);
  for (const [name,width,height] of [['desktop',1440,900],['phone',375,812]]) {
   await page.setViewportSize({width,height});
   await card.getByRole('heading',{name:heading,exact:true}).scrollIntoViewIfNeeded();
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:`${shots}/${kind}-${name}-scope.png`,animations:'disabled'});
   await page.getByRole('textbox',{name:'メッセージ',exact:true}).focus();
   await card.getByRole('button',{name:'確認して削除',exact:true}).focus();
   await expect(card.getByRole('button',{name:'確認して削除',exact:true})).toBeInViewport();
   await page.screenshot({path:`${shots}/${kind}-${name}.png`,animations:'disabled'});
  }
  await card.getByRole('button',{name:'内容を修正',exact:true}).click();
  await expect(card.getByText(/削除対象を変更する場合はメッセージで伝えてください/)).toBeVisible();
  await card.getByRole('button',{name:'差分を更新',exact:true}).click();
  await expect(card.getByRole('heading',{name:'確認待ち · 第2版'})).toBeVisible();
  await card.getByRole('button',{name:'確認して削除',exact:true}).click();
  await expect(card.getByRole('heading',{name:'保存済み',exact:true})).toBeVisible();
  await page.getByRole('navigation',{name:'メインナビゲーション'}).getByRole('link',{name:'軌跡',exact:true}).click();
  if(kind==='day') {
   await expect(page.locator(`#trajectory-date option[value="${date}"]`)).toHaveCount(0);
   expect((await page.request.get(`/api/trajectory/${date}`)).status()).toBe(404);
  } else {
   await page.getByRole('combobox',{name:'表示する日付'}).selectOption(date);
   await expect(page.locator('.trajectory-event')).toHaveCount(kind==='event'?2:3);
   await expect(page.locator('.trajectory-leg-label')).toHaveCount(kind==='event'?0:1);
   if(kind==='event')await expect(page.locator('.trajectory-event').filter({hasText:'削除する店'})).toHaveCount(0);
   await page.reload();
   await page.getByRole('combobox',{name:'表示する日付'}).selectOption(date);
   await expect(page.locator('.trajectory-event')).toHaveCount(kind==='event'?2:3);
  }
 });
}
