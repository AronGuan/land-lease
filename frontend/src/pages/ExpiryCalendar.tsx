import { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Table, Tag, Typography } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import PageHead from '../components/PageHead';
import { fmtNum, TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '欠缴看板', path: '/collection' },
  { label: '到期日历', path: '/collection/expiry' },
  { label: '催缴跟踪', path: '/collection/dunning' },
];

/** 核算基准日（与系统顶栏一致） */
const TODAY = new Date('2026-09-30');

/** 90 天内的紧急度：红 30 / 橙 60 / 蓝 90 */
const levelOf = (days: number): 'red' | 'orange' | 'blue' =>
  days <= 30 ? 'red' : days <= 60 ? 'orange' : 'blue';

const LV_COLOR: Record<string, string> = { red: '#cf1322', orange: '#d46b08', blue: '#1677ff' };

/** 月：{ y: 年, m: 月 0-11 } */
type Month = { y: number; m: number };
const keyOf = (v: Month) => `${v.y}-${String(v.m + 1).padStart(2, '0')}`;
const monthOf = (date: string) => date.slice(0, 7);

export default function ExpiryCalendar() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  /** null = 尚未定位；加载完成后自动定位到最近有事件的月份 */
  const [cur, setCur] = useState<Month | null>(null);
  const [alerts, setAlerts] = useState<any>(null);

  useEffect(() => {
    api.expiryCalendar().then((r) => {
      setRows(r);
      setCur(pickMonth(r));
    }).finally(() => setLoading(false));
    api.expiryAlerts(90).then(setAlerts);
  }, []);

  const view: Month = cur ?? { y: TODAY.getFullYear(), m: TODAY.getMonth() };

  const shift = (delta: number) =>
    setCur((v) => {
      const base = v ?? { y: TODAY.getFullYear(), m: TODAY.getMonth() };
      const d = new Date(base.y, base.m + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() };
    });

  /** 当前月 → 日 → 事件 */
  const byDay = useMemo(() => {
    const m: Record<number, any[]> = {};
    rows.forEach((r) => {
      if (!r.end_date) return;
      const d = new Date(r.end_date);
      if (d.getFullYear() === view.y && d.getMonth() === view.m) {
        (m[d.getDate()] ||= []).push(r);
      }
    });
    return m;
  }, [rows, view]);

  const hasEvent = Object.keys(byDay).length > 0;

  /** 本月日历格（周一开头） */
  const cells = useMemo(() => {
    const lead = (new Date(view.y, view.m, 1).getDay() + 6) % 7; // 周一=0
    const days = new Date(view.y, view.m + 1, 0).getDate();
    const arr: (number | null)[] = [
      ...Array(lead).fill(null),
      ...Array.from({ length: days }, (_, i) => i + 1),
    ];
    while (arr.length % 7 !== 0) arr.push(null);
    return arr;
  }, [view]);

  const isToday = (d: number) =>
    view.y === TODAY.getFullYear() && view.m === TODAY.getMonth() && d === TODAY.getDate();

  /** 待办：以基准日为界，最近到期优先（含已过期未续，避免演示数据为空） */
  const levelItems = rows
    .filter((r) => r.end_date)
    .map((r) => ({
      ...r,
      days: Math.round((new Date(r.end_date).getTime() - TODAY.getTime()) / 86400000),
    }))
    .sort((a, b) => Math.abs(a.days) - Math.abs(b.days))
    .slice(0, 8);

  return (
    <div>
      <PageHead group="收缴管理" desc="欠缴看板·到期日历·催缴跟踪" tabs={TABS} />

      <Card
        size="small"
        title={`${view.y} 年 ${view.m + 1} 月 · 合同到期 / 缴费期限日历`}
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}
        extra={
          <Space size={16} wrap>
            <Text type="secondary" style={{ fontSize: 12 }}>
              <span style={{ color: '#cf1322' }}>●</span> 30 天内　
              <span style={{ color: '#d46b08' }}>●</span> 60 天内　
              <span style={{ color: '#1677ff' }}>●</span> 90 天内
            </Text>
            <Space size={4}>
              <Button size="small" icon={<LeftOutlined />} onClick={() => shift(-1)}>
                上一月
              </Button>
              <Button
                size="small"
                onClick={() => setCur({ y: TODAY.getFullYear(), m: TODAY.getMonth() })}
              >
                回到基准月
              </Button>
              <Button size="small" onClick={() => shift(1)}>
                下一月 <RightOutlined />
              </Button>
            </Space>
          </Space>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 4 }}>
          {['一', '二', '三', '四', '五', '六', '日'].map((d) => (
            <div
              key={d}
              style={{ textAlign: 'center', fontSize: 12, color: 'rgba(0,0,0,.45)', padding: 4 }}
            >
              {d}
            </div>
          ))}
          {cells.map((d, i) => {
            const evs = d ? byDay[d] || [] : [];
            return (
              <div
                key={i}
                style={{
                  minHeight: 74, border: '1px solid #f0f0f0', borderRadius: 4, padding: 4,
                  background: isToday(d as number) ? '#e6f4ff' : d ? '#fff' : '#fafafa',
                }}
              >
                {d && <div style={{ fontSize: 12, color: 'rgba(0,0,0,.65)' }}>{d}</div>}
                {d && isToday(d) && (
                  <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>今天</Tag>
                )}
                {evs.map((e: any) => {
                  const days = Math.round(
                    (new Date(e.end_date).getTime() - TODAY.getTime()) / 86400000,
                  );
                  const lv = levelOf(Math.abs(days));
                  return (
                    <div key={e.archive_no} style={{ fontSize: 10, marginTop: 2 }} title={e.end_date}>
                      <span style={{ color: LV_COLOR[lv] }}>●</span>
                      {e.archive_no}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {!loading && !hasEvent && (
          <div
            style={{
              marginTop: 12, padding: '10px 12px', background: '#fafafa',
              border: '1px dashed #e5e5e5', borderRadius: 6,
              fontSize: 12, color: 'rgba(0,0,0,.55)',
            }}
          >
            本月（{keyOf(view)}）无合同到期 / 缴费期限事件 —— 可点「上一月 / 下一月」查看其他月份，或直接看下方的「近期待办」。
          </div>
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card size="small" title="分级提醒规则" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <div style={{ fontSize: 13, lineHeight: 2.2 }}>
              <div><span style={{ color: '#cf1322' }}>●</span> <b>红色（紧急）</b>：30 天内到期 / 欠缴超 3 年 — 系统弹窗 + 每日汇总</div>
              <div><span style={{ color: '#d46b08' }}>●</span> <b>橙色（重要）</b>：60 天内到期 / 欠缴 1–3 年 — 列表置顶</div>
              <div><span style={{ color: '#1677ff' }}>●</span> <b>蓝色（一般）</b>：90 天内到期 / 常规缴费期限 — 日历标记</div>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            size="small" variant="borderless"
            title={<>近期待办（到期 / 缴费期限）
              {alerts && <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
                已到期未续 {alerts.summary.overdue} · 30 天内 {alerts.summary.within_30}
                　60 天内 {alerts.summary.within_60} · 90 天内 {alerts.summary.within_90}
                （共 {alerts.summary.total} 项）
              </Text>}</>}
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <Table
              size="small" rowKey={(r: any) => r.parcel_key} loading={loading}
              dataSource={alerts?.items || []} pagination={{ pageSize: 10, size: 'small' }}
              columns={[
                { title: '事项', render: (_: any, r: any) =>
                  `${r.parcel_key} ${r.status}（${r.end_date}）`
                  + (r.status === '已到期未续' ? '，按最后合同计收至 2026' : '，需评估续期') },
                { title: '状态', dataIndex: 'status', width: 100,
                  render: (v: string) => <Tag color={v === '已到期未续' ? 'red' : 'blue'}>{v}</Tag> },
                { title: '剩余', dataIndex: 'remain_days', width: 90, align: 'right' as const,
                  render: (v: number) => v >= 0 ? `${v} 天` : <Text type="danger">超 {Math.abs(v)} 天</Text> },
                { title: '级别', dataIndex: 'level', width: 80,
                  render: (v: string, r: any) => <Tag color={v}>{r.level_name}</Tag> },
                { title: '欠缴', dataIndex: 'arrears', width: 100, align: 'right' as const,
                  render: (v: number) => <span className="num-cell" style={{ color: v > 0 ? TOKENS.error : undefined }}>
                    {v > 0 ? fmtNum(v) : '—'}</span> },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}

/** 初始定位：优先基准月及之后第一个有事件的月份；否则取最近的过去月份 */
function pickMonth(rows: any[]): Month {
  const months = Array.from(
    new Set(rows.filter((r) => r.end_date).map((r) => monthOf(r.end_date))),
  ).sort();
  if (!months.length) return { y: TODAY.getFullYear(), m: TODAY.getMonth() };
  const curKey = `${TODAY.getFullYear()}-${String(TODAY.getMonth() + 1).padStart(2, '0')}`;
  const pick = months.find((k) => k >= curKey) ?? months[months.length - 1];
  const [y, m] = pick.split('-').map(Number);
  return { y, m: m - 1 };
}
