import React, { useEffect, useMemo, useState } from 'react';
import {
  Card, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, Switch,
  message, Popconfirm, Typography, Empty, Row, Col,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, StarFilled, StarOutlined } from '@ant-design/icons';
import client from '../../api/client';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface Persona { id: number; name: string }

interface Outfit {
  id: number;
  persona_id: number;
  outfit_name: string;
  category: string;
  visual_prompt_override: string;
  scene_prompt: string | null;
  unlock_condition_json: Record<string, unknown> | null;
  thumbnail_url: string | null;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
}

const CATEGORY_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'formal', label: 'Formal' },
  { value: 'seasonal', label: 'Seasonal' },
  { value: 'event', label: 'Event' },
  { value: 'intimate', label: 'Intimate' },
  { value: 'workout', label: 'Workout' },
  { value: 'sleepwear', label: 'Sleepwear' },
];

const UNLOCK_TYPE_OPTIONS = [
  { value: 'free', label: 'Free' },
  { value: 'gem', label: 'Gem (cost)' },
  { value: 'intimacy', label: 'Intimacy level' },
  { value: 'event', label: 'Event reward' },
  { value: 'gacha', label: 'Gacha' },
];

const OutfitsPage: React.FC = () => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [filterPersona, setFilterPersona] = useState<number | undefined>();
  const [filterCategory, setFilterCategory] = useState<string | undefined>();
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<Outfit | null>(null);
  const [form] = Form.useForm();

  const loadPersonas = async () => {
    const res = await client.get('/personas');
    setPersonas(res.data);
  };

  const loadOutfits = async () => {
    const params: Record<string, unknown> = { include_inactive: true };
    if (filterPersona !== undefined) params.persona_id = filterPersona;
    if (filterCategory) params.category = filterCategory;
    const res = await client.get('/outfits', { params });
    setOutfits(res.data || []);
  };

  useEffect(() => { loadPersonas(); }, []);
  useEffect(() => { loadOutfits(); }, [filterPersona, filterCategory]);

  const personaName = (id: number) =>
    personas.find((p) => p.id === id)?.name || `#${id}`;

  const grouped = useMemo(() => {
    const groups: Record<number, Outfit[]> = {};
    outfits.forEach((o) => {
      (groups[o.persona_id] ||= []).push(o);
    });
    return groups;
  }, [outfits]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      category: 'daily',
      sort_order: 0,
      is_default: false,
      is_active: true,
      unlock_type: 'free',
      unlock_value: '',
    });
    setModal(true);
  };

  const openEdit = (o: Outfit) => {
    setEditing(o);
    const cond = (o.unlock_condition_json || {}) as Record<string, unknown>;
    form.setFieldsValue({
      ...o,
      unlock_type: (cond.type as string) || 'free',
      unlock_value: cond.value !== undefined ? String(cond.value) : '',
    });
    setModal(true);
  };

  const save = async () => {
    const values = await form.validateFields();
    const { unlock_type, unlock_value, ...rest } = values;
    const condition: Record<string, unknown> = { type: unlock_type };
    if (unlock_value !== undefined && unlock_value !== '') {
      const numeric = Number(unlock_value);
      condition.value = Number.isNaN(numeric) ? unlock_value : numeric;
    }
    const payload = { ...rest, unlock_condition_json: condition };
    try {
      if (editing) {
        await client.put(`/outfits/${editing.id}`, payload);
      } else {
        await client.post('/outfits', payload);
      }
      message.success('Saved');
      setModal(false);
      loadOutfits();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Save failed');
    }
  };

  const setDefault = async (id: number) => {
    await client.post(`/outfits/${id}/set-default`);
    message.success('Set as default');
    loadOutfits();
  };

  const remove = async (id: number) => {
    await client.delete(`/outfits/${id}`);
    message.success('Archived');
    loadOutfits();
  };

  const renderOutfit = (o: Outfit) => {
    const cond = (o.unlock_condition_json || {}) as Record<string, unknown>;
    const unlockType = (cond.type as string) || 'free';
    return (
      <Card
        key={o.id}
        size="small"
        style={{ width: 240, opacity: o.is_active ? 1 : 0.5 }}
        cover={
          o.thumbnail_url ? (
            <img src={o.thumbnail_url} alt={o.outfit_name}
              style={{ height: 180, objectFit: 'cover' }} />
          ) : (
            <div style={{ height: 180, background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>
              no image
            </div>
          )
        }
        actions={[
          <Button key="default" type="text" icon={o.is_default ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
            onClick={() => !o.is_default && setDefault(o.id)} title={o.is_default ? 'Default' : 'Set default'} />,
          <Button key="edit" type="text" icon={<EditOutlined />} onClick={() => openEdit(o)} />,
          <Popconfirm key="del" title="Archive?" onConfirm={() => remove(o.id)}>
            <Button type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>,
        ]}
      >
        <Card.Meta
          title={
            <Space>
              <span>{o.outfit_name}</span>
              {o.is_default && <Tag color="gold">Default</Tag>}
            </Space>
          }
          description={
            <Space direction="vertical" size={2} style={{ width: '100%' }}>
              <Tag color="blue">{o.category}</Tag>
              <Tag color={unlockType === 'free' ? 'green' : 'purple'}>
                Unlock: {unlockType}
                {cond.value !== undefined ? ` (${String(cond.value)})` : ''}
              </Tag>
              <Text ellipsis style={{ fontSize: 11, color: '#666' }}>
                {o.visual_prompt_override}
              </Text>
            </Space>
          }
        />
      </Card>
    );
  };

  const personaIds = Object.keys(grouped).map(Number);

  return (
    <div>
      <Title level={4}>Outfit Manager</Title>
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
          placeholder="Filter by category"
          style={{ width: 160 }}
          value={filterCategory}
          onChange={setFilterCategory}
          options={CATEGORY_OPTIONS}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          New Outfit
        </Button>
      </Space>

      {personaIds.length === 0 && <Empty description="No outfits found" />}

      {personaIds.map((pid) => (
        <div key={pid} style={{ marginBottom: 24 }}>
          <Title level={5}>{personaName(pid)}</Title>
          <Row gutter={[12, 12]}>
            {grouped[pid].map((o) => (
              <Col key={o.id}>{renderOutfit(o)}</Col>
            ))}
          </Row>
        </div>
      ))}

      <Modal
        title={editing ? `Edit Outfit #${editing.id}` : 'New Outfit'}
        open={modal}
        onOk={save}
        onCancel={() => setModal(false)}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="outfit_name" label="Outfit Name" rules={[{ required: true }]} style={{ flex: 2, marginRight: 12 }}>
              <Input />
            </Form.Item>
            <Form.Item name="persona_id" label="Persona" rules={[{ required: true }]} style={{ flex: 1, marginRight: 12 }}>
              <Select disabled={!!editing}
                options={personas.map((p) => ({ value: p.id, label: p.name }))} />
            </Form.Item>
            <Form.Item name="category" label="Category" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Select options={CATEGORY_OPTIONS} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="visual_prompt_override" label="Visual Prompt Override" rules={[{ required: true }]}>
            <TextArea rows={4} style={{ fontFamily: 'monospace' }}
              placeholder="white silk blouse, navy pleated skirt, soft golden-hour lighting..." />
          </Form.Item>
          <Form.Item name="scene_prompt" label="Scene Prompt">
            <TextArea rows={3} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="thumbnail_url" label="Thumbnail URL">
            <Input />
          </Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="unlock_type" label="Unlock Type" style={{ flex: 1, marginRight: 12 }}>
              <Select options={UNLOCK_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item name="unlock_value" label="Unlock Value" style={{ flex: 1, marginRight: 12 }}>
              <Input placeholder="e.g. 50 (gems) or 30 (intimacy)" />
            </Form.Item>
            <Form.Item name="sort_order" label="Sort Order" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space.Compact>
          <Space size={32}>
            <Form.Item name="is_default" label="Default" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_active" label="Active" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default OutfitsPage;
