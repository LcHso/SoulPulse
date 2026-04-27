import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Space, Tag, message, Tabs, Card, Descriptions, Typography, Select } from 'antd';
import { EditOutlined, EyeOutlined, SendOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;

interface Persona {
  id: number;
  name: string;
  bio: string;
  profession: string;
  category: string;
  archetype: string;
  gender_tag: string;
  avatar_url: string;
  is_active: number;
  base_face_url: string | null;
  visual_prompt_tags: string | null;
  personality_prompt: string;
}

const PersonaPage: React.FC = () => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [loading, setLoading] = useState(false);
  const [editModal, setEditModal] = useState<{ visible: boolean; persona: Persona | null }>({ visible: false, persona: null });
  const [previewMsg, setPreviewMsg] = useState('');
  const [previewReply, setPreviewReply] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [form] = Form.useForm();
  const [tab, setTab] = useState('list');
  const [selectedPersona, setSelectedPersona] = useState<Persona | null>(null);
  const [emotions, setEmotions] = useState<any[]>([]);
  const [milestones, setMilestones] = useState<any[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await client.get('/personas');
      setPersonas(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openEdit = (p: Persona) => {
    setEditModal({ visible: true, persona: p });
    form.setFieldsValue(p);
  };

  const saveEdit = async () => {
    const values = form.getFieldsValue();
    await client.put(`/personas/${editModal.persona!.id}`, values);
    message.success('Persona updated');
    setEditModal({ visible: false, persona: null });
    load();
  };

  const runPreview = async () => {
    if (!selectedPersona || !previewMsg.trim()) return;
    setPreviewLoading(true);
    try {
      const res = await client.post('/personas/prompt-preview', {
        persona_id: selectedPersona.id,
        user_message: previewMsg,
      });
      setPreviewReply(res.data.reply);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Preview failed');
    } finally {
      setPreviewLoading(false);
    }
  };

  const loadEmotions = async (personaId: number) => {
    const res = await client.get(`/emotions/${personaId}`);
    setEmotions(res.data);
  };

  const loadMilestones = async (personaId: number) => {
    const res = await client.get(`/milestones/${personaId}`);
    setMilestones(res.data);
  };

  const viewPersona = (p: Persona) => {
    setSelectedPersona(p);
    setTab('detail');
    loadEmotions(p.id);
    loadMilestones(p.id);
  };

  const columns = [
    {
      title: 'Avatar', dataIndex: 'avatar_url', width: 60,
      render: (url: string) => <img src={url} alt="" style={{ width: 36, height: 36, borderRadius: 18 }} />,
    },
    { title: 'Name', dataIndex: 'name', width: 120 },
    { title: 'Profession', dataIndex: 'profession', width: 120 },
    { title: 'Category', dataIndex: 'category', width: 100, render: (c: string) => <Tag>{c}</Tag> },
    { title: 'Active', dataIndex: 'is_active', width: 80, render: (v: number) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag> },
    {
      title: 'Actions', width: 160,
      render: (_: any, r: Persona) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => viewPersona(r)}>View</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>Edit</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={4}>Persona & Soul Lab</Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'list', label: 'All Personas' },
        { key: 'detail', label: selectedPersona ? selectedPersona.name : 'Detail', disabled: !selectedPersona },
      ]} />

      {tab === 'list' && (
        <Table dataSource={personas} columns={columns} rowKey="id" loading={loading} size="small" pagination={false} />
      )}

      {tab === 'detail' && selectedPersona && (
        <div>
          <Card title="Persona Info" size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="Name">{selectedPersona.name}</Descriptions.Item>
              <Descriptions.Item label="Profession">{selectedPersona.profession}</Descriptions.Item>
              <Descriptions.Item label="Bio" span={2}>{selectedPersona.bio}</Descriptions.Item>
              <Descriptions.Item label="Face URL">{selectedPersona.base_face_url || 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="Visual Tags">{selectedPersona.visual_prompt_tags || 'N/A'}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="Prompt Sandbox" size="small" style={{ marginBottom: 16 }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input placeholder="Type a user message..." value={previewMsg} onChange={(e) => setPreviewMsg(e.target.value)} style={{ flex: 1 }} onPressEnter={runPreview} />
              <Button type="primary" icon={<SendOutlined />} loading={previewLoading} onClick={runPreview}>Preview</Button>
            </Space.Compact>
            {previewReply && <Card size="small" style={{ marginTop: 8, background: '#f6f6f6' }}>{previewReply}</Card>}
          </Card>

          <Card title="Emotion States" size="small" style={{ marginBottom: 16 }}>
            <Table dataSource={emotions} rowKey="id" size="small" pagination={{ pageSize: 10 }}>
              <Table.Column title="User ID" dataIndex="user_id" width={80} />
              <Table.Column title="Energy" dataIndex="energy" render={(v: number) => v?.toFixed(1)} />
              <Table.Column title="Pleasure" dataIndex="pleasure" render={(v: number) => v?.toFixed(2)} />
              <Table.Column title="Activation" dataIndex="activation" render={(v: number) => v?.toFixed(2)} />
              <Table.Column title="Longing" dataIndex="longing" render={(v: number) => v?.toFixed(2)} />
              <Table.Column title="Security" dataIndex="security" render={(v: number) => v?.toFixed(2)} />
              <Table.Column title="Updated" dataIndex="updated_at" render={(d: string) => formatDateTime(d)} />
            </Table>
          </Card>

          <Card title="Milestones" size="small">
            <Table dataSource={milestones} rowKey="id" size="small" pagination={false}>
              <Table.Column title="Level" dataIndex="intimacy_level" width={80} />
              <Table.Column title="Name" dataIndex="level_name" />
              <Table.Column title="Min Score" dataIndex="min_score" width={100} />
              <Table.Column title="Trigger Message" dataIndex="trigger_message" ellipsis />
            </Table>
          </Card>
        </div>
      )}

      <Modal title="Edit Persona" open={editModal.visible} onOk={saveEdit} onCancel={() => setEditModal({ visible: false, persona: null })} width={640}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name"><Input /></Form.Item>
          <Form.Item name="bio" label="Bio"><TextArea rows={2} /></Form.Item>
          <Form.Item name="profession" label="Profession"><Input /></Form.Item>
          <Form.Item name="archetype" label="Archetype">
            <Select
              allowClear
              options={[
                { value: '温柔治愈', label: '温柔治愈' },
                { value: '高冷傲娇', label: '高冷傲娇' },
                { value: '阳光开朗', label: '阳光开朗' },
                { value: '神秘深沉', label: '神秘深沉' },
                { value: '霸道总裁', label: '霸道总裁' },
                { value: '邻家暖男', label: '邻家暖男' },
                { value: '清冷仙气', label: '清冷仙气' },
                { value: '活力元气', label: '活力元气' },
              ]}
            />
          </Form.Item>
          <Form.Item name="gender_tag" label="Gender Tag">
            <Select
              options={[
                { value: 'male', label: 'Male' },
                { value: 'female', label: 'Female' },
                { value: 'non_binary', label: 'Non-Binary' },
              ]}
            />
          </Form.Item>
          <Form.Item name="category" label="Category">
            <Select
              options={[
                { value: 'otome', label: 'Otome (乙女向)' },
                { value: 'bl', label: 'BL (BL向)' },
                { value: 'gl', label: 'GL (GL向)' },
                { value: 'general', label: 'General (通用)' },
              ]}
            />
          </Form.Item>
          <Form.Item name="personality_prompt" label="Personality Prompt"><TextArea rows={4} /></Form.Item>
          <Form.Item name="base_face_url" label="Base Face URL"><Input /></Form.Item>
          <Form.Item name="visual_prompt_tags" label="Visual Prompt Tags"><TextArea rows={2} /></Form.Item>
          <Form.Item name="avatar_url" label="Avatar URL"><Input /></Form.Item>
          <Form.Item name="is_active" label="Active">
            <Select options={[{ value: 1, label: 'Active' }, { value: 0, label: 'Inactive' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PersonaPage;
