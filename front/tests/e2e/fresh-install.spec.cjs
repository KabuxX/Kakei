const { test, expect } = require('@playwright/test');

test('fresh install stays empty despite old browser data and preserves the first saved transaction', async ({ page }) => {
  test.skip(test.info().config.projects[0].use.baseURL !== 'http://127.0.0.1:8769', 'requires a fresh disposable DB');
  await page.clock.install({ time: new Date('2026-10-06T12:00:00+09:00') });
  await page.addInitScript(() => localStorage.setItem('kakei-transactions-v1', JSON.stringify([
    { id: 'old-browser-data', title: '以前のブラウザデータ', date: '2026-09-01', type: 'income', category: '収入', amount: 320000 },
  ])));
  await page.goto('/');
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  expect(await (await page.request.get('/api/transactions')).json()).toEqual({ transactions: [] });
  expect(await (await page.request.get('/api/trajectory')).json()).toEqual({ dates: [] });
  await expect(page.locator('#transaction-count')).toHaveText('0');
  await expect(page.locator('#balance-amount')).toHaveText('¥0');

  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await expect(page.locator('#month-label')).toBeInViewport();
    await expect(page.locator('#balance-amount')).toBeInViewport();
    await expect(page.getByRole('button', { name: '取引を追加', exact: true })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.superpowers/fresh-install/${viewport.width}.png`, animations: 'disabled' });
  }

  await page.getByRole('link', { name: '軌跡', exact: true }).click();
  await expect(page.getByText('軌跡の記録はまだありません。')).toBeVisible();
  await page.getByRole('link', { name: '概要', exact: true }).click();
  await page.getByRole('button', { name: '取引を追加', exact: true }).click();
  await page.getByRole('textbox', { name: /内容/ }).fill('最初の取引');
  await page.getByRole('spinbutton', { name: /金額/ }).fill('100');
  await page.getByRole('textbox', { name: /店名・取引先/ }).fill('テスト店舗');
  await page.getByRole('combobox', { name: /支払方法/ }).selectOption('cash');
  await page.getByRole('button', { name: '追加する', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  const saved = await (await page.request.get('/api/transactions')).json();
  expect(saved.transactions).toHaveLength(1);
  expect(saved.transactions[0]).toMatchObject({ title: '最初の取引', amount: 100 });
  await page.reload();
  await expect(page.locator('#dashboard-view')).toHaveClass(/data-ready/);
  expect(await (await page.request.get('/api/transactions')).json()).toEqual(saved);
  expect(await (await page.request.get('/api/trajectory')).json()).toEqual({ dates: [] });
});
