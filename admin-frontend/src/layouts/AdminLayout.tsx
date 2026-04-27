import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, theme } from 'antd';
import {
  DashboardOutlined,
  PictureOutlined,
  UserSwitchOutlined,
  DatabaseOutlined,
  TeamOutlined,
  ShoppingOutlined,
  ToolOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../stores/authStore';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/admin', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/admin/aigc', icon: <PictureOutlined />, label: 'AIGC Control' },
  { key: '/admin/persona', icon: <UserSwitchOutlined />, label: 'Persona Lab' },
  { key: '/admin/memory', icon: <DatabaseOutlined />, label: 'Memory' },
  { key: '/admin/users', icon: <TeamOutlined />, label: 'Users & Safety' },
  { key: '/admin/commerce', icon: <ShoppingOutlined />, label: 'Commerce' },
  { key: '/admin/devops', icon: <ToolOutlined />, label: 'DevOps' },
];

const AdminLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken();

  const selectedKey = menuItems.find(
    (item) => location.pathname === item.key || (item.key !== '/admin' && location.pathname.startsWith(item.key))
  )?.key || '/admin';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider trigger={null} collapsible collapsed={collapsed} theme="dark">
        <div style={{ height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: collapsed ? 14 : 18 }}>
          {collapsed ? 'SP' : 'SoulPulse SDC'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 16px', background: colorBgContainer, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <Button type="text" icon={<LogoutOutlined />} onClick={() => { logout(); navigate('/admin/login'); }}>
            Logout
          </Button>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: colorBgContainer, borderRadius: borderRadiusLG, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AdminLayout;
