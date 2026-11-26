import { useEffect, useState } from 'react';
import { Card, Input, Select, Space, Table, Tag, Typography, Empty, Button } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { api, Parcel } from '../api/client';
import PageHead from '../components/PageHead';
import ParcelDetailDrawer from '../components/ParcelDetailDrawer';
import { fmtMoney, fmtNum, TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '宗地台账', path: '/ledger' },
  { label: '合同生成', path: '/ledger/contract-gen' },
];

export default function ParcelLedger() {
  const [rows, setRows] = useState<Parcel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [kw, setKw] = useState('');
  const [usage, setUsage] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [archives, setArchives] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(false);

  const load = () => {
    setLoading(true);
    api.parcels({ page, page_size: pageSize, keyword: kw || undefined, land_usage: usage })
      .then((r) => { setRows(r.items); setTotal(r.total); setArchives(Object.fromEntries(r.items.map((x: any) => [x.parcel_key, x.archives || x.parcel_key]))); })
      .finally(() => setLoading(false));
  };
  useEffect(load, [page, pageSize, kw, usage]);

  const [detailKey, setDetailKey] = useState<string | null>(null);
  const openDetail = (key: string) => { setDetailKey(key); setOpen(true); };

  return (
    <div>
      <PageHead group="宗地台账" desc="宗地台账·合同生成" tabs={TABS}
        extra={
          <Space>
            <Input.Search placeholder="宗地键 / 关键字" allowClear style={{ width: 200 }}
                          onSearch={(v) => { setPage(1); setKw(v); }} />
            <Select placeholder="用途" allowClear style={{ width: 120 }}
                    value={usage} onChange={(v) => { setPage(1); setUsage(v); }}
                    options={['住宅', '商服', '工业', '仓储'].map((u) => ({ label: u, value: u }))} />
            <Button size="small" icon={<DownloadOutlined />} onClick={async () => {
              // 导出全部宗地（按当前筛选条件，不受分页限制）
              const all = await api.parcels({ page: 1, page_size: 200, keyword: kw || undefined, land_usage: usage });
              const esc = (v: any) => {
                const s = v === null || v === undefined ? '' : String(v);
                return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
              };
              const head = ['宗地键', '档案号列表', '坐落', '用途', '级别', '承租人',
                            '累计应缴', '累计实缴', '欠缴', '催缴状态'].map(esc).join(',');
              const body = all.items.map((r: any) => [
                r.parcel_key, r.archives || archives[r.parcel_key] || r.parcel_key,
                r.reg_location, r.land_usage, r.land_level, r.contract_lessee,
                r.total_due, r.total_paid, r.arrears, r.dunning_status || '未催缴',
              ].map(esc).join(',')).join('\r\n');
              const blob = new Blob(['\ufeff' + head + '\r\n' + body], { type: 'text/csv;charset=utf-8' });
              const a = document.createElement('a');
              a.href = URL.createObjectURL(blob);
              a.download = `宗地台账_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.csv`;
              a.click();
              URL.revokeObjectURL(a.href);
            }}>导出 CSV</Button>
          </Space>
        }
      />

      <Card variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small"
          rowKey="parcel_key"
          loading={loading}
          dataSource={rows}
          pagination={{
            current: page, pageSize, total, showSizeChanger: true,
            showTotal: (t) => `共 ${t} 宗`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
          columns={[
            {
              title: '宗地键', dataIndex: 'parcel_key', width: 96, fixed: 'left' as const,
              render: (v: string) => <a onClick={() => openDetail(v)}>{v}</a>,
            },
            { title: '档案号列表', width: 150, ellipsis: true,
              render: (_: any, r: Parcel) => (r as any).archives || archives[r.parcel_key] || r.parcel_key },
            { title: '坐落', dataIndex: 'reg_location', ellipsis: true },
            { title: '用途', dataIndex: 'land_usage', width: 76 },
            { title: '级别', dataIndex: 'land_level', width: 76 },
            {
              title: '登记/合同面积', width: 140, align: 'right' as const,
              render: (_: any, r: Parcel) => (
                <span className="num-cell">
                  {fmtNum(r.reg_area)} / {fmtNum(r.contract_area)}
                </span>
              ),
            },
            {
              title: '合同状态', dataIndex: 'contract_status', width: 100,
              render: (v: string) => (
                <Tag color={v === '有效' ? 'green' : v === '到期未续' ? 'orange' : 'default'}>{v}</Tag>
              ),
            },
            { title: '承租人', dataIndex: 'contract_lessee', width: 110, ellipsis: true },
            {
              title: '累计应缴', dataIndex: 'total_due', width: 120, align: 'right' as const,
              render: (v: string) => <span className="num-cell">{fmtNum(v)}</span>,
            },
            {
              title: '累计实缴', dataIndex: 'total_paid', width: 120, align: 'right' as const,
              render: (v: string) => <span className="num-cell">{fmtNum(v)}</span>,
            },
            {
              title: '欠缴', dataIndex: 'arrears', width: 120, align: 'right' as const,
              render: (v: string) => {
                const n = Number(v || 0);
                return (
                  <span className="num-cell" style={{ color: n > 0 ? TOKENS.error : TOKENS.success, fontWeight: 500 }}>
                    {fmtNum(v)}
                  </span>
                );
              },
            },
            {
              title: '欠缴年度', dataIndex: 'arrears_years', width: 160, ellipsis: true,
              render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '—'}</Text>,
            },
          ]}
          scroll={{ x: 1280 }}
        />
      </Card>

      <ParcelDetailDrawer
        parcelKey={detailKey}
        open={open}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}
