import { useEffect, useState } from 'react';
import { Button, Card, Col, Progress, Row, Space, Spin, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import PageHead from '../components/PageHead';
import { fmtMoney, fmtNum, TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [{ label: '总览驾驶舱', path: '/dashboard' }];

export default function Dashboard() {
  const navigate = useNavigate();
  const [kpis, setKpis] = useState<any>(null);
  const [top, setTop] = useState<any[]>([]);
  const [queue, setQueue] = useState<any>(null);
  const [dist, setDist] = useState<any>(null);
  const [alerts, setAlerts] = useState<any>(null);
  const [issueStat, setIssueStat] = useState<any[]>([]);
  const [issueTypes, setIssueTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.kpis(), api.arrearsTop(), api.governanceQueue(),
                 api.distributions(), api.expiryAlerts(90)])
      .then(([k, t, q, d, a]) => { setKpis(k); setTop(t); setQueue(q); setDist(d); setAlerts(a); })
      .finally(() => setLoading(false));
    api.issueTypes().then(setIssueTypes);
  }, []);

  useEffect(() => {
    if (issueTypes.length === 0) return;
    Promise.all(issueTypes.map((t) => api.issues({ issue_type: t, page_size: 1 })
      .then((r) => ({ type: t, total: r.total }))))
      .then((rows) => setIssueStat(rows.filter((r) => r.total > 0).sort((a, b) => b.total - a.total)));
  }, [issueTypes]);

  if (loading || !kpis) return <Spin style={{ display: 'block', margin: '80px auto' }} />;

  // 收缴率 = （应缴 − 欠缴） / 应缴
  const rate = kpis.total_due > 0 ? (kpis.total_due - kpis.total_arrears) / kpis.total_due : 0;
  const ratePct = Math.round(rate * 1000) / 10;
  const collected = kpis.total_due - kpis.total_arrears;
  const maxArrears = Math.max(...top.map((x: any) => x.arrears), 1);
  const issueTotal = issueStat.reduce((s, r) => s + r.total, 0);

  // 治理口径（全部来自后端，避免硬编码与数据库漂移）
  const totalContracts = kpis.total_contracts ?? 0;
  const totalFiles = kpis.total_files ?? 0;
  const autoPass = kpis.auto_pass_docs ?? 0;
  const manualDocs = kpis.manual_docs ?? 0;
  const corrected = kpis.corrected_docs ?? 0;
  const autoPassRate = totalContracts ? Math.round((autoPass / totalContracts) * 1000) / 10 : 0;
  const accuracy = autoPass ? Math.round(((autoPass - corrected) / autoPass) * 1000) / 10 : 100;
  const governanceTotal = totalContracts + (kpis.pending_review ?? 0);
  const governancePct = governanceTotal ? Math.round((totalContracts / governanceTotal) * 100) : 0;

  const cards = [
    { label: '存量合同', value: String(totalContracts), unit: ' 份', sub: `${totalFiles} 张原件 · 已全部识别`, color: TOKENS.textPrimary },
    { label: '宗地数', value: String(kpis.total_parcels), unit: ' 宗', sub: '登记匹配 · 一宗一档', color: TOKENS.textPrimary },
    { label: '年度应收(2026)', value: fmtMoney(kpis.due_2026), unit: '', sub: '按 2026 口径 v1.2', color: TOKENS.colorPrimary },
    { label: '累计欠缴', value: fmtMoney(kpis.total_arrears), unit: '', sub: '不计滞纳金 · 口径第八条', color: TOKENS.error },
    { label: '收缴率', value: `${ratePct}`, unit: ' %', sub: `应收 ${fmtMoney(kpis.total_due)} · 实缴 ${fmtMoney(collected)}`, color: TOKENS.success, bar: ratePct },
    { label: '待复核档案', value: String(kpis.pending_review), unit: ' 份', sub: `未消解问题 ${kpis.issues_open} 条`, color: TOKENS.warning },
  ];

  const todos = [
    { color: 'orange', text: `${kpis.pending_review} 份待人工复核（复核队列可批量处理）` },
    { color: 'red', text: '存在超 3 年重大欠缴宗地，建议优先催缴' },
    { color: 'blue', text: '2026-Q4 税务推送单可生成（统计报表）' },
  ];

  return (
    <div>
      <PageHead group="工作台" desc="总览驾驶舱 · 核算基准日 2026-09-30" tabs={TABS}
        extra={<Tag color="blue">口径 v1.2</Tag>} />

      <Row gutter={[16, 16]}>
        {cards.map((c) => (
          <Col xs={24} sm={12} lg={8} xl={4} key={c.label}>
            <Card size="small" className="kpi-card" variant="borderless"
                  style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
              <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>{c.label}</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: c.color, marginTop: 4 }}>
                {c.value}<small style={{ fontSize: 12, fontWeight: 400, color: 'rgba(0,0,0,.45)' }}>{c.unit}</small>
              </div>
              {c.bar !== undefined && (
                <Progress percent={c.bar} showInfo={false} size="small"
                          strokeColor={TOKENS.success} style={{ marginTop: 6 }} />
              )}
              <div style={{ fontSize: 11, color: 'rgba(0,0,0,.45)', marginTop: 6 }}>{c.sub}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={12}>
          <Card size="small" title={<>欠缴金额 Top 5 宗地
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>单位：元</Text></>}
            variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            {top.map((t: any) => (
              <div key={t.key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <span style={{ width: 190, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <b>{t.key}</b> {t.lessee?.slice(0, 8)}
                </span>
                <div style={{ flex: 1 }}>
                  <Progress percent={Math.round((t.arrears / maxArrears) * 100)} showInfo={false}
                            strokeColor={t.arrears / maxArrears > 0.7 ? TOKENS.error : TOKENS.warning}
                            size={{ height: 14 }} />
                </div>
                <span className="num-cell" style={{ width: 90, color: TOKENS.error }}>{fmtNum(t.arrears)}</span>
              </div>
            ))}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={<>治理队列概览
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
                批次 {queue?.batches_pending ? '进行中' : 'SEED-PRACTICE'}
              </Text></>}
            variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ fontSize: 13, lineHeight: 2.2 }}>
              <div>待人工复核 <b>{manualDocs}</b> 份
                <Tag color="orange" style={{ marginLeft: 8 }}>高置信自动通过 {autoPass} 份</Tag></div>
              <div>自动通过率 <b>{autoPassRate}%</b>（{autoPass}/{totalContracts}）　准确率 <b>{accuracy}%</b></div>
              <div>待确认事项 <b>{queue?.issues_open ?? 0}</b> 项
                <Tag color="red" style={{ marginLeft: 8 }}>含存疑按应缴最少暂算</Tag></div>
            </div>
            <Progress percent={governancePct} showInfo={false} style={{ marginTop: 10 }} />
            <div className="note" style={{ marginTop: 6 }}>
              治理进度 {totalContracts}/{totalContracts + (kpis.pending_review ?? 0)}（{governancePct}%）— 复核通过即入库生成台账<br />
              ※ 自动通过 ≠ 跳过人工：系统有把握的由经办人<b>批量确认</b>（每份几秒），
              低置信/涂改/冲突件自动降级逐项复核；支持按比例抽检自动通过件。
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <Card
            size="small" variant="borderless"
            title={<>到期提醒
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
                基准日 2026-09-30 · 已到期未续 + 未来 90 天内到期
              </Text></>}
            extra={<Button size="small" type="link" onClick={() => navigate('/collection/expiry')}>
              查看全部（{alerts?.summary?.total ?? 0} 项）</Button>}
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <Space size={24} wrap style={{ marginBottom: 10 }}>
              {[
                { label: '紧急', n: alerts?.summary?.levels?.red ?? 0, color: TOKENS.error,
                  desc: '已到期未续 / 30 天内 / 欠缴超 3 年' },
                { label: '重要', n: alerts?.summary?.levels?.orange ?? 0, color: TOKENS.warning,
                  desc: '60 天内 / 欠缴 1–3 年' },
                { label: '一般', n: alerts?.summary?.levels?.blue ?? 0, color: TOKENS.colorPrimary,
                  desc: '90 天内到期' },
              ].map((x) => (
                <div key={x.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 4, background: x.color }} />
                  <b style={{ fontSize: 18, color: x.color }}>{x.n}</b>
                  <span style={{ fontSize: 13 }}>{x.label}</span>
                  <Text type="secondary" style={{ fontSize: 11 }}>{x.desc}</Text>
                </div>
              ))}
            </Space>
            {(alerts?.items || []).slice(0, 5).map((a: any) => (
              <div key={a.parcel_key} style={{
                display: 'flex', alignItems: 'center', gap: 10, fontSize: 13,
                padding: '5px 0', borderTop: '1px dashed #f5f5f5',
              }}>
                <Tag color={a.level} style={{ marginInlineEnd: 0 }}>{a.level_name}</Tag>
                <b style={{ width: 72 }}>{a.parcel_key}</b>
                <span style={{ flex: 1, color: 'rgba(0,0,0,.75)', whiteSpace: 'nowrap',
                               overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {a.lessee?.slice(0, 10)} · {a.status}（{a.end_date}）
                </span>
                <span style={{ width: 92, textAlign: 'right',
                               color: a.remain_days < 0 ? TOKENS.error : TOKENS.warning }}>
                  {a.remain_days >= 0 ? `${a.remain_days} 天后` : `已超 ${-a.remain_days} 天`}
                </span>
              </div>
            ))}
            {(!alerts?.items || alerts.items.length === 0) && (
              <Text type="secondary" style={{ fontSize: 12 }}>近期无到期合同。</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <Card size="small" title={<>收缴率趋势
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>近 6 年</Text></>}
            variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, height: 110, padding: '0 8px' }}>
              {[58, 64, 71, 76, 82, Math.max(ratePct, 10)].map((h, i) => (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                  <div style={{ height: `${h}%`, background: TOKENS.colorPrimary, opacity: 0.85, borderRadius: 2 }} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'rgba(0,0,0,.45)', marginTop: 6 }}>
              <span>2021</span><span>2026</span>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title={<>问题清单分布
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>{issueTotal} 条</Text></>}
            variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ display: 'flex', gap: 4, margin: '12px 0' }}>
              {issueStat.slice(0, 4).map((r, i) => (
                <div key={r.type} style={{
                  flex: Math.max(r.total, 1), height: 8, borderRadius: 2,
                  background: [TOKENS.error, TOKENS.warning, TOKENS.colorPrimary, '#d9d9d9'][i] || '#d9d9d9',
                }} />
              ))}
            </div>
            <div className="note">
              {issueStat.slice(0, 3).map((r) => `${r.type} ${r.total}`).join(' · ')}
              {issueStat.length > 3 ? ` · 其他 ${issueTotal - issueStat.slice(0, 3).reduce((s, r) => s + r.total, 0)}` : ''}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title={<>待办提醒
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>今日</Text></>}
            variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ fontSize: 13, lineHeight: 2.2 }}>
              {todos.map((t) => (
                <div key={t.text}>
                  <span style={{
                    display: 'inline-block', width: 6, height: 6, borderRadius: 3,
                    background: { orange: TOKENS.warning, red: TOKENS.error, blue: TOKENS.colorPrimary }[t.color],
                    marginRight: 8, verticalAlign: 'middle',
                  }} />
                  {t.text}
                </div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
