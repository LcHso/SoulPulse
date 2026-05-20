import React, { useEffect, useState } from 'react';
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag,
  message, Popconfirm, Typography,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import client from '../../api/client';

const { Title } = Typography;
const { TextArea } = Input;

interface Persona { id: number; name: string }

interface Scene {
  id: number;
  persona_id: number;
  scene_name: string;
  scene_type: string;
  setting_description: string;
  mood_preset: string | null;
  system_prompt_addon: string;
  required_intimacy: number;
  unlock_type: string;
  unlock_cost: number;
  max_messages: number;
  completion_reward_json: Record<string, unknown> | null;
  scene_cg_url: string | null;
  is_active: boolean;
  sort_order: number;
}

const SCENE_TYPE_OPTIONS = [
  { value: 'date', label: 'Date' },
  { value: 'roleplay', label: 'Roleplay' },
  { value: 'event', label: 'Event' },
  { value: 'milestone', label: 'Milestone' },
  { value: 'daily', label: 'Daily' },
  { value: 'fantasy', label: 'Fantasy' },
];

const UNLOCK_TYPE_OPTIONS = [
  { value: 'free', label: 'Free' },
  { value: 'gem', label: 'Gem' },
  { value: 'gacha', label: 'Gacha' },
];

const ScenesPage: React.FC = () => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterPersona, setFilterPersona] = useState<number | undefined>();
  const [filterType, setFilterType] = useState<string | undefined>();
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<Scene | null>(null);
  const [form] = Form.useForm();

  const loadPersonas = async () => {
    const res = await client.get('/personas');
    setPersonas(res.data);
  };

  const loadScenes = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page_size: 100 };
      if (filterPersona !== undefined) params.persona_id = filterPersona;
      if (filterType) params.scene_type = filterType;
      const res = await client.get('/scenes/', { params });
      setScenes(res.data.scenes || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadPersonas(); }, []);
  useEffect(() => { loadScenes(); }, [filterPersona, filterType]);

  const personaName = (id: number) =>
    personas.find((p) => p.id === id)?.name || `#${id}`;

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      scene_type: 'date',
      unlock_type: 'free',
      unlock_cost: 0,
      max_messages: 20,
      required_intimacy: 0,
      sort_order: 0,
    });
    setModal(true);
  };

  const openEdit = (s: Scene) => {
    setEditing(s);
    form.setFieldsValue({
      ...s,
      completion_reward_json: s.completion_reward_json
        ? JSON.stringify(s.completion_reward_json, null, 2)
        : '',
    });
    setModal(true);
  };

  const save = async () => {
    const values = await form.validateFields();
    let reward: Record<string, unknown> | null = null;
    if (values.completion_reward_json && typeof values.completion_reward_json === 'string') {
      try {
        reward = values.completion_reward_json.trim()
          ? JSON.parse(values.completion_reward_json)
          : null;
      } catch {
        message.error('Reward JSON is invalid');
        return;
      }
    }
    const payload = { ...values, completion_reward_json: reward };
    try {
      if (editing) {
        await client.put(`/scenes/${editing.id}`, payload);
      } else {
        await client.post('/scenes/', payload);
      }
      message.success('Saved');
      setModal(false);
      loadScenes();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Save failed');
    }
  };

  const remove = async (id: number) => {
    await client.delete(`/scenes/${id}`);
    message.success('Archived');
    loadScenes();
  };

  return (
    <div>
      <Title level={4}>Scene Manager</Title>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear
          placeholder="Filter by persona"
          style={{ width: 200 }}
          value={filterPersona}
          onChange={setFilterPersona}
          options={personas.map((p) => ({ value: p.id, label: p.name }))}
        />
        <Select
          allowClear
          placeholder="Filter by type"
          style={{ width: 160 }}
          value={filterType}
          onChange={setFilterType}
          options={SCENE_TYPE_OPTIONS}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          New Scene
        </Button>
      </Space>

      <Table dataSource={scenes} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 20 }}>
        <Table.Column title="ID" dataIndex="id" width={60} />
        <Table.Column title="Persona" dataIndex="persona_id" width={120}
          render={(id: number) => personaName(id)} />
        <Table.Column title="Scene Name" dataIndex="scene_name" />
        <Table.Column title="Type" dataIndex="scene_type" width={100}
          render={(t: string) => <Tag color="blue">{t}</Tag>} />
        <Table.Column title="Intimacy" dataIndex="required_intimacy" width={90} />
        <Table.Column title="Unlock" dataIndex="unlock_type" width={100}
          render={(u: string, r: Scene) => (
            <Tag color={u === 'free' ? 'green' : u === 'gem' ? 'gold' : 'purple'}>
              {u}{u !== 'free' ? `:${r.unlock_cost}` : ''}
            </Tag>
          )} />
        <Table.Column title="Active" dataIndex="is_active" width={80}
          render={(v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
        <Table.Column title="Actions" width={140} render={(_: unknown, r: Scene) => (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
            <Popconfirm title="Archive this scene?" onConfirm={() => remove(r.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        )} />
      </Table>

      <Modal
        title={editing ? `Edit Scene #${editing.id}` : 'New Scene'}
        open={modal}
        onOk={save}
        onCancel={() => setModal(false)}
        width={760}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="scene_name" label="Scene Name" rules={[{ required: true }]} style={{ flex: 2, marginRight: 12 }}>
              <Input />
            </Form.Item>
            <Form.Item name="persona_id" label="Persona" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select
                disabled={!!editing}
                options={personas.map((p) => ({ value: p.id, label: p.name }))}
              />
            </Form.Item>
          </Space.Compact>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="scene_type" label="Scene Type" rules={[{ required: true }]} style={{ flex: 1, marginRight: 12 }}>
              <Select options={SCENE_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item name="mood_preset" label="Mood Preset" style={{ flex: 1, marginRight: 12 }}>
              <Input placeholder="warm / playful / tense ..." />
            </Form.Item>
            <Form.Item name="required_intimacy" label="Required Intimacy" style={{ flex: 1 }}>
              <InputNumber min={0} max={100} style={{ width: '100%' }} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="setting_description" label="Setting Description" rules={[{ required: true }]}>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="system_prompt_addon" label="System Prompt Addon" rules={[{ required: true }]}>
            <TextArea rows={6} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="unlock_type" label="Unlock Type" style={{ flex: 1, marginRight: 12 }}>
              <Select options={UNLOCK_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item name="unlock_cost" label="Unlock Cost" style={{ flex: 1, marginRight: 12 }}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="max_messages" label="Max Messages" style={{ flex: 1, marginRight: 12 }}>
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="sort_order" label="Sort Order" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="scene_cg_url" label="Scene CG URL">
            <Input />
          </Form.Item>
          <Form.Item name="completion_reward_json" label="Completion Reward (JSON)">
            <TextArea rows={3} placeholder='{"intimacy": 5, "gems": 10}' style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="is_active" label="Active" initialValue>
            <Select options={[{ value: true, label: 'Active' }, { value: false, label: 'Archived' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ScenesPage;
