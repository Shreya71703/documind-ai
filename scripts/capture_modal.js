const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Navigating to live frontend...');
  await page.goto('https://documind-frontend-tgpv.onrender.com/dashboard');
  await page.waitForLoadState('networkidle');

  console.log('Clicking New Chat...');
  await page.click('button:has-text("New Chat")');
  await page.waitForSelector('text=Start Grounded Chat');
  
  // Wait a moment for modal animation
  await page.waitForTimeout(500);

  // Take screenshot of the modal state
  await page.screenshot({ path: 'docs/images/modal.png' });
  console.log('Screenshot saved to docs/images/modal.png');

  await browser.close();
})();
