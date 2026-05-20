import React, { useEffect, useState } from 'react';
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, DatePicker, Space, Tag,
  message, Popconfirm, Typography, Steps, Card,
} from 'antd';
import { PlusOutlined, DeleteOutlined, ForwardOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;

interface Persona { id: number; name: string }

interface Campaign {
  id: number;
  persona_id: number;
  campaign_name: string;
  teaser_start: string | null;
  launch_date: string | null;
  settling_end: string | null;
  teaser_silhouette_url: string | null;
  teaser_hints_json: string[] | null;
  reveal_cg_url: string | null;
  launch_discount_percent: number;
  daily_post_boost: number;
  current_phase: string;
  is_active: boolean;
  created_at: string | null;
}

const PHASES = ['planned', 'teaser', 'launched', 'settling', 'integrated'] as const;

const phaseStep = (phase: string) => {
  const idx = PHASES.indexOf(phase as typeof PHASES[number]);
  return idx >= 0 ? idx : 0;
};

const phaseColor: Record<string, string> = {
  planned: 'default',
  teaser: 'blue',
  launched: 'magenta',
  settling: 'orange',
  integrated: 'green',
};

const LaunchesPage: React.FC = () => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [form] = Form.useForm();

  const loadPersonas = async () => {
    const res = await client.get('/personas');
    setPersonas(res.data);
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await client.get('/launches/campaigns');
      setCampaigns(res.data.campaigns || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadPersonas(); load(); }, []);

  const personaName = (id: number) =>
    personas.find((p) => p.id === id)?.name || `#${id}`;

  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({
      launch_discount_percent: 20,
      daily_post_boost: 3,
      teaser_hints: '',
    });
    setModal(true);
  };

  const save = async () => {
    const values = await form.validateFields();
    const launch_date: Dayjs = values.launch_date;
    const teaser_hints_json = values.teaser_hints
      ? String(values.teaser_hints).split('\n').map((s: string) => s.trim()).filter(Boolean)
      : [];
    const payload = {
      persona_id: values.persona_id,
      campaign_name: values.campaign_name,
      launch_date: launch_date.toISOString(),
      teaser_silhouette_url: values.teaser_silhouette_url || null,
      reveal_cg_url: values.reveal_cg_url || null,
      launch_discount_percent: values.launch_discount_percent,
      daily_post_boost: values.daily_post_boost,
      teaser_hints_json,
    };
    try {
      await client.post('/launches/campaigns', payload);
      message.success('Campaign created');
      setModal(false);
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Create failed');
    }
  };

  const advance = async (id: number) => {
    try {
      await client.post(`/launches/campaigns/${id}/advance`);
      message.success('Phase advanced');
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Advance failed');
    }
  };

  const cancel = async (id: number) => {
    try {
      await client.delete(`/launches/campaigns/${id}`);
      message.success('Cancelled');
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Cancel failed');
    }
  };

  return (
    <div>
      <Title level={4}>Launch Campaigns</Title>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          New Campaign
        </Button>
      </Space>

      <Card title="Active Campaign Timeline" size="small" style={{ marginBottom: 16 }}>
        {campaigns.filter((c) => c.is_active).length === 0 && (
          <span style={{ color: '#999' }}>No active campaigns</span>
        )}
        {campaigns.filter((c) => c.is_active).map((c) => (
          <div key={c.id} style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8 }}>
              <strong>{c.campaign_name}</strong>{' '}
              <Tag>{personaName(c.persona_id)}</Tag>
              <Tag color={phaseColor[c.current_phase] || 'default'}>{c.current_phase}</Tag>
            </div>
            <Steps
              size="small"
              current={phaseStep(c.current_phase)}
              items={PHASES.map((p) => ({ title: p }))}
            />
          </div>
        ))}
      </Card>

      <Table dataSource={campaigns} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 20 }}>
        <Table.Column title="ID" dataIndex="id" width={60} />
        <Table.Column title="Persona" dataIndex="persona_id" width={120}
          render={(id: number) => personaName(id)} />
        <Table.Column title="Campaign" dataIndex="campaign_name" />
        <Table.Column title="Phase" dataIndex="current_phase" width={100}
          render={(p: string) => <Tag color={phaseColor[p] || 'default'}>{p}</Tag>} />
        <Table.Column title="Teaser" dataIndex="teaser_start" width={140}
          render={(d: string) => formatDateTime(d)} />
        <Table.Column title="Launch" dataIndex="launch_date" width={140}
          render={(d: string) => formatDateTime(d)} />
        <Table.Column title="Settling End" dataIndex="settling_end" width={140}
          render={(d: string) => formatDateTime(d)} />
        <Table.Column title="Active" dataIndex="is_active" width={80}
          render={(v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
        <Table.Column title="Actions" width={180} render={(_: unknown, r: Campaign) => (
          <Space>
            <Button size="small" icon={<ForwardOutlined />} disabled={!r.is_active || r.current_phase === 'integrated'}
              onClick={() => advance(r.id)}>Advance</Button>
            <Popconfirm title="Cancel campaign?" onConfirm={() => cancel(r.id)} disabled={!r.is_active}>
              <Button size="small" danger icon={<DeleteOutlined />} disabled={!r.is_active} />
            </Popconfirm>
          </Space>
        )} />
      </Table>

      <Modal
        title="New Campaign"
        open={modal}
        onOk={save}
        onCancel={() => setModal(false)}
        width={680}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="persona_id" label="Persona" rules={[{ required: true }]} style={{ flex: 1, marginRight: 12 }}>
              <Select options={personas.map((p) => ({ value: p.id, label: p.name }))} />
            </Form.Item>
            <Form.Item name="campaign_name" label="Campaign Name" rules={[{ required: true }]} style={{ flex: 2 }}>
              <Input />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="launch_date" label="Launch Date" rules={[{ required: true }]}>
            <DatePicker showTime style={{ width: '100%' }}
              disabledDate={(d) => d && d < dayjs().startOf('day')} />
          </Form.Item>
          <Form.Item name="teaser_silhouette_url" label="Teaser Silhouette URL">
            <Input />
          </Form.Item>
          <Form.Item name="reveal_cg_url" label="Reveal CG URL">
            <Input />
          </Form.Item>
          <Form.Item name="teaser_hints" label="Teaser Hints (one per line)">
            <TextArea rows={3} placeholder="A familiar voice from the roof...&#10;A new song under the moonlight..." />
          </Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="launch_discount_percent" label="Launch Discount %" style={{ flex: 1, marginRight: 12 }}>
              <InputNumber min={0} max={100} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="daily_post_boost" label="Daily Post Boost" style={{ flex: 1 }}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </Space.Compact>
        </Form>
      </Modal>
    </div>
  );
};

export default LaunchesPage;
