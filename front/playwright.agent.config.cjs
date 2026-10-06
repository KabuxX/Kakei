const { defineConfig }=require('@playwright/test');
module.exports=defineConfig({
 testDir:'./tests/e2e',workers:1,
 use:{baseURL:'http://127.0.0.1:8767',browserName:'chromium',locale:'ja-JP',timezoneId:'Asia/Tokyo',viewport:{width:1440,height:900}},
 webServer:{command:'uv run --project ../backend --locked python ../backend/tests/agent_browser_server.py',cwd:__dirname,url:'http://127.0.0.1:8767/api/status',reuseExistingServer:false,timeout:30000},
});
