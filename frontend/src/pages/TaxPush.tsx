import { useEffect, useState } from 'react';
import { App, Button, Card, InputNumber, Space, Table, Tag, Typography } from 'antd';
import { CloudUploadOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import PageHead from '../components/PageHead';
import { fmtMoney, fmtNum } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '治理进度', path: '/report' },
  { label: '税务推送', path: '/report/tax' },
];

export default function TaxPush() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<any[]>([]);
  const [items, setItems] = useState<any[]>([]);
  const [year, setYear] = useState(2026);
  const [loading, setLoading] = useState(false);

  const load = () => api.taxPushes().then(setRows);
  useEffect(() => { load(); }, []);

  const push = async () => {
    setLoading(true);
    try {
      const r = await api.pushTax(year);
      message.success(`已生成推送单 #${r.push_id}，覆盖 ${r.row_count} 宗地`);
      load();
    } finally {
      setLoading(false);
    }
  };

  const showItems = (id: number) => api.pushItems(id).then(setItems);

  return (
    <div>
      <PageHead group="统计报表" desc="治理进度·税务推送" tabs={TABS} />

      <Card
        size="small"
        title="税务推送单 · 生成记录"
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}
        extra={
          <Space>
            <span style={{ fontSize: 13, color: 'rgba(0,0,0,.65)' }}>年度</span>
            <InputNumber size="small" value={year} onChange={(v) => setYear(v || 2026)} min={2000} max={2100}
                         style={{ width: 90 }} />
            <Button size="small" type="primary" icon={<CloudUploadOutlined />} loading={loading} onClick={push}>
              生成本期推送单
            </Button>
          </Space>
        }
      >
        <Table
          size="small" rowKey="id" dataSource={rows}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: '期次', dataIndex: 'period', width: 110 },
            { title: '生成时间', dataIndex: 'created_at', width: 175 },
            { title: '覆盖年度', dataIndex: 'year', width: 95 },
            { title: '宗地数', dataIndex: 'row_count', width: 90, align: 'right' as const },
            {
              title: '推送金额合计(元)', dataIndex: 'total_amount', width: 150, align: 'right' as const,
              render: (v: string) => <span className="num-cell">{fmtMoney(v)}</span>,
            },
            { title: '操作人', dataIndex: 'operator', width: 110 },
            {
              title: '状态', width: 100,
              render: () => <Tag color="green">已留存</Tag>,
            },
            {
              title: '操作', width: 130,
              render: (_: any, r: any) => (
                <Space>
                  <Button size="small" type="link" onClick={() => showItems(r.id)}>查看</Button>
                  <Button size="small" type="link"
                          onClick={() => message.info('导出 xlsx 为后续开发项')}>导出 xlsx</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" title="推送单字段（按税务部门模板）" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        {items.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 13 }}>
            点上方「查看」载入推送单明细。字段：宗地编号 / 不动产单元号 / 承租人 / 证件号码 / 年度 / 应缴 / 实缴 / 欠缴。
          </Text>
        ) : (
          <Table
            size="small" rowKey="id" dataSource={items} pagination={{ pageSize: 10 }}
            columns={[
              { title: '宗地编号', dataIndex: 'parcel_key', width: 100,
                render: (v: string) => <b>{v}</b> },
              { title: '不动产单元号', dataIndex: 'unit_no', ellipsis: true },
              { title: '承租人', dataIndex: 'lessee', width: 150, ellipsis: true },
              { title: '年度', dataIndex: 'year', width: 80 },
              { title: '应缴(元)', dataIndex: 'due_amount', width: 110, align: 'right' as const,
                render: (v: string) => <span className="num-cell">{fmtNum(v)}</span> },
              { title: '实缴(元)', dataIndex: 'paid_amount', width: 110, align: 'right' as const,
                render: (v: string) => <span className="num-cell">{fmtNum(v)}</span> },
              { title: '欠缴(元)', dataIndex: 'arrears', width: 110, align: 'right' as const,
                render: (v: string) => Number(v) > 0
                  ? <span className="num-cell" style={{ color: '#cf1322', fontWeight: 600 }}>{fmtNum(v)}</span>
                  : <span className="num-cell">0.00</span> },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
