const { test, expect } = require('@playwright/test');
const shots = process.env.KAKEI_E2E_ARTIFACT_DIR || '../.superpowers/transaction-address';

test('saved transaction address wraps and opens the linked coordinates at desktop and phone widths', async ({ page }) => {
  const address = '〒810-0001 福岡県福岡市中央区天神2-11-3 商業施設中央棟地下1階 北側エントランス横';
  const record = { id: 'address-preview', type: 'expense', title: 'コーヒーとサンドイッチ', merchant: '喫茶テスト 天神店', date: '2026-10-02T12:19', amount: 850, category: '食費', paymentMethod: 'e_money', items: [] };
  await page.route('**/api/status', route => route.fulfill({ json: { initialized: true } }));
  await page.route('**/api/transactions', route => route.fulfill({ json: { transactions: [record] } }));
  await page.route('**/api/transactions/address-preview/receipts', route => route.fulfill({ json: { receipts: [] } }));
  await page.route('**/api/trajectory/2026-10-02', route => route.fulfill({ json: { places: { shop: { name: record.merchant, address, coordinates: [130.3990083, 33.5900778] } }, days: [{ date: '2026-10-02', events: [{ transactionId: record.id, placeId: 'shop' }] }] } }));
  await page.goto('/#transaction/address-preview');
  await expect(page.getByText(address, { exact: true })).toBeVisible();
  const link = page.getByRole('link', { name: /地図で見る/ });
  await expect(link).toHaveAttribute('href', 'https://www.openstreetmap.org/?mlat=33.5900778&mlon=130.3990083#map=18/33.5900778/130.3990083');
  await expect(link).toHaveAttribute('target', '_blank');
  for (const [name, width, height] of [['desktop', 1440, 1000], ['phone', 375, 812]]) {
    await page.setViewportSize({ width, height });
    await page.getByRole('heading', { name: '取引詳細', exact: true }).focus();
    await link.focus();
    await expect(link).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await link.boundingBox()).height).toBeGreaterThanOrEqual(44);
    if (name === 'phone') {
      const navigation = await page.getByRole('navigation', { name: 'メインナビゲーション' }).boundingBox();
      await expect.poll(async () => { const box = await link.boundingBox(); return box.y + box.height; }).toBeLessThanOrEqual(navigation.y);
    }
    await page.screenshot({ path: `${shots}/transaction-address-${name}.png`, fullPage: name === 'desktop', animations: 'disabled' });
  }
});
