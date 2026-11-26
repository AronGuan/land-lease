import React from 'react';
import { Segmented, Tag } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';

export interface TabItem {
  label: string;
  path: string;
}

interface Props {
  /** 组名，如「系统管理」 */
  group: string;
  /** 组说明（Tab 名串联，如「计租标准·核算口径·模型·审计·设置」） */
  desc: string;
  tabs: TabItem[];
  /** 右侧额外操作（刷新、批量确认等），显示在 Tab 之后 */
  extra?: React.ReactNode;
  /** 是否显示「原型演示·数据为练习集样例」标记 */
  demo?: boolean;
}

/**
 * 页头条：左侧组名 + 说明，右侧页内 Segmented Tab（原型定稿形态）。
 * 通栏白条 + 灰底内容区，与系统原型.html 一致。
 */
export default function PageHead({ group, desc, tabs, extra, demo = true }: Props) {
  const nav = useNavigate();
  const loc = useLocation();
  // 精确匹配优先，其次前缀匹配（详情页高亮所属 Tab）
  const exact = tabs.find((t) => t.path === loc.pathname);
  const prefix = exact ? undefined : tabs.find((t) => loc.pathname.startsWith(t.path));
  const active = (exact ?? prefix)?.path ?? tabs[0]?.path;

  return (
    <div className="page-head">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span className="page-title">{group}</span>
        <span className="page-desc" style={{ marginTop: 0 }}>{desc}</span>
        {demo && (
          <Tag color="orange" style={{ fontSize: 11, margin: 0 }}>原型演示·数据为练习集样例</Tag>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Segmented
          value={active}
          onChange={(v) => nav(v as string)}
          options={tabs.map((t) => ({ label: t.label, value: t.path }))}
        />
        {extra}
      </div>
    </div>
  );
}
