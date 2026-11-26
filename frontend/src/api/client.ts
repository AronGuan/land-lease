import axios from 'axios';

/** 统一 API 客户端：开发期走 vite proxy，生产同域部署。 */
export const http = axios.create({ baseURL: '/api', timeout: 60000 });

http.interceptors.response.use(
  (r) => r,
  (e) => {
    const detail = e?.response?.data?.detail;
    if (detail) e.message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    return Promise.reject(e);
  },
);

export interface PageResp<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Batch {
  id: number;
  batch_no: string;
  batch_type: string;
  status: string;
  file_count: number;
  doc_count: number;
  created_by: string | null;
  created_at: string;
}

export interface ContractDoc {
  id: string;
  batch_id: number;
  doc_type: string | null;
  contract_no: string | null;
  sign_date: string | null;
  lessor: string | null;
  lessee: string | null;
  id_no: string | null;
  phone: string | null;
  location: string | null;
  area: string | null;
  land_usage: string | null;
  land_level: string | null;
  start_date: string | null;
  end_date: string | null;
  years: number | null;
  rent_mode: string | null;
  rent_amount: string | null;
  altered_field: string | null;
  altered_before: string | null;
  altered_seal: number | null;
  has_map: number | null;
  process_type: string;
  status: string;
  /** 关键字段最低置信度（≥0.90 才可能是「自动通过」） */
  min_confidence?: number | null;
}

export interface FieldExtraction {
  id: number;
  field_name: string;
  ai_value: string | null;
  final_value: string | null;
  confidence: string | null;
  source: string;
  reason: { level?: string; rules?: string[]; issues?: string[] } | null;
}

export interface Parcel {
  parcel_key: string;
  unit_no: string | null;
  reg_location: string | null;
  reg_area: string | null;
  contract_area: string | null;
  land_usage: string | null;
  land_level: string | null;
  rent_mode: string | null;
  contract_status: string | null;
  end_date: string | null;
  contract_lessee: string | null;
  reg_owner: string | null;
  dunning_target: string | null;
  phone: string | null;
  due_2026: string | null;
  total_due: string | null;
  total_paid: string | null;
  arrears: string | null;
  arrears_years: string | null;
  process_type: string;
  updated_at: string;
  /** 列表页附加列 */
  archives?: string | null;
  dunning_status?: string | null;
  dunning_notice_id?: number | null;
  dunning_at?: string | null;
}

export interface Issue {
  id: number;
  target: string;
  issue_type: string;
  description: string | null;
  temp_algorithm: string | null;
  diff_amount: string | null;
  status: string;
  created_at: string;
}

export const api = {
  health: () => http.get('/health').then((r) => r.data),
  // 批次
  batches: (params?: any) => http.get<PageResp<Batch>>('/batches', { params }).then((r) => r.data),
  createBatch: (body: any) => http.post('/batches', body).then((r) => r.data),
  batchDetail: (id: number) => http.get(`/batches/${id}`).then((r) => r.data),
  uploadFiles: (id: number, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    return http.post(`/batches/${id}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }).then((r) => r.data);
  },
  runBatch: (id: number) => http.post(`/batches/${id}/run`, {}, { timeout: 300000 }).then((r) => r.data),
  rollbackBatch: (id: number) => http.post(`/batches/${id}/rollback`).then((r) => r.data),
  // 复核
  reviewDocs: (params?: any) =>
    http.get<PageResp<ContractDoc>>('/review/docs', { params }).then((r) => r.data),
  docDetail: (id: string) =>
    http.get<{ doc: ContractDoc; fields: FieldExtraction[] }>(`/review/docs/${id}`).then((r) => r.data),
  docPages: (id: string) =>
    http.get<{ archive_no: string; batch_no: string | null; page_count: number; pages: { page_no: number; url: string }[] }>(
      `/review/docs/${id}/pages`).then((r) => r.data),
  correctField: (id: string, body: any) =>
    http.post(`/review/docs/${id}/correct`, body).then((r) => r.data),
  confirmDoc: (id: string) => http.post(`/review/docs/${id}/confirm`).then((r) => r.data),
  batchConfirm: (body: any) => http.post('/review/batch-confirm', body).then((r) => r.data),
  revertDoc: (id: string) => http.post(`/review/docs/${id}/revert`).then((r) => r.data),
  // 宗地
  parcels: (params?: any) => http.get<PageResp<Parcel>>('/parcels', { params }).then((r) => r.data),
  parcelDetail: (key: string) => http.get(`/parcels/${key}`).then((r) => r.data),
  contractDraft: (key: string, years = 10) =>
    http.get(`/parcels/${key}/contract-draft`, { params: { years } }).then((r) => r.data),
  pushItems: (id: number) => http.get(`/tax/${id}/items`).then((r) => r.data),
  modelLogs: () => http.get('/system/model-logs').then((r) => r.data),
  // 问题
  issues: (params?: any) => http.get<PageResp<Issue>>('/issues', { params }).then((r) => r.data),
  issueTypes: () => http.get<string[]>('/issues/types').then((r) => r.data),
  resolveIssue: (id: number) => http.post(`/issues/${id}/resolve`).then((r) => r.data),
  // 看板
  kpis: () => http.get('/dashboard/kpis').then((r) => r.data),
  arrearsTop: () => http.get('/dashboard/arrears-top').then((r) => r.data),
  distributions: () => http.get('/dashboard/distributions').then((r) => r.data),
  governanceQueue: () => http.get('/dashboard/governance-queue').then((r) => r.data),
  // 催缴
  notices: (params?: any) => http.get<PageResp<any>>('/dunning/notices', { params }).then((r) => r.data),
  genNotices: (keys: string[]) => http.post('/dunning/notices', keys).then((r) => r.data),
  noticeTracks: (id: number) => http.get(`/dunning/notices/${id}/tracks`).then((r) => r.data),
  addNoticeTrack: (id: number, body: { amount: number; pay_date?: string; receipt_no?: string }) =>
    http.post(`/dunning/notices/${id}/tracks`, null, { params: body }).then((r) => r.data),
  noticePdfUrl: (id: number) => `/api/dunning/notices/${id}/pdf`,
  expiryCalendar: () => http.get('/dunning/expiry-calendar').then((r) => r.data),
  expiryAlerts: (days = 90) => http.get('/dunning/expiry-alerts', { params: { days } }).then((r) => r.data),
  // 税务
  taxPushes: () => http.get('/tax').then((r) => r.data),
  pushTax: (year: number) => http.post(`/tax/push?year=${year}`).then((r) => r.data),
  // 系统
  standards: () => http.get('/system/standards').then((r) => r.data),
  streetLevels: () => http.get('/system/street-levels').then((r) => r.data),
  reductions: () => http.get('/system/reductions').then((r) => r.data),
  issueTypeStats: () => http.get('/issues/type-stats').then((r) => r.data),
  auditLogs: (params?: any) => http.get<PageResp<any>>('/system/audit-logs', { params }).then((r) => r.data),
  models: () => http.get('/system/models').then((r) => r.data),
  activateModel: (id: number) => http.post(`/system/models/${id}/activate`).then((r) => r.data),
  testModel: (id: number) => http.post(`/system/models/${id}/test`).then((r) => r.data),
  updateModel: (id: number, body: any) => http.put(`/system/models/${id}`, body).then((r) => r.data),
  // 基础数据（02 登记 / 03 缴费 / 04 减免 / 05 标准）
  refdataStatus: () => http.get('/refdata/status').then((r) => r.data),
  refdataPreview: (kind: string, file: File, sheet?: string) => {
    const fd = new FormData();
    fd.append('file', file);
    return http.post('/refdata/preview', fd, {
      params: { kind, ...(sheet ? { sheet } : {}) },
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data);
  },
  refdataCommit: (body: { token: string; kind: string; mode: string; sheet?: string; operator?: string; relink?: boolean }) =>
    http.post('/refdata/commit', body).then((r) => r.data),
  refdataRelink: (operator?: string) =>
    http.post('/refdata/relink', null, { params: { operator: operator || '系统' } }).then((r) => r.data),
  refdataDuplicates: () => http.get('/refdata/duplicates').then((r) => r.data),
  refdataMerge: (operator?: string) =>
    http.post('/refdata/merge', null, { params: { operator: operator || '系统' } }).then((r) => r.data),
};
