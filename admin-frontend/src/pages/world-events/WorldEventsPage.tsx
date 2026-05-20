import React, { useEffect, useState } from 'react';
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, DatePicker, Space, Tag,
  message, Popconfirm, Typography, Switch,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

interface Persona { id: number; name: string }

interface WorldEvent {
  id: number;
  event_type: string;
  title: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  affected_persona_ids: number[];
  mood_modifier_json: Record<string, number>;
  content_directive: string | null;
  is_active: boolean;
}

const EVENT_TYPE_OPTIONS = [
  { value: 'holiday', label: 'Holiday' },
  { value: 'season', label: 'Season' },
  { value: 'story_arc', label: 'Story Arc' },
  { value: 'concert', label: 'Concert' },
  { value: 'festival', label: 'Festival' },
  { value: 'anniversary', label: 'Anniversary' },
];

const MOOD_KEYS = ['energy', 'pleasure', 'activation', 'longing', 'security'] as const;

const eventColor: Record<string, string> = {
  holiday: 'red',
  season: 'cyan',
  story_arc: 'purple',
  concert: 'magenta',
  festival: 'orange',
  anniversary: 'gold',
};

const WorldEventsPage: React.FC = () => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [events, setEvents] = useState<WorldEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<WorldEvent | null>(null);
  const [form] = Form.useForm();

  const loadPersonas = async () => {
    const res = await client.get('/personas');
    setPersonas(res.data);
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await client.get('/world-events/');
      setEvents(res.data.events || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadPersonas(); load(); }, []);

  const personaName = (id: number) =>
    personas.find((p) => p.id === id)?.name || `#${id}`;

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      event_type: 'holiday',
      is_active: true,
      affected_persona_ids: [],
    });
    setModal(true);
  };

  const openEdit = (e: WorldEvent) => {
    setEditing(e);
    const moodFields: Record<string, number> = {};
    MOOD_KEYS.forEach((k) => {
      moodFields[`mood_${k}`] = (e.mood_modifier_json && e.mood_modifier_json[k]) || 0;
    });
    form.setFieldsValue({
      ...e,
      ...moodFields,
      date_range: [
        e.start_date ? dayjs(e.start_date) : null,
        e.end_date ? dayjs(e.end_date) : null,
      ],
    });
    setModal(true);
  };

  const save = async () => {
    const values = await form.validateFields();
    const range: [Dayjs | null, Dayjs | null] = values.date_range || [null, null];
    if (!range[0]) {
      message.error('Start date is required');
      return;
    }
    const mood: Record<string, number> = {};
    MOOD_KEYS.forEach((k) => {
      const v = values[`mood_${k}`];
      if (typeof v === 'number' && v !== 0) mood[k] = v;
    });
    const payload = {
      event_type: values.event_type,
      title: values.title,
      description: values.description || null,
      start_date: range[0].toISOString(),
      end_date: range[1] ? range[1].toISOString() : null,
      affected_persona_ids: values.affected_persona_ids || [],
      mood_modifier_json: mood,
      content_directive: values.content_directive || null,
      is_active: values.is_active,
    };
    try {
      if (editing) {
        await client.put(`/world-events/${editing.id}`, payload);
      } else {
        await client.post('/world-events/', payload);
      }
      message.success('Saved');
      setModal(false);
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Save failed');
    }
  };

  const toggleActive = async (e: WorldEvent, value: boolean) => {
    try {
      await client.put(`/world-events/${e.id}`, { is_active: value });
      load();
    } catch {
      message.error('Toggle failed');
    }
  };

  const remove = async (id: number) => {
    await client.delete(`/world-events/${id}`);
    message.success('Deactivated');
    load();
  };

  return (
    <div>
      <Title level={4}>World Events</Title>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          New Event
        </Button>
      </Space>

      <Table dataSource={events} rowKey="id" loading={loading} size="small" pagination={{ pageSize: 20 }}>
        <Table.Column title="ID" dataIndex="id" width={60} />
        <Table.Column title="Type" dataIndex="event_type" width={110}
          render={(t: string) => <Tag color={eventColor[t] || 'default'}>{t}</Tag>} />
        <Table.Column title="Title" dataIndex="title" />
        <Table.Column title="Start" dataIndex="start_date" width={140}
          render={(d: string) => formatDateTime(d)} />
        <Table.Column title="End" dataIndex="end_date" width={140}
          render={(d: string | null) => d ? formatDateTime(d) : '∞'} />
        <Table.Column title="Affected" dataIndex="affected_persona_ids" width={200}
          render={(ids: number[]) => (
            <Space wrap size={2}>
              {(ids && ids.length > 0)
                ? ids.slice(0, 3).map((id) => <Tag key={id}>{personaName(id)}</Tag>)
                : <Tag>All</Tag>}
              {ids && ids.length > 3 && <Tag>+{ids.length - 3}</Tag>}
            </Space>
          )} />
        <Table.Column title="Active" dataIndex="is_active" width={80}
          render={(v: boolean, r: WorldEvent) => (
            <Switch checked={v} onChange={(checked) => toggleActive(r, checked)} size="small" />
          )} />
        <Table.Column title="Actions" width={120} render={(_: unknown, r: WorldEvent) => (
          <Space>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
            <Popconfirm title="Deactivate event?" onConfirm={() => remove(r.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        )} />
      </Table>

      <Modal
        title={editing ? `Edit Event #${editing.id}` : 'New World Event'}
        open={modal}
        onOk={save}
        onCancel={() => setModal(false)}
        width={760}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="event_type" label="Event Type" rules={[{ required: true }]} style={{ flex: 1, marginRight: 12 }}>
              <Select options={EVENT_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item name="title" label="Title" rules={[{ required: true }]} style={{ flex: 2 }}>
              <Input />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="date_range" label="Date Range (end optional)" rules={[{ required: true }]}>
            <RangePicker showTime allowEmpty={[false, true]} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="affected_persona_ids" label="Affected Personas (empty = all)">
            <Select
              mode="multiple"
              placeholder="Select personas"
              options={personas.map((p) => ({ value: p.id, label: p.name }))}
            />
          </Form.Item>
          <div style={{ marginBottom: 8 }}><strong>Mood Modifiers</strong></div>
          <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
            {MOOD_KEYS.map((k, idx) => (
              <Form.Item key={k} name={`mood_${k}`} label={k}
                style={{ flex: 1, marginRight: idx === MOOD_KEYS.length - 1 ? 0 : 8 }}
                initialValue={0}>
                <InputNumber step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            ))}
          </Space.Compact>
          <Form.Item name="content_directive" label="Content Directive">
            <TextArea rows={3} placeholder="In posts and messages, evoke the festive mood..." />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default WorldEventsPage;
