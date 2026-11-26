/** 全局设计 token（对齐系统原型.html / PRD 十一） */
export const TOKENS = {
  colorPrimary: '#1677ff',
  success: '#389e0d',
  warning: '#d46b08',
  error: '#cf1322',
  textPrimary: 'rgba(0,0,0,.88)',
  textSecondary: 'rgba(0,0,0,.65)',
  borderColor: '#f0f0f0',
  bgLayout: '#f5f5f5',
  radius: 8,
  radiusLg: 12,
  space: 8,
};

/** 金额格式化：¥1,234.56 */
export const fmtMoney = (v: number | string | null | undefined): string => {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isNaN(n)) return '—';
  return `¥${n.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

/** 金额（不带币符，用于表格右对齐数字） */
export const fmtNum = (v: number | string | null | undefined): string => {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isNaN(n)) return '—';
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

/** 三级识别标签色：L1 绿 / L2 橙 / L3 红 */
export const LEVEL_COLOR: Record<string, string> = {
  L1: TOKENS.success,
  L2: TOKENS.warning,
  L3: TOKENS.error,
};

export const LEVEL_TEXT: Record<string, string> = {
  L1: '直接识别',
  L2: '反推 / 复核',
  L3: '不可识别',
};
