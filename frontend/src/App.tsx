import { useState } from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  DashboardOutlined,
  FileSearchOutlined,
  AccountBookOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ReviewWorkbench from './pages/ReviewWorkbench';
import BatchImport from './pages/BatchImport';
import IssueList from './pages/IssueList';
import ArrearsBoard from './pages/ArrearsBoard';
import ParcelLedger from './pages/ParcelLedger';
import ContractGen from './pages/ContractGen';
import ExpiryCalendar from './pages/ExpiryCalendar';
import Dunning from './pages/Dunning';
import GovernanceProgress from './pages/GovernanceProgress';
import TaxPush from './pages/TaxPush';
import Standards from './pages/Standards';
import CalcRules from './pages/CalcRules';
import RefDataImport from './pages/RefDataImport';
import RefDataRecalc from './pages/RefDataRecalc';
import IssueTypes from './pages/IssueTypes';
import ModelMgmt from './pages/ModelMgmt';
import AuditLog from './pages/AuditLog';
import Settings from './pages/Settings';

const { Header, Sider, Content } = Layout;

/** 6 组导航（对齐 PRD 五 / 系统原型） */
const NAV = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/contract', icon: <FileSearchOutlined />, label: '合同治理' },
  { key: '/collection', icon: <AccountBookOutlined />, label: '收缴管理' },
  { key: '/ledger', icon: <AppstoreOutlined />, label: '宗地台账' },
  { key: '/report', icon: <BarChartOutlined />, label: '统计报表' },
  { key: '/data', icon: <DatabaseOutlined />, label: '基础数据' },
  { key: '/system', icon: <SettingOutlined />, label: '系统管理' },
];

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const loc = useLocation();
  const nav = useNavigate();
  const group = '/' + (loc.pathname.split('/')[1] || 'dashboard');

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} trigger={null} theme="dark" width={200}>
        <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography.Text style={{ color: '#fff', fontWeight: 600, fontSize: collapsed ? 12 : 14 }}>
            {collapsed ? '租赁' : '国有土地租赁管理'}
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[group]}
          items={NAV}
          onClick={(e) => nav(e.key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff', padding: '0 16px', height: 56, lineHeight: '56px',
            display: 'flex', alignItems: 'center', gap: 12,
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <span
            onClick={() => setCollapsed(!collapsed)}
            style={{ cursor: 'pointer', fontSize: 16, color: 'rgba(0,0,0,.65)' }}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </span>
          <Typography.Text strong>
            {NAV.find((n) => n.key === group)?.label || '工作台'}
          </Typography.Text>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: 'rgba(0,0,0,.45)' }}>
            核算基准日 2026-09-30 · 口径 v1.2
          </span>
        </Header>
        <Content className="app-content">
          <div className="app-content-inner">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/contract/review" element={<ReviewWorkbench />} />
              <Route path="/contract/batch" element={<BatchImport />} />
              <Route path="/contract/issues" element={<IssueList />} />
              {/* 合同治理默认落到首个 Tab：批次导入（导入 → 复核 → 问题清单） */}
              <Route path="/contract" element={<Navigate to="/contract/batch" replace />} />
              <Route path="/collection" element={<ArrearsBoard />} />
              <Route path="/collection/expiry" element={<ExpiryCalendar />} />
              <Route path="/collection/dunning" element={<Dunning />} />
              <Route path="/ledger" element={<ParcelLedger />} />
              <Route path="/ledger/contract-gen" element={<ContractGen />} />
              <Route path="/report" element={<GovernanceProgress />} />
              <Route path="/data/import" element={<RefDataImport />} />
              <Route path="/data/recalc" element={<RefDataRecalc />} />
              {/* 基础数据默认落到首个 Tab：数据导入 */}
              <Route path="/data" element={<Navigate to="/data/import" replace />} />
              <Route path="/report/tax" element={<TaxPush />} />
              <Route path="/system" element={<Standards />} />
              <Route path="/system/rules" element={<CalcRules />} />
              <Route path="/system/issue-types" element={<IssueTypes />} />
              <Route path="/system/models" element={<ModelMgmt />} />
              <Route path="/system/audit" element={<AuditLog />} />
              <Route path="/system/settings" element={<Settings />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
