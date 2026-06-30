import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Space, Tag, message, Tabs, Card, Descriptions, Typography, Select, Upload, Alert, Spin } from 'antd';
import type { UploadFile, RcFile } from 'antd/es/upload/interface';
import { EditOutlined, EyeOutlined, SendOutlined, ImportOutlined, InboxOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;
const { Dragger } = Upload;

interface ParsedCardPreview {
  name: string;
  bio: string;
  avatarDataUrl: string | null;
  isPng: boolean;
}

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

  // ── Import-card modal state ───────────────────────────────
  const [importVisible, setImportVisible] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [nameOverride, setNameOverride] = useState('');
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [preview, setPreview] = useState<ParsedCardPreview | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

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

  // ── Import-card flow ───────────────────────────────────────
  const resetImportState = () => {
    setImportFile(null);
    setNameOverride('');
    setPreview(null);
    setImportError(null);
    setParsing(false);
    setImporting(false);
  };

  const openImport = () => {
    resetImportState();
    setImportVisible(true);
  };

  const closeImport = () => {
    if (importing) return;
    setImportVisible(false);
    resetImportState();
  };

  const readFileAsDataUrl = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });

  const parseFile = async (file: File) => {
    setParsing(true);
    setImportError(null);
    setPreview(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      // Preview endpoint lives at /api/character-cards/import (outside /api/admin),
      // override baseURL on this single request.
      const res = await client.post('/character-cards/import', formData, {
        baseURL: '/api',
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const card = res.data?.card ?? {};
      const dataSection = (card && typeof card.data === 'object' && card.data) || {};
      const parsedName: string =
        (dataSection.name as string) || (card.name as string) || '';
      const parsedBio: string =
        (dataSection.description as string) ||
        (card.description as string) ||
        (dataSection.personality as string) ||
        '';

      const isPng =
        (file.name || '').toLowerCase().endsWith('.png') ||
        file.type === 'image/png';
      const avatarDataUrl = isPng ? await readFileAsDataUrl(file) : null;

      setPreview({
        name: parsedName,
        bio: parsedBio,
        avatarDataUrl,
        isPng,
      });
    } catch (err: any) {
      setImportError(
        err?.response?.data?.detail || err?.message || 'Failed to parse card',
      );
    } finally {
      setParsing(false);
    }
  };

  const handleFileChosen = (file: RcFile): boolean => {
    const name = (file.name || '').toLowerCase();
    const isPng = name.endsWith('.png') || file.type === 'image/png';
    const isJson =
      name.endsWith('.json') ||
      file.type === 'application/json' ||
      file.type === 'text/json';
    if (!isPng && !isJson) {
      message.error('Only .png or .json character card files are accepted');
      return false;
    }
    if (file.size > 10 * 1024 * 1024) {
      message.error('File too large. Maximum allowed size is 10MB.');
      return false;
    }
    setImportFile(file);
    parseFile(file);
    // Returning false prevents antd Upload from auto-uploading.
    return false;
  };

  const confirmImport = async () => {
    if (!importFile) {
      setImportError('Please choose a character card file first');
      return;
    }
    setImporting(true);
    setImportError(null);
    try {
      const formData = new FormData();
      formData.append('file', importFile);
      if (nameOverride.trim()) {
        formData.append('name_override', nameOverride.trim());
      }
      const res = await client.post('/personas/import-card', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      message.success(`Imported persona: ${res.data?.name ?? 'OK'}`);
      setImportVisible(false);
      resetImportState();
      load();
    } catch (err: any) {
      setImportError(
        err?.response?.data?.detail || err?.message || 'Import failed',
      );
    } finally {
      setImporting(false);
    }
  };

  const uploadFileList: UploadFile[] = importFile
    ? [
        {
          uid: '-1',
          name: importFile.name,
          status: 'done',
          size: importFile.size,
          type: importFile.type,
        },
      ]
    : [];

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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Title level={4} style={{ margin: 0 }}>Persona & Soul Lab</Title>
        <Space>
          <Button type="primary" icon={<ImportOutlined />} onClick={openImport}>
            Import Card
          </Button>
        </Space>
      </div>
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

      <Modal
        title="Import Character Card"
        open={importVisible}
        onCancel={closeImport}
        width={640}
        maskClosable={!importing}
        closable={!importing}
        footer={[
          <Button key="cancel" onClick={closeImport} disabled={importing}>
            Cancel
          </Button>,
          <Button
            key="confirm"
            type="primary"
            loading={importing}
            disabled={!importFile || parsing || !!importError}
            onClick={confirmImport}
          >
            Confirm Import
          </Button>,
        ]}
      >
        <Dragger
          accept=".png,.json,image/png,application/json"
          multiple={false}
          maxCount={1}
          beforeUpload={handleFileChosen}
          onRemove={() => {
            setImportFile(null);
            setPreview(null);
            setImportError(null);
            return true;
          }}
          fileList={uploadFileList}
          disabled={importing}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">Click or drag a .png / .json character card here</p>
          <p className="ant-upload-hint">SillyTavern V2 cards supported. Max 10MB.</p>
        </Dragger>

        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="Name Override (optional)">
            <Input
              placeholder="Leave empty to use the card's name"
              value={nameOverride}
              onChange={(e) => setNameOverride(e.target.value)}
              disabled={importing}
              allowClear
            />
          </Form.Item>
        </Form>

        {parsing && (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <Spin /> <Text type="secondary" style={{ marginLeft: 8 }}>Parsing card…</Text>
          </div>
        )}

        {preview && !parsing && (
          <Card size="small" title="Preview" style={{ marginTop: 8 }}>
            <div style={{ display: 'flex', gap: 16 }}>
              {preview.avatarDataUrl ? (
                <img
                  src={preview.avatarDataUrl}
                  alt="avatar preview"
                  style={{
                    width: 96,
                    height: 96,
                    objectFit: 'cover',
                    borderRadius: 8,
                    border: '1px solid #f0f0f0',
                    flex: '0 0 auto',
                  }}
                />
              ) : (
                <div
                  style={{
                    width: 96,
                    height: 96,
                    borderRadius: 8,
                    background: '#fafafa',
                    border: '1px dashed #d9d9d9',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#bbb',
                    fontSize: 12,
                    flex: '0 0 auto',
                  }}
                >
                  JSON
                </div>
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="Name">
                    {nameOverride.trim() ? (
                      <Space>
                        <Text>{nameOverride.trim()}</Text>
                        <Tag color="blue">overridden</Tag>
                        <Text type="secondary" delete>{preview.name || '(empty)'}</Text>
                      </Space>
                    ) : (
                      preview.name || <Text type="secondary">(empty)</Text>
                    )}
                  </Descriptions.Item>
                </Descriptions>
                <Paragraph
                  type="secondary"
                  style={{ marginTop: 8, marginBottom: 0 }}
                  ellipsis={{ rows: 4, expandable: true, symbol: 'more' }}
                >
                  {preview.bio || '(no description)'}
                </Paragraph>
              </div>
            </div>
          </Card>
        )}

        {importError && (
          <Alert
            type="error"
            showIcon
            message="Import error"
            description={importError}
            style={{ marginTop: 12 }}
            closable
            onClose={() => setImportError(null)}
          />
        )}
      </Modal>
    </div>
  );
};

export default PersonaPage;
