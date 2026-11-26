import { useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Radio, Row, Space, Table, Tag, Typography, Upload,
} from 'antd';
import { DatabaseOutlined, InboxOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import PageHead from '../components/PageHead';

const { Text } = Typography;

const TABS = [
  { label: '数据导入', path: '/data/import' },
  { label: '重算与差异', path: '/data/recalc' },
];

const KIND_ORDER = ['registry', 'payments', 'reductions', 'standards'];

export default function RefDataImport() {
  const { message, modal } = App.useApp();
  const [status, setStatus] = useState<any>(null);
  const [kind, setKind] = useState<string>('registry');
  const [mode, setMode] = useState<string>('replace');
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.refdataStatus().then(setStatus);
  useEffect(() => { load(); }, []);

  const upload = async (file: File) => {
    setBusy(true);
    try {
      const r = await api.refdataPreview(kind, file);
      setPreview(r);
      if (r.warnings?.length) message.warning(r.warnings.join('；'));
      else message.success(`解析成功：${r.row_count} 行`);
    } catch (e: any) {
      message.error(`解析失败：${e?.response?.data?.detail || e.message || e}`);
    } finally {
      setBusy(false);
    }
  };

  const commit = () => {
    if (!preview) return;
    modal.confirm({
      title: `确认导入「${preview.label}」${preview.row_count} 行？`,
      width: 560,
      content: (
        <div style={{ marginTop: 12, fontSize: 13 }}>
          <div>
            方式：
            <b>{mode === 'replace' ? '全量替换' : '追加'}</b>
            {mode === 'replace' && (
              <Text type="danger"> （现有 {status?.data?.[kind]?.row_count ?? 0} 行将被清空）</Text>
            )}
          </div>
          <div style={{ marginTop: 6 }}>影响：{preview.affects}</div>
          <div style={{ marginTop: 6 }}>导入后将自动重新归集并全量重算应缴 / 欠缴。</div>
        </div>
      ),
      okText: '确认导入', cancelText: '取消',
      onOk: async () => {
        setBusy(true);
        try {
          const r = await api.refdataCommit({ token: preview.token, kind, mode, operator: '张贯贯' });
          const rl = r.relink || {};
          message.success(
            `导入完成：${r.rows_before} → ${r.rows_after} 行；`
            + `重算 ${rl.parcel_count ?? 0} 宗，${rl.changed_count ?? 0} 宗金额有变化`,
          );
          setPreview(null);
          await load();
        } catch (e: any) {
          message.error(`导入失败：${e?.response?.data?.detail || e.message || e}`);
        } finally {
          setBusy(false);
        }
      },
    });
  };

  return (
    <div>
      <PageHead group="基础数据" desc="02 登记 · 03 缴费 · 04 减免 · 05 标准的导入与重算" tabs={TABS} />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card size="small" title="上传参考数据" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>数据类型</Text>
                <div style={{ marginTop: 6 }}>
                  <Radio.Group value={kind} onChange={(e) => { setKind(e.target.value); setPreview(null); }}>
                    <Space wrap>
                      {KIND_ORDER.map((k) => (
                        <Radio.Button key={k} value={k}>
                          {status?.kinds?.[k]?.label || k}
                        </Radio.Button>
                      ))}
                    </Space>
                  </Radio.Group>
                </div>
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>导入方式</Text>
                <div style={{ marginTop: 6 }}>
                  <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
                    <Radio value="replace">全量替换</Radio>
                    <Radio value="append">追加</Radio>
                  </Radio.Group>
                </div>
              </div>
              <Upload.Dragger
                accept=".xlsx,.xls,.csv"
                showUploadList={false}
                beforeUpload={(f) => { upload(f as File); return false; }}
              >
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p style={{ fontSize: 13 }}>
                  点击或拖放 {status?.kinds?.[kind]?.source || ''}
                </p>
                <p style={{ fontSize: 12, color: 'rgba(0,0,0,.45)' }}>
                  {status?.kinds?.[kind]?.desc || ''}
                </p>
              </Upload.Dragger>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card size="small" title="库内现状" variant="borderless"
                style={{ border: '1px solid #f0f0f0', borderRadius: 12 }}>
            <Table
              size="small" rowKey="kind" pagination={false}
              dataSource={KIND_ORDER.map((k) => ({ kind: k, ...(status?.data?.[k] || {}) }))}
              columns={[
                { title: '类型', dataIndex: 'label', width: 130 },
                { title: '行数', dataIndex: 'row_count', width: 70, align: 'right' as const,
                  render: (v: number) => v ?? '—' },
                { title: '最近导入', dataIndex: 'last_import_at',
                  render: (v: string) => v ? v.slice(0, 16).replace('T', ' ') : <Text type="secondary">由 seed 灌入</Text> },
              ]}
            />
            {status?.data?.standards?.street_level_count != null && (
              <div className="note" style={{ marginTop: 8 }}>
                街路→土地级别：{status.data.standards.street_level_count} 条
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {preview && (
        <Card size="small" style={{ border: '1px solid #f0f0f0', borderRadius: 12, marginTop: 16 }}
              variant="borderless"
              title={<>解析预览 · {preview.label}
                <Tag color="blue" style={{ marginLeft: 8 }}>{preview.row_count} 行</Tag>
              </>}
              extra={
                <Space>
                  <Button size="small" onClick={() => setPreview(null)}>取消</Button>
                  <Button size="small" type="primary" loading={busy} onClick={commit}>确认导入</Button>
                </Space>
              }>
          {preview.warnings?.length > 0 && (
            <Alert type="warning" showIcon style={{ marginBottom: 10 }}
                   message={preview.warnings.join('；')} />
          )}
          <Space size={16} wrap style={{ marginBottom: 10, fontSize: 12 }}>
            <Text type="secondary">工作表：{preview.sheets?.join(' / ')}</Text>
            {preview.duplicate_key && (
              <Text type={preview.duplicate_count ? 'warning' : 'secondary'}>
                {preview.duplicate_key} 重复 {preview.duplicate_count} 条
              </Text>
            )}
            {Object.keys(preview.blank_required || {}).length > 0 && (
              <Text type="warning">
                必备列空值：
                {Object.entries(preview.blank_required).map(([k, v]) => `${k} ${v}`).join('、')}
              </Text>
            )}
            {preview.street_level_count != null && (
              <Text type="secondary">街路级别 {preview.street_level_count} 条</Text>
            )}
          </Space>
          <Table
            size="small" rowKey={(_: any, i?: number) => String(i)} pagination={false}
            dataSource={preview.sample}
            columns={(preview.columns || []).slice(0, 6).map((c: string) => ({
              title: c, dataIndex: c, ellipsis: true,
              render: (v: any) => v === null || v === undefined ? '—' : String(v),
            }))}
          />
          <div className="note" style={{ marginTop: 8 }}>
            仅预览前 5 行 · 影响范围：{preview.affects}
          </div>
        </Card>
      )}

      <div className="note" style={{ marginTop: 12 }}>
        <DatabaseOutlined /> 导入只改基础数据，不碰合同本身；确认后立即重新归集缴费/减免并全量重算，
        变更明细见「重算与差异」。
      </div>
    </div>
  );
}
