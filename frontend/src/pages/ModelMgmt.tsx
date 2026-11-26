import { useCallback, useEffect, useState } from 'react';
import {
  App, Alert, Badge, Button, Card, Col, Form, Input, Modal, Row, Space, Table, Tag, Typography,
} from 'antd';
import { api } from '../api/client';
import PageHead from '../components/PageHead';
import { TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '计租标准', path: '/system' },
  { label: '核算口径', path: '/system/rules' },
  { label: '问题类型', path: '/system/issue-types' },
  { label: '模型管理', path: '/system/models' },
  { label: '审计日志', path: '/system/audit' },
  { label: '系统设置', path: '/system/settings' },
];

type Channel = {
  id: number;
  name: string;
  kind: 'cloud' | 'opensource' | 'local';
  kind_label: string;
  base_url: string;
  model_id: string;
  api_key_env: string;
  available: boolean;
  is_active: boolean;
  params: Record<string, any>;
};

/** 通道类型 → 标签配色（闭源=蓝、开源=绿、本地=灰） */
const KIND_COLOR: Record<string, string> = {
  cloud: 'blue',
  opensource: 'green',
  local: 'default',
};

export default function ModelMgmt() {
  const { message } = App.useApp();
  const [logs, setLogs] = useState<any[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [editing, setEditing] = useState<Channel | null>(null);
  const [form] = Form.useForm();

  const load = useCallback(() => {
    api.models().then(setChannels);
    api.modelLogs().then(setLogs);
  }, []);

  useEffect(() => { load(); }, [load]);

  const activate = async (c: Channel) => {
    setBusy(c.id);
    try {
      const r: any = await api.activateModel(c.id);
      message.success(r?.message || `主通道已切换为 ${c.name}`);
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '切换失败');
    } finally {
      setBusy(null);
    }
  };

  const test = async (c: Channel) => {
    setBusy(c.id);
    try {
      const r: any = await api.testModel(c.id);
      if (r.ok) message.success(`${c.name} 连通正常（${r.latency_ms}ms）`);
      else message.warning(`${c.name} 不通：${r.message}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '探测失败');
    } finally {
      setBusy(null);
    }
  };

  const openEdit = (c: Channel) => {
    setEditing(c);
    form.setFieldsValue({
      name: c.name,
      model_id: c.model_id,
      endpoint: c.base_url,
      api_key_env: c.api_key_env,
    });
  };

  const submitEdit = async () => {
    const v = await form.validateFields();
    try {
      await api.updateModel(editing!.id, v);
      message.success('通道配置已保存');
      setEditing(null);
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败');
    }
  };

  const activeName = channels.find((c) => c.is_active)?.name || '—';

  return (
    <div>
      <PageHead group="系统管理" desc="计租标准·核算口径·模型·审计·设置" tabs={TABS} />

      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="模型只负责「图片 → 字段」，不参与任何金额计算"
        description="核算全部由 calc.py 纯规则引擎完成；模型输出带置信度，低于阈值自动转人工复核。"
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {channels.map((c) => (
          <Col xs={24} md={8} key={c.id}>
            <Card
              size="small"
              variant="borderless"
              style={{
                border: `1px solid ${c.is_active ? TOKENS.colorPrimary : '#f0f0f0'}`,
                background: c.is_active ? '#e6f4ff' : '#fff',
                borderRadius: 12, height: '100%',
              }}
              title={
                <Space size={4} wrap>
                  <span>{c.name}</span>
                  <Tag color={c.is_active ? 'blue' : KIND_COLOR[c.kind]}>
                    {c.is_active ? '当前主通道' : c.kind_label}
                  </Tag>
                </Space>
              }
            >
              <div style={{ fontSize: 13, lineHeight: 1.9, whiteSpace: 'pre-line' }}>
                {c.params?.vendor ? `${c.params.vendor} · ` : ''}{c.params?.desc || ''}
              </div>

              <div style={{ fontSize: 12, lineHeight: 1.9, marginTop: 6 }}>
                <div>模型：<Text code style={{ fontSize: 11 }}>{c.model_id}</Text></div>
                {c.kind !== 'local' && (
                  <div style={{ color: 'rgba(0,0,0,.45)', wordBreak: 'break-all' }}>
                    地址：{c.base_url || '—'}
                  </div>
                )}
                {c.kind !== 'local' && (
                  <div>
                    凭据：
                    <Badge
                      status={c.available ? 'success' : 'error'}
                      text={
                        <span style={{ fontSize: 12 }}>
                          {c.available ? '已配置' : `未配置 ${c.api_key_env}`}
                        </span>
                      }
                    />
                    {c.params?.open_weight && (
                      <Tag color="green" style={{ marginLeft: 6 }}>
                        开源{` ${c.params?.license || ''}`.trim()}
                      </Tag>
                    )}
                  </div>
                )}
              </div>

              <Space size={6} wrap style={{ marginTop: 10 }}>
                {!c.is_active && (
                  <Button size="small" type="primary" ghost
                          loading={busy === c.id}
                          onClick={() => activate(c)}>
                    设为主通道
                  </Button>
                )}
                <Button size="small" loading={busy === c.id} onClick={() => test(c)}>
                  测试连通
                </Button>
                <Button size="small" type="link" onClick={() => openEdit(c)}>
                  编辑
                </Button>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Card size="small" title="模型调用日志（审计留痕）" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="id" pagination={false} dataSource={logs}
          locale={{ emptyText: '暂无调用记录（识别批次执行后自动落 model_call_log）' }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 170 },
            { title: '模型', dataIndex: 'model_name', width: 200,
              render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
            { title: '对象', dataIndex: 'target', width: 150 },
            { title: '耗时', width: 90, align: 'right' as const,
              render: (_: any, r: any) => r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '—' },
            { title: 'Tokens', dataIndex: 'tokens', width: 90, align: 'right' as const },
            { title: '平均置信度', dataIndex: 'avg_confidence', width: 110, align: 'right' as const,
              render: (v: string) => v ? Number(v).toFixed(2) : '—' },
            {
              title: '结果', dataIndex: 'result', width: 130,
              render: (v: string) => v?.includes('低置信')
                ? <Tag color="orange">{v}</Tag> : <Tag color="green">{v || '成功'}</Tag>,
            },
          ]}
        />
        <div className="note" style={{ marginTop: 8 }}>
          当前主通道：<b>{activeName}</b>。切换只改 model_config.is_active 并写审计，
          下一份文档立即走新通道（不重启）。降级链：主通道超时 3 次 → 备通道 → 仍失败标 L3 人工录入；
          离线环境切本地 PaddleOCR。
        </div>
      </Card>

      <Modal
        open={!!editing}
        title={`编辑通道：${editing?.name || ''}`}
        onCancel={() => setEditing(null)}
        onOk={submitEdit}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Alert
          type="warning" showIcon style={{ marginBottom: 12 }}
          message="凭据只填环境变量名，明文密钥写 .env"
          description="改完地址或密钥后需重启后端才生效（.env 在启动时加载）。"
        />
        <Form form={form} layout="vertical" size="small">
          <Form.Item name="name" label="通道名称" rules={[{ required: true }]}>
            <Input placeholder="如 Qwen3-VL-32B（开源）" />
          </Form.Item>
          <Form.Item name="model_id" label="模型名（model_id）" rules={[{ required: true }]}>
            <Input placeholder="如 Qwen/Qwen3-VL-32B-Instruct" />
          </Form.Item>
          <Form.Item name="endpoint" label="服务地址（OpenAI 兼容 base_url）">
            <Input placeholder="如 https://api.siliconflow.cn/v1" />
          </Form.Item>
          <Form.Item
            name="api_key_env" label="凭据环境变量名"
            extra="填 .env 里的变量名，如 OPENSOURCE_API_KEY；本地通道留空"
          >
            <Input placeholder="OPENSOURCE_API_KEY" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
