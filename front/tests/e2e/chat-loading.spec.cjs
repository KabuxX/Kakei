const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
test('user message and accessible animation precede a delayed answer; lost-response retry stays unique',async({page})=>{
 const createGate=deferred(),answerGate=deferred();
 await page.route('**/api/agent/threads',async route=>{
  if(route.request().method()==='POST')await createGate.promise;
  await route.continue();
 });
 let turn=0,threadUrl='';const bodies=[];
 await page.route('**/api/agent/threads/*/messages',async route=>{
  turn++;
  threadUrl=route.request().url().replace(/\/messages$/,'');bodies.push(route.request().postDataJSON());
  if(turn===1){await answerGate.promise;await route.continue();}
  else if(turn===2){await route.fetch();await route.abort('failed');}
  else await route.continue();
 });
 await page.goto('/#agent');
 const field=page.getByRole('textbox',{name:'メッセージ',exact:true});
 await field.fill('給与を記録して');
 await page.getByRole('button',{name:'送信',exact:true}).click();
 const user=page.locator('.agent-message.user');
 const progress=page.getByRole('status',{name:'Agentが処理中'});
 await expect(user).toHaveText('あなた給与を記録して');
 await expect(field).toHaveValue('');await expect(progress).toBeInViewport();
 await expect(page.locator('.agent-message.assistant')).toHaveCount(0);
 createGate.resolve();
 const dir='../.superpowers/chat-loading';fs.mkdirSync(dir,{recursive:true});
 await page.screenshot({path:`${dir}/desktop.png`});
 await page.setViewportSize({width:375,height:812});
 await expect(user).toBeInViewport();await expect(progress).toBeInViewport();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`${dir}/phone.png`});
 await page.emulateMedia({reducedMotion:'reduce'});
 expect(await page.locator('.agent-loading-dots i').first().evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
 answerGate.resolve();
 await expect(page.locator('.agent-message.assistant')).toHaveCount(1);
 await expect(progress).toHaveCount(0);await expect(user).toHaveCount(1);
 await expect(page.getByRole('article',{name:'変更案'})).toHaveCount(1);
 await field.fill('再送の確認');await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByRole('alert')).toBeVisible();
 await expect(progress).toHaveCount(0);await expect(user).toHaveCount(2);
 await page.getByRole('button',{name:'再送',exact:true}).click();
 await expect(page.locator('.agent-message.assistant')).toHaveCount(2);
 await expect(user).toHaveCount(2);await expect(progress).toHaveCount(0);
 expect(bodies[2]).toEqual(bodies[1]);
 const saved=await(await page.request.get(threadUrl)).json();
 expect(saved.thread.messages.filter(m=>m.role==='user')).toHaveLength(2);
});
