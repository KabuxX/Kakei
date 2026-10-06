const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  testMatch: 'fresh-install.spec.cjs',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8769',
    browserName: 'chromium',
    locale: 'ja-JP',
    timezoneId: 'Asia/Tokyo',
    viewport: { width: 1440, height: 900 },
  },
  webServer: {
    command: 'uv run --project ../backend --locked python ../backend/tests/fresh_install_browser_server.py',
    cwd: __dirname,
    url: 'http://127.0.0.1:8769/api/status',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
