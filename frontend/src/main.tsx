import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import 'antd/dist/reset.css';
import './index.css';
import App from './App';
import { TOKENS } from './theme';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: TOKENS.colorPrimary,
          colorSuccess: TOKENS.success,
          colorWarning: TOKENS.warning,
          colorError: TOKENS.error,
          borderRadius: TOKENS.radius,
          colorBgLayout: TOKENS.bgLayout,
        },
        components: {
          Table: { headerBg: '#fafafa', rowHoverBg: '#fafafa' },
          Card: { borderRadiusLG: TOKENS.radiusLg },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
