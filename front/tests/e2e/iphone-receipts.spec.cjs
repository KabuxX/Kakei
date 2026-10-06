const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');
const { basename } = require('node:path');

function photo(format) {
  return execFileSync('uv', ['run', '--project', '../backend', '--locked', 'python', '-c',
    "import sys;sys.path.insert(0,'../backend/tests');from receipt_image_fixtures import phone_photo;sys.stdout.buffer.write(phone_photo(sys.argv[1]))", format]);
}

test.beforeEach(async ({ page }) => {
  test.skip(test.info().config.projects[0].use.baseURL !== 'http://127.0.0.1:8767', 'requires disposable agent fixture');
  await page.goto('/#agent');
  await expect(page.getByLabel('レシートファイル')).toBeEnabled();
});

async function attach(page, name, mimeType, buffer) {
  const upload = page.waitForResponse(r => r.request().method() === 'POST' && /\/receipts$/.test(new URL(r.url()).pathname));
  await page.getByLabel('レシートファイル').setInputFiles({ name, mimeType, buffer });
  const response = await upload;
  expect(response.status()).toBe(201);
  const receipt = await response.json();
  expect(receipt.sha256).toBe(createHash('sha256').update(buffer).digest('hex'));
  const image = page.getByRole('img', { name: '添付レシート' });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  const original = await page.request.get(await page.getByRole('link', { name: '添付レシートを開く' }).getAttribute('href'));
  expect(await original.body()).toEqual(buffer);
  const preview = await page.request.get(await image.getAttribute('src'));
  expect(preview.headers()['content-type']).toBe('image/jpeg');
}

test('phone formats display and HEIC can be sent for receipt review', async ({ page }) => {
  for (const [format, name, mime] of [['JPEG', 'phone.JPG', 'image/jpeg'], ['MPO', 'phone.JPEG', 'image/jpeg'], ['MPO', 'phone.mpo', 'application/octet-stream']]) {
    await attach(page, name, mime, photo(format));
    await page.getByRole('button', { name: '添付を外す' }).click();
  }
  await attach(page, 'phone.HEIC', 'image/heic', photo('HEIF'));
  await page.getByRole('button', { name: '送信', exact: true }).click();
  const review = page.getByRole('img', { name: 'レシートのプレビュー' });
  await expect(review).toBeVisible();
  await expect.poll(() => review.evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(page.getByRole('combobox', { name: '保存先' })).toBeVisible();
});

test('reported iPhone photo displays on desktop and phone without changing the original', async ({ page }) => {
  const path = process.env.KAKEI_PHONE_PHOTO;
  test.skip(!path, 'optional local reported photo; never committed');
  await attach(page, basename(path), 'image/jpeg', readFileSync(path));
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await expect(page.getByRole('img', { name: '添付レシート' })).toBeInViewport();
    await expect(page.getByRole('button', { name: '送信', exact: true })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.superpowers/iphone-receipts/${viewport.width}.png`, animations: 'disabled' });
  }
});
