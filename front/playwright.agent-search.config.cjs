const base = require('./playwright.config.cjs');
const python = process.env.KAKEI_TEST_PYTHON || '../backend/.venv/bin/python';
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
module.exports = {
  ...base,
  use: { ...base.use, baseURL: 'http://127.0.0.1:8767' },
  webServer: {
    command: `${quote(python)} ../backend/tests/agent_browser_server.py`,
    cwd: __dirname,
    url: 'http://127.0.0.1:8767',
    reuseExistingServer: false,
    env: { VITE_MAPBOX_ACCESS_TOKEN: '' },
  },
};
