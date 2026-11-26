import { useEffect, useState } from 'react';
import {
  App, Button, Card, Drawer, Empty, Form, Input, InputNumber, Modal, Space,
  Table, Tag, Timeline, Typography, Alert,
} from 'antd';
import { DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { api, Parcel } from '../api/client';
import PageHead from '../components/PageHead';
import { fmtMoney, fmtNum, TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '欠缴看板', path: '/collection' },
  { label: '到期日历', path: '/collection/expiry' },
  { label: '催缴跟踪', path: '/collection/dunning' },
];

export default function Dunning() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<any>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [parcelMap, setParcelMap] = useState<Map<string, Parcel>>(new Map());

  // 催缴记录抽屉
  const [trackOpen, setTrackOpen] = useState(false);
  const [track, setTrack] = useState<any>(null);
  const [trackLoading, setTrackLoading] = useState(false);
  const [form] = Form.useForm();

  const load = () => {
    setLoading(true);
    Promise.all([api.notices({ page: 1, page_size: 50 }), api.parcels({ page: 1, page_size: 200 })])
      .then(([n, p]) => {
        setRows(n.items);
        const pm = new Map<string, Parcel>(p.items.map((x: Parcel) => [x.parcel_key, x]));
        setParcelMap(pm);
        // 预览改为弹窗按需打开，不在页面加载时自动弹出
        setPreview((s: any) => (s ? { notice: n.items.find((x: any) => x.id === s.notice.id) || s.notice,
                                      parcel: pm.get(s.notice.parcel_key) } : null));
      })
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  /** 批量生成：幂等（已有未回款通知书的复用），生成后直接下载 PDF / zip */
  const batchGen = () => {
    if (selected.length === 0) { message.warning('请先勾选需要生成通知书的宗地'); return; }
    const keys = Array.from(new Set(selected.map(
      (id) => rows.find((r) => r.id === id)?.parcel_key).filter(Boolean))) as string[];
    Modal.confirm({
      title: `为 ${keys.length} 个宗地生成催缴通知书？`,
      content: `宗地：${keys.join('、')}。已存在未回款通知书的宗地会复用原通知书并刷新欠缴金额，`
             + `生成后自动下载 PDF（多份打包 zip）。`,
      okText: '生成并下载', cancelText: '取消',
      onOk: async () => {
        const r = await api.genNotices(keys);
        const parts = [];
        if (r.created_count) parts.push(`新建 ${r.created_count} 份`);
        if (r.reused_count) parts.push(`复用 ${r.reused_count} 份`);
        if (r.skipped?.length) parts.push(`无欠缴跳过 ${r.skipped.length} 宗`);
        message.success(`已生成 ${r.notice_ids.length} 份通知书：${parts.join('，')}`);
        setSelected([]);
        load();
        if (r.notice_ids.length) {
          window.open(`/api/dunning/notices/pdf-batch?ids=${r.notice_ids.join(',')}`, '_blank');
        }
      },
    });
  };

  const openTracks = async (noticeId: number) => {
    setTrackOpen(true);
    setTrackLoading(true);
    try {
      setTrack(await api.noticeTracks(noticeId));
    } finally {
      setTrackLoading(false);
    }
  };

  const submitTrack = async () => {
    const v = await form.validateFields();
    await api.addNoticeTrack(track.notice.id, v);
    message.success('已登记回款（仅留痕，入账以缴费归集为准）');
    form.resetFields();
    setTrack(await api.noticeTracks(track.notice.id));
    load();
  };

  return (
    <div>
      <PageHead group="收缴管理" desc="欠缴看板·到期日历·催缴跟踪" tabs={TABS} />

      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="短信通道为演示占位：点击后仅记录「模拟发送」事件并写入催缴台账，不真实下发。正式环境接入政务短信网关。"
      />

      <Card
        size="small"
        title={<>催缴对象 · 通知书与短信
          {selected.length > 0 && <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
            已选 {selected.length} 条</Text>}</>}
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}
        extra={
          <Space>
            <Button size="small" icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            <Button size="small" type="primary" icon={<PlusOutlined />}
                    disabled={selected.length === 0} onClick={batchGen}>
              批量生成通知书{selected.length ? `（${selected.length}）` : ''}
            </Button>
          </Space>
        }
      >
        {rows.length === 0 && !loading ? (
          <Empty description="暂无催缴记录，可在「欠缴看板」勾选宗地生成" />
        ) : (
          <Table
            size="small" rowKey="id" loading={loading} dataSource={rows}
            rowSelection={{ selectedRowKeys: selected, onChange: (k) => setSelected(k as number[]) }}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: '宗地键', dataIndex: 'parcel_key', width: 100,
                render: (v: string) => <b>{v}</b> },
              {
                title: '欠缴金额(元)', dataIndex: 'arrears', width: 130, align: 'right' as const,
                render: (v: string) => (
                  <span className="num-cell" style={{ color: TOKENS.error, fontWeight: 600 }}>{fmtNum(v)}</span>
                ),
              },
              { title: '通知书', width: 110, render: () => <Tag color="green">已生成</Tag> },
              { title: '短信', width: 100, render: () => <Tag color="blue">模拟发送</Tag> },
              {
                title: '缴纳结果', dataIndex: 'status', width: 110,
                render: (v: string) => v === '已回款' ? <Tag color="green">已回款</Tag>
                  : v === '部分回款' ? <Tag color="orange">部分回款</Tag>
                  : <Tag color="red">未缴纳</Tag>,
              },
              { title: '生成时间', dataIndex: 'created_at', width: 170 },
              {
                title: '操作', width: 230,
                render: (_: any, r: any) => (
                  <Space>
                    <Button size="small" type="link"
                            onClick={() => setPreview({ notice: r, parcel: parcelMap.get(r.parcel_key) })}>
                      查看通知书
                    </Button>
                    <Button size="small" type="link" onClick={() => openTracks(r.id)}>
                      催缴记录
                    </Button>
                    <Button size="small" type="link" icon={<DownloadOutlined />}
                            href={api.noticePdfUrl(r.id)} target="_blank">
                      PDF
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        )}
      </Card>

      {/* 通知书弹窗预览 */}
      <Modal
        open={!!preview}
        onCancel={() => setPreview(null)}
        width={660}
        centered
        destroyOnClose
        title={preview ? `催缴通知书 · ${preview.notice.parcel_key} · 第 ${String(preview.notice.id).padStart(3, '0')} 号` : ''}
        footer={preview ? [
          <Button key="close" onClick={() => setPreview(null)}>关闭</Button>,
          <Button key="pdf" type="primary" icon={<DownloadOutlined />}
                  href={api.noticePdfUrl(preview.notice.id)} target="_blank">
            下载 PDF
          </Button>,
        ] : null}
      >
        {preview && (
          <>
            <div style={{
              background: '#fff', border: '1px solid #eee', borderRadius: 6,
              boxShadow: '0 4px 16px rgba(0,0,0,.08)',
              padding: '32px 40px', margin: '8px 4px 12px',
              fontFamily: 'Songti SC, SimSun, serif',
            }}>
              <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 20, letterSpacing: 2, marginBottom: 6 }}>
                国有土地租金催缴通知书
              </div>
              <div style={{ textAlign: 'center', color: 'rgba(0,0,0,.45)', fontSize: 12, marginBottom: 22,
                            paddingBottom: 12, borderBottom: '2px solid #cf1322' }}>
                ×土租催〔2026〕第 {String(preview.notice.id).padStart(3, '0')} 号
              </div>
              <div style={{ fontSize: 14, lineHeight: 2.3, textIndent: 0 }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>
                  {preview.parcel?.contract_lessee || preview.parcel?.dunning_target || '（催缴对象）'}：
                </div>
                <div style={{ textIndent: '2em' }}>
                  你单位承租的位于 <b>{preview.parcel?.reg_location || '（坐落）'}</b> 的国有土地
                  （宗地面积 {fmtNum(preview.parcel?.reg_area)} ㎡，宗地键 {preview.notice.parcel_key}），
                  截至 2026-09-30 累计欠缴土地租金{' '}
                  <b style={{ color: TOKENS.error, fontSize: 16 }}>{fmtMoney(preview.notice.arrears)}</b>
                  （欠缴年度：{preview.parcel?.arrears_years || '见附页'}）。
                </div>
                <div style={{ textIndent: '2em', marginTop: 8 }}>
                  请于收到本通知之日起 30 日内，按原缴费渠道补缴上述租金。逾期未缴的，将依照合同约定及有关规定处理。
                </div>
                <div style={{ textIndent: '2em', marginTop: 8 }}>特此通知。</div>
                <div style={{ textAlign: 'right', marginTop: 28, lineHeight: 2 }}>
                  ××县自然资源和规划局（模拟）<br />
                  2026 年 10 月 28 日
                </div>
              </div>
              <div style={{ marginTop: 18, paddingTop: 10, borderTop: '1px dashed #e8e8e8',
                            fontSize: 11, color: 'rgba(0,0,0,.45)' }}>
                模板版本 {preview.notice.template_version || 'v1.0'} · 演示环境文书，仅用于系统演示
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'rgba(0,0,0,.45)', textAlign: 'center' }}>
              催缴对象取登记现权利人，查不到取最新承租人；电话优先登记（口径第九条）。
            </div>
          </>
        )}
      </Modal>

      {/* 催缴记录抽屉 */}
      <Drawer
        title={track ? `催缴记录 · ${track.notice.parcel_key} · 通知书 #${track.notice.id}` : '催缴记录'}
        width={520} open={trackOpen} onClose={() => { setTrackOpen(false); setTrack(null); }}
      >
        {trackLoading || !track ? <Text type="secondary">加载中…</Text> : (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <div>催缴对象：<b>{track.parcel?.owner || track.parcel?.lessee || '—'}</b>
                  <Text type="secondary" style={{ marginLeft: 8 }}>{track.parcel?.phone || '—'}</Text></div>
                <div>坐落：{track.parcel?.location || '—'}</div>
                <div>欠缴年度：<Text type="secondary">{track.parcel?.arrears_years || '—'}</Text></div>
                <div>通知书欠缴金额：<b style={{ color: TOKENS.error }}>{fmtMoney(track.notice.arrears)}</b></div>
                <div>已登记回款：<b style={{ color: TOKENS.success }}>{fmtMoney(track.recovered)}</b>
                  　剩余：<b>{fmtMoney(track.remain)}</b>
                  <Tag color={track.notice.status === '已回款' ? 'green'
                    : track.notice.status === '部分回款' ? 'orange' : 'red'}
                       style={{ marginLeft: 8 }}>
                    {track.notice.status === '已回款' ? '已回款'
                      : track.notice.status === '部分回款' ? '部分回款' : '未缴纳'}
                  </Tag>
                </div>
              </Space>
            </Card>

            <div>
              <Text strong>催缴台账时间线</Text>
              <Timeline
                style={{ marginTop: 10 }}
                items={[
                  ...(track.timeline || []).map((t: any) => ({
                    // 已发生事件用完成态颜色：生成通知书=绿、短信=蓝、回款=绿
                    color: t.type === 'sms' ? 'blue' : 'green',
                    children: (
                      <div>
                        <b>{t.title}</b>
                        {t.type === 'notice' && <Tag color="green" style={{ marginLeft: 6 }}>已完成</Tag>}
                        {t.type === 'sms' && <Tag color="blue" style={{ marginLeft: 6 }}>已发送</Tag>}
                        {t.type === 'payment' && <Tag color="green" style={{ marginLeft: 6 }}>已登记</Tag>}
                        <div style={{ fontSize: 12, color: 'rgba(0,0,0,.65)' }}>{t.detail}</div>
                        <div style={{ fontSize: 11, color: 'rgba(0,0,0,.45)' }}>{t.at || '—'}</div>
                      </div>
                    ),
                  })),
                  {
                    color: track.remain > 0 ? 'gray' : 'green',
                    children: (
                      <div>
                        <b>{track.remain > 0 ? '待回款' : '已结清'}</b>
                        {track.remain > 0
                          ? <Tag style={{ marginLeft: 6 }}>进行中</Tag>
                          : <Tag color="green" style={{ marginLeft: 6 }}>全部回款</Tag>}
                        <div style={{ fontSize: 12, color: 'rgba(0,0,0,.65)' }}>
                          欠缴 {fmtMoney(track.notice.arrears)} − 已回款 {fmtMoney(track.recovered)}
                          ＝ 剩余 <b>{fmtMoney(track.remain)}</b>
                        </div>
                      </div>
                    ),
                  },
                ]}
              />
            </div>

            <Card size="small" title="登记回款（留痕）" variant="borderless"
                  style={{ border: '1px solid #f0f0f0' }}>
              <Form form={form} layout="vertical" size="small">
                <Space align="start" wrap>
                  <Form.Item name="amount" label="回款金额" rules={[{ required: true, message: '请填金额' }]}>
                    <InputNumber min={0.01} style={{ width: 140 }} placeholder="0.00" />
                  </Form.Item>
                  <Form.Item name="pay_date" label="缴费日期">
                    <Input style={{ width: 150 }} placeholder="2026-10-28" />
                  </Form.Item>
                  <Form.Item name="receipt_no" label="票据号">
                    <Input style={{ width: 150 }} placeholder="如 PZ20261028" />
                  </Form.Item>
                </Space>
                <Button type="primary" size="small" onClick={submitTrack}>登记</Button>
                <div className="note" style={{ marginTop: 8 }}>{track.note}</div>
              </Form>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
