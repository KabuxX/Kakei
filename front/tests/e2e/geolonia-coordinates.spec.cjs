const {test,expect}=require('@playwright/test');
const shots=process.env.KAKEI_E2E_ARTIFACT_DIR||'../docs/verification/2026-10-04-geolonia-coordinates';
test('confirms address coordinates and keeps provenance after save and reload',async({page})=>{
 await page.goto('/#agent');
 await page.getByRole('textbox',{name:'メッセージ',exact:true}).fill('Geolonia座標の確認');
 await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByText('住所に対応する座標',{exact:true})).toBeVisible();
 await expect(page.getByRole('radio')).toHaveCount(2);
 await page.getByRole('radio').first().check();
 const confirm=page.getByRole('checkbox',{name:'住所・出典と地図の位置を確認しました'});
 await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeDisabled();
 await expect(page.getByRole('link',{name:/座標データ/})).toBeVisible();
 await expect(page.getByRole('link',{name:/CC BY 4.0/})).toHaveAttribute('href','https://creativecommons.org/licenses/by/4.0/');
 await confirm.check();await page.getByRole('radio').last().check();
 await expect(confirm).not.toBeChecked();await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeDisabled();
 await page.getByRole('radio').first().check();await expect(confirm).not.toBeChecked();await confirm.check();
 for(const [name,width,height] of [['desktop',1440,900],['phone',375,812]]){
  await page.setViewportSize({width,height});
  await confirm.scrollIntoViewIfNeeded();await expect(confirm).toBeInViewport();
  await page.getByRole('textbox',{name:'メッセージ',exact:true}).focus();
  await page.getByRole('button',{name:'この地点を選ぶ'}).focus();
  await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeInViewport();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${shots}/confirmation-${name}.png`,fullPage:true,animations:'disabled'});
  await page.getByRole('radio').first().focus();
  await page.getByText('住所に対応する座標',{exact:true}).scrollIntoViewIfNeeded();
  await expect(page.getByText('住所に対応する座標',{exact:true})).toBeInViewport();
  await page.screenshot({path:`${shots}/evidence-${name}.png`,fullPage:true,animations:'disabled'});
 }
 await page.getByRole('button',{name:'この地点を選ぶ'}).click();
 await page.getByRole('button',{name:'確認して保存'}).click();
 await expect(page.getByRole('heading',{name:'保存済み'})).toBeVisible();
 await page.goto('/#trajectory');await page.reload();
 await page.getByRole('combobox',{name:'表示する日付'}).selectOption('2027-03-01');
 await expect(page.getByText('住所に対応する座標',{exact:true})).toBeVisible();
 await expect(page.getByText(/照合住所:.*本郷一丁目2-3/)).toBeVisible();
 await expect(page.getByText('利用者が位置を確認済み')).toBeVisible();
 await expect(page.getByText(/店舗の入口は未確認/)).toBeVisible();
 for(const [name,width,height] of [['desktop',1440,900],['phone',375,812]]){
  await page.setViewportSize({width,height});
  await page.getByRole('combobox',{name:'表示する日付'}).focus();
  await page.getByText('住所に対応する座標',{exact:true}).scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${shots}/trajectory-${name}.png`,fullPage:true,animations:'disabled'});
 }
});
