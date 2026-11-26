import { useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Descriptions, Empty, InputNumber, Row, Select,
  Space, Spin, Table, Tag, Typography,
} from 'antd';
import { FileAddOutlined, PrinterOutlined } from '@ant-design/icons';
import { api, Parcel } from '../api/client';
import PageHead from '../components/PageHead';

const { Text } = Typography;

const TABS = [
  { label: '宗地台账', path: '/ledger' },
  { label: '合同生成', path: '/ledger/contract-gen' },
];

export default function ContractGen() {
  const { message } = App.useApp();
  const [parcels, setParcels] = useState<Parcel[]>([]);
  const [key, setKey] = useState<string>();
  const [years, setYears] = useState(10);
  const [draft, setDraft] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.parcels({ page: 1, page_size: 200 }).then((r) => setParcels(r.items));
  }, []);

  const gen = async () => {
    if (!key) { message.warning('请先选择宗地'); return; }
    setLoading(true);
    try {
      const d = await api.contractDraft(key, years);
      setDraft(d);
      message.success('合同草稿已生成');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHead group="宗地台账" desc="宗地台账·合同生成" tabs={TABS} />

      <Card size="small" title="选择宗地并生成续签合同草稿" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}>
        <Space wrap>
          <Select
            showSearch
            placeholder="选择宗地（可搜索宗地键）"
            style={{ width: 320 }}
            value={key}
            onChange={setKey}
            optionFilterProp="label"
            options={parcels.map((p) => ({
              label: `${p.parcel_key} · ${p.reg_location || ''} · ${p.contract_lessee || ''}`,
              value: p.parcel_key,
            }))}
          />
          <Space size={4}>
            <Text type="secondary" style={{ fontSize: 13 }}>续期年限</Text>
            <InputNumber min={1} max={50} value={years} onChange={(v) => setYears(v || 10)}
                         style={{ width: 90 }} />
          </Space>
          <Button type="primary" icon={<FileAddOutlined />} loading={loading} onClick={gen}>
            生成草稿
          </Button>
        </Space>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            续期起租日 = 原合同期满次日；终止日 = 起租日 + 年限 − 1 天（与核算口径一致）
          </Text>
        </div>
      </Card>

      {!draft ? (
        <Card variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
          <Empty description="选择宗地后生成合同草稿" style={{ margin: '50px 0' }} />
        </Card>
      ) : (
        <Spin spinning={loading}>
          <Card
            size="small"
            title={`${draft.parcel_key} · 续签合同草稿`}
            variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}
            extra={
              <Space>
                <Button icon={<PrinterOutlined />}
                        onClick={() => message.info('打印/导出 PDF 为后续开发项')}>
                  打印草稿
                </Button>
                <Button type="primary"
                        onClick={() => message.success('草稿已存入待签约队列（演示）')}>
                  确认生成
                </Button>
              </Space>
            }
          >
            {draft.warnings?.length > 0 && (
              <Alert
                type="warning" showIcon style={{ marginBottom: 12 }}
                message="签约前需核实"
                description={
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                    {draft.warnings.map((w: string) => <li key={w}>{w}</li>)}
                  </ul>
                }
              />
            )}
            <Descriptions size="small" column={2} bordered
              items={[
                { key: '1', label: '合同类型', children: draft.doc_type },
                { key: '2', label: '原合同编号', children: draft.orig_contract_no || '—' },
                { key: '3', label: '出租人', children: draft.lessor || '—' },
                { key: '4', label: '承租人', children: draft.lessee || '—' },
                { key: '5', label: '证件号码', children: draft.id_no || '—' },
                { key: '6', label: '联系电话', children: draft.phone || '—' },
                { key: '7', label: '坐落', children: draft.location || '—' },
                { key: '8', label: '宗地号', children: draft.parcel_no || '—' },
                { key: '9', label: '土地面积', children: draft.area ? `${draft.area} ㎡` : '—' },
                { key: '10', label: '用途 / 级别', children: `${draft.land_usage || '—'} / ${draft.land_level || '—'}` },
                { key: '11', label: '计租方式', children: draft.rent_mode || '—' },
                { key: '12', label: '现行标准', children: draft.rate ? `${draft.rate} 元/㎡·年` : '—' },
                { key: '13', label: '起租日', children: draft.start_date },
                { key: '14', label: '终止日', children: draft.end_date },
                { key: '15', label: '租赁年限', children: `${draft.years} 年` },
                {
                  key: '16', label: '建议年租金',
                  children: draft.suggest_rent
                    ? <Text strong style={{ color: '#1677ff' }}>¥{Number(draft.suggest_rent).toFixed(2)}</Text>
                    : '—',
                },
              ]}
            />
            <div style={{ marginTop: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                生成规则：面积 × 起租年度有效标准（随标准调整型）；固定型由经办人填列。
                草稿仅供签约参考，正式合同须经法务审核与用印。
              </Text>
            </div>
          </Card>
        </Spin>
      )}

      <Card size="small" title="生成与变更记录" variant="borderless"
            style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="no" pagination={false}
          dataSource={[
            { no: 1, time: '2012-10-25 11:02', type: '续期', parcel: 'LX-001R',
              doc: '×国土租字（2012）续字第019号', operator: '系统（历史归档）', status: '已归档' },
            { no: 2, time: '2026-10-22 16:40', type: '变更', parcel: 'LX-018C',
              doc: '×国土租变字（2026）第018号', operator: '演示', status: '已归档' },
          ]}
          columns={[
            { title: '时间', dataIndex: 'time', width: 160 },
            { title: '类型', dataIndex: 'type', width: 90,
              render: (v: string) => <Tag color={v === '续期' ? 'blue' : 'orange'}>{v}</Tag> },
            { title: '宗地', dataIndex: 'parcel', width: 110 },
            { title: '文书号', dataIndex: 'doc' },
            { title: '操作人', dataIndex: 'operator', width: 150 },
            { title: '状态', dataIndex: 'status', width: 90,
              render: (v: string) => <Tag color="green">{v}</Tag> },
            { title: '操作', width: 70, render: () => <Button size="small" type="link">查看</Button> },
          ]}
        />
        <div className="note" style={{ marginTop: 8 }}>
          生成后进入经办确认 → 双轨归档（电子留存 + 纸质并行），合同状态变更写台账与审计日志。
        </div>
      </Card>
    </div>
  );
}
