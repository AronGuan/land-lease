/** 复核工作台验证：原件对照 + 逐字段核对 + 高亮联动。 */
const { chromium } = require('playwright-core');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 1100 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e).slice(0, 200)));

  await page.goto('http://127.0.0.1:5173/contract/review', {
    waitUntil: 'domcontentloaded', timeout: 30000,
  });
  await page.waitForSelector('.review-layout', { timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'shots/复核工作台-原件对照.png', fullPage: true });

  const img = await page.locator('.imgstage img').count();
  const thumbs = await page.locator('.thumbs img').count();
  const rows = await page.locator('tr.fieldrow').count();
  const queueLabel = await page.locator('.ant-card').first().locator('strong, .ant-typography').first().textContent().catch(() => '');
  console.log(`原件图片=${img} 缩略图=${thumbs} 字段行=${rows} 队列=${(queueLabel || '').trim()}`);

  // 点击字段行 → 原图高亮
  await page.locator('tr.fieldrow').nth(3).click();
  await page.waitForTimeout(500);
  const hl = await page.locator('.hlbox').isVisible();
  console.log('高亮框可见:', hl);

  // 翻页
  if (thumbs > 1) {
    await page.locator('.thumbs img').nth(1).click();
    await page.waitForTimeout(600);
    const pageLabel = await page.locator('.imgbar span').first().textContent();
    console.log('翻页后:', pageLabel);
  }

  // 灰度增强
  await page.getByRole('button', { name: '灰度增强' }).click();
  await page.waitForTimeout(400);
  const filter = await page.locator('.imgstage img').evaluate((el) => el.style.filter);
  console.log('灰度滤镜:', filter);

  await page.screenshot({ path: 'shots/复核工作台-字段高亮.png', fullPage: true });
  console.log('页面错误:', errs.length, errs.slice(0, 3));
  await browser.close();
})();
