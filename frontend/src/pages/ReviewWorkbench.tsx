import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, App, Badge, Button, Card, Checkbox, Drawer, Empty, Input, Segmented,
  Space, Spin, Table, Tag, Tooltip, Typography,
} from 'antd';
import {
  CheckOutlined, LeftOutlined, RightOutlined, UnorderedListOutlined, WarningFilled,
} from '@ant-design/icons';
import { api, ContractDoc, FieldExtraction } from '../api/client';
import PageHead from '../components/PageHead';
import { TOKENS, fmtMoney } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '批次导入', path: '/contract/batch' },
  { label: '复核工作台', path: '/contract/review' },
  { label: '问题清单', path: '/contract/issues' },
];

/** 字段 → 原图高亮近似坐标（演示用，x/y/w/h 为百分比） */
const BOX: Record<string, [number, number, number, number]> = {
  合同编号: [8, 10, 62, 6], 承租人: [8, 24, 52, 6], 坐落: [8, 38, 58, 6],
  土地面积: [8, 52, 40, 6], 租赁起始日: [8, 60, 50, 6], 租赁终止日: [8, 68, 50, 6],
  年租金小写: [8, 76, 60, 6], 联系电话: [8, 86, 36, 6],
};

export default function ReviewWorkbench() {
  const { message, modal } = App.useApp();

  const [queue, setQueue] = useState<ContractDoc[]>([]);
  const [queueTotal, setQueueTotal] = useState(0);
  const [filter, setFilter] = useState<string>('pending');
  const [kw, setKw] = useState('');
  const [idx, setIdx] = useState(0);
  const [doc, setDoc] = useState<ContractDoc | null>(null);
  const [fields, setFields] = useState<FieldExtraction[]>([]);
  const [pages, setPages] = useState<any>(null);
  const [pageNo, setPageNo] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [gray, setGray] = useState(false);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [activeField, setActiveField] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  /** 队列：一次取全量（演示 40 份以内），供「上一份/下一份」导航 */
  const loadQueue = () => {
    setLoading(true);
    const params: any = { page: 1, page_size: 200 };
    if (filter === 'review') params.process_type = '人工复核';
    if (filter === 'pending') params.status = 'pending';
    if (kw.trim()) params.keyword = kw.trim();
    api.reviewDocs(params)
      .then((r) => { setQueue(r.items); setQueueTotal(r.total); })
      .finally(() => setLoading(false));
  };
  useEffect(loadQueue, [filter, kw]);
  // 筛选或关键词变化后回到队列第一条（搜索即定位，不用一页页翻）
  useEffect(() => { setIdx(0); }, [filter, kw]);

  const current = queue[idx] ?? null;

  useEffect(() => {
    if (!current) { setDoc(null); setFields([]); setPages(null); return; }
    setDoc(current);
    setPageNo(1); setZoom(1); setActiveField(null); setEditing({});
    Promise.all([api.docDetail(current.id), api.docPages(current.id)])
      .then(([d, p]) => {
        setFields(d.fields);
        setPages(p);
        const init: Record<string, boolean> = {};
        d.fields.forEach((f) => {
          const lv = (f.reason?.level as string)
            || (f.confidence && Number(f.confidence) >= 0.9 ? 'L1' : 'L2');
          init[f.field_name] = lv === 'L1';
        });
        setChecked(init);
      });
  }, [current?.id]);

  const levelOf = (f: FieldExtraction): string =>
    (f.reason?.level as string)
    || (f.confidence ? (Number(f.confidence) >= 0.9 ? 'L1' : 'L2') : 'L3');

  const attentionCount = useMemo(
    () => fields.filter((f) => levelOf(f) !== 'L1' || (f.reason?.issues?.length ?? 0) > 0).length,
    [fields],
  );
  const l2Fields = fields.filter((f) => levelOf(f) === 'L2');
  const l3Fields = fields.filter((f) => levelOf(f) === 'L3');

  const go = (delta: number) => {
    const next = idx + delta;
    if (next < 0 || next >= queue.length) { message.info('已到队列边界'); return; }
    setIdx(next);
  };

  const saveField = async (f: FieldExtraction) => {
    if (!doc) return;
    const val = editing[f.field_name];
    if (val === undefined || val === (f.final_value ?? '')) return;
    const r: any = await api.correctField(doc.id, {
      field_name: f.field_name, after_value: val,
      before_value: f.final_value, operator: '张贯贯',
    });
    if (r?.ledger_recomputed) {
      message.success(
        `已改正「${f.field_name}」→ ${val || '（空）'}，宗地 ${r.parcel_key} 台账已重算：` +
        `累计应缴 ${fmtMoney(r.total_due)} · 欠缴 ${fmtMoney(r.arrears)}`);
    } else {
      message.success(`已改正「${f.field_name}」→ ${val || '（空）'}（尚未入库，确认后生成台账）`);
    }
    const d = await api.docDetail(doc.id);
    setFields(d.fields);
    setDoc(d.doc);
    setEditing((e) => { const n = { ...e }; delete n[f.field_name]; return n; });
    loadQueue();
  };

  /** 已入库档案撤回：台账回滚，回到待复核（改字段→重新确认的完整流程） */
  const revertOne = () => {
    if (!doc) return;
    modal.confirm({
      title: `撤回 ${doc.id} 的入库？`,
      content: '撤回后该宗地台账将按剩余已确认合同重算（若无其他合同则整宗移除），'
             + '档案回到待复核。改完字段再点「确认入库」即可重新生成台账。',
      okText: '确认撤回', okType: 'danger', cancelText: '取消',
      onOk: async () => {
        const r: any = await api.revertDoc(doc.id);
        message.success(`${doc.id} 已撤回，宗地 ${r.parcel_key ?? '—'} 台账已回滚`);
        loadQueue();
        const d = await api.docDetail(doc.id);
        setDoc(d.doc); setFields(d.fields);
      },
    });
  };

  const confirmOne = async () => {
    if (!doc) return;
    await api.confirmDoc(doc.id);
    message.success(`${doc.id} 已确认入库`);
    loadQueue();
    const d = await api.docDetail(doc.id);
    setDoc(d.doc);
  };

  /** 当前队列里可批量确认的：自动通过 且 未确认入库 */
  const autoDocs = queue.filter((d) => d.process_type === '自动通过' && d.status !== 'confirmed');

  /** 批量确认（自动通过项）——必须二次确认（PRD 8.3） */
  const batchConfirm = () => {
    if (autoDocs.length === 0) { message.warning('当前队列没有待确认的「自动通过」档案'); return; }
    // 按关键字段最低置信度升序，把最不确定的排前面供人工先看
    const byConf = [...autoDocs].sort(
      (a, b) => (a.min_confidence ?? 1) - (b.min_confidence ?? 1));
    modal.confirm({
      title: `批量确认 ${autoDocs.length} 份自动通过项`,
      width: 640,
      icon: <WarningFilled style={{ color: TOKENS.warning }} />,
      content: (
        <div style={{ marginTop: 12 }}>
          <Alert
            type="warning" showIcon style={{ marginBottom: 10 }}
            message="确认前请核对最低置信度预警"
            description={
              <div style={{ fontSize: 12 }}>
                抽检比例 10%（{Math.max(1, Math.round(autoDocs.length * 0.1))} 份）· 抽检件自动转复核队列
                <br />
                最低置信档案（按关键字段最低置信度排序）：
                {' '}
                {byConf.slice(0, 3).map((d) => `${d.id} ${((d.min_confidence ?? 0) * 100).toFixed(0)}%`).join('、')}
              </div>
            }
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            「自动通过」= 关键字段全对且校验通过，经办人批量确认（不是跳过人工）；
            评分规则为 自动通过且对 +1、错 −1、人工复核 +0.5。
          </Text>
        </div>
      ),
      okText: '确认通过',
      cancelText: '再看看',
      onOk: async () => {
        const r = await api.batchConfirm({
          archive_nos: autoDocs.map((d) => d.id), operator: '张贯贯', sample_inspect_rate: 0.1,
        });
        message.success(`已确认 ${r.confirmed?.length ?? autoDocs.length} 份`);
        loadQueue();
      },
    });
  };

  const pageUrl = pages?.pages?.find((p: any) => p.page_no === pageNo)?.url;

  /** 高亮框：已知字段用标定坐标，其余按字段序等比推算（演示用近似坐标） */
  const box: [number, number, number, number] | null = (() => {
    if (!activeField) return null;
    const known = BOX[activeField];
    if (known) return known;
    const i = fields.findIndex((f) => f.field_name === activeField);
    if (i < 0) return null;
    return [8, Math.min(8 + i * 3.2, 88), 52, 5];
  })();

  return (
    <div>
      <PageHead group="合同治理" desc="导入 → 复核 → 问题处理" tabs={TABS} />

      {/* 复核队列工具条 */}
      <Card
        size="small"
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}
        styles={{ body: { padding: '10px 16px' } }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Space size={10} wrap>
            <Button size="small" icon={<UnorderedListOutlined />} onClick={() => setListOpen(true)}>
              复核队列
            </Button>
            <Text strong>{current ? `${current.id}（第 ${idx + 1}/${queue.length} 份）` : '—'}</Text>
            {attentionCount > 0 && <Tag color="orange">{attentionCount} 处需关注</Tag>}
            {doc && (
              <Tag color={doc.process_type === '自动通过' ? 'green' : 'orange'}>{doc.process_type}</Tag>
            )}
            <Input.Search
              size="small"
              allowClear
              placeholder="搜档案号 / 承租人 / 合同编号 / 坐落"
              style={{ width: 250 }}
              value={kw}
              onChange={(e) => setKw(e.target.value)}
              onSearch={(v) => { setIdx(0); setKw(v); }}
            />
            {kw.trim() && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                命中 {queueTotal} 份
              </Text>
            )}
            <Segmented
              size="small"
              value={filter}
              onChange={(v) => { setIdx(0); setFilter(v as string); }}
              options={[
                { label: '全部', value: 'all' },
                { label: '待复核', value: 'pending' },
                { label: '人工复核档', value: 'review' },
              ]}
            />
          </Space>
          <Space size={8}>
            <Button size="small" icon={<LeftOutlined />} disabled={idx <= 0} onClick={() => go(-1)}>
              上一份
            </Button>
            <Button size="small" disabled={idx >= queue.length - 1} onClick={() => go(1)}>
              下一份<RightOutlined />
            </Button>
            <Tooltip
              title={
                autoDocs.length > 0
                  ? `当前队列有 ${autoDocs.length} 份「自动通过」且未入库的档案，可批量确认`
                  : '仅当队列中存在「自动通过」且未确认入库的档案时可点击：需先执行批次识别，'
                    + '且该档案 6 个关键字段（承租人/证件号码/土地面积/起租日/终止日/年租金）'
                    + '置信度均 ≥90%、校验通过、无涂改'
              }
            >
              <Button
                size="small" type="primary" icon={<CheckOutlined />}
                disabled={autoDocs.length === 0}
                onClick={batchConfirm}
              >
                批量确认自动通过项{autoDocs.length > 0 ? `（${autoDocs.length}）` : ''}
              </Button>
            </Tooltip>
          </Space>
        </div>
      </Card>

      {loading && !doc ? (
        <Spin style={{ display: 'block', margin: '80px auto' }} />
      ) : !doc ? (
        <Card variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
          <Empty
            description={
              filter === 'pending'
                ? '暂无待复核档案：新批次「执行识别」完成后，未确认的档案会出现在这里'
                : filter === 'review'
                  ? '暂无人工复核档：仅当新导入合同触发「涂改 / 关键字段低置信 / 校验未过 / 关键字段不可识别」时才会进入'
                  : '队列为空，请先导入批次'
            }
            style={{ margin: '60px 0' }}
          />
        </Card>
      ) : (
        <div className="review-layout">
          {/* 左：原件对照 */}
          <Card
            size="small"
            variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}
            title={
              <span>
                原件对照 · 档案 {doc.id}
                <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 10 }}>
                  批次 {pages?.batch_no || '—'}
                </Text>
              </span>
            }
          >
            <div className="imgbar">
              <span>第 {pageNo} 页 / 共 {pages?.page_count ?? 1} 页</span>
              <Space size={6}>
                <Button size="small" disabled={zoom <= 0.6}
                        onClick={() => setZoom((z) => +(z - 0.2).toFixed(1))}>缩小 −</Button>
                <Button size="small" disabled={zoom >= 2.4}
                        onClick={() => setZoom((z) => +(z + 0.2).toFixed(1))}>放大 +</Button>
                <Button size="small" onClick={() => setGray((g) => !g)}>
                  {gray ? '原图' : '灰度增强'}
                </Button>
              </Space>
            </div>

            <div className="imgstage" ref={stageRef}>
              {pageUrl ? (
                <div style={{ position: 'relative', width: '100%', overflow: 'auto' }}>
                  <img
                    src={pageUrl}
                    alt={`${doc.id} 第 ${pageNo} 页原件`}
                    style={{
                      display: 'block', width: '100%',
                      transform: `scale(${zoom})`, transformOrigin: 'top left',
                      transition: 'transform .15s ease',
                      filter: gray ? 'grayscale(1) contrast(1.35) brightness(1.05)' : 'none',
                    }}
                  />
                  {box && (
                    <div
                      className="hlbox"
                      style={{
                        display: 'block',
                        left: `${box[0]}%`, top: `${box[1]}%`,
                        width: `${box[2]}%`, height: `${box[3]}%`,
                        transform: `scale(${zoom})`, transformOrigin: 'top left',
                      }}
                    />
                  )}
                </div>
              ) : (
                <div className="doc-thumb" style={{ height: 360 }}>
                  {pages === null ? '加载原件中…' : '该档案无原件图片（storage 与样本包均未找到）'}
                </div>
              )}
            </div>

            <div className="thumbs">
              {(pages?.pages || []).map((p: any) => (
                <img
                  key={p.page_no}
                  src={p.url}
                  className={p.page_no === pageNo ? 'active' : ''}
                  alt={`第 ${p.page_no} 页`}
                  onClick={() => setPageNo(p.page_no)}
                />
              ))}
            </div>
            <div className="note" style={{ marginTop: 8 }}>
              点击右侧字段行 → 原图高亮对应区域；支持缩放与灰度增强切换（演示用近似坐标）
            </div>
          </Card>

          {/* 右：逐字段核对 */}
          <Card
            size="small"
            variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}
            title="AI 抽取结果 · 逐字段核对"
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                全部字段可人工修正 · 修正记审计日志
              </Text>
            }
          >
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              scroll={{ y: 520 }}
              dataSource={fields}
              onRow={(f) => ({
                onClick: () => setActiveField(f.field_name),
                className: [
                  'fieldrow',
                  activeField === f.field_name ? 'active' : '',
                  levelOf(f) === 'L2' ? 'field-row-inferred' : '',
                  levelOf(f) === 'L3' ? 'field-row-unreadable' : '',
                ].filter(Boolean).join(' '),
              })}
              columns={[
                { title: '字段', dataIndex: 'field_name', width: 96 },
                {
                  title: '识别值（可修正）', width: 250,
                  render: (_: any, f: FieldExtraction) => {
                    const lv = levelOf(f);
                    return (
                      <Input
                        size="small"
                        variant={lv === 'L1' ? 'borderless' : 'outlined'}
                        value={editing[f.field_name] ?? (f.final_value ?? '')}
                        placeholder={lv === 'L3' ? '对照原件输入…' : ''}
                        onChange={(e) => setEditing((s) => ({ ...s, [f.field_name]: e.target.value }))}
                        onPressEnter={() => saveField(f)}
                        onBlur={() => saveField(f)}
                        style={
                          lv === 'L2' ? { background: '#fffbe6' }
                            : lv === 'L3' ? { background: '#fff1f0' } : undefined
                        }
                        suffix={
                          editing[f.field_name] !== undefined ? (
                            <Tooltip title="保存（记审计日志）">
                              <span
                                onClick={() => saveField(f)}
                                style={{ cursor: 'pointer', color: TOKENS.colorPrimary, fontSize: 12 }}
                              >
                                保存
                              </span>
                            </Tooltip>
                          ) : null
                        }
                      />
                    );
                  },
                },
                {
                  title: '置信度', dataIndex: 'confidence', width: 78, align: 'right' as const,
                  render: (v: string) => {
                    if (!v) return <Tag color="red">—</Tag>;
                    const n = Number(v);
                    const color = n >= 0.9 ? 'green' : n >= 0.8 ? 'orange' : 'red';
                    return <Tag color={color} style={{ fontSize: 11 }}>{n.toFixed(2)}</Tag>;
                  },
                },
                {
                  title: '来源', width: 104,
                  render: (_: any, f: FieldExtraction) => {
                    const lv = levelOf(f);
                    if (lv === 'L3') return <Tag color="red">人工录入</Tag>;
                    if (lv === 'L2') return <Tag color="orange">反推</Tag>;
                    return <Text style={{ fontSize: 12 }}>直接识别</Text>;
                  },
                },
                {
                  title: '确认', width: 56, align: 'center' as const,
                  render: (_: any, f: FieldExtraction) => (
                    <Checkbox
                      checked={checked[f.field_name] ?? false}
                      onChange={(e) => setChecked((c) => ({ ...c, [f.field_name]: e.target.checked }))}
                    />
                  ),
                },
              ]}
            />

            <div className="note" style={{ marginTop: 8 }}>
              ※ 任一字段被人工修改后：原 AI 值 → 修正值自动写入审计日志（改前/改后 + 修改人 + 时间），
              该份处理方式自动改为「人工复核」。
            </div>

            {l2Fields.length > 0 && (
              <div className="reason">
                <b>反推原因（L2）：</b>
                {l2Fields.slice(0, 3).map((f) => (
                  <div key={f.field_name} style={{ marginTop: 2 }}>
                    {f.field_name}：{f.reason?.rules?.join('；') || '由其他字段推导，置信度偏低'} →
                    <b> {f.final_value ?? '（空）'}</b>
                  </div>
                ))}
                <div style={{ marginTop: 4 }}>建议人工对照原件复核确认。</div>
              </div>
            )}

            {l3Fields.length > 0 && (
              <div className="unknown">
                <b>不可识别（L3）：</b>
                {l3Fields.slice(0, 4).map((f) => f.field_name).join('、')}
                —— 已列入问题清单，请对照原件人工录入。
              </div>
            )}

            {(doc.altered_field || doc.process_type === '人工复核') && (
              <Alert
                type="error" showIcon style={{ marginTop: 10 }}
                message={`强制复核${doc.altered_field ? `（涂改字段：${doc.altered_field}）` : ''}`}
                description={
                  <span style={{ fontSize: 12 }}>
                    {doc.altered_field
                      ? `原件「${doc.altered_field}」处有涂改${doc.altered_seal ? '，涂改处有签章' : '，涂改处无签章'}；按口径四(四)与第十二条，需对照原件确认后入库。`
                      : '该档案存在低置信/校验未过/存疑情形，需逐项对照原件。'}
                  </span>
                }
              />
            )}

            <div style={{ marginTop: 14, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Button onClick={() => message.info('已退回问题清单（演示）')}>退回问题清单</Button>
              <Button onClick={() => message.info('已标记存疑待确认（演示）')}>标记存疑待确认</Button>
              {doc.status === 'confirmed' && (
                <Button danger onClick={revertOne}>撤回入库</Button>
              )}
              <Button type="primary" onClick={confirmOne} disabled={doc.status === 'confirmed'}>
                {doc.status === 'confirmed' ? '已确认入库' : '确认入库（生成宗地台账）'}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* 队列抽屉 */}
      <Drawer
        title={`复核队列（${queueTotal}）`}
        width={380}
        open={listOpen}
        onClose={() => setListOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={6}>
          {queue.map((d, i) => (
            <div
              key={d.id}
              onClick={() => { setIdx(i); setListOpen(false); }}
              style={{
                padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                border: `1px solid ${i === idx ? TOKENS.colorPrimary : '#f0f0f0'}`,
                background: i === idx ? '#e6f4ff' : '#fff',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Badge status={d.status === 'confirmed' ? 'success' : 'processing'} />
                <Text strong style={{ fontSize: 13 }}>{d.id}</Text>
                <Tag
                  color={d.process_type === '自动通过' ? 'green' : 'orange'}
                  style={{ marginLeft: 'auto', fontSize: 11 }}
                >
                  {d.process_type}
                </Tag>
              </div>
              <div style={{ fontSize: 12, color: 'rgba(0,0,0,.55)', marginTop: 2, marginLeft: 18 }}>
                {d.lessee || '—'} · {d.end_date || '无终止日'}
              </div>
            </div>
          ))}
          {queue.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </Space>
      </Drawer>
    </div>
  );
}
