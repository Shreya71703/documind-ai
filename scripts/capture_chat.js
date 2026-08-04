const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Navigating to live frontend...');
  await page.goto('https://documind-frontend-tgpv.onrender.com/dashboard');
  await page.waitForLoadState('networkidle');

  console.log('Opening chat...');
  // Find a document that is already indexed in the list and click its chat button, 
  // or just click the first chat in the sidebar history if it exists.
  const firstChat = page.locator('button:has-text("New Chat")').nth(1); 
  if (await firstChat.isVisible()) {
      await firstChat.click();
  } else {
      await page.click('button:has-text("New Chat")');
      await page.waitForSelector('text=Start Grounded Chat');
      await page.locator('div[role="dialog"]').locator('div').filter({ hasText: 'Indexed' }).first().click();
      await page.click('button:has-text("Start Chat")');
  }

  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Take screenshot of the chat state
  await page.screenshot({ path: 'docs/images/chat.png' });
  console.log('Screenshot saved to docs/images/chat.png');

  await browser.close();
})();
