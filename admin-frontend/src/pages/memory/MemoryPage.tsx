import React, { useEffect, useState } from 'react';
import { Table, Button, Input, Space, Tabs, Card, Modal, Form, message, Tag, Popconfirm, Typography } from 'antd';
import { SearchOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;

const MemoryPage: React.FC = () => {
  const [tab, setTab] = useState('memories');
  const [memories, setMemories] = useState<any[]>([]);
  const [memTotal, setMemTotal] = useState(0);
  const [memPage, setMemPage] = useState(1);
  const [memLoading, setMemLoading] = useState(false);
  const [memFilters, setMemFilters] = useState({ user_id: '', ai_id: '' });

  const [anchors, setAnchors] = useState<any[]>([]);
  const [knowledge, setKnowledge] = useState<any[]>([]);
  const [knowledgeModal, setKnowledgeModal] = useState(false);
  const [kForm] = Form.useForm();

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const loadMemories = async (p = 1) => {
    setMemLoading(true);
    try {
      const params: any = { limit: 20, offset: (p - 1) * 20 };
      if (memFilters.user_id) params.user_id = Number(memFilters.user_id);
      if (memFilters.ai_id) params.ai_id = Number(memFilters.ai_id);
      const res = await client.get('/memories', { params });
      setMemories(res.data.memories);
      setMemTotal(res.data.total);
    } finally {
      setMemLoading(false);
    }
  };

  const loadAnchors = async () => {
    const res = await client.get('/anchors', { params: { limit: 100 } });
    setAnchors(res.data);
  };

  const loadKnowledge = async () => {
    const res = await client.get('/knowledge');
    setKnowledge(res.data);
  };

  useEffect(() => { loadMemories(); loadAnchors(); loadKnowledge(); }, []);

  const deleteMemory = async (id: number) => {
    await client.delete(`/memories/${id}`);
    message.success('Memory deleted');
    loadMemories(memPage);
  };

  const deleteAnchor = async (id: number) => {
    await client.delete(`/anchors/${id}`);
    message.success('Anchor deleted');
    loadAnchors();
  };

  const createKnowledge = async () => {
    const values = kForm.getFieldsValue();
    await client.post('/knowledge', values);
    message.success('Knowledge entry created');
    setKnowledgeModal(false);
    kForm.resetFields();
    loadKnowledge();
  };

  const deleteKnowledge = async (id: number) => {
    await client.delete(`/knowledge/${id}`);
    message.success('Knowledge entry deleted');
    loadKnowledge();
  };

  const doSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const res = await client.get('/memories/search/semantic', { params: { query: searchQuery, limit: 10 } });
      setSearchResults(res.data);
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div>
      <Title level={4}>Memory & Cognitive Management</Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'memories', label: 'Memories' },
        { key: 'anchors', label: 'Anchors' },
        { key: 'knowledge', label: 'Knowledge Base' },
        { key: 'search', label: 'Semantic Search' },
      ]} />

      {tab === 'memories' && (
        <div>
          <Space style={{ marginBottom: 16 }}>
            <Input placeholder="User ID" value={memFilters.user_id} onChange={(e) => setMemFilters({ ...memFilters, user_id: e.target.value })} style={{ width: 120 }} />
            <Input placeholder="AI ID" value={memFilters.ai_id} onChange={(e) => setMemFilters({ ...memFilters, ai_id: e.target.value })} style={{ width: 120 }} />
            <Button icon={<SearchOutlined />} onClick={() => { setMemPage(1); loadMemories(1); }}>Filter</Button>
          </Space>
          <Table dataSource={memories} rowKey="id" size="small" loading={memLoading}
            pagination={{ current: memPage, total: memTotal, pageSize: 20, onChange: (p) => { setMemPage(p); loadMemories(p); } }}>
            <Table.Column title="ID" dataIndex="id" width={60} />
            <Table.Column title="User" dataIndex="user_id" width={70} />
            <Table.Column title="AI" dataIndex="ai_id" width={60} />
            <Table.Column title="Type" dataIndex="memory_type" width={80} render={(t: string) => <Tag>{t}</Tag>} />
            <Table.Column title="Content" dataIndex="content" ellipsis />
            <Table.Column title="Created" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
            <Table.Column title="" width={60} render={(_: any, r: any) => (
              <Popconfirm title="Delete this memory?" onConfirm={() => deleteMemory(r.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            )} />
          </Table>
        </div>
      )}

      {tab === 'anchors' && (
        <Table dataSource={anchors} rowKey="id" size="small" pagination={{ pageSize: 20 }}>
          <Table.Column title="User" dataIndex="user_id" width={70} />
          <Table.Column title="AI" dataIndex="ai_id" width={60} />
          <Table.Column title="Type" dataIndex="anchor_type" width={100} render={(t: string) => <Tag>{t}</Tag>} />
          <Table.Column title="Content" dataIndex="content" ellipsis />
          <Table.Column title="Severity" dataIndex="severity" width={80} />
          <Table.Column title="Hits" dataIndex="hit_count" width={60} />
          <Table.Column title="" width={60} render={(_: any, r: any) => (
            <Popconfirm title="Delete?" onConfirm={() => deleteAnchor(r.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )} />
        </Table>
      )}

      {tab === 'knowledge' && (
        <div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setKnowledgeModal(true)} style={{ marginBottom: 16 }}>Add Entry</Button>
          <Table dataSource={knowledge} rowKey="id" size="small" pagination={{ pageSize: 20 }}>
            <Table.Column title="ID" dataIndex="id" width={60} />
            <Table.Column title="Category" dataIndex="category" width={120} render={(c: string) => <Tag>{c}</Tag>} />
            <Table.Column title="Content" dataIndex="content" ellipsis />
            <Table.Column title="Active" dataIndex="is_active" width={80} render={(v: number) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
            <Table.Column title="" width={60} render={(_: any, r: any) => (
              <Popconfirm title="Delete?" onConfirm={() => deleteKnowledge(r.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            )} />
          </Table>
          <Modal title="Add Knowledge Entry" open={knowledgeModal} onOk={createKnowledge} onCancel={() => setKnowledgeModal(false)}>
            <Form form={kForm} layout="vertical">
              <Form.Item name="category" label="Category" initialValue="general"><Input /></Form.Item>
              <Form.Item name="content" label="Content" rules={[{ required: true }]}><TextArea rows={4} /></Form.Item>
            </Form>
          </Modal>
        </div>
      )}

      {tab === 'search' && (
        <div>
          <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
            <Input placeholder="Semantic search query..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onPressEnter={doSearch} />
            <Button type="primary" icon={<SearchOutlined />} loading={searchLoading} onClick={doSearch}>Search</Button>
          </Space.Compact>
          {searchResults.map((r, i) => (
            <Card key={i} size="small" style={{ marginBottom: 8 }}>
              <p><strong>Collection:</strong> {r.collection} | <strong>Distance:</strong> {r.distance?.toFixed(4)}</p>
              <p>{r.content}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default MemoryPage;
