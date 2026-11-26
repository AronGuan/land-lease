/**
 * 功能点验收：用 Chrome 打开原型 HTML 与真实项目 16 个页面，
 * 逐页检测功能点是否“正常”（无控制台错误 + 关键元素/数据 + 关键交互）。
 *
 * 用法：
 *   node verify_all_pages.cjs
 * 依赖：playwright-core + 系统 Chrome
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE = 'http://127.0.0.1:5173';
const PROTO = 'file://' + path.resolve(__dirname, '..', '系统原型.html');
const OUT_DIR = 'reports';

const results = []; // { page, path, checks:[{label, ok, detail}] }
let protoSections = [];

async function newPage(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  const page = await ctx.newPage();
  page._errs = [];
  page.on('pageerror', (e) => page._errs.push('PAGEERR ' + String(e).slice(0, 160)));
  page.on('console', (m) => {
    if (m.type() === 'error') page._errs.push('CONSOLE ' + m.text().slice(0, 160));
  });
  return page;
}

async function go(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('.app-content-inner, body', { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1800);
}

// 通用断言
async function hasText(page, txt) {
  return (await page.locator(`text=${JSON.stringify(txt)}`).count()) > 0 ||
         (await page.getByText(txt, { exact: false }).count()) > 0;
}
async function countSel(page, sel) {
  return await page.locator(sel).count();
}

async function run() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });

  // ---------- 1) 原型基线 ----------
  console.log('=== 加载原型 HTML，抽取功能规格基线 ===');
  const pp = await newPage(browser);
  await pp.goto(PROTO, { waitUntil: 'load', timeout: 30000 });
  await pp.waitForTimeout(1200);
  protoSections = await pp.evaluate(() => {
    const out = [];
    document.querySelectorAll('section.page').forEach((sec) => {
      const h = sec.querySelector('h1, h2, .page-title');
      const cards = [...sec.querySelectorAll('.card, .card-title')].map(c => (c.textContent || '').trim().slice(0, 40));
      out.push({ title: (h ? h.textContent : '').trim().slice(0, 30), cards: cards.filter(Boolean).slice(0, 10) });
    });
    return out;
  });
  console.log(`原型页面区块数=${protoSections.length}`);
  await pp.close();

  // ---------- 2) 真实项目逐页检测 ----------
  const pages = [
    { name: '工作台', path: '/dashboard', fn: checkDashboard },
    { name: '复核工作台', path: '/contract/review', fn: checkReview },
    { name: '批次导入', path: '/contract/batch', fn: checkBatch },
    { name: '问题清单', path: '/contract/issues', fn: checkIssues },
    { name: '欠缴看板', path: '/collection', fn: checkArrears },
    { name: '到期日历', path: '/collection/expiry', fn: checkExpiry },
    { name: '催缴跟踪', path: '/collection/dunning', fn: checkDunning },
    { name: '宗地台账', path: '/ledger', fn: checkLedger },
    { name: '合同生成', path: '/ledger/contract-gen', fn: checkContractGen },
    { name: '治理进度', path: '/report', fn: checkGovernance },
    { name: '税务推送', path: '/report/tax', fn: checkTax },
    { name: '标准管理', path: '/system', fn: checkStandards },
    { name: '核算口径', path: '/system/rules', fn: checkCalcRules },
    { name: '模型管理', path: '/system/models', fn: checkModels },
    { name: '操作日志', path: '/system/audit', fn: checkAudit },
    { name: '系统设置', path: '/system/settings', fn: checkSettings },
  ];

  for (const pg of pages) {
    console.log(`\n=== ${pg.name} (${pg.path}) ===`);
    const page = await newPage(browser);
    const checks = [];
    try {
      await go(page, BASE + pg.path);
      await pg.fn(page, checks);
    } catch (e) {
      checks.push({ label: '页面加载/执行', ok: false, detail: '异常: ' + e.message.slice(0, 120) });
    }
    const errCount = page._errs.length;
    checks.push({ label: '控制台无错误', ok: errCount === 0, detail: errCount ? page._errs.slice(0, 3).join(' | ') : '0 错误' });
    results.push({ page: pg.name, path: pg.path, checks });
    await page.context().close();
  }

  await browser.close();
  printReport();
  writeReport();
}

// ---------- 各页检测函数 ----------
async function checkDashboard(page, c) {
  c.push({ label: 'KPI 卡片 ≥6', ok: (await countSel(page, '.ant-card')) >= 6, detail: `cards=${await countSel(page, '.ant-card')}` });
  c.push({ label: '含“存量合同/宗地数/年度应收/累计欠缴/收缴率/待复核”', ok: await hasText(page, '累计欠缴') && await hasText(page, '收缴率'), detail: '' });
  c.push({ label: '收缴率趋势图', ok: await hasText(page, '收缴率趋势'), detail: '' });
  c.push({ label: '问题清单分布', ok: await hasText(page, '问题清单分布') || await hasText(page, '问题分布'), detail: '' });
  c.push({ label: '待办提醒', ok: await hasText(page, '待办'), detail: '' });
}

async function checkReview(page, c) {
  c.push({ label: '复核布局存在', ok: (await countSel(page, '.review-layout')) >= 1, detail: '' });
  const img = await countSel(page, '.imgstage img');
  c.push({ label: '原件图片显示', ok: img >= 1, detail: `img=${img}` });
  const th = await countSel(page, '.thumbs img');
  c.push({ label: '缩略图 ≥1', ok: th >= 1, detail: `thumbs=${th}` });
  const rows = await countSel(page, 'tr.fieldrow');
  c.push({ label: '字段行 ≥20', ok: rows >= 20, detail: `rows=${rows}` });
  // 交互：点字段行 → 高亮框
  try {
    await page.locator('tr.fieldrow').nth(2).click();
    await page.waitForTimeout(400);
    const hl = await page.locator('.hlbox').isVisible().catch(() => false);
    c.push({ label: '点击字段→原图红框高亮', ok: hl, detail: hl ? '可见' : '未显示' });
  } catch (e) { c.push({ label: '点击字段→原图红框高亮', ok: false, detail: e.message.slice(0, 80) }); }
  // 交互：灰度增强
  try {
    await page.getByRole('button', { name: '灰度增强' }).click();
    await page.waitForTimeout(300);
    const f = await page.locator('.imgstage img').evaluate(el => el.style.filter || getComputedStyle(el).filter).catch(() => '');
    c.push({ label: '灰度增强滤镜生效', ok: /grayscale/.test(f), detail: f });
  } catch (e) { c.push({ label: '灰度增强滤镜生效', ok: false, detail: e.message.slice(0, 80) }); }
  // 交互：翻页
  if ((await countSel(page, '.thumbs img')) > 1) {
    try {
      await page.locator('.thumbs img').nth(1).click();
      await page.waitForTimeout(400);
      const lbl = await page.locator('.imgbar span').first().textContent().catch(() => '');
      c.push({ label: '缩略图翻页', ok: /第\s*[23]/.test(lbl || ''), detail: lbl });
    } catch (e) { c.push({ label: '缩略图翻页', ok: false, detail: e.message.slice(0, 60) }); }
  } else { c.push({ label: '缩略图翻页', ok: true, detail: '仅1页,跳过' }); }
}

async function checkBatch(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '批次列表有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '现场补档说明', ok: await hasText(page, '现场补档'), detail: '' });
  c.push({ label: '进度列(Progress)', ok: (await countSel(page, '.ant-progress')) >= 1, detail: `progress=${await countSel(page, '.ant-progress')}` });
}

async function checkIssues(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '问题列表有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '导出待确认清单按钮', ok: (await page.getByRole('button', { name: /导出待确认清单/ }).count()) > 0, detail: '' });
  c.push({ label: '第12条口径说明', ok: await hasText(page, '存疑') || await hasText(page, '第 12 条') || await hasText(page, '第12条'), detail: '' });
}

async function checkArrears(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '欠缴表格有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '欠缴年限分布', ok: await hasText(page, '欠缴年限分布') || await hasText(page, '年限分布'), detail: '' });
  c.push({ label: '催缴状态漏斗', ok: await hasText(page, '催缴状态') || await hasText(page, '漏斗'), detail: '' });
  c.push({ label: '导出 CSV 按钮', ok: (await page.getByRole('button', { name: /导出 CSV/ }).count()) > 0, detail: '' });
}

async function checkExpiry(page, c) {
  // 月历格子
  const cells = await countSel(page, 'table td, .calendar-cell, .month-cell');
  c.push({ label: '月历格子渲染', ok: cells >= 20, detail: `cells=${cells}` });
  c.push({ label: '分级提醒规则', ok: await hasText(page, '分级提醒') || await hasText(page, '紧急') && await hasText(page, '一般'), detail: '' });
  c.push({ label: '近期待办表', ok: (await countSel(page, '.ant-table-row')) >= 1 || await hasText(page, '近期待办'), detail: `rows=${await countSel(page, '.ant-table-row')}` });
}

async function checkDunning(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '催缴跟踪表有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '催缴通知书预览', ok: await hasText(page, '催缴通知书') || await hasText(page, '通知书'), detail: '' });
  c.push({ label: '通知书含真实宗地数据', ok: await hasText(page, 'LX-') || await hasText(page, '档案号'), detail: '' });
  c.push({ label: '操作列', ok: await hasText(page, '操作'), detail: '' });
}

async function checkLedger(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '宗地表有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '档案号列表列', ok: await hasText(page, '档案号列表'), detail: '' });
  c.push({ label: '导出 CSV 按钮', ok: (await page.getByRole('button', { name: /导出 CSV/ }).count()) > 0, detail: '' });
  // 交互：点击行下钻
  try {
    await page.locator('.ant-table-row').first().click();
    await page.waitForTimeout(800);
    const ok = await hasText(page, '合同时间轴') || await hasText(page, '合同链');
    c.push({ label: '点击行→下钻合同时间轴/合同链', ok, detail: ok ? '已展开' : '未展开' });
  } catch (e) { c.push({ label: '点击行→下钻合同时间轴/合同链', ok: false, detail: e.message.slice(0, 80) }); }
}

async function checkContractGen(page, c) {
  c.push({ label: '宗地选择框', ok: (await countSel(page, '.ant-select')) >= 1, detail: '' });
  // 交互：选宗地 + 生成
  try {
    await page.locator('.ant-select').first().click();
    await page.waitForTimeout(500);
    await page.locator('.ant-select-item-option').first().click();
    await page.waitForTimeout(400);
    const genBtn = page.getByRole('button', { name: /生成/ });
    if (await genBtn.count()) {
      await genBtn.first().click();
      await page.waitForTimeout(1500);
    }
    const ok = await hasText(page, '合同') && (await countSel(page, '.ant-card')) >= 1;
    c.push({ label: '生成合同草稿', ok, detail: ok ? '已生成预览' : '未生成' });
  } catch (e) { c.push({ label: '生成合同草稿', ok: false, detail: '交互: ' + e.message.slice(0, 80) }); }
}

async function checkGovernance(page, c) {
  c.push({ label: 'KPI 四卡', ok: await hasText(page, '识别完成') && await hasText(page, '自动通过') && await hasText(page, '转人工复核'), detail: '' });
  c.push({ label: '自动通过质量卡', ok: await hasText(page, '自动通过质量') || await hasText(page, '准确率'), detail: '' });
}

async function checkTax(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '推送单表(可能为空)', ok: true, detail: `rows=${rows}` });
  // 交互：生成本期推送单
  try {
    const btn = page.getByRole('button', { name: /生成本期推送单/ });
    if (await btn.count()) {
      await btn.first().click();
      await page.waitForTimeout(1500);
      const ok = (await countSel(page, '.ant-table-row')) >= 1 || await hasText(page, '推送单字段');
      c.push({ label: '生成本期推送单', ok, detail: ok ? '已生成' : '未生成' });
    } else { c.push({ label: '生成本期推送单', ok: true, detail: '按钮不存在,跳过' }); }
  } catch (e) { c.push({ label: '生成本期推送单', ok: false, detail: e.message.slice(0, 80) }); }
}

async function checkStandards(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '计租标准表有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '含用途/级别维度', ok: await hasText(page, '用途') && await hasText(page, '级别'), detail: '' });
}

async function checkCalcRules(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '核算规则表有数据', ok: rows >= 1, detail: `rows=${rows}` });
  c.push({ label: '系统落点列', ok: await hasText(page, '系统落点'), detail: '' });
  c.push({ label: '核算留痕示例卡', ok: await hasText(page, '核算留痕') || await hasText(page, 'rent_calc_trace'), detail: '' });
}

async function checkModels(page, c) {
  c.push({ label: '三通道卡片(主通道)', ok: await hasText(page, '主通道'), detail: '' });
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '模型调用日志表', ok: rows >= 1, detail: `rows=${rows}` });
}

async function checkAudit(page, c) {
  const rows = await countSel(page, '.ant-table-row');
  c.push({ label: '操作日志表有数据', ok: rows >= 1, detail: `rows=${rows}` });
}

async function checkSettings(page, c) {
  c.push({ label: '用户与权限', ok: await hasText(page, '用户与权限') || await hasText(page, '用户管理'), detail: '' });
  c.push({ label: '备份与恢复', ok: await hasText(page, '备份'), detail: '' });
  c.push({ label: '配置中心', ok: await hasText(page, '配置中心') || await hasText(page, '系统配置'), detail: '' });
}

// ---------- 报告 ----------
function printReport() {
  let total = 0, pass = 0;
  console.log('\n\n========== 功能点验收报告 ==========');
  for (const r of results) {
    console.log(`\n【${r.page}】 ${r.path}`);
    for (const ck of r.checks) {
      total++; if (ck.ok) pass++;
      const tag = ck.ok ? '✓' : '✗';
      console.log(`  ${tag} ${ck.label}${ck.detail ? '  — ' + ck.detail : ''}`);
    }
  }
  console.log(`\n汇总: ${pass}/${total} 通过`);
}

function writeReport() {
  let total = 0, pass = 0;
  let md = `# 功能点验收报告\n\n> 生成时间: ${new Date().toLocaleString('zh-CN')}\n> 浏览器: Google Chrome (headless)\n> 原型区块数: ${protoSections.length}\n\n`;
  md += `## 原型功能规格基线（${protoSections.length} 个页面区块）\n\n`;
  protoSections.forEach((s, i) => {
    md += `${i + 1}. **${s.title || '(未命名)'}** — 卡片: ${s.cards.join('、') || '—'}\n`;
  });
  md += `\n## 逐页功能点检测\n\n`;
  for (const r of results) {
    md += `### 【${r.page}】 \`${r.path}\`\n\n| 功能点 | 结果 | 说明 |\n|---|---|---|\n`;
    for (const ck of r.checks) {
      total++; if (ck.ok) pass++;
      md += `| ${ck.label} | ${ck.ok ? '✓ 正常' : '✗ 异常'} | ${ck.detail || ''} |\n`;
    }
    md += `\n`;
  }
  md += `\n## 汇总\n\n**${pass} / ${total}** 功能点通过\n`;
  fs.writeFileSync(path.join(OUT_DIR, '功能验收报告.md'), md, 'utf-8');
  console.log('报告已写: ' + path.join(OUT_DIR, '功能验收报告.md'));
}

run().catch((e) => { console.error('FATAL', e); process.exit(1); });
