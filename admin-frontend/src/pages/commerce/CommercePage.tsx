import React, { useEffect, useState } from 'react';
import { Table, Button, Tabs, Modal, Form, Input, InputNumber, Select, Space, Tag, message, Popconfirm, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, DownloadOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;

const CommercePage: React.FC = () => {
  const [tab, setTab] = useState('gacha');
  const [gachas, setGachas] = useState<any[]>([]);
  const [gifts, setGifts] = useState<any[]>([]);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [txTotal, setTxTotal] = useState(0);
  const [txPage, setTxPage] = useState(1);
  const [revenue, setRevenue] = useState<any>(null);

  const [gachaModal, setGachaModal] = useState(false);
  const [giftModal, setGiftModal] = useState(false);
  const [editingGacha, setEditingGacha] = useState<any>(null);
  const [editingGift, setEditingGift] = useState<any>(null);
  const [gForm] = Form.useForm();
  const [giftForm] = Form.useForm();

  const loadGachas = async () => { const res = await client.get('/gacha'); setGachas(res.data); };
  const loadGifts = async () => { const res = await client.get('/gifts'); setGifts(res.data); };
  const loadTransactions = async (p = 1) => {
    const res = await client.get('/transactions', { params: { limit: 20, offset: (p - 1) * 20 } });
    setTransactions(res.data.transactions);
    setTxTotal(res.data.total);
  };
  const loadRevenue = async () => { const res = await client.get('/revenue/summary'); setRevenue(res.data); };

  useEffect(() => { loadGachas(); loadGifts(); loadTransactions(); loadRevenue(); }, []);

  const saveGacha = async () => {
    const values = gForm.getFieldsValue();
    if (editingGacha) {
      await client.put(`/gacha/${editingGacha.id}`, values);
    } else {
      await client.post('/gacha', values);
    }
    message.success('Saved');
    setGachaModal(false); setEditingGacha(null); gForm.resetFields();
    loadGachas();
  };

  const saveGift = async () => {
    const values = giftForm.getFieldsValue();
    if (editingGift) {
      await client.put(`/gifts/${editingGift.id}`, values);
    } else {
      await client.post('/gifts', values);
    }
    message.success('Saved');
    setGiftModal(false); setEditingGift(null); giftForm.resetFields();
    loadGifts();
  };

  return (
    <div>
      <Title level={4}>Commercial Operations</Title>

      {revenue && (
        <div style={{ marginBottom: 16, display: 'flex', gap: 16 }}>
          <Tag color="blue">Gems Spent (30d): {revenue.total_gems_spent}</Tag>
          <Tag color="green">Gems Earned (30d): {revenue.total_gems_earned}</Tag>
          <Tag>Transactions: {revenue.transaction_count}</Tag>
        </div>
      )}

      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'gacha', label: 'Gacha Scripts' },
        { key: 'gifts', label: 'Virtual Gifts' },
        { key: 'transactions', label: 'Transactions' },
      ]} />

      {tab === 'gacha' && (
        <div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingGacha(null); gForm.resetFields(); setGachaModal(true); }} style={{ marginBottom: 16 }}>Add Script</Button>
          <Table dataSource={gachas} rowKey="id" size="small" pagination={false}>
            <Table.Column title="Title" dataIndex="title" />
            <Table.Column title="Persona" dataIndex="persona_id" width={80} />
            <Table.Column title="Cost" dataIndex="gem_cost" width={80} />
            <Table.Column title="Active" dataIndex="is_active" width={80} render={(v: number) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
            <Table.Column title="" width={120} render={(_: any, r: any) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => { setEditingGacha(r); gForm.setFieldsValue(r); setGachaModal(true); }} />
                <Popconfirm title="Delete?" onConfirm={async () => { await client.delete(`/gacha/${r.id}`); loadGachas(); }}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            )} />
          </Table>
          <Modal title={editingGacha ? 'Edit Script' : 'New Script'} open={gachaModal} onOk={saveGacha} onCancel={() => setGachaModal(false)} width={600}>
            <Form form={gForm} layout="vertical">
              <Form.Item name="title" label="Title" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="persona_id" label="Persona ID" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} /></Form.Item>
              <Form.Item name="gem_cost" label="Gem Cost" initialValue={10}><InputNumber min={0} /></Form.Item>
              <Form.Item name="system_prompt_override" label="System Prompt Override"><TextArea rows={3} /></Form.Item>
              <Form.Item name="storyline_json" label="Storyline JSON" initialValue="[]"><TextArea rows={3} /></Form.Item>
              <Form.Item name="is_active" label="Active" initialValue={1}><Select options={[{ value: 1, label: 'Active' }, { value: 0, label: 'Inactive' }]} /></Form.Item>
            </Form>
          </Modal>
        </div>
      )}

      {tab === 'gifts' && (
        <div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingGift(null); giftForm.resetFields(); setGiftModal(true); }} style={{ marginBottom: 16 }}>Add Gift</Button>
          <Table dataSource={gifts} rowKey="id" size="small" pagination={false}>
            <Table.Column title="Name" dataIndex="name" />
            <Table.Column title="Cost" dataIndex="gem_cost" width={80} />
            <Table.Column title="Energy" dataIndex="energy_recovery" width={80} />
            <Table.Column title="Category" dataIndex="category" width={100} />
            <Table.Column title="Active" dataIndex="is_active" width={80} render={(v: number) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
            <Table.Column title="" width={120} render={(_: any, r: any) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => { setEditingGift(r); giftForm.setFieldsValue(r); setGiftModal(true); }} />
                <Popconfirm title="Delete?" onConfirm={async () => { await client.delete(`/gifts/${r.id}`); loadGifts(); }}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            )} />
          </Table>
          <Modal title={editingGift ? 'Edit Gift' : 'New Gift'} open={giftModal} onOk={saveGift} onCancel={() => setGiftModal(false)}>
            <Form form={giftForm} layout="vertical">
              <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="gem_cost" label="Gem Cost" initialValue={1}><InputNumber min={0} /></Form.Item>
              <Form.Item name="energy_recovery" label="Energy Recovery" initialValue={0}><InputNumber step={0.1} /></Form.Item>
              <Form.Item name="category" label="Category" initialValue="general"><Input /></Form.Item>
              <Form.Item name="icon_url" label="Icon URL"><Input /></Form.Item>
              <Form.Item name="is_active" label="Active" initialValue={1}><Select options={[{ value: 1, label: 'Active' }, { value: 0, label: 'Inactive' }]} /></Form.Item>
            </Form>
          </Modal>
        </div>
      )}

      {tab === 'transactions' && (
        <div>
          <Button icon={<DownloadOutlined />} style={{ marginBottom: 16 }} onClick={async () => {
            try {
              const res = await client.get('/transactions/export/csv', { responseType: 'blob' });
              const url = window.URL.createObjectURL(new Blob([res.data]));
              const a = document.createElement('a'); a.href = url; a.download = 'transactions.csv'; a.click();
              window.URL.revokeObjectURL(url);
            } catch { message.error('Export failed'); }
          }}>Export CSV</Button>
        <Table dataSource={transactions} rowKey="id" size="small"
          pagination={{ current: txPage, total: txTotal, pageSize: 20, onChange: (p) => { setTxPage(p); loadTransactions(p); } }}>
          <Table.Column title="ID" dataIndex="id" width={60} />
          <Table.Column title="User" dataIndex="user_id" width={70} />
          <Table.Column title="Amount" dataIndex="amount" width={80} render={(v: number) => <span style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f' }}>{v >= 0 ? '+' : ''}{v}</span>} />
          <Table.Column title="Balance" dataIndex="balance_after" width={80} />
          <Table.Column title="Type" dataIndex="tx_type" width={100} render={(t: string) => <Tag>{t}</Tag>} />
          <Table.Column title="Description" dataIndex="description" ellipsis />
          <Table.Column title="Time" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
        </Table>
        </div>
      )}
    </div>
  );
};

export default CommercePage;
