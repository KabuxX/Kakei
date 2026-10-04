const {test,expect}=require('@playwright/test');
const shots=process.env.KAKEI_E2E_ARTIFACT_DIR||'../docs/verification/2026-10-04-web-coordinates';
test('reviews published and estimated coordinates, switches confirmation, saves and reloads',async({page})=>{
 await page.goto('/#agent');
 await page.getByRole('textbox',{name:'メッセージ',exact:true}).fill('推定位置の確認');
 await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByRole('radio').first()).toBeVisible();
 await page.getByRole('radio').first().check();
 await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeDisabled();
 await page.getByRole('checkbox',{name:'住所・出典と地図の位置を確認しました'}).check();
 await page.getByRole('radio').last().check();
 await expect(page.getByRole('checkbox',{name:'この推定位置を確認しました'})).not.toBeChecked();
 await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeDisabled();
 await page.getByRole('checkbox',{name:'この推定位置を確認しました'}).check();
 for(const [name,width,height] of [['desktop',1440,900],['phone',375,812]]){
  await page.setViewportSize({width,height});
  await page.getByRole('checkbox',{name:'この推定位置を確認しました'}).scrollIntoViewIfNeeded();
  await expect(page.getByRole('checkbox',{name:'この推定位置を確認しました'})).toBeInViewport();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'この地点を選ぶ'}).focus();
  await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeInViewport();
  await page.screenshot({path:`${shots}/confirmation-${name}.png`,animations:'disabled'});
 }
 await page.getByRole('button',{name:'この地点を選ぶ'}).click();
 await expect(page.getByRole('button',{name:'確認して保存'})).toBeEnabled();
 await page.getByRole('button',{name:'確認して保存'}).click();
 await expect(page.getByRole('heading',{name:'保存済み'})).toBeVisible();
 await page.goto('/#trajectory');await page.reload();
 await page.getByRole('combobox',{name:'表示する日付'}).selectOption('2027-01-06');
 await expect(page.getByText('推定位置を含む概算',{exact:true})).toBeVisible();
 await expect(page.getByText('位置は推定',{exact:true}).first()).toBeVisible();
 await expect(page.getByText(/建物・施設内の推定位置/).first()).toBeVisible();
 await expect(page.getByRole('link',{name:/店舗情報/}).first()).toBeVisible();
 for(const [name,width,height] of [['desktop',1440,900],['phone',375,812]]){
  await page.setViewportSize({width,height});
  await page.getByText('位置は推定',{exact:true}).first().scrollIntoViewIfNeeded();
  await expect(page.getByText('Google Mapsのブラウザ用キーを設定すると地図を表示できます。時系列はそのまま確認できます。')).toBeVisible();
  await page.getByRole('navigation',{name:'メインナビゲーション'}).getByRole('link',{name:'軌跡',exact:true}).focus();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${shots}/trajectory-${name}.png`,fullPage:true,animations:'disabled'});
 }
});
