import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { App, Button, Card, Input, Select, Space, Table, Tag, Typography } from 'antd';
import { CheckCircleOutlined, DownloadOutlined } from '@ant-design/icons';
import { api, Issue } from '../api/client';
import PageHead from '../components/PageHead';
import { TOKENS } from '../theme';

const { Text } = Typography;

const TABS = [
  { label: '批次导入', path: '/contract/batch' },
  { label: '复核工作台', path: '/contract/review' },
  { label: '问题清单', path: '/contract/issues' },
];

/** 13 类问题清单（文件层 / 宗地层 / 通用） */
const TYPE_COLOR: Record<string, string> = {
  关键字段有涂改: 'volcano', 合同缺页: 'red', 缺宗地图: 'orange',
  年租金大小写不一致: 'gold', 证件号码异常: 'magenta', 联系电话缺失或无效: 'cyan',
  坐落或宗地号与登记不一致: 'blue', 面积与登记不一致: 'geekblue',
  合同到期未续: 'purple', 承租人已变更未办合同变更: 'lime',
  登记数据中无对应宗地: 'default', 缴费记录异常: 'gold', 存疑待确认: 'red',
};

export default function IssueList() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Issue[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [types, setTypes] = useState<string[]>([]);
  // 支持从「系统管理 → 问题类型」跳转带入筛选：/contract/issues?issue_type=xxx&status=open
  const [params] = useSearchParams();
  const [type, setType] = useState<string | undefined>(params.get('issue_type') || undefined);
  // 有 status 参数时按传入值（空串 = 全部），否则默认只看未消解
  const [status, setStatus] = useState<string>(
    params.has('status') ? (params.get('status') || '') : 'open');
  const [kw, setKw] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.issueTypes().then(setTypes); }, []);

  /** 全量累计（含已消解），用于提示「只看未消解」时漏掉多少 */
  const [allTotal, setAllTotal] = useState(0);
  useEffect(() => {
    api.issueTypeStats()
      .then((r) => setAllTotal(Object.values(r.stats || {})
        .reduce((a: number, s: any) => a + (s?.total || 0), 0)))
      .catch(() => {});
  }, [rows]);

  const load = () => {
    setLoading(true);
    api.issues({ page, page_size: 10, issue_type: type, status: status || undefined, keyword: kw || undefined })
      .then((r) => { setRows(r.items); setTotal(r.total); })
      .finally(() => setLoading(false));
  };
  useEffect(load, [page, type, status, kw]);

  const resolve = async (id: number) => {
    await api.resolveIssue(id);
    message.success('已消解并留痕');
    load();
  };

  return (
    <div>
      <PageHead group="合同治理" desc="批次导入·复核工作台·问题清单" tabs={TABS}
        extra={
          <Space wrap>
            <Input.Search placeholder="档案号 / 说明" allowClear style={{ width: 200 }}
                          onSearch={(v) => { setPage(1); setKw(v); }} />
            <Select placeholder="问题类型" allowClear style={{ width: 180 }}
                    value={type} onChange={(v) => { setPage(1); setType(v); }}
                    options={types.map((t) => ({ label: t, value: t }))} />
            <Select style={{ width: 110 }} value={status}
                    onChange={(v) => { setPage(1); setStatus(v); }}
                    options={[
                      { label: '未消解', value: 'open' },
                      { label: '已消解', value: 'resolved' },
                      { label: '全部', value: '' },
                    ]} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {total} 条
              {status === 'open' && allTotal > total && `（含已消解共 ${allTotal} 条）`}
            </Text>
          </Space>
        }
      />

      <Card size="small" title="问题清单 · 逐条处理" variant="borderless"
            extra={<Button size="small" onClick={() => message.info('导出待确认清单为交付成果第 3 项（演示占位）')}>导出待确认清单</Button>}
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="id" loading={loading} dataSource={rows}
          pagination={{
            current: page, pageSize: 10, total, showTotal: (t) => `共 ${t} 条`,
            onChange: (p) => setPage(p),
          }}
          columns={[
            { title: '档案号 / 宗地', dataIndex: 'target', width: 120 },
            {
              title: '问题类型', dataIndex: 'issue_type', width: 190,
              render: (v: string) => <Tag color={TYPE_COLOR[v] || 'default'}>{v}</Tag>,
            },
            { title: '说明', dataIndex: 'description', ellipsis: true },
            {
              title: '暂算算法', dataIndex: 'temp_algorithm', width: 180, ellipsis: true,
              render: (v: string) => v ? <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> : '—',
            },
            {
              title: '差额', dataIndex: 'diff_amount', width: 110, align: 'right' as const,
              render: (v: string) => v ? <span style={{ color: TOKENS.warning }}>{v}</span> : '—',
            },
            {
              title: '状态', dataIndex: 'status', width: 90,
              render: (v: string) => v === 'open'
                ? <Tag color="red">未消解</Tag> : <Tag color="green">已消解</Tag>,
            },
            {
              title: '操作', width: 100,
              render: (_: any, r: Issue) => r.status === 'open' ? (
                <Button size="small" type="link" icon={<CheckCircleOutlined />}
                        onClick={() => resolve(r.id)}>消解</Button>
              ) : <Text type="secondary" style={{ fontSize: 12 }}>—</Text>,
            },
          ]}
          scroll={{ x: 1100 }}
        />
        <div className="note" style={{ marginTop: 8 }}>
          ※ 存疑事项（第 12 条口径）：资料说不清、可有两种以上算法的，按对产权人有利的算法暂算，列入待确认清单；正式落地时向主管部门书面确认。
        </div>
      </Card>
    </div>
  );
}
