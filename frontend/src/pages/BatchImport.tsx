import { useEffect, useState } from 'react';
import { App, Button, Card, Space, Table, Tag, Upload, Typography, Steps, Alert, Modal } from 'antd';
import { InboxOutlined, PlusOutlined, ThunderboltOutlined, RollbackOutlined, LoadingOutlined } from '@ant-design/icons';
import { Progress } from 'antd';
import { api, Batch } from '../api/client';
import PageHead from '../components/PageHead';

const { Text } = Typography;
const { Dragger } = Upload;

const TABS = [
  { label: '批次导入', path: '/contract/batch' },
  { label: '复核工作台', path: '/contract/review' },
  { label: '问题清单', path: '/contract/issues' },
];

const STATUS_COLOR: Record<string, string> = {
  created: 'default', uploaded: 'blue', processing: 'orange',
  done: 'green', rolled_back: 'red', failed: 'red',
};

const STATUS_LABEL: Record<string, string> = {
  created: '已创建', uploaded: '已上传', processing: '识别中',
  done: '已完成', rolled_back: '已撤回', failed: '失败',
};

export default function BatchImport() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Batch[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [running, setRunning] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    api.batches({ page, page_size: 10 })
      .then((r) => { setRows(r.items); setTotal(r.total); })
      .finally(() => setLoading(false));
  };
  useEffect(load, [page]);

  // 有批次处于「识别中」时自动轮询（跳转页面回来也能看到实时状态）
  const processing = rows.some((r) => r.status === 'processing');
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(() => {
      api.batches({ page, page_size: 10 }).then((r) => { setRows(r.items); setTotal(r.total); });
    }, 3000);
    return () => clearInterval(t);
  }, [processing, page]);

  const selected = rows.find((r) => r.id === selectedId) || null;

  const create = async (type: string) => {
    const b = await api.createBatch({ batch_type: type });
    message.success(`已创建批次 ${b.batch_no}`);
    setSelectedId(b.id);
    load();
  };

  // 逐文件上传（后端幂等：同批次同路径覆盖，重复上传安全）
  const handleUpload = (file: File) => {
    if (!selectedId) {
      message.warning('请先选择或新建批次');
      return Upload.LIST_IGNORE;
    }
    api.uploadFiles(selectedId, [file])
      .then((r) => {
        message.success(`已上传 ${file.name}（当前 ${r.file_count} 图 / ${r.archive_count} 份）`);
        load();
      })
      .catch((e: any) => message.error(`上传失败：${e.message || e}`));
    return false; // 阻止 antd 默认上传行为
  };

  const runPipeline = async (batch: Batch) => {
    setRunning(batch.id);
    try {
      const r = await api.runBatch(batch.id);
      message.success(r?.message || '识别任务已提交，正在后台执行…');
      load();     // 立刻拉一次，状态变「识别中」，随后自动轮询
    } catch (e: any) {
      message.error(`提交识别失败：${e.message || e}`);
    } finally {
      setRunning(null);
    }
  };

  const rollback = async (batch: Batch) => {
    Modal.confirm({
      title: `确认撤回批次 ${batch.batch_no}？`,
      content: `将级联删除该批次产生的 ${batch.doc_count || 0} 份合同及其字段抽取、字段改正、问题清单记录，操作留痕，不可恢复。`,
      okText: '确认撤回', okType: 'danger', cancelText: '取消',
      onOk: async () => {
        try {
          const r = await api.rollbackBatch(batch.id);
          message.success(
            `已撤回 ${r.batch_no}：删除合同 ${r.contracts}、字段 ${r.fields}、改正 ${r.corrections}、问题 ${r.issues}`);
          if (selectedId === batch.id) setSelectedId(null);
          load();
        } catch (e: any) {
          message.error(`撤回失败：${e.message || e}`);
        }
      },
    });
  };

  // 步骤条根据选中批次状态推进
  const stepIdx = selected
    ? selected.status === 'created' ? 0
      : selected.status === 'uploaded' ? 1
      : (selected.status === 'processing' || selected.status === 'done') ? 3
      : 0
    : 0;

  return (
    <div>
      <PageHead group="合同治理" desc="批次导入·复核工作台·问题清单" tabs={TABS}
        extra={
          <Space>
            <Button icon={<PlusOutlined />} onClick={() => create('新签')}>新建批次</Button>
          </Space>
        }
      />

      <Card size="small" variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}>
        <Steps
          size="small"
          current={stepIdx}
          items={[
            { title: '新建批次' },
            { title: '上传扫描件', description: '文件名：档案号_页序.jpg' },
            { title: '识别 + 归宗 + 核算' },
            { title: '复核确认' },
          ]}
        />
      </Card>

      {selected && (
        <Alert
          type="info" showIcon
          style={{ marginBottom: 16 }}
          message={`当前批次：${selected.batch_no} · 状态：${STATUS_LABEL[selected.status] || selected.status} · ${selected.file_count || 0} 图 / ${selected.doc_count || 0} 份`}
          description={
            <Space>
              {selected.status === 'created' && <Text type="secondary">请在下方上传扫描件</Text>}
              {selected.status === 'uploaded' && <Text type="warning">已上传，请点击「执行识别」</Text>}
              {selected.status === 'processing' && <Text type="warning">识别管道执行中…</Text>}
              {selected.status === 'done' && <Text type="success">识别完成，可前往复核工作台查看</Text>}
              {selected.status === 'rolled_back' && <Text type="secondary">已撤回，如需重新导入请新建批次</Text>}
            </Space>
          }
        />
      )}

      <Card size="small" title="上传区" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}>
        <Dragger
          multiple
          accept="image/*"
          beforeUpload={handleUpload}
          showUploadList={true}
          disabled={!selectedId}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">拖入或点击选择扫描件</p>
          <p className="ant-upload-hint">
            命名规范「档案号_页序.jpg」→ 同档案号多页自动合成一份 · 上传后写入 SHA256 校验值
          </p>
        </Dragger>
        {!selectedId && (
          <Text type="warning" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            请先点击上方「新建批次」或选择下方已有批次，再上传文件。
          </Text>
        )}
      </Card>

      <Card size="small" title="批次列表" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="id" loading={loading} dataSource={rows}
          rowClassName={(r) => r.id === selectedId ? 'ant-table-row-selected' : ''}
          onRow={(r) => ({ onClick: () => setSelectedId(r.id) })}
          pagination={{ current: page, pageSize: 10, total, onChange: setPage,
                        showTotal: (t) => `共 ${t} 个批次` }}
          columns={[
            { title: '批次号', dataIndex: 'batch_no', width: 220 },
            { title: '类型', dataIndex: 'batch_type', width: 110 },
            {
              title: '状态', dataIndex: 'status', width: 110,
              render: (v: string) => (
                <Tag color={STATUS_COLOR[v] || 'default'}
                     icon={v === 'processing' ? <LoadingOutlined /> : undefined}>
                  {STATUS_LABEL[v] || v}
                </Tag>
              ),
            },
            { title: '文件 / 档案', width: 110, align: 'right' as const,
              render: (_: any, r: Batch) => r.file_count ? `${r.file_count} 图 / ${r.doc_count} 份` : '—' },
            { title: '进度', width: 140,
              render: (_: any, r: Batch) => {
                const pct = r.status === 'done' ? 100 : r.status === 'processing' ? 45 : r.status === 'uploaded' ? 20 : 0;
                return <Progress percent={pct} size="small" showInfo={false}
                                 status={r.status === 'processing' ? 'active' : 'normal'}
                                 strokeColor={r.status === 'rolled_back' ? '#cf1322' : undefined} />;
              } },
            { title: '档案数', dataIndex: 'doc_count', width: 90, align: 'right' as const },
            { title: '创建时间', dataIndex: 'created_at', width: 180 },
            {
              title: '操作', width: 200,
              render: (_: any, r: Batch) => (
                <Space>
                  <Button size="small" type="link" icon={<ThunderboltOutlined />}
                          loading={running === r.id}
                          disabled={r.status !== 'uploaded'}
                          onClick={(e) => { e.stopPropagation(); runPipeline(r); }}>
                    执行识别
                  </Button>
                  <Button size="small" type="link" danger icon={<RollbackOutlined />}
                          disabled={r.status === 'rolled_back' || r.status === 'created'}
                          onClick={(e) => { e.stopPropagation(); rollback(r); }}>
                    撤回
                  </Button>
                </Space>
              ),
            },
          ]}
          scroll={{ x: 1100 }}
        />
      </Card>
    </div>
  );
}
