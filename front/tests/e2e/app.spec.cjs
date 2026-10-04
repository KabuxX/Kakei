const { test, expect } = require('@playwright/test');
const shots = process.env.KAKEI_E2E_ARTIFACT_DIR || '../.superpowers/e2e';

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-02T12:00:00+09:00') });
});

test('first viewport shows period and financial state at desktop and phone widths', async ({ page }) => {
  let initialized = [];
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/status') return route.fulfill({ status: 200, json: { initialized: false } });
    if (pathname === '/api/initialize') { initialized = route.request().postDataJSON().transactions; return route.fulfill({ status: 201, json: { count: initialized.length } }); }
    if (pathname === '/api/transactions') return route.fulfill({ status: 200, json: { transactions: initialized } });
    return route.continue();
  });
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await expect(page.locator('#month-label')).toHaveText('2026年9月');
  await expect(page.locator('#balance-amount')).not.toHaveText('—');
  expect(initialized).toHaveLength(37);
  await expect(page.getByRole('button', { name: '取引を追加' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const desktop = await page.locator('.balance-card').boundingBox();
  expect(desktop.y).toBeLessThan(200);
  await page.setViewportSize({ width: 375, height: 812 });
  const phone = await page.locator('.balance-card').boundingBox();
  expect(phone.y).toBeLessThan(150);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('sidebar can be hidden and restored without hiding phone navigation', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  const sidebar = page.getByRole('complementary', { name: 'サイドバー', includeHidden: true });
  const toggle = page.getByRole('button', { name: 'サイドバーを隠す' });
  const widthBefore = (await page.locator('#main').boundingBox()).width;

  await toggle.click();
  await expect(sidebar).toBeHidden();
  await expect(page.getByRole('button', { name: 'サイドバーを表示' })).toHaveAttribute('aria-expanded', 'false');
  await expect.poll(async () => (await page.locator('#main').boundingBox()).width).toBeGreaterThan(widthBefore + 200);
  await expect(page.locator('#month-label')).toBeVisible();
  await expect(page.locator('#balance-amount')).not.toHaveText('—');
  await page.evaluate(() => { window.location.hash = '#transactions'; });
  await expect(sidebar).toBeHidden();

  await page.getByRole('button', { name: 'サイドバーを表示' }).focus();
  await page.keyboard.press('Enter');
  await expect(sidebar).toBeVisible();
  await page.getByRole('button', { name: 'サイドバーを隠す' }).click();
  for (const width of [1024, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(sidebar).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(sidebar).toBeVisible();
  await expect(page.getByRole('button', { name: 'サイドバーを表示', includeHidden: true })).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('trajectory shows a dated Tokyo sample on desktop and phone', async ({ page }) => {
  await page.goto('/#trajectory');
  await expect(page.getByRole('link', { name: '軌跡' })).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('#dashboard-view')).toBeHidden();
  await expect(page.locator('#trajectory-view')).toHaveCSS('display', 'block');
  await expect(page.getByRole('heading', { name: '生活軌跡' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '生活軌跡' })).toBeFocused();
  await expect(page.getByRole('combobox', { name: '表示する日付' })).toHaveValue('2026-09-19');
  await expect(page.getByText('3地点')).toBeVisible();
  await expect(page.getByRole('heading', { name: '時系列' })).toBeVisible();
  await expect(page.getByText(/Google Mapsのブラウザ用キー/)).toBeVisible();
  await page.getByRole('button', { name: '次の記録日' }).click();
  await expect(page.getByRole('combobox', { name: '表示する日付' })).toHaveValue('2026-09-20');
  await page.getByRole('combobox', { name: '表示する日付' }).selectOption('2026-09-29');
  await expect(page.getByText('JR恵比寿駅')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole('combobox', { name: '表示する日付' })).toBeInViewport();
  await expect(page.getByText('5地点')).toBeInViewport();
  for (const control of [page.getByRole('button', { name: '前の記録日' }), page.getByRole('button', { name: '次の記録日' }), page.getByRole('combobox', { name: '表示する日付' })]) {
    const box = await control.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThanOrEqual(44);
  }
  await expect(page.getByRole('link', { name: '軌跡' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('link', { name: '概要' }).click();
  await expect(page.locator('#dashboard-view')).toBeVisible();
  await expect(page.locator('#month-label')).toBeVisible();
});

test('deletion confirmation keeps the selected transaction and actions visible at desktop and phone widths', async ({ page }) => {
  await page.goto('/#transaction/sample-0/delete');
  await expect(page.getByRole('heading', { name: 'この取引を削除しますか？' })).toBeVisible();
  await expect(page.getByRole('article', { name: '削除する取引' })).toContainText('給与');
  await expect(page.getByRole('button', { name: '削除する' })).toBeInViewport();
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole('article', { name: '削除する取引' })).toBeInViewport();
  await expect(page.getByRole('link', { name: '取引詳細へ戻る' })).toBeInViewport();
  await expect(page.getByRole('button', { name: '削除する' })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('imports an existing browser array once', async ({ page }) => {
  const record = { id: 'from-browser', date: '2026-09-12', type: 'income', title: '移行した収入', category: '収入', amount: 1234 };
  await page.addInitScript((saved) => localStorage.setItem('kakei-transactions-v1', JSON.stringify(saved)), [record]);
  let imported;
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/status') return route.fulfill({ status: 200, json: { initialized: false } });
    if (pathname === '/api/initialize') { imported = route.request().postDataJSON(); return route.fulfill({ status: 201, json: { count: 1 } }); }
    if (pathname === '/api/transactions') return route.fulfill({ status: 200, json: { transactions: [record] } });
    return route.continue();
  });
  await page.goto('/');
  await expect(page.getByRole('link', { name: '移行した収入' })).toBeVisible();
  expect(imported).toEqual({ transactions: [record] });
});

test('modal Escape restores focus and detail back restores the list row', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  const trigger = page.getByRole('button', { name: '取引を追加' });
  await trigger.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(trigger).toBeFocused();
  const row = page.getByRole('link', { name: '給与' });
  await row.click();
  await expect(page.getByRole('heading', { name: '給与' })).toBeVisible();
  await page.getByRole('link', { name: '取引履歴へ戻る' }).click();
  await expect(row).toBeFocused();
});

test('adds and deletes a real expense through FastAPI', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await page.getByRole('button', { name: '取引を追加', exact: true }).click();
  await page.getByRole('textbox', { name: /内容/ }).fill('React 移行テスト');
  await page.getByRole('spinbutton', { name: /金額/ }).fill('2345');
  await page.getByRole('textbox', { name: /店名・取引先/ }).fill('テスト店舗');
  await page.getByRole('combobox', { name: /支払方法/ }).selectOption('cash');
  await page.getByRole('button', { name: '追加する', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  const row = page.getByRole('link', { name: 'React 移行テスト' });
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByText('テスト店舗')).toBeVisible();
  await page.getByRole('link', { name: '取引を削除' }).click();
  await expect(page.getByRole('heading', { name: 'この取引を削除しますか？' })).toBeVisible();
  await expect(page.getByRole('article', { name: '削除する取引' })).toContainText('React 移行テスト');
  await page.getByRole('button', { name: '削除する' }).click();
  await expect(page.locator('#dashboard-view')).toBeVisible();
  await expect(page.getByRole('link', { name: 'React 移行テスト' })).toHaveCount(0);
});

test('failed refresh after a successful write offers retry without duplicate POST', async ({ page }) => {
  let writes = 0;
  let reads = 0;
  await page.route('**/api/transactions', async (route) => {
    if (route.request().method() === 'POST') { writes += 1; return route.fulfill({ status: 201, json: { transaction: { id: 'saved' } } }); }
    reads += 1;
    if (reads === 1) return route.fulfill({ status: 200, json: { transactions: [] } });
    if (reads === 2) return route.abort();
    return route.fulfill({ status: 200, json: { transactions: [{ id: 'saved', date: '2026-10-02T12:00', type: 'income', title: '保存済み', category: '収入', amount: 1000 }] } });
  });
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await page.getByRole('button', { name: '取引を追加', exact: true }).click();
  await page.getByRole('radio', { name: '収入' }).check();
  await page.getByRole('textbox', { name: /内容/ }).fill('保存済み');
  await page.getByRole('spinbutton', { name: /金額/ }).fill('1000');
  await page.getByRole('button', { name: '追加する', exact: true }).click();
  await expect(page.locator('#sync-status')).toBeVisible();
  await expect(page.locator('#sync-status')).toContainText('保存は完了しました');
  expect(writes).toBe(1);
  await page.getByRole('button', { name: '表示を再読み込み' }).click();
  await expect(page.getByRole('link', { name: '保存済み' })).toBeVisible();
  expect(writes).toBe(1);
});

test('load error can retry without losing the selected month', async ({ page }) => {
  let statusCalls = 0;
  await page.route('**/api/status', (route) => {
    statusCalls += 1;
    if (statusCalls === 1) return route.abort();
    return route.continue();
  });
  await page.goto('/');
  await expect(page.getByText('取引を読み込めませんでした', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '次の月' }).click();
  await page.getByRole('button', { name: '再試行' }).click();
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await expect(page.locator('#month-label')).toHaveText('2026年10月');
});

test('failed save and delete keep the record state and explain the failure', async ({ page }) => {
  await page.route('**/api/transactions', async (route) => {
    if (route.request().method() === 'POST') return route.fulfill({ status: 500, json: { error: { code: 'database_error', message: '保存できませんでした。' } } });
    return route.continue();
  });
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await page.getByRole('button', { name: '取引を追加', exact: true }).click();
  await page.getByRole('radio', { name: '収入' }).check();
  await page.getByRole('textbox', { name: /内容/ }).fill('失敗テスト');
  await page.getByRole('spinbutton', { name: /金額/ }).fill('1000');
  await page.getByRole('button', { name: '追加する', exact: true }).click();
  await expect(page.locator('#form-error')).toBeVisible();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: '閉じる' }).click();
  await page.route('**/api/transactions/sample-0', (route) => route.fulfill({ status: 500, json: { error: { code: 'database_error', message: '削除できませんでした。' } } }));
  await page.goto('/#transaction/sample-0');
  await expect(page.getByRole('heading', { name: '給与' })).toBeVisible();
  await page.getByRole('link', { name: '取引を削除' }).click();
  await page.getByRole('button', { name: '削除する' }).click();
  await expect(page.getByRole('alert')).toContainText('削除できませんでした');
  await expect(page.getByRole('heading', { name: '給与' })).toBeVisible();
});

test('overview anchors still scroll to Budget and Insights after leaving detail', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const target of ['#budget', '#insights']) {
    await page.goto('/#transaction/sample-0');
    await expect(page.locator('#detail-view')).toBeVisible();
    await page.evaluate((hash) => { window.location.hash = hash; }, target);
    await expect(page.locator(target)).toBeVisible();
    await expect.poll(async () => page.locator(target).evaluate((element) => Math.round(element.getBoundingClientRect().top))).toBeLessThan(200);
  }
});

test('agent approval survives lost response and refreshes visible app data', async ({page})=>{
  test.skip(test.info().config.projects[0].use.baseURL!=='http://127.0.0.1:8767','requires isolated fake runner');
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await page.getByRole('link',{name:'Agent Chat'}).click();
  await expect(page.getByRole('heading',{name:'Agent Chat'})).toBeFocused();
  await page.getByRole('textbox',{name:'メッセージ'}).fill('給与を追加');
  await page.getByRole('button',{name:'送信',exact:true}).click();
  await expect(page.getByRole('article',{name:'変更案'})).toContainText('12');
  await page.getByRole('button',{name:'内容を修正'}).click();
  await page.getByRole('spinbutton',{name:'金額 1'}).fill('15000');
  await page.getByRole('button',{name:'差分を更新'}).click();
  await expect(page.getByText('確認待ち · 第2版')).toBeVisible();
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({animations:'disabled',path:`${shots}/agent-desktop.png`});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({animations:'disabled',path:`${shots}/agent-phone.png`});
  let count=0;
  await page.route('**/api/agent/proposals/*/approve',async route=>{
    count++; if(count===1){await route.fetch();return route.abort();}return route.continue();
  });
  await page.getByRole('button',{name:'確認して保存'}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button',{name:'変更案を再読み込み'}).click();
  await expect(page.getByText('保存済み',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'概要',exact:true}).click();
  await expect(page.getByRole('link',{name:'Agent 動作確認'})).toHaveCount(1);
  await expect(page.locator('#month-label')).toHaveText('2026年9月');
  expect((await page.locator('.balance-card').boundingBox()).y).toBeLessThan(160);
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  expect((await page.locator('.balance-card').boundingBox()).y).toBeGreaterThanOrEqual(0);
  await page.screenshot({animations:'disabled',path:`${shots}/dashboard-phone-after-agent.png`});
  await page.setViewportSize({width:1440,height:900});
  await page.clock.runFor(300);
  await page.screenshot({animations:'disabled',path:`${shots}/dashboard-desktop-after-agent.png`});
});

test('receipt upload corrects discrepancy then saves and opens attached bytes',async({page})=>{
 test.skip(test.info().config.projects[0].use.baseURL!=='http://127.0.0.1:8767','requires isolated fake runner');
 await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
 await page.getByRole('link',{name:'Agent Chat'}).click();
 await page.getByLabel('レシートファイル').setInputFiles({name:'receipt.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAE0lEQVR4nGP8//8/AwwwwVl4OQCWbgMF7ZjH1AAAAABJRU5ErkJggg==','base64')});
 await expect(page.getByRole('img',{name:'添付レシート'})).toBeVisible();
 await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByText(/品目合計と合計金額が一致しません/)).toBeVisible();
 await expect(page.getByRole('button',{name:'変更案を確認'})).toBeDisabled();
 await page.getByRole('combobox',{name:'保存先'}).selectOption('new');
 await page.getByRole('button',{name:'品目を保存しない'}).click();
 await page.screenshot({animations:'disabled',path:`${shots}/receipt-desktop.png`,fullPage:true});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({animations:'disabled',path:`${shots}/receipt-phone.png`,fullPage:true});
 await page.getByRole('button',{name:'変更案を確認'}).click();
 await expect(page.getByRole('img',{name:'確認するレシート'})).toBeVisible();
 const original=await page.request.get(await page.getByRole('link',{name:'レシート原本を開く'}).getAttribute('href'));
 expect(original.status()).toBe(200);
 await page.screenshot({animations:'disabled',path:`${shots}/receipt-approval-phone.png`,fullPage:true});
 await page.getByRole('button',{name:'確認して保存'}).click();
 await expect(page.getByText('保存済み',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'概要',exact:true}).click();
 await page.getByRole('link',{name:'レシート店舗',exact:true}).click();
 const receipt=page.getByRole('link',{name:'レシート 1 を開く'});
 await expect(receipt).toBeVisible();
 const response=await page.request.get(await receipt.getAttribute('href'));
 expect(response.headers()['content-type']).toBe('image/png');expect(response.status()).toBe(200);
});

test('trajectory proposal binds a place and confirms order then appears in live API view',async({page})=>{
 test.skip(test.info().config.projects[0].use.baseURL!=='http://127.0.0.1:8767','requires isolated fake runner');
 await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
 await page.getByRole('link',{name:'Agent Chat'}).click();
 await page.getByRole('textbox',{name:'メッセージ'}).fill('2027-01-04の軌跡を作成');await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByRole('button',{name:'確認して保存'})).toBeDisabled();
 await page.getByRole('radio',{name:/New York/}).check();await page.getByRole('button',{name:'この地点を選ぶ'}).click();
 await expect(page.getByText('確認待ち · 第2版')).toBeVisible();
 await page.getByRole('radio',{name:/London/}).check();await page.getByRole('button',{name:'この地点を選ぶ'}).click();
 await expect(page.getByText('確認待ち · 第3版')).toBeVisible();
 await page.getByRole('button',{name:'この訪問順を確認した'}).click();
 await expect(page.getByText('確認待ち · 第4版')).toBeVisible();
 await page.screenshot({animations:'disabled',path:`${shots}/review-desktop.png`,fullPage:true});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({animations:'disabled',path:`${shots}/review-phone.png`,fullPage:true});
 await page.getByRole('button',{name:'確認して保存'}).click();await expect(page.getByText('保存済み',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'軌跡',exact:true}).click();await page.getByRole('combobox',{name:'表示する日付'}).selectOption('2027-01-04');
 await expect(page.getByText('時刻不明 · 不明')).toHaveCount(2);
 await expect(page.getByText(/Google Mapsのブラウザ用キー/)).toBeVisible();
 await expect(page.getByText('© OpenStreetMap contributors',{exact:false})).toHaveCount(2);
 await expect(page.getByText(/実際に通った経路や移動距離ではありません/)).toBeVisible();
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
 await page.screenshot({animations:'disabled',path:`${shots}/trajectory-phone.png`,fullPage:true});
 await page.setViewportSize({width:1440,height:900});
 await page.screenshot({animations:'disabled',path:`${shots}/trajectory-desktop.png`,fullPage:true});
});

test('web sources persist through candidate approval and plain conversation reload',async({page})=>{
 test.skip(test.info().config.projects[0].use.baseURL!=='http://127.0.0.1:8767','requires isolated fake runner');
 await page.goto('/');await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
 await page.getByRole('link',{name:'Agent Chat'}).click();
 await page.getByRole('textbox',{name:'メッセージ'}).fill('Web出典 軌跡');
 const turnPromise=page.waitForResponse(r=>r.url().includes('/messages')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'送信',exact:true}).click();
 const turn=await (await turnPromise).json();
 await expect(page.getByRole('heading',{name:'位置未確認',exact:true})).toBeVisible();
 expect(await page.getByRole('region',{name:'位置未確認の店舗'}).getByRole('radio').count()).toBe(0);
 await expect(page.getByRole('link',{name:/引用: 店舗情報/})).toHaveAttribute('href','https://store.example/detail?id=12');
 const forged=await page.request.post(`/api/agent/proposals/${turn.proposal.id}/places/selection`,{headers:{Origin:'http://127.0.0.1:8767'},data:{revision:1,candidateId:'unlocated'}});
 expect(forged.status()).toBe(400);
 const unconfirmed=await page.request.post(`/api/agent/proposals/${turn.proposal.id}/places/selection`,{headers:{Origin:'http://127.0.0.1:8767'},data:{revision:1,candidateId:'web-candidate'}});
 expect(unconfirmed.status()).toBe(400);
 await page.getByText('座標を自分で指定する',{exact:true}).click();
 await page.setViewportSize({width:1440,height:900});
 await page.locator('.agent-unlocated').scrollIntoViewIfNeeded();
 await page.screenshot({animations:'disabled',path:`${shots}/web-evidence-desktop.png`});
 await page.setViewportSize({width:375,height:812});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('.agent-unlocated').getByRole('link').focus();
 await page.screenshot({animations:'disabled',path:`${shots}/web-evidence-phone.png`});
 await page.getByRole('spinbutton',{name:'緯度',exact:true}).focus();
 await page.screenshot({animations:'disabled',path:`${shots}/web-manual-phone.png`});
 await page.getByRole('radio',{name:/ドトール/}).check();
 await expect(page.getByRole('button',{name:'この地点を選ぶ'})).toBeDisabled();
 await expect(page.getByRole('link',{name:/地図で位置を確認/})).toHaveAttribute('href',/mlat=33.59/);
 await page.getByRole('checkbox',{name:'住所と地図を確認しました'}).focus();
 await page.screenshot({animations:'disabled',path:`${shots}/coordinate-review-phone.png`});
 await page.setViewportSize({width:1440,height:900});
 await page.locator('.agent-coordinate-review').scrollIntoViewIfNeeded();
 await page.screenshot({animations:'disabled',path:`${shots}/coordinate-review-desktop.png`});
 await page.getByRole('checkbox',{name:'住所と地図を確認しました'}).check();
 await page.getByRole('button',{name:'この地点を選ぶ'}).click();
 await expect(page.getByText('確認待ち · 第2版')).toBeVisible();
 await page.getByRole('button',{name:'確認して保存'}).click();await expect(page.getByText('保存済み',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'軌跡',exact:true}).click();await page.getByRole('combobox',{name:'表示する日付'}).selectOption('2027-01-05');
 await expect(page.getByRole('link',{name:/店舗情報/})).toHaveAttribute('href','https://store.example/detail?id=12');
 await expect(page.getByText(/座標: © Mapbox.*利用者.*補間/)).toBeVisible();
 await page.setViewportSize({width:1440,height:900});
 await page.getByRole('link',{name:'Agent Chat'}).click();await page.getByRole('button',{name:'新しい会話',exact:true}).click();
 await page.getByRole('textbox',{name:'メッセージ'}).fill('Web出典だけ教えて');await page.getByRole('button',{name:'送信',exact:true}).click();
 await expect(page.getByRole('link',{name:/引用: 店舗情報/})).toBeVisible();
 await page.reload();await page.getByRole('link',{name:'Agent Chat'}).click();
 await page.getByRole('button',{name:'Web出典だけ教えて',exact:true}).click();
 await expect(page.getByRole('link',{name:/引用: 店舗情報/})).toHaveAttribute('href','https://store.example/detail?id=12');
 await expect(page.getByRole('button',{name:'確認して保存'})).toHaveCount(0);
});
