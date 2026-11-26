import { useEffect, useMemo, useState } from 'react';
import { App, Button, Card, Table, Tag, Typography, Upload } from 'antd';
import { ImportOutlined } from '@ant-design/icons';
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

const USAGE_ORDER = ['商服', '住宅', '工业', '仓储'];
const LEVEL_ORDER = ['一级', '二级', '三级', '四级'];

export default function Standards() {
  const { message } = App.useApp();
  const [standards, setStandards] = useState<any[]>([]);
  const [streets, setStreets] = useState<any[]>([]);
  const [reductions, setReductions] = useState<any[]>([]);

  useEffect(() => {
    api.standards().then(setStandards);
    api.streetLevels().then(setStreets);
    api.reductions().then(setReductions);
  }, []);

  /** 宽表：用途 × 级别 为行，执行起始日（版本）为列（对齐原型） */
  const { versions, rows } = useMemo(() => {
    const vset = new Set<string>();
    standards.forEach((s) => vset.add(s.effective_from));
    const versions = [...vset].sort();
    const map = new Map<string, any>();
    standards.forEach((s) => {
      const k = `${s.land_usage}|${s.land_level}`;
      if (!map.has(k)) map.set(k, { key: k, land_usage: s.land_usage, land_level: s.land_level });
      map.get(k)[s.effective_from] = Number(s.price);
    });
    const rows = [...map.values()].sort((a, b) => {
      const ua = USAGE_ORDER.indexOf(a.land_usage), ub = USAGE_ORDER.indexOf(b.land_usage);
      if (ua !== ub) return ua - ub;
      return LEVEL_ORDER.indexOf(a.land_level) - LEVEL_ORDER.indexOf(b.land_level);
    });
    return { versions, rows };
  }, [standards]);

  return (
    <div>
      <PageHead group="系统管理" desc="计租标准·核算口径·模型·审计·设置" tabs={TABS} />

      <Card
        size="small"
        title={
          <span>
            计租标准（元/平方米·年）
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
              四套标准，按公布日生效
            </Text>
          </span>
        }
        variant="borderless"
        style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}
        extra={
          <Upload
            accept=".xlsx,.xls"
            showUploadList={false}
            beforeUpload={() => {
              message.info('标准导入为后续开发项（当前由 seed 脚本灌入）');
              return false;
            }}
          >
            <Button size="small" icon={<ImportOutlined />}>导入/更新标准</Button>
          </Upload>
        }
      >
        <Table
          size="small"
          rowKey="key"
          dataSource={rows}
          pagination={false}
          columns={[
            { title: '用途', dataIndex: 'land_usage', width: 100 },
            { title: '土地级别', dataIndex: 'land_level', width: 110 },
            ...versions.map((v, i) => ({
              title: (
                <div style={{ lineHeight: 1.3 }}>
                  <div>{v.slice(0, 4)} 版</div>
                  <div style={{ fontSize: 11, color: 'rgba(0,0,0,.45)', fontWeight: 400 }}>
                    {v} 起{i === versions.length - 1 ? '（现行）' : ''}
                  </div>
                </div>
              ),
              dataIndex: v,
              align: 'right' as const,
              render: (val: number) => val === undefined ? '—' : (
                <span
                  className="num-cell"
                  style={{
                    fontWeight: i === versions.length - 1 ? 600 : 400,
                    color: i === versions.length - 1 ? '#1677ff' : undefined,
                  }}
                >
                  {val.toFixed(2)}
                </span>
              ),
            })),
          ]}
        />
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            适用规则：随标准调整型按「当年 1 月 1 日有效的标准」取价（口径四(二)）；固定型按合同约定年租金。
          </Text>
        </div>
      </Card>

      <Card size="small" title={`土地级别范围（${streets.length} 条街路）`} variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginBottom: 16 }}>
        <Table
          size="small" rowKey="street_name" dataSource={streets} pagination={{ pageSize: 8 }}
          columns={[
            { title: '街路', dataIndex: 'street_name' },
            {
              title: '级别', dataIndex: 'land_level', width: 100,
              render: (v: string) => <Tag color="blue">{v}</Tag>,
            },
          ]}
        />
      </Card>

      <Card size="small" title={`减免登记（${reductions.length} 条）`} variant="borderless"
            style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
        <Table
          size="small" rowKey="id" dataSource={reductions} pagination={false}
          columns={[
            { title: '宗地键', dataIndex: 'parcel_key', width: 110 },
            { title: '起始年度', dataIndex: 'from_year', width: 100 },
            { title: '终止年度', dataIndex: 'to_year', width: 100 },
            {
              title: '减免比例', dataIndex: 'ratio', width: 110,
              render: (v: string) => `${(Number(v) * 100).toFixed(0)}%`,
            },
            { title: '批准文号', dataIndex: 'doc_no' },
          ]}
        />
      </Card>
    </div>
  );
}
