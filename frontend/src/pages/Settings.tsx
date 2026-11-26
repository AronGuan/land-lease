import { useEffect, useState } from 'react';
import { App, Button, Card, Col, Descriptions, Row, Space, Table, Tag, Typography, Switch } from 'antd';
import { api } from '../api/client';
import PageHead from '../components/PageHead';

const { Text } = Typography;

const TABS = [
  { label: '计租标准', path: '/system' },
  { label: '核算口径', path: '/system/rules' },
  { label: '问题类型', path: '/system/issue-types' },
  { label: '模型管理', path: '/system/models' },
  { label: '审计日志', path: '/system/audit' },
  { label: '系统设置', path: '/system/settings' },
];

export default function Settings() {
  const { message } = App.useApp();
  const [health, setHealth] = useState<any>(null);
  const [models, setModels] = useState<any[]>([]);

  useEffect(() => {
    api.health().then(setHealth);
    api.models().then(setModels);
  }, []);

  return (
    <div>
      <PageHead group="系统管理" desc="计租标准·核算口径·模型·审计·设置" tabs={TABS} />

      <Card size="small" title="运行状态" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}>
        {health && (
          <Descriptions size="small" column={3} bordered
            items={[
              { key: '1', label: '服务状态',
                children: <Tag color={health.status === 'ok' ? 'green' : 'orange'}>{health.status}</Tag> },
              { key: '2', label: '数据库', children: health.database },
              { key: '3', label: '已建表', children: `${health.table_count} 张` },
              { key: '4', label: '主通道模型', children: health.model },
              { key: '5', label: 'API Key', 
                children: health.api_key_configured
                  ? <Tag color="green">已配置</Tag> : <Tag color="red">未配置</Tag> },
              { key: '6', label: '口径版本', children: health.rule_version },
            ]}
          />
        )}
      </Card>

      <Card size="small" title="模型通道" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}>
        <Table
          size="small" rowKey="id" dataSource={models} pagination={false}
          locale={{ emptyText: '尚无模型配置记录（默认使用 .env 中 qwen3-vl-plus）' }}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '通道', dataIndex: 'kind_label', width: 120,
              render: (v: string) => v || '—' },
            { title: '模型 ID', dataIndex: 'model_id', width: 220,
              render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
            {
              title: '主通道', dataIndex: 'is_active', width: 90,
              render: (v: number) => <Switch size="small" checked={!!v} disabled />,
            },
          ]}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          设计：主通道 qwen3-vl-plus（云端）· 备通道 qwen3.5-ocr（困难页增强）· 本地 PaddleOCR（离线演示）
        </Text>
      </Card>

      <Card size="small" title="数据维护" variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Space>
          <Button onClick={() => message.success('备份任务已提交（演示占位）')}>立即备份</Button>
          <Button onClick={() => message.info('配置项编辑见 /api/system/audit-logs（演示占位）')}>
            配置项
          </Button>
        </Space>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            备份策略：每日 02:00 mysqldump + storage 目录校验 SHA256；保留 30 天
          </Text>
        </div>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card size="small" title="用户与权限" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12, height: '100%' }}>
            <Table
              size="small" rowKey="name" pagination={false}
              dataSource={[
                { name: 'admin', role: '管理员', scope: '全部 + 批次撤回 + 用户管理', on: true },
                { name: '张经办', role: '经办人', scope: '导入 / 复核 / 催缴 / 台账查询', on: true },
                { name: '李复核', role: '复核员', scope: '复核 / 问题清单 / 税务推送', on: true },
              ]}
              columns={[
                { title: '用户', dataIndex: 'name', width: 90 },
                { title: '角色', dataIndex: 'role', width: 90,
                  render: (v: string) => <Tag color={v === '管理员' ? 'blue' : 'default'}>{v}</Tag> },
                { title: '权限范围', dataIndex: 'scope' },
                { title: '状态', dataIndex: 'on', width: 70,
                  render: (v: boolean) => <Tag color="green">{v ? '启用' : '停用'}</Tag> },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="备份与恢复" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12, height: '100%' }}>
            <div style={{ fontSize: 13, lineHeight: 2.1 }}>
              <div style={{ display: 'flex' }}><span style={{ width: 110, color: 'rgba(0,0,0,.55)' }}>上次备份</span><span>每日 02:00（自动）</span></div>
              <div style={{ display: 'flex' }}><span style={{ width: 110, color: 'rgba(0,0,0,.55)' }}>备份内容</span><span>MySQL dump + storage/ 原件目录</span></div>
              <div style={{ display: 'flex' }}><span style={{ width: 110, color: 'rgba(0,0,0,.55)' }}>完整性校验</span><Tag color="green">SHA256 全量通过</Tag></div>
            </div>
            <Space style={{ marginTop: 10 }}>
              <Button size="small" type="primary" onClick={() => message.success('备份任务已提交（演示占位）')}>立即备份</Button>
              <Button size="small" onClick={() => message.info('恢复演练为运维操作（演示占位）')}>恢复演练</Button>
              <Button size="small" onClick={() => message.info('下载备份为运维操作（演示占位）')}>下载备份</Button>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="配置中心（口径 / 模板 / 阈值均可配置）" variant="borderless"
            style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="key" pagination={false}
          dataSource={[
            { key: '核算口径版本', value: 'v1.2', desc: '计租标准 4 套 / 分段方式 / 减免情形（尚待主管部门确认项留空）' },
            { key: '自动通过置信度阈值', value: '0.90', desc: '练习集实测：100% 自动通过 × 100% 准确率' },
            { key: '到期提醒分级', value: '30 / 60 / 90 天', desc: '红 / 橙 / 蓝三级' },
            { key: '文书模板', value: '合同 / 催缴通知书 / 短信 / 税务推送单', desc: '制式模板，可替换（以主管部门实际模板为准）' },
          ]}
          columns={[
            { title: '配置项', dataIndex: 'key', width: 170 },
            { title: '当前值', dataIndex: 'value', width: 250,
              render: (v: string) => <b>{v}</b> },
            { title: '说明', dataIndex: 'desc' },
            { title: '操作', width: 110,
              render: () => <Button size="small" type="link"
                                    onClick={() => message.info('配置调整写审计日志（演示占位）')}>调整</Button> },
          ]}
        />
      </Card>
    </div>
  );
}
