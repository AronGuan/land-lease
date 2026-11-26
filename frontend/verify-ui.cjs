/** 全页面 + 页内 Tab 验证。 */
const { chromium } = require('playwright-core');

const PAGES = [
  ['/dashboard', '工作台'],
  ['/contract/batch', '合同治理-批次导入'],
  ['/contract/review', '合同治理-复核工作台'],
  ['/contract/issues', '合同治理-问题清单'],
  ['/collection', '收缴管理-欠缴看板'],
  ['/collection/expiry', '收缴管理-到期日历'],
  ['/collection/dunning', '收缴管理-催缴跟踪'],
  ['/ledger', '宗地台账'],
  ['/ledger/contract-gen', '宗地台账-合同生成'],
  ['/report', '统计报表-治理进度'],
  ['/report/tax', '统计报表-税务推送'],
  ['/system', '系统管理-计租标准'],
  ['/system/rules', '系统管理-核算口径'],
  ['/system/models', '系统管理-模型管理'],
  ['/system/audit', '系统管理-审计日志'],
  ['/system/settings', '系统管理-系统设置'],
];

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console] ${m.text().slice(0, 160)}`); });
  page.on('pageerror', (e) => errors.push(`[pageerror] ${String(e).slice(0, 180)}`));

  for (const [path, name] of PAGES) {
    await page.goto(`http://127.0.0.1:5173${path}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForSelector('.page-head', { timeout: 45000 });
    await page.waitForTimeout(400);
    const tabs = await page.locator('.page-head .ant-segmented-item').count();
    const activeTab = await page.locator('.page-head .ant-segmented-item-selected').textContent().catch(() => '-');
    const rows = await page.locator('.ant-table-row').count();
    await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
    console.log(`${name.padEnd(22)} tabs=${tabs} 选中=${(activeTab || '-').trim().padEnd(8)} rows=${rows}`);
  }

  console.log(`\n控制台错误 ${errors.length} 条`);
  [...new Set(errors)].slice(0, 10).forEach((e) => console.log('  ' + e));
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
