import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Space, Tag, message, Tabs, Card, Descriptions, Popconfirm, Typography } from 'antd';
import { SearchOutlined, StopOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;

interface User {
  id: number;
  email: string;
  nickname: string;
  avatar_url: string | null;
  gem_balance: number;
  is_admin: number;
  created_at: string;
}

const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState('list');
  const [detail, setDetail] = useState<any>(null);
  const [chatHistory, setChatHistory] = useState<any[]>([]);
  const [modLogs, setModLogs] = useState<any[]>([]);

  const loadUsers = async (p = 1, q = '') => {
    setLoading(true);
    try {
      const params: any = { limit: 20, offset: (p - 1) * 20 };
      if (q) params.search = q;
      const res = await client.get('/users', { params });
      setUsers(res.data.users);
      setTotal(res.data.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadUsers(); }, []);

  const viewUser = async (userId: number) => {
    const res = await client.get(`/users/${userId}`);
    setDetail(res.data);
    const chatRes = await client.get(`/users/${userId}/chat-history`, { params: { limit: 50 } });
    setChatHistory(chatRes.data);
    setTab('detail');
  };

  const toggleAdmin = async (userId: number, current: number) => {
    await client.post(`/users/${userId}/set-admin?is_admin=${current ? 0 : 1}`);
    message.success('Admin role updated');
    loadUsers(page, search);
  };

  const banUser = async (userId: number) => {
    await client.post(`/users/${userId}/ban`, null, { params: { reason: 'Admin action' } });
    message.success('User banned');
  };

  const loadModLogs = async () => {
    const res = await client.get('/moderation-logs', { params: { limit: 100 } });
    setModLogs(res.data);
  };

  useEffect(() => { if (tab === 'moderation') loadModLogs(); }, [tab]);

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: 'Email', dataIndex: 'email' },
    { title: 'Nickname', dataIndex: 'nickname', width: 120 },
    { title: 'Gems', dataIndex: 'gem_balance', width: 80 },
    { title: 'Admin', dataIndex: 'is_admin', width: 80, render: (v: number) => <Tag color={v ? 'blue' : 'default'}>{v ? 'Yes' : 'No'}</Tag> },
    { title: 'Created', dataIndex: 'created_at', width: 140, render: (d: string) => formatDateTime(d) },
    {
      title: 'Actions', width: 200,
      render: (_: any, r: User) => (
        <Space size="small">
          <Button size="small" onClick={() => viewUser(r.id)}>Detail</Button>
          <Button size="small" onClick={() => toggleAdmin(r.id, r.is_admin)}>{r.is_admin ? 'Revoke' : 'Grant'} Admin</Button>
          <Popconfirm title="Ban this user?" onConfirm={() => banUser(r.id)}>
            <Button size="small" danger icon={<StopOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={4}>Users & Trust Safety</Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'list', label: 'Users' },
        { key: 'detail', label: detail ? detail.nickname : 'Detail', disabled: !detail },
        { key: 'moderation', label: 'Moderation Logs' },
      ]} />

      {tab === 'list' && (
        <div>
          <Space style={{ marginBottom: 16 }}>
            <Input placeholder="Search email or nickname" value={search} onChange={(e) => setSearch(e.target.value)} onPressEnter={() => { setPage(1); loadUsers(1, search); }} style={{ width: 260 }} />
            <Button icon={<SearchOutlined />} onClick={() => { setPage(1); loadUsers(1, search); }}>Search</Button>
          </Space>
          <Table dataSource={users} columns={columns} rowKey="id" size="small" loading={loading}
            pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); loadUsers(p, search); } }} />
        </div>
      )}

      {tab === 'detail' && detail && (
        <div>
          <Card size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="ID">{detail.id}</Descriptions.Item>
              <Descriptions.Item label="Email">{detail.email}</Descriptions.Item>
              <Descriptions.Item label="Nickname">{detail.nickname}</Descriptions.Item>
              <Descriptions.Item label="Gender">{detail.gender}</Descriptions.Item>
              <Descriptions.Item label="Gems">{detail.gem_balance}</Descriptions.Item>
              <Descriptions.Item label="Messages">{detail.total_messages}</Descriptions.Item>
              <Descriptions.Item label="Admin">{detail.is_admin ? 'Yes' : 'No'}</Descriptions.Item>
              <Descriptions.Item label="Registered">{formatDateTime(detail.created_at)}</Descriptions.Item>
            </Descriptions>
          </Card>

          {detail.persona_interactions?.length > 0 && (
            <Card title="Persona Interactions" size="small" style={{ marginBottom: 16 }}>
              {detail.persona_interactions.map((pi: any) => (
                <Tag key={pi.ai_id}>AI #{pi.ai_id}: {pi.message_count} msgs</Tag>
              ))}
            </Card>
          )}

          <Card title="Chat History" size="small">
            <Table dataSource={chatHistory} rowKey="id" size="small" pagination={{ pageSize: 20 }}>
              <Table.Column title="AI" dataIndex="ai_id" width={60} />
              <Table.Column title="Role" dataIndex="role" width={80} render={(r: string) => <Tag color={r === 'user' ? 'blue' : 'green'}>{r}</Tag>} />
              <Table.Column title="Content" dataIndex="content" ellipsis />
              <Table.Column title="Time" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
            </Table>
          </Card>
        </div>
      )}

      {tab === 'moderation' && (
        <Table dataSource={modLogs} rowKey="id" size="small" pagination={{ pageSize: 20 }}>
          <Table.Column title="ID" dataIndex="id" width={60} />
          <Table.Column title="Type" dataIndex="content_type" width={120} render={(t: string) => <Tag>{t}</Tag>} />
          <Table.Column title="User" dataIndex="user_id" width={70} />
          <Table.Column title="Reason" dataIndex="reason" ellipsis />
          <Table.Column title="Action" dataIndex="action_taken" width={100} />
          <Table.Column title="Time" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
        </Table>
      )}
    </div>
  );
};

export default UsersPage;
