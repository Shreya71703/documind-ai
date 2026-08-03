const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  console.log('=== STARTING PLAYWRIGHT LIVE DEPLOYMENT AUDIT & VERIFICATION ===');
  const artifactsDir = 'C:/Users/shrey/.gemini/antigravity/brain/ea21cc81-b6f8-4ee8-98e3-7ae0a7f1cbb0';

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleLogs = [];
  const networkRequests = [];
  const networkErrors = [];

  page.on('console', msg => {
    consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    console.log(`[Browser Console ${msg.type()}] ${msg.text()}`);
  });

  page.on('requestfailed', req => {
    const failure = req.failure();
    const errText = failure ? failure.errorText : 'Unknown error';
    networkErrors.push(`[FAIL] ${req.method()} ${req.url()} - ${errText}`);
    console.log(`[Network Error] ${req.method()} ${req.url()} - ${errText}`);
  });

  page.on('response', response => {
    const req = response.request();
    networkRequests.push({
      method: req.method(),
      url: response.url(),
      status: response.status(),
      contentType: response.headers()['content-type'] || '',
    });
  });

  console.log('1. Navigating to Live Frontend: https://documind-frontend-tgpv.onrender.com');
  await page.goto('https://documind-frontend-tgpv.onrender.com', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(2000);

  // Take homepage screenshot
  await page.screenshot({ path: path.join(artifactsDir, 'playwright_1_homepage.png'), fullPage: true });
  console.log('Saved homepage screenshot.');

  console.log('2. Clicking "Get Started" to navigate to /dashboard...');
  const getStartedBtn = page.getByRole('button', { name: /get started/i }).first();
  if (await getStartedBtn.isVisible()) {
    await getStartedBtn.click();
    await page.waitForTimeout(3000);
  } else {
    await page.goto('https://documind-frontend-tgpv.onrender.com/dashboard', { waitUntil: 'networkidle' });
  }

  await page.screenshot({ path: path.join(artifactsDir, 'playwright_2_dashboard.png'), fullPage: true });
  console.log('Saved dashboard screenshot.');

  // Create test document content
  const samplePdfPath = path.join(__dirname, 'sample_test_doc.pdf');
  const samplePdfContent = `%PDF-1.4
1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj
2 0 obj <</Type /Pages /Count 1 /Kids [3 0 R]>> endobj
3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj
4 0 obj <</Length 250>> stream
BT
/F1 12 Tf
100 700 Td
(DocuMind AI Test Document) Tj
0 -20 Td
(Section 1: AI RAG document architecture provides grounded contextual Q&A using vector search.) Tj
0 -20 Td
(Section 2: High dimensional embeddings index documents and compute cosine similarity for retrieval.) Tj
0 -20 Td
(Section 3: Fast responses with exact source citations mapping back to page numbers and chunk offsets.) Tj
ET
endstream endobj
5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000261 00000 n 
0000000560 00000 n 
trailer <</Size 6 /Root 1 0 R>>
startxref
639
%%EOF`;
  fs.writeFileSync(samplePdfPath, samplePdfContent);

  console.log('3. Uploading sample PDF...');
  const fileInput = await page.$('input[type="file"]');
  if (fileInput) {
    await fileInput.setInputFiles(samplePdfPath);
    console.log('Uploaded file, waiting for indexing...');
    await page.waitForTimeout(8000);
    await page.screenshot({ path: path.join(artifactsDir, 'playwright_3_document_indexed.png'), fullPage: true });
    console.log('Saved indexing screenshot.');
  } else {
    console.log('No file input found on dashboard.');
  }

  // Create or select chat session if available
  const newChatBtn = page.getByRole('button', { name: /new chat/i }).first();
  if (await newChatBtn.isVisible()) {
    console.log('Clicking New Chat button...');
    await newChatBtn.click();
    await page.waitForTimeout(2000);
    // Select document if modal appears
    const docCheckbox = await page.$('input[type="checkbox"]');
    if (docCheckbox) {
      await docCheckbox.check();
      await page.waitForTimeout(500);
    }
    const createSessionBtn = page.getByRole('button', { name: /start chat|create chat|create session/i }).first();
    if (await createSessionBtn.isVisible()) {
      await createSessionBtn.click();
      await page.waitForTimeout(3000);
    }
  }

  // Ask Question 1
  const askQuestion = async (qText, stepName) => {
    console.log(`Asking question: "${qText}"...`);
    const input = page.locator('textarea, input[placeholder*="Ask"], input[type="text"]').last();
    if (await input.isVisible()) {
      await input.fill(qText);
      await page.waitForTimeout(500);
      await page.keyboard.press('Enter');
      console.log('Sent question, waiting for response...');
      await page.waitForTimeout(12000);
      await page.screenshot({ path: path.join(artifactsDir, `playwright_${stepName}.png`), fullPage: true });
      console.log(`Saved screenshot for ${stepName}.`);
    } else {
      console.log('Input field not visible.');
    }
  };

  await askQuestion('What is this document about?', '4_question1');
  await askQuestion('Summarize section 2', '5_question2');

  console.log('\n=== AUDIT SUMMARY ===');
  console.log(`Total Requests Recorded: ${networkRequests.length}`);
  console.log(`Total Console Logs Recorded: ${consoleLogs.length}`);
  console.log(`Total Network Errors Recorded: ${networkErrors.length}`);

  await browser.close();
  console.log('Playwright script execution complete.');
})();
