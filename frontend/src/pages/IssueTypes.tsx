import { useEffect, useState } from 'react';
import { Alert, Card, Space, Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
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

/** 第十一条 表 1：13 种问题类型（封闭集合，判定口径照录原文） */
const SPEC: { name: string; level: string; rule: string }[] = [
  { name: '关键字段有涂改', level: '文件', rule: '土地面积、租赁终止日期、年租金、联系电话等处有划改' },
  { name: '合同缺页', level: '文件', rule: '合同页数不全，如缺签章页' },
  { name: '缺宗地图', level: '文件', rule: '新签或续期合同未附宗地图；变更协议不要求附图' },
  { name: '年租金大小写不一致', level: '文件', rule: '年租金小写与大写金额不一致' },
  { name: '证件号码异常', level: '文件', rule: '个人证件号码为 15 位旧号码，或 18 位号码校验位不对' },
  { name: '联系电话缺失或无效', level: '文件', rule: '未填联系电话，或位数不是 11 位' },
  { name: '坐落或宗地号与登记不一致', level: '文件', rule: '逐份文件与登记比对：坐落写法与登记不同（如"街"与"大街"、汉字门牌号、加"院"字、以县名代替镇名、无门牌号），或宗地号对应不上；旧地号省略前导零不算' },
  { name: '面积与登记不一致', level: '文件', rule: '新签或续期合同的土地面积与登记面积不同' },
  { name: '合同到期未续', level: '宗地', rule: '最后一份合同已在核算基准日前期满，未见续期合同' },
  { name: '承租人已变更未办合同变更', level: '宗地', rule: '登记权利人与最新合同承租人不同，且没有变更协议' },
  { name: '登记数据中无对应宗地', level: '宗地', rule: '登记导出中查不到该宗地' },
  { name: '缴费记录异常', level: '宗地', rule: '票据号重复登记；缴款人既不是任何一份合同或变更协议的承租人，也不是登记权利人；注明年度的缴款与当年应缴不符' },
  { name: '存疑待确认', level: '文件/宗地', rule: '按第十二条暂算的事项。填引起存疑的文件；涉及两份合同的，填签订较晚的一份；存疑之处不在合同上的（如减免、缴费），填宗地键' },
];

const LEVEL_COLOR: Record<string, string> = { '文件': 'blue', '宗地': 'green', '文件/宗地': 'purple' };

export default function IssueTypes() {
  const nav = useNavigate();
  const [stats, setStats] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.issueTypeStats()
      .then((r) => setStats(r.stats || {}))
      .finally(() => setLoading(false));
  }, []);

  const rows = SPEC.map((s) => ({ ...s, stat: stats[s.name] || { open: 0, resolved: 0, total: 0 } }));
  const totalOpen = rows.reduce((a, r) => a + r.stat.open, 0);
  const totalAll = rows.reduce((a, r) => a + r.stat.total, 0);
  const used = rows.filter((r) => r.stat.total > 0).length;

  return (
    <div>
      <PageHead group="系统管理" desc="计租标准·核算口径·问题类型·模型·审计·设置" tabs={TABS}
        extra={<Tag color="blue">第十一条 · 表 1</Tag>} />

      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="问题清单只使用以下 13 种类型，不得自创（第十一条）"
        description={
          <span style={{ fontSize: 12 }}>
            合同文件层面的问题填该文件的<b>档案号</b>；宗地层面的问题填该宗地<b>宗地键</b>
            （即该宗地最新一份新签或续期合同的档案号）。
            当前已用 {used}/13 类，累计 {totalAll} 条，其中<b>未消解 {totalOpen} 条</b>、
            已消解 {totalAll - totalOpen} 条。
            <br />
            口径说明：确认入库时该档案的未消解问题会自动置为「已消解」并留痕（不删除），
            所以「累计」是历史总量，「未消解」才是当前待办；
            问题清单页默认只看未消解，两处数字应相差已消解部分。
          </span>
        }
      />

      <Card
        size="small"
        title="问题类型与判定口径"
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>点击条数可跳问题清单查看</Text>}
      >
        <Table
          size="small" rowKey="name" pagination={false} loading={loading}
          dataSource={rows}
          columns={[
            {
              title: '问题类型', dataIndex: 'name', width: 210,
              render: (v: string) => <Text strong>{v}</Text>,
            },
            {
              title: '层面', dataIndex: 'level', width: 90,
              render: (v: string) => <Tag color={LEVEL_COLOR[v] || 'default'}>{v}</Tag>,
            },
            { title: '判定口径', dataIndex: 'rule' },
            {
              title: '未消解（待办）', dataIndex: ['stat', 'open'], width: 110, align: 'right' as const,
              render: (v: number, r: any) => (
                <a onClick={() => nav(`/contract/issues?issue_type=${encodeURIComponent(r.name)}&status=open`)}
                   style={{ color: v > 0 ? '#cf1322' : undefined }}>
                  {v || '—'}
                </a>
              ),
            },
            {
              title: '累计（含已消解）', dataIndex: ['stat', 'total'], width: 130, align: 'right' as const,
              render: (v: number, r: any) => (
                <a onClick={() => nav(`/contract/issues?issue_type=${encodeURIComponent(r.name)}&status=`)}>
                  {v || '—'}
                </a>
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" title="填写纪律" variant="borderless"
            style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Space direction="vertical" size={4} style={{ fontSize: 13, lineHeight: 1.9 }}>
          <div>· 类型取值自 <Text code>grouping.ISSUE_TYPES</Text>，接口与界面同源，杜绝手写错字</div>
          <div>· 同一档案同一类型只记一条，避免字段层与登记比对重复</div>
          <div>· 复核入库时该档案的未消解问题自动置为已消解并留痕；撤回后重新打开</div>
          <div>· 存疑事项（第十二条）要写清：存疑之处、暂按哪种算法、与应缴最多的算法相差多少元</div>
        </Space>
      </Card>
    </div>
  );
}
