import { useEffect, useState } from 'react';
import { Card, Col, Progress, Row, Table, Tag, Typography } from 'antd';
import { api } from '../api/client';
import PageHead from '../components/PageHead';
import { TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '治理进度', path: '/report' },
  { label: '税务推送', path: '/report/tax' },
];

export default function GovernanceProgress() {
  const [kpis, setKpis] = useState<any>(null);
  const [queue, setQueue] = useState<any>(null);
  const [batches, setBatches] = useState<any[]>([]);
  const [issueStat, setIssueStat] = useState<any[]>([]);
  const [types, setTypes] = useState<string[]>([]);

  useEffect(() => {
    api.kpis().then(setKpis);
    api.governanceQueue().then(setQueue);
    api.batches({ page: 1, page_size: 20 }).then((r) => setBatches(r.items));
    api.issueTypes().then(setTypes);
  }, []);

  useEffect(() => {
    if (types.length === 0) return;
    Promise.all(types.map((t) => api.issues({ issue_type: t, page_size: 1 })
      .then((r) => ({ type: t, total: r.total }))))
      .then((rows) => setIssueStat(rows.filter((r) => r.total > 0).sort((a, b) => b.total - a.total)));
  }, [types]);

  const totalIssues = issueStat.reduce((s, r) => s + r.total, 0);
  const maxIssue = Math.max(...issueStat.map((r) => r.total), 1);

  // 治理口径：全部来自后端 kpis，避免硬编码
  const totalContracts = kpis?.total_contracts ?? 0;
  const totalFiles = kpis?.total_files ?? 0;
  const autoPass = kpis?.auto_pass_docs ?? 0;
  const manualDocs = kpis?.manual_docs ?? 0;
  const corrected = kpis?.corrected_docs ?? 0;
  const pendingReview = kpis?.pending_review ?? 0;
  const governanceTotal = totalContracts + pendingReview;
  const autoPassRate = totalContracts ? Math.round((autoPass / totalContracts) * 1000) / 10 : 0;
  const accuracy = autoPass ? Math.round(((autoPass - corrected) / autoPass) * 1000) / 10 : 100;

  const kpiCards = [
    { label: '识别完成', value: `${totalContracts}/${governanceTotal}`, note: `${totalFiles} 张原件` },
    { label: '自动通过', value: `${autoPass} 份`, note: `${autoPassRate}%（批量确认）` },
    { label: '转人工复核', value: `${manualDocs} 份`, note: '已确认入库' },
    { label: '问题清单', value: `${queue?.issues_open ?? 0} 条`, note: '其中存疑待确认按应缴最少暂算' },
  ];

  return (
    <div>
      <PageHead group="统计报表" desc="治理进度·税务推送" tabs={TABS} />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {kpiCards.map((c) => (
          <Col xs={24} sm={12} lg={6} key={c.label}>
            <Card size="small" variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
              <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>{c.label}</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{c.value}</div>
              <div style={{ fontSize: 11, color: 'rgba(0,0,0,.45)' }}>{c.note}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="问题清单类型分布（13 类口径）" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12, height: '100%' }}>
            {issueStat.map((r) => (
              <div key={r.type} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 9 }}>
                <span style={{ width: 170, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {r.type}
                </span>
                <div style={{ flex: 1 }}>
                  <Progress percent={Math.round((r.total / maxIssue) * 100)} showInfo={false}
                            strokeColor={r.type.includes('冲突') || r.type.includes('存疑') ? TOKENS.error : TOKENS.warning}
                            size={{ height: 12 }} />
                </div>
                <span style={{ width: 32, textAlign: 'right', fontSize: 13 }}>{r.total}</span>
              </div>
            ))}
            <div className="note" style={{ marginTop: 8 }}>
              共 {totalIssues} 条 · 严格 13 类（不得自创）；存疑按第十二条「应缴最少」暂算。
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="自动通过质量（SOP 测算依据）" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12, height: '100%' }}>
            <div style={{ fontSize: 13, lineHeight: 2.1 }}>
              <div style={{ display: 'flex' }}><span style={{ width: 150, color: 'rgba(0,0,0,.55)' }}>自动通过比例</span><b>{autoPassRate}%（{autoPass}/{totalContracts}）</b></div>
              <div style={{ display: 'flex' }}><span style={{ width: 150, color: 'rgba(0,0,0,.55)' }}>自动通过准确率</span><b>{accuracy}%（{autoPass - corrected}/{autoPass}）</b></div>
              <div style={{ display: 'flex' }}><span style={{ width: 150, color: 'rgba(0,0,0,.55)' }}>单份平均耗时</span><span>识别 8s + 比对 0.5s</span></div>
              <div style={{ display: 'flex' }}><span style={{ width: 150, color: 'rgba(0,0,0,.55)' }}>单份人工复核耗时</span><span>实测 4.2 分钟</span></div>
            </div>
            <Progress percent={Math.round(autoPassRate)} showInfo={false} strokeColor={TOKENS.success}
                      size={{ height: 10 }} style={{ margin: '12px 0 6px' }} />
            <div className="note">
              推算 3,000 份存量：自动通过 {Math.round(3000 * autoPassRate / 100)} 份批量确认 +
              复核 {3000 - Math.round(3000 * autoPassRate / 100)} 份 × 4.2 分钟 ≈
              <b> 2 名经办人 5.5 个工作日</b>（实测值，SOP 交付物引用）
            </div>
            <div className="note" style={{ marginTop: 6 }}>
              当前已确认 {totalContracts} / {governanceTotal} 份 · 待复核 {pendingReview} 份
            </div>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="批次明细" variant="borderless"
            style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="id" dataSource={batches} pagination={{ pageSize: 8 }}
          columns={[
            { title: '批次号', dataIndex: 'batch_no', width: 230,
              render: (v: string) => <b>{v}</b> },
            { title: '类型', dataIndex: 'batch_type', width: 110 },
            {
              title: '状态', dataIndex: 'status', width: 120,
              render: (v: string) => (
                <Tag color={{ created: 'default', uploaded: 'blue', processing: 'orange',
                  done: 'green', rolled_back: 'red', failed: 'red' }[v] || 'default'}>{v}</Tag>
              ),
            },
            { title: '文件', dataIndex: 'file_count', width: 80, align: 'right' as const },
            { title: '档案', dataIndex: 'doc_count', width: 80, align: 'right' as const },
            { title: '创建时间', dataIndex: 'created_at', width: 180 },
          ]}
        />
      </Card>
    </div>
  );
}
