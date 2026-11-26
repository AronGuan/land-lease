import { Button, Card, Space, Tag, Typography, Alert, Table } from 'antd';
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

/** 核算口径（PRD 七 · 13 条），只读展示 */
const RULES = [
  { no: '三', title: '自然年度计收', desc: '年度应缴 = 适用年租金 × 计费月数 ÷ 12；起租当月与终止当月均计入；每年 6/30 前缴纳' },
  { no: '四(一)', title: '固定方式', desc: '按合同约定年租金；大小写不一致暂按大写并记问题清单' },
  { no: '四(二)', title: '随标准调整', desc: '面积 × 当年 1 月 1 日有效的计租标准，四舍五入到分' },
  { no: '四(三)', title: '面积口径', desc: '面积与登记不一致时暂按合同面积并记问题（存疑宗地按应缴最少暂算）' },
  { no: '四(四)', title: '涂改处理', desc: '涂改处有签章按涂改后值；无签章按第十二条存疑处理' },
  { no: '五', title: '期限口径', desc: '续期自原合同期满次日起；期满未续按最后合同计收至核算基准日（2026）；解除/收回计至当月' },
  { no: '六', title: '减免', desc: '先算当年应缴（舍入到分），再乘（1 − 减免比例）后舍入' },
  { no: '七', title: '实缴归集', desc: '重复票据计一次；按缴费日期与票据号排序；注明年度归该年（超额为多缴不冲抵）；未注明冲抵最早欠缴年' },
  { no: '八', title: '欠缴', desc: '欠缴 = 各年度应缴和 − 实缴和，不计滞纳金；负数为多缴' },
  { no: '九', title: '催缴对象', desc: '取登记现权利人，查不到取最新承租人；电话优先登记' },
  { no: '十', title: '旧地号映射', desc: '旧地号 09-05-0106 ↔ 单元号 000000009005GB00106F00089385（第 7-9/10-12/15-19 位）' },
  { no: '十一', title: '问题清单口径', desc: '问题清单只用 13 种类型；文件层填档案号，宗地层填宗地键' },
  { no: '十二', title: '存疑处理', desc: '不能确定算法时列出各种算法，按应缴最少（对产权人有利）暂算，列入问题清单待书面确认' },
];

const CODE_OF: Record<string, string> = {
  '三': 'calc.monthly_prorate', '四(一)': 'calc.applied_rent', '四(二)': 'calc.applied_rent',
  '四(三)': 'issue', '四(四)': 'doc.parse', '五': 'calc.timeline', '六': 'calc.reduction',
  '七': 'alloc.allocate', '八': 'calc.arrears', '九': 'dunning.resolve', '十': 'match.unit_no',
  '十一': 'issue', '十二': 'calc.ambiguous',
};

export default function CalcRules() {
  return (
    <div>
      <PageHead group="系统管理" desc="计租标准·核算口径·模型·审计·设置" tabs={TABS}
        extra={<Tag color="blue">v1.2</Tag>} />

      <Alert
        type="success" showIcon style={{ marginBottom: 16 }}
        message="口径已验证：练习集 30/30 宗地、618/618 年度；盲测 test_20 4/4 宗地、92/92 年度（100%）"
      />

      <Card
        size="small"
        title="核算口径 v1.2"
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}
        extra={
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>核算基准日 2026-09-30</Text>
            <Button size="small">升级版本</Button>
            <Button size="small">查看历史</Button>
          </Space>
        }
      >
        <Table
          size="small"
          rowKey="no"
          pagination={false}
          dataSource={RULES}
          columns={[
            {
              title: '条', dataIndex: 'no', width: 80,
              render: (v: string) => <Tag color="blue">{v}</Tag>,
            },
            { title: '规则', dataIndex: 'desc' },
            {
              title: '系统落点', dataIndex: 'no', width: 190,
              render: (v: string) => <Text code style={{ fontSize: 12 }}>{CODE_OF[v] || '—'}</Text>,
            },
          ]}
        />
      </Card>

      <Card
        size="small"
        title="核算留痕示例（rent_calc_trace）"
        variant="borderless"
        style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 12 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>每一笔账都能解释</Text>}
      >
        <div style={{ fontSize: 13, lineHeight: 1.9 }}>
          <b>对象</b>：LX-001 / 2016 年　<b>口径版本</b> v1.2<br />
          <b>输入快照</b>：计租方式=固定；年租金小写 3,998.25；大写 叁仟玖佰玖拾捌元贰角伍分；面积 8,885.00；计费月数 12<br />
          <b>公式</b>：适用年租金 3,998.25 × 12 ÷ 12 = 3,998.25（固定方式，不随标准调整）<br />
          <b>输出</b>：应缴 3,998.25　实缴 0.00　欠缴 3,998.25<br />
          <b>关联问题</b>：<Tag color="orange">关键字段有涂改（年租金，涂改前有签章 → 按涂改后 3,998.25）</Tag>
        </div>
      </Card>

      <Card size="small" title="计算纪律" variant="borderless"
            style={{ marginTop: 16, border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 2 }}>
          <li>金额一律 <Text code>DECIMAL(14,2)</Text>，禁用 float 存库；运算链与标准答案生成器对齐</li>
          <li>评分容差 <Text code>±0.01</Text> 元</li>
          <li>每次核算落 <Text code>rent_calc_trace</Text>（输入快照 + 公式 + 口径版本），保证可解释可复核</li>
        </ul>
      </Card>
    </div>
  );
}
