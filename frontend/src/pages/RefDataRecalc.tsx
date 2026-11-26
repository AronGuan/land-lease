import { useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Empty, Row, Space, Table, Tag, Typography,
} from 'antd';
import { MergeCellsOutlined, RedoOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import PageHead from '../components/PageHead';

const { Text } = Typography;

const TABS = [
  { label: '数据导入', path: '/data/import' },
  { label: '重算与差异', path: '/data/recalc' },
];

export default function RefDataRecalc() {
  const { message, modal } = App.useApp();
  const [result, setResult] = useState<any>(null);
  const [dups, setDups] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const loadDups = () => api.refdataDuplicates().then(setDups);
  useEffect(() => { loadDups(); }, []);

  const relink = async () => {
    setBusy(true);
    try {
      const r = await api.refdataRelink('张贯贯');
      setResult(r);
      await loadDups();
      message.success(
        `重算完成：${r.parcel_count} 宗，${r.changed_count} 宗金额有变化；`
        + `缴费归集 ${r.payment_matched}/${r.payment_matched + r.payment_missed}`,
      );
    } catch (e: any) {
      message.error(`重算失败：${e?.response?.data?.detail || e.message || e}`);
    } finally {
      setBusy(false);
    }
  };

  const merge = () => {
    if (!dups?.group_count) return;
    modal.confirm({
      title: `合并 ${dups.group_count} 组重复宗地？`,
      width: 600,
      content: (
        <div style={{ marginTop: 12, fontSize: 13 }}>
          同一宗地在不同合同里可能写旧地号，也可能写完整不动产单元号，
          识别阶段未能归并时会被拆成多个宗地键。合并后保留档案号最小者，
          合同、缴费、减免、问题清单一并迁移，然后重算。
          <div style={{ marginTop: 8 }}>
            {dups.groups.map((g: any) => (
              <div key={g.keep}>
                · 保留 <b>{g.keep}</b> ← 并入 {g.merge.join('、')}（合同 {g.contracts.join('、')}）
              </div>
            ))}
          </div>
        </div>
      ),
      okText: '合并并重算', cancelText: '取消',
      onOk: async () => {
        setBusy(true);
        try {
          const r = await api.refdataMerge('张贯贯');
          setResult(r);
          await loadDups();
          message.success(`已合并 ${r.merged} 宗，现有 ${r.parcel_count} 宗`);
        } catch (e: any) {
          message.error(`合并失败：${e?.response?.data?.detail || e.message || e}`);
        } finally {
          setBusy(false);
        }
      },
    });
  };

  return (
    <div>
      <PageHead group="基础数据" desc="重新归集 · 全量重算 · 差异留痕" tabs={TABS} />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card
            size="small" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}
            title="重算应缴与欠缴"
            extra={
              <Space>
                <Button size="small" icon={<RedoOutlined />} loading={busy} onClick={relink}>
                  重新归集并重算
                </Button>
                <Button
                  size="small" icon={<MergeCellsOutlined />} loading={busy}
                  disabled={!dups?.group_count} onClick={merge}
                >
                  合并重复宗地{dups?.group_count ? `（${dups.group_count}）` : ''}
                </Button>
              </Space>
            }
          >
            {dups?.group_count > 0 && (
              <Alert
                type="warning" showIcon style={{ marginBottom: 12 }}
                message={`检测到 ${dups.group_count} 组宗地指向同一不动产单元号`}
                description={dups.groups.map((g: any) => (
                  <div key={g.keep} style={{ fontSize: 12 }}>
                    {g.parcel_keys.join('、')} → 建议保留 <b>{g.keep}</b>
                  </div>
                ))}
              />
            )}
            {!result ? (
              <Empty
                description="点「重新归集并重算」：重新匹配登记、归集缴费与减免，然后全量重算，下面会列出金额变化的宗地"
                style={{ margin: '40px 0' }}
              />
            ) : (
              <div>
                <Space size={16} wrap style={{ marginBottom: 12 }}>
                  <Text>宗地 <b>{result.parcel_count}</b></Text>
                  <Text>应缴 <b>{result.total_due?.toLocaleString()}</b></Text>
                  <Text>实缴 <b>{result.total_paid?.toLocaleString()}</b></Text>
                  <Text>欠缴 <b>{result.total_arrears?.toLocaleString()}</b></Text>
                  <Tag color={result.changed_count ? 'orange' : 'green'}>
                    {result.changed_count} 宗金额有变化
                  </Tag>
                  {result.payment_missed > 0 && (
                    <Tag color="gold">缴费未匹配 {result.payment_missed} 条</Tag>
                  )}
                </Space>
                <Table
                  size="small" rowKey="parcel_key" pagination={{ pageSize: 10 }}
                  dataSource={result.diff || []}
                  columns={[
                    { title: '宗地', dataIndex: 'parcel_key', width: 90 },
                    { title: '应缴（前→后）', width: 170, align: 'right' as const,
                      render: (_: any, r: any) => `${r.due_before} → ${r.due_after}` },
                    { title: '应缴差额', dataIndex: 'delta_due', width: 100, align: 'right' as const,
                      render: (v: number) => (
                        <Text type={v > 0 ? 'danger' : v < 0 ? 'success' : undefined}>
                          {v > 0 ? '+' : ''}{v}
                        </Text>
                      ) },
                    { title: '欠缴（前→后）', width: 170, align: 'right' as const,
                      render: (_: any, r: any) => `${r.arrears_before} → ${r.arrears_after}` },
                    { title: '欠缴差额', dataIndex: 'delta_arrears', width: 100, align: 'right' as const,
                      render: (v: number) => (
                        <Text type={v > 0 ? 'danger' : v < 0 ? 'success' : undefined}>
                          {v > 0 ? '+' : ''}{v}
                        </Text>
                      ) },
                  ]}
                />
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card size="small" title="重算做了什么" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <ol style={{ fontSize: 12, lineHeight: 2, paddingLeft: 18, margin: 0 }}>
              <li>按合同宗地号 ↔ 不动产单元号段位重新匹配登记</li>
              <li>缴费记录归集到宗地（票据去重 · 注明年度归该年 · 未注明冲抵最早欠缴年）</li>
              <li>减免记录归集到宗地（口径六：先算应缴再乘 1−减免比例）</li>
              <li>逐宗重算逐年应缴 / 实缴 / 欠缴</li>
              <li>全过程写入审计日志（refdata_relink / parcel_merge）</li>
            </ol>
            <div className="note" style={{ marginTop: 10 }}>
              重算不改变合同本身，只改核算结果；差异清单可当场向评委说明。
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
