const {test,expect}=require('@playwright/test');
const shots=process.env.KAKEI_E2E_ARTIFACT_DIR || '../.superpowers/transaction-edit';
test('edits expense fields and items and saves through reload',async({page,baseURL})=>{
 const headers={Origin:baseURL};
 await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
 const created=await page.request.post('/api/transactions',{headers,data:{title:'取引編集の確認',date:'2026-10-04T10:00',type:'expense',category:'食費',amount:300,merchant:'確認店舗',merchantAddress:'東京都渋谷区神宮前5-50-6 中島ビル1-2F',paymentMethod:'cash',items:[{name:'パン',amount:100},{name:'飲料',amount:200}]}});
 expect(created.ok()).toBe(true);const tx=(await created.json()).transaction;
 await page.goto('/#transaction/'+tx.id);await page.reload();
 await page.getByRole('link',{name:'編集',exact:true}).click();
 await expect(page.getByRole('heading',{name:'取引を編集'})).toBeVisible();
 await expect(page.getByRole('textbox',{name:/内容/})).toHaveValue('取引編集の確認');
 for(const [name,width,height] of [['desktop',1440,1000],['phone',375,812]]){
  await page.setViewportSize({width,height});
  await page.getByRole('textbox',{name:/内容/}).focus();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${shots}/edit-${name}.png`,fullPage:true});
 }
 await page.getByRole('textbox',{name:/内容/}).fill('変更した買物');
 await page.getByRole('textbox',{name:/店名・取引先/}).fill('変更店舗');
 await page.getByLabel(/日付と時刻/).fill('2026-10-04T14:25');
 await page.getByRole('combobox',{name:'カテゴリ',exact:true}).selectOption('日用品');
 await page.getByLabel(/支払方法/).selectOption('credit_card');
 await page.getByRole('spinbutton',{name:'品目2の金額（円）'}).fill('250');
 await expect(page.locator('#edit-amount-input')).toHaveValue('350');
 await page.getByRole('button',{name:'＋ 品目を追加'}).click();
 await page.getByRole('textbox',{name:'品目3の名前'}).fill('追加品目');
 await page.getByRole('spinbutton',{name:'品目3の金額（円）'}).fill('50');
 await page.getByRole('button',{name:'品目1を削除'}).click();
 await expect(page.locator('#edit-amount-input')).toHaveValue('300');
 await page.getByRole('textbox',{name:'住所（任意）',exact:true}).fill('東京都渋谷区神宮前5-50-7 新館2階');
 // A failed PUT retains the user's changes, then the real API succeeds on retry.
 await page.route('**/api/transactions/'+tx.id,route=>route.request().method()==='PUT'?route.fulfill({status:503,json:{error:{message:'offline'}}}):route.continue());
 await page.getByRole('button',{name:'保存する'}).click();await expect(page.getByText(/保存できませんでした/)).toBeVisible();
 await expect(page.getByRole('textbox',{name:/内容/})).toHaveValue('変更した買物');
 await page.unroute('**/api/transactions/'+tx.id);
 await page.getByRole('button',{name:'保存する'}).click();await expect(page.getByRole('heading',{name:'変更した買物'})).toBeVisible();
 await page.reload();await expect(page.getByText('東京都渋谷区神宮前5-50-7 新館2階',{exact:true})).toBeVisible();
 const saved=(await (await page.request.get('/api/transactions/'+tx.id)).json()).transaction;
 expect(saved).toMatchObject({amount:300,date:'2026-10-04T14:25',category:'日用品',merchant:'変更店舗',paymentMethod:'credit_card',items:[{name:'飲料',amount:250},{name:'追加品目',amount:50}]});
 await page.getByRole('link',{name:'編集',exact:true}).click();await page.getByRole('textbox',{name:/内容/}).fill('キャンセルする内容');await page.getByRole('button',{name:'キャンセル',exact:true}).click();
 await expect(page.getByRole('heading',{name:'変更した買物'})).toBeVisible();
 await page.getByRole('link',{name:'編集',exact:true}).click();await page.getByRole('radio',{name:'収入',exact:true}).check();await page.locator('#edit-amount-input').fill('1000');
 await page.getByRole('button',{name:'保存する'}).click();await expect(page.locator('#detail-type')).toHaveText('収入');
 const income=(await (await page.request.get('/api/transactions/'+tx.id)).json()).transaction;
 expect(income).toMatchObject({amount:1000,type:'income',category:'収入'});expect(income.merchantAddress).toBeUndefined();
});
