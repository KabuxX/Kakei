const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-02T12:00:00+09:00') });
});

test('first viewport shows period and financial state at desktop and phone widths', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  await expect(page.locator('#month-label')).toHaveText('2026年9月');
  await expect(page.locator('#balance-amount')).not.toHaveText('—');
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
  await expect(page.getByRole('combobox', { name: '表示する日付' })).toHaveValue('2026-09-01');
  await expect(page.getByText('3地点')).toBeVisible();
  await expect(page.getByRole('heading', { name: '時系列' })).toBeVisible();
  await expect(page.getByText(/Mapbox の公開トークン/)).toBeVisible();
  await page.getByRole('button', { name: '次の日' }).click();
  await expect(page.getByRole('combobox', { name: '表示する日付' })).toHaveValue('2026-09-02');
  await expect(page.getByText('JR恵比寿駅')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole('combobox', { name: '表示する日付' })).toBeInViewport();
  await expect(page.getByText('5地点')).toBeInViewport();
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
    return route.fulfill({ status: 200, json: { transactions: [{ id: 'saved', date: '2026-09-01', type: 'income', title: '保存済み', category: '収入', amount: 1000 }] } });
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
