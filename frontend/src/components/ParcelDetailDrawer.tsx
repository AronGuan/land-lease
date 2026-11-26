import { useEffect, useState } from 'react';
import { Card, Descriptions, Drawer, Space, Spin, Table, Tag, Typography } from 'antd';
import { api } from '../api/client';
import { fmtMoney, fmtNum, TOKENS } from '../theme';

const { Text } = Typography;

/** 宗地详情抽屉（宗地台账下钻 / 欠缴看板详情 共用） */
export default function ParcelDetailDrawer({
  parcelKey, open, onClose,
}: { parcelKey: string | null; open: boolean; onClose: () => void }) {
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !parcelKey) { setDetail(null); return; }
    setLoading(true);
    api.parcelDetail(parcelKey)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [open, parcelKey]);

  return (
    <Drawer
      title={detail?.parcel?.parcel_key ? `${detail.parcel.parcel_key} · 宗地详情` : '宗地详情'}
      width={900}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {loading || !detail ? <Spin style={{ display: 'block', margin: '80px auto' }} /> : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {[
              { label: '累计应缴', value: fmtMoney(detail.parcel.total_due), color: TOKENS.textPrimary },
              { label: '累计实缴', value: fmtMoney(detail.parcel.total_paid), color: TOKENS.success },
              { label: '欠缴金额', value: fmtMoney(detail.parcel.arrears), color: Number(detail.parcel.arrears) > 0 ? TOKENS.error : TOKENS.success },
              { label: '2026 年度应缴', value: fmtMoney(detail.parcel.due_2026), color: TOKENS.colorPrimary },
            ].map((x) => (
              <div key={x.label} style={{
                flex: '1 1 160px', border: '1px solid #f0f0f0', borderRadius: 10, padding: '10px 14px',
              }}>
                <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>{x.label}</div>
                <div style={{ fontSize: 18, fontWeight: 600, color: x.color }}>{x.value}</div>
              </div>
            ))}
          </div>

          <Descriptions size="small" column={2} bordered
            items={[
              { key: '1', label: '不动产单元号', children: detail.parcel.unit_no || '—' },
              { key: '2', label: '登记坐落', children: detail.parcel.reg_location || '—' },
              { key: '3', label: '登记面积', children: `${fmtNum(detail.parcel.reg_area)} ㎡` },
              { key: '4', label: '合同面积', children: `${fmtNum(detail.parcel.contract_area)} ㎡` },
              { key: '5', label: '用途 / 级别', children: `${detail.parcel.land_usage} / ${detail.parcel.land_level}` },
              { key: '6', label: '计租方式', children: detail.parcel.rent_mode || '—' },
              { key: '7', label: '合同状态', children: detail.parcel.contract_status || '—' },
              { key: '8', label: '合同终止日', children: detail.parcel.end_date || '—' },
              { key: '9', label: '承租人', children: detail.parcel.contract_lessee || '—' },
              { key: '10', label: '登记权利人', children: detail.parcel.reg_owner || '—' },
              { key: '11', label: '催缴对象', children: detail.parcel.dunning_target || '—' },
              { key: '12', label: '联系电话', children: detail.parcel.phone || '—' },
            ]}
          />

          <Card size="small" title="合同时间轴">
            <div style={{ fontSize: 13, lineHeight: 2 }}>
              {(detail.contracts || []).map((c: any) => (
                <div key={c.id}>
                  <Tag color="blue">{c.doc_type || '合同'}</Tag>
                  <b>{c.id}</b>　{c.start_date || '—'} → {c.end_date || '—'}
                  {c.rent_mode ? `　${c.rent_mode}` : ''}
                  {c.rent_amount ? ` ${c.rent_amount} 元/年` : ''}
                </div>
              ))}
              {detail.parcel.contract_status === '到期未续' && (
                <div><Tag color="red">到期未续</Tag> 期满后按最后合同继续计收至 2026（口径第五条）</div>
              )}
            </div>
          </Card>

          <Card size="small" title="合同链">
            <Table size="small" rowKey="id" pagination={false}
              dataSource={detail.contracts}
              columns={[
                { title: '档案号', dataIndex: 'id', width: 90 },
                { title: '类型', dataIndex: 'doc_type', width: 70 },
                { title: '合同编号', dataIndex: 'contract_no', ellipsis: true },
                { title: '起租', dataIndex: 'start_date', width: 100 },
                { title: '终止', dataIndex: 'end_date', width: 100 },
                { title: '年租金', dataIndex: 'rent_amount', width: 100, align: 'right' as const,
                  render: (v: string) => fmtNum(v) },
              ]}
            />
          </Card>

          <Card size="small" title="逐年应缴 / 实缴 / 欠缴">
            <Table size="small" rowKey="year" pagination={false}
              dataSource={detail.dues}
              scroll={{ y: 260 }}
              columns={[
                { title: '年度', dataIndex: 'year', width: 80 },
                { title: '计费月数', dataIndex: 'months', width: 90, align: 'right' as const },
                { title: '应缴', dataIndex: 'due_amount', align: 'right' as const,
                  render: (v: string) => <span className="num-cell">{fmtNum(v)}</span> },
                { title: '实缴', dataIndex: 'paid_amount', align: 'right' as const,
                  render: (v: string) => <span className="num-cell">{fmtNum(v)}</span> },
                {
                  title: '欠缴', dataIndex: 'arrears', align: 'right' as const,
                  render: (v: string) => (
                    <span className="num-cell" style={{ color: Number(v) > 0 ? TOKENS.error : TOKENS.success }}>
                      {fmtNum(v)}
                    </span>
                  ),
                },
              ]}
            />
          </Card>

          {detail.reductions?.length > 0 && (
            <Card size="small" title="减免登记">
              <Table size="small" rowKey="id" pagination={false}
                dataSource={detail.reductions}
                columns={[
                  { title: '起', dataIndex: 'from_year', width: 80 },
                  { title: '止', dataIndex: 'to_year', width: 80 },
                  { title: '比例', dataIndex: 'ratio', width: 100,
                    render: (v: string) => `${(Number(v) * 100).toFixed(0)}%` },
                  { title: '批准文号', dataIndex: 'doc_no' },
                ]}
              />
            </Card>
          )}

          {detail.payments?.length > 0 && (
            <Card size="small" title={`缴费记录（${detail.payments.length}）`}>
              <Table size="small" rowKey={(r: any) => r.payment.id} pagination={false}
                dataSource={detail.payments}
                scroll={{ y: 240 }}
                columns={[
                  { title: '票据号', render: (_: any, r: any) => r.payment.ticket_no, width: 120 },
                  { title: '缴费日期', render: (_: any, r: any) => r.payment.pay_date, width: 110 },
                  { title: '金额', align: 'right' as const,
                    render: (_: any, r: any) => <span className="num-cell">{fmtNum(r.payment.amount)}</span> },
                  { title: '归集年度', render: (_: any, r: any) => r.alloc.year || '—', width: 90 },
                  { title: '重复', render: (_: any, r: any) =>
                    r.payment.is_duplicate ? <Tag color="red">重复</Tag> : '—', width: 70 },
                ]}
              />
            </Card>
          )}

          {!detail.payments?.length && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              该宗地暂无缴费归集记录，实缴按 0 计。
            </Text>
          )}
        </Space>
      )}
    </Drawer>
  );
}
