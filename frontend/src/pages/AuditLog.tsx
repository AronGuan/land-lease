import { useEffect, useState } from 'react';
import { Card, Select, Table, Tag, Typography } from 'antd';
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

const ACTION_COLOR: Record<string, string> = {
  batch_run: 'blue', batch_rollback: 'red', batch_confirm: 'green',
  doc_confirm: 'green', doc_revert: 'orange', field_correct: 'gold',
  issue_resolve: 'cyan', seed: 'default',
};

export default function AuditLog() {
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api.auditLogs({ page, page_size: 15, action })
      .then((r) => { setRows(r.items); setTotal(r.total); })
      .finally(() => setLoading(false));
  };
  useEffect(load, [page, action]);

  return (
    <div>
      <PageHead group="系统管理" desc="计租标准·核算口径·模型·审计·设置" tabs={TABS}
        extra={
          <Select placeholder="操作类型" allowClear style={{ width: 200 }}
                  value={action} onChange={(v) => { setPage(1); setAction(v); }}
                  options={Object.keys(ACTION_COLOR).map((k) => ({ label: k, value: k }))} />
        }
      />

      <Card variant="borderless" style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="id" loading={loading} dataSource={rows}
          pagination={{ current: page, pageSize: 15, total, onChange: setPage,
                        showTotal: (t) => `共 ${t} 条` }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 180 },
            { title: '操作人', dataIndex: 'actor', width: 110 },
            {
              title: '动作', dataIndex: 'action', width: 160,
              render: (v: string) => <Tag color={ACTION_COLOR[v] || 'default'}>{v}</Tag>,
            },
            { title: '对象', width: 180,
              render: (_: any, r: any) => `${r.target_type || '—'} ${r.target_id || ''}` },
            {
              title: '前值', dataIndex: 'before_value', width: 180, ellipsis: true,
              render: (v: string) => v ? <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> : '—',
            },
            {
              title: '后值', dataIndex: 'after_value', ellipsis: true,
              render: (v: string) => v ? <Text style={{ fontSize: 12 }}>{v}</Text> : '—',
            },
          ]}
        />
      </Card>
    </div>
  );
}
