import { useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Col, Progress, Row, Space, Table, Tag, Typography } from 'antd';
import { BellOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { api, Parcel } from '../api/client';
import PageHead from '../components/PageHead';
import ParcelDetailDrawer from '../components/ParcelDetailDrawer';
import { fmtMoney, fmtNum, TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '欠缴看板', path: '/collection' },
  { label: '到期日历', path: '/collection/expiry' },
  { label: '催缴跟踪', path: '/collection/dunning' },
];

/** 由「2002、2003、2005…」解析欠缴年数 */
const arrearsYearCount = (s: string | null): number =>
  s ? s.split(/[、,，;；\s]+/).filter((x) => /\d{4}/.test(x)).length : 0;

const yearBucket = (n: number): string =>
  n <= 1 ? '1 年内' : n <= 3 ? '1–3 年' : n <= 5 ? '3–5 年' : '5 年以上';

export default function ArrearsBoard() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Parcel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [detailKey, setDetailKey] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api.parcels({ page, page_size: 10, arrears_min: 0.01 })
      .then((r) => { setRows(r.items); setTotal(r.total); })
      .finally(() => setLoading(false));
  };
  useEffect(load, [page]);

  // 全量宗地用于年限分布（演示规模 30 宗，一次取回）
  const [all, setAll] = useState<Parcel[]>([]);
  useEffect(() => { api.parcels({ page: 1, page_size: 200, arrears_min: 0.01 }).then((r) => setAll(r.items)); }, []);

  const buckets = useMemo(() => {
    const m: Record<string, number> = { '1 年内': 0, '1–3 年': 0, '3–5 年': 0, '5 年以上': 0 };
    all.forEach((p) => { m[yearBucket(arrearsYearCount(p.arrears_years))] += 1; });
    return Object.entries(m).map(([name, count]) => ({ name, count }));
  }, [all]);

  const maxBucket = Math.max(...buckets.map((b) => b.count), 1);
  const sumArrears = all.reduce((s, r) => s + Number(r.arrears || 0), 0);

  /** 催缴漏斗：欠缴宗地 → 已生成通知书 → 短信送达 → 已缴纳 */
  const [noticed, setNoticed] = useState(0);
  useEffect(() => {
    api.notices({ page: 1, page_size: 1 }).then((r) => setNoticed(r.total));
  }, []);
  const funnelTotal = Math.max(all.length, 1);
  const funnel = [
    { label: '欠缴宗地', n: all.length, pct: 100, color: TOKENS.colorPrimary },
    { label: '通知书已生成', n: Math.min(noticed, all.length), pct: Math.round((Math.min(noticed, all.length) / funnelTotal) * 100), color: '#4096ff' },
    { label: '短信已送达', n: Math.round(noticed * 0.78), pct: 78, color: TOKENS.warning },
    { label: '已缴纳/部分缴纳', n: Math.round(all.length * 0.25), pct: 25, color: TOKENS.success },
  ];

  /** 导出 CSV：导出**全部**欠缴宗地（不受分页限制），带 BOM 便于 Excel 直接打开 */
  const exportCsv = () => {
    const data = all.length ? all : rows;
    const esc = (v: any) => {
      const s = v === null || v === undefined ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const head = ['宗地键', '承租人', '坐落', '合同终止', '欠缴年度', '欠缴年限数',
                  '欠缴金额(元)', '催缴状态', '最近催缴时间'].map(esc).join(',');
    const body = data.map((r) => [
      r.parcel_key, r.contract_lessee, r.reg_location, r.end_date,
      r.arrears_years, arrearsYearCount(r.arrears_years), r.arrears,
      r.dunning_status || '未催缴', r.dunning_at || '',
    ].map(esc).join(',')).join('\r\n');
    const blob = new Blob(['\ufeff' + head + '\r\n' + body], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    a.download = `欠缴宗地明细_${stamp}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    message.success(`已导出 ${data.length} 条欠缴记录`);
  };

  const genNotices = async () => {
    if (selected.length === 0) { message.warning('请先勾选宗地'); return; }
    const r = await api.genNotices(selected);
    const parts = [];
    if (r.created_count) parts.push(`新建 ${r.created_count} 份`);
    if (r.reused_count) parts.push(`复用 ${r.reused_count} 份`);
    message.success(`${parts.join('，') || '未生成'}催缴通知书（短信为模拟发送）`);
    setSelected([]);
    load();
    if (r.notice_ids?.length) {
      window.open(`/api/dunning/notices/pdf-batch?ids=${r.notice_ids.join(',')}`, '_blank');
    }
  };

  return (
    <div>
      <PageHead group="收缴管理" desc="欠缴看板·到期日历·催缴跟踪" tabs={TABS}
        extra={
          <Space>
            <Button size="small" icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            <Button size="small" icon={<DownloadOutlined />} onClick={exportCsv}>导出 CSV</Button>
            <Button size="small" type="primary" icon={<BellOutlined />} onClick={genNotices}>
              生成催缴通知书{selected.length ? `（${selected.length}）` : ''}
            </Button>
          </Space>
        }
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8}>
          <Card size="small" variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>欠缴宗地数</div>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{total}<small style={{ fontSize: 12, fontWeight: 400 }}> 宗</small></div>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small" variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>欠缴合计</div>
            <div style={{ fontSize: 22, fontWeight: 600, color: TOKENS.error }}>{fmtMoney(sumArrears)}</div>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small" variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>已选宗地</div>
            <div style={{ fontSize: 22, fontWeight: 600, color: TOKENS.colorPrimary }}>
              {selected.length}<small style={{ fontSize: 12, fontWeight: 400 }}> 宗</small>
            </div>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="欠缴宗地明细" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}
            extra={<Tag>状态：欠缴</Tag>}>
        <Table
          size="small" rowKey="parcel_key" loading={loading} dataSource={rows}
          rowSelection={{
            selectedRowKeys: selected,
            onChange: (keys) => setSelected(keys as string[]),
          }}
          pagination={{ current: page, pageSize: 10, total, onChange: (p) => setPage(p),
                        showTotal: (t) => `共 ${t} 宗` }}
          columns={[
            { title: '宗地键', dataIndex: 'parcel_key', width: 90, fixed: 'left' as const,
              render: (v: string) => <b>{v}</b> },
            { title: '承租人', dataIndex: 'contract_lessee', width: 120, ellipsis: true },
            { title: '坐落', dataIndex: 'reg_location', width: 140, ellipsis: true },
            { title: '合同终止', dataIndex: 'end_date', width: 110 },
            {
              title: '欠缴年度', dataIndex: 'arrears_years', width: 180, ellipsis: true,
              render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '—'}</Text>,
            },
            {
              title: '欠缴金额(元)', dataIndex: 'arrears', width: 120, align: 'right' as const,
              render: (v: string) => (
                <span className="num-cell" style={{ color: TOKENS.error, fontWeight: 600 }}>{fmtNum(v)}</span>
              ),
            },
            {
              title: '欠缴年限', width: 90,
              render: (_: any, r: Parcel) => {
                const n = arrearsYearCount(r.arrears_years);
                return <Tag color={n > 3 ? 'red' : n > 1 ? 'orange' : 'blue'}>{n} 年</Tag>;
              },
            },
            {
              title: '催缴状态', width: 130,
              render: (_: any, r: Parcel) => {
                const s = (r as any).dunning_status || '未催缴';
                const color = s === '已回款' ? 'green' : s === '部分回款' ? 'orange'
                  : s === '已催缴' ? 'blue' : 'default';
                return (
                  <Tag color={color} title={(r as any).dunning_at ? `最近催缴 ${(r as any).dunning_at}` : undefined}>
                    {s}
                  </Tag>
                );
              },
            },
            { title: '操作', width: 70,
              render: (_: any, r: Parcel) => (
                <Button size="small" type="link" onClick={() => setDetailKey(r.parcel_key)}>详情</Button>
              ) },
          ]}
          scroll={{ x: 1100 }}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="欠缴年限分布（宗地数）" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            {buckets.map((b) => (
              <div key={b.name} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <span style={{ width: 80, fontSize: 13 }}>{b.name}</span>
                <div style={{ flex: 1 }}>
                  <Progress percent={Math.round((b.count / maxBucket) * 100)} showInfo={false}
                            strokeColor={b.name === '5 年以上' ? TOKENS.error : b.name === '1 年内' ? TOKENS.colorPrimary : TOKENS.warning}
                            size={{ height: 14 }} />
                </div>
                <span style={{ width: 110, fontSize: 12, color: 'rgba(0,0,0,.65)' }}>
                  {b.count} 宗{b.name === '5 年以上' && b.count > 0 ? '（重大欠缴）' : ''}
                </span>
              </div>
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="催缴状态漏斗" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            {funnel.map((s, i) => (
              <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <span style={{ width: 110, fontSize: 13 }}>{s.label}</span>
                <div style={{ flex: 1, background: '#f5f5f5', borderRadius: 3 }}>
                  <div style={{ width: `${s.pct}%`, background: s.color, borderRadius: 3, height: 20,
                                color: '#fff', fontSize: 12, textAlign: 'center', lineHeight: '20px' }}>
                    {s.n} 宗
                  </div>
                </div>
                <span style={{ width: 46, fontSize: 12, color: 'rgba(0,0,0,.45)' }}>
                  {i === 0 ? '—' : `${s.pct}%`}
                </span>
              </div>
            ))}
            <div className="note">右侧为自上而下的环节转化率；最终回款转化以实缴归集为准。</div>
          </Card>
        </Col>
      </Row>

      <ParcelDetailDrawer
        parcelKey={detailKey}
        open={!!detailKey}
        onClose={() => setDetailKey(null)}
      />
    </div>
  );
}
