const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const shots=process.env.KAKEI_E2E_ARTIFACT_DIR || '../.superpowers/merchant-address';
const address='〒810-0001 福岡県福岡市中央区天神2-11-3 商業施設中央棟地下1階 北側エントランス横';
test('address editing persists, invalidates only related locations, and exports CSV',async({page,baseURL})=>{
 await page.clock.install({time:new Date('2026-10-04T12:00:00+09:00')});
 await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
 const headers={Origin:baseURL};
 const created=await page.request.post('/api/transactions',{headers,data:{title:'住所の統合確認',date:'2026-10-04T12:00',type:'expense',category:'食費',amount:800,merchant:'住所テスト店',paymentMethod:'cash',items:[]}});
 expect(created.ok()).toBe(true);const tx=(await created.json()).transaction;
 await page.goto('/#transaction/'+tx.id);await page.reload();
 await page.getByRole('button',{name:'住所を追加'}).click();await page.getByRole('textbox',{name:'住所（任意）',exact:true}).fill(address);
 await page.getByRole('button',{name:'住所を保存'}).click();await expect(page.getByText(address,{exact:true})).toBeVisible();
 await page.reload();await expect(page.getByText(address,{exact:true})).toBeVisible();
 for(const [name,width,height] of [['desktop',1440,1000],['phone',375,812]]){
  await page.setViewportSize({width,height});await page.getByRole('button',{name:'住所を編集'}).click();
  await page.getByRole('textbox',{name:'住所（任意）',exact:true}).fill('𠮷'.repeat(501));await page.getByRole('button',{name:'住所を保存'}).click();
  await expect(page.getByText('住所は500文字以内で入力してください。')).toBeVisible();
  await page.getByRole('textbox',{name:'住所（任意）',exact:true}).fill(address);await page.getByRole('textbox',{name:'住所（任意）',exact:true}).focus();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${shots}/address-edit-${name}.png`,fullPage:name==='desktop'});
  await page.getByRole('button',{name:'キャンセル',exact:true}).click();
 }
 await page.getByRole('button',{name:'住所を編集'}).click();await page.getByRole('textbox',{name:'住所（任意）',exact:true}).fill('');await page.getByRole('button',{name:'住所を保存'}).click();await expect(page.getByRole('button',{name:'住所を追加'})).toBeVisible();
 const placeId='merchant-address-place';
 expect((await page.request.post('/api/trajectory',{headers,data:{kind:'place',id:placeId,data:{name:tx.merchant,address,coordinates:[130.399,33.590],sourceUrl:'https://example.com/shop',placeEvidence:'user'}}})).ok()).toBe(true);
 expect((await page.request.post('/api/trajectory',{headers,data:{kind:'day',date:'2026-10-04',data:{events:[{id:'address-visit',placeId,time:'12:00',timeEvidence:'exact',transactionId:tx.id}],legs:[]}}})).ok()).toBe(true);
 await page.reload();await page.getByRole('button',{name:'この住所を取引に保存'}).click();await expect(page.getByRole('textbox',{name:'住所（任意）',exact:true})).toHaveValue(address);await page.getByRole('button',{name:'住所を保存'}).click();
 await expect(page.getByRole('link',{name:/地図で見る/})).toBeVisible();
 await page.getByRole('button',{name:'住所を編集'}).click();await page.getByRole('textbox',{name:'住所（任意）',exact:true}).fill('福岡市中央区天神2-11-30');await page.getByRole('button',{name:'住所を保存'}).click();
 await expect(page.getByText('住所が変わったため、位置の再確認が必要です')).toBeVisible();await expect(page.getByRole('link',{name:/地図で見る/})).toHaveCount(0);
 await page.getByRole('button',{name:'Agentで位置を再確認'}).click();await expect(page.getByRole('textbox',{name:'メッセージ',exact:true})).toHaveValue(new RegExp(tx.id));
 const outgoing=[];page.on('request',r=>{if(r.method()==='POST')outgoing.push(r.url());});
 await page.goto('/#trajectory');await page.locator('#trajectory-date').selectOption('2026-10-04');await expect(page.getByText('住所と位置の再確認が必要')).toBeVisible();
 await expect(page.getByText('地図に表示する地点はありません。')).toBeVisible();
 await page.getByRole('button',{name:'Agentで位置を再確認'}).click();await expect(page.getByRole('textbox',{name:'メッセージ',exact:true})).toHaveValue(new RegExp(tx.id));expect(outgoing).toEqual([]);
 await page.goto('/#overview');await page.getByRole('button',{name:'次の月',exact:true}).click();await expect(page.locator('#month-label')).toHaveText('2026年10月');
 // Navigate through the real month controls, whose current initial month follows saved records.
 const transactions=await page.request.get('/api/transactions');expect((await transactions.json()).transactions.find(t=>t.id===tx.id).merchantAddress).toBe('福岡市中央区天神2-11-30');
 const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'取引をCSVで保存'}).click();const download=await downloadPromise;
 const csv=fs.readFileSync(await download.path(),'utf8');expect(csv).toContain('取引先住所');expect(csv).toContain('関連軌跡住所');expect(csv).toContain('福岡市中央区天神2-11-30');
 await page.goto('/#agent');await page.getByRole('textbox',{name:'メッセージ',exact:true}).fill('住所の位置を修正');await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByRole('article',{name:'変更案'})).toBeVisible();
 await page.getByRole('radio',{name:/住所テスト店/}).check();await page.getByRole('button',{name:'この地点を選ぶ',exact:true}).click();
 await page.getByRole('button',{name:'確認して保存',exact:true}).click();await expect(page.getByText('保存済み',{exact:true})).toBeVisible();
 await page.goto('/#trajectory');await page.locator('#trajectory-date').selectOption('2026-10-04');await expect(page.getByText('住所と位置の再確認が必要')).toHaveCount(0);
 const fixed=await page.request.get('/api/trajectory/2026-10-04');expect((await fixed.json()).days[0].events[0].locationStatus).toBe('matched');
 await page.goto('/#transaction/'+tx.id);await expect(page.getByRole('link',{name:/地図で見る/})).toHaveAttribute('href',/130.401/);

});
