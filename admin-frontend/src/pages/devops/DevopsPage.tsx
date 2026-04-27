import React, { useEffect, useState } from 'react';
import { Tabs, Table, Card, Tag, Button, Input, Space, Descriptions, Modal, Form, message, Typography, Popconfirm } from 'antd';
import { SendOutlined, PlusOutlined, DeleteOutlined, DownloadOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;

// Check if a config key contains sensitive keywords
const isSensitiveKey = (key: string): boolean => {
  const sensitivePatterns = ['key', 'secret', 'password', 'token'];
  const lowerKey = key.toLowerCase();
  return sensitivePatterns.some(pattern => lowerKey.includes(pattern));
};

const DevopsPage: React.FC = () => {
  const [tab, setTab] = useState('config');
  const [configs, setConfigs] = useState<any[]>([]);
  const [models, setModels] = useState<any>(null);
  const [apiUsage, setApiUsage] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [schedulerStatus, setSchedulerStatus] = useState<any>(null);
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set());

  // Sandbox
  const [sandboxPrompt, setSandboxPrompt] = useState('You are a helpful AI assistant.');
  const [sandboxMsg, setSandboxMsg] = useState('');
  const [sandboxReply, setSandboxReply] = useState('');
  const [sandboxLoading, setSandboxLoading] = useState(false);

  // Config modal
  const [configModal, setConfigModal] = useState(false);
  const [configForm] = Form.useForm();

  const loadConfigs = async () => { const res = await client.get('/config'); setConfigs(res.data); };
  const loadModels = async () => { const res = await client.get('/models/current'); setModels(res.data); };
  const loadApiUsage = async () => { const res = await client.get('/api-usage/summary'); setApiUsage(res.data); };
  const loadAuditLogs = async (p = 1) => {
    const res = await client.get('/audit-logs', { params: { limit: 20, offset: (p - 1) * 20 } });
    setAuditLogs(res.data.logs);
    setAuditTotal(res.data.total);
  };
  const loadScheduler = async () => { try { const res = await client.get('/scheduler/status'); setSchedulerStatus(res.data); } catch { } };

  useEffect(() => { loadConfigs(); loadModels(); loadApiUsage(); loadAuditLogs(); loadScheduler(); }, []);

  const saveConfig = async () => {
    const values = configForm.getFieldsValue();
    await client.put('/config', values);
    message.success('Config saved');
    setConfigModal(false);
    configForm.resetFields();
    loadConfigs();
  };

  const deleteConfig = async (key: string) => {
    await client.delete(`/config/${key}`);
    message.success('Config deleted');
    loadConfigs();
  };

  const runSandbox = async () => {
    if (!sandboxMsg.trim()) return;
    setSandboxLoading(true);
    try {
      const res = await client.post('/sandbox/chat', { system_prompt: sandboxPrompt, user_message: sandboxMsg });
      setSandboxReply(res.data.reply);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Sandbox error');
    } finally {
      setSandboxLoading(false);
    }
  };

  return (
    <div>
      <Title level={4}>DevOps & Model Tuning</Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'config', label: 'System Config' },
        { key: 'models', label: 'Models' },
        { key: 'api', label: 'API Usage' },
        { key: 'sandbox', label: 'Prompt Sandbox' },
        { key: 'scheduler', label: 'Scheduler' },
        { key: 'audit', label: 'Audit Logs' },
      ]} />

      {tab === 'config' && (
        <div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { configForm.resetFields(); setConfigModal(true); }} style={{ marginBottom: 16 }}>Add Config</Button>
          <Table dataSource={configs} rowKey="id" size="small" pagination={false}>
            <Table.Column title="Key" dataIndex="key" />
            <Table.Column title="Value" dataIndex="value" ellipsis render={(value: string, record: any) => {
              const isSensitive = isSensitiveKey(record.key);
              const isRevealed = revealedKeys.has(record.key);
              
              if (!isSensitive) {
                return value;
              }
              
              const toggleReveal = () => {
                setRevealedKeys(prev => {
                  const next = new Set(prev);
                  if (next.has(record.key)) {
                    next.delete(record.key);
                  } else {
                    next.add(record.key);
                  }
                  return next;
                });
              };
              
              return (
                <Space>
                  <span style={{ fontFamily: 'monospace' }}>
                    {isRevealed ? value : '••••••••'}
                  </span>
                  <Popconfirm
                    title="Reveal sensitive value?"
                    description="This will show the actual secret value on screen."
                    onConfirm={toggleReveal}
                    okText="Show"
                    cancelText="Cancel"
                    disabled={isRevealed}
                  >
                    <Button 
                      size="small" 
                      type="text" 
                      icon={isRevealed ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                      onClick={isRevealed ? toggleReveal : undefined}
                    />
                  </Popconfirm>
                </Space>
              );
            }} />
            <Table.Column title="Description" dataIndex="description" ellipsis />
            <Table.Column title="Updated" dataIndex="updated_at" width={140} render={(d: string) => formatDateTime(d)} />
            <Table.Column title="" width={60} render={(_: any, r: any) => (
              <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteConfig(r.key)} />
            )} />
          </Table>
          <Modal title="Add/Update Config" open={configModal} onOk={saveConfig} onCancel={() => setConfigModal(false)}>
            <Form form={configForm} layout="vertical">
              <Form.Item name="key" label="Key" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="value" label="Value" rules={[{ required: true }]}><TextArea rows={2} /></Form.Item>
              <Form.Item name="description" label="Description"><Input /></Form.Item>
            </Form>
          </Modal>
        </div>
      )}

      {tab === 'models' && models && (
        <Card size="small">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="Chat Model">{models.chat_model}</Descriptions.Item>
            <Descriptions.Item label="Character Model">{models.character_model}</Descriptions.Item>
            <Descriptions.Item label="Image Model">{models.image_model}</Descriptions.Item>
            <Descriptions.Item label="Video Model">{models.video_model}</Descriptions.Item>
            <Descriptions.Item label="Embedding Model">{models.embedding_model}</Descriptions.Item>
          </Descriptions>
          <p style={{ marginTop: 8, color: '#999', fontSize: 12 }}>Models are configured via environment variables. Changes require service restart.</p>
        </Card>
      )}

      {tab === 'api' && (
        <Table dataSource={apiUsage} rowKey="service" size="small" pagination={false}>
          <Table.Column title="Service" dataIndex="service" />
          <Table.Column title="Calls" dataIndex="total_calls" />
          <Table.Column title="Req Tokens" dataIndex="total_request_tokens" />
          <Table.Column title="Resp Tokens" dataIndex="total_response_tokens" />
          <Table.Column title="Avg Latency" dataIndex="avg_latency_ms" render={(v: number) => `${v}ms`} />
          <Table.Column title="Errors" dataIndex="error_count" render={(v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <Tag color="green">0</Tag>} />
          <Table.Column title="Cost" dataIndex="total_cost" render={(v: number) => `$${v?.toFixed(4)}`} />
        </Table>
      )}

      {tab === 'sandbox' && (
        <div>
          <Card size="small" style={{ marginBottom: 16 }}>
            <p style={{ marginBottom: 8, fontWeight: 500 }}>System Prompt:</p>
            <TextArea rows={4} value={sandboxPrompt} onChange={(e) => setSandboxPrompt(e.target.value)} />
          </Card>
          <Space.Compact style={{ width: '100%' }}>
            <Input placeholder="User message..." value={sandboxMsg} onChange={(e) => setSandboxMsg(e.target.value)} onPressEnter={runSandbox} />
            <Button type="primary" icon={<SendOutlined />} loading={sandboxLoading} onClick={runSandbox}>Send</Button>
          </Space.Compact>
          {sandboxReply && <Card size="small" style={{ marginTop: 12, background: '#f6f6f6' }}><pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{sandboxReply}</pre></Card>}
        </div>
      )}

      {tab === 'scheduler' && (
        <Card size="small">
          {schedulerStatus ? (
            <Descriptions column={1} size="small">
              {Object.entries(schedulerStatus).map(([svc, status]) => (
                <Descriptions.Item key={svc} label={svc}>
                  <Tag color={status === 'active' ? 'green' : 'red'}>{status as string}</Tag>
                </Descriptions.Item>
              ))}
            </Descriptions>
          ) : <p>Unable to fetch scheduler status</p>}
        </Card>
      )}

      {tab === 'audit' && (
        <div>
          <Button icon={<DownloadOutlined />} style={{ marginBottom: 16 }} onClick={async () => {
            try {
              const res = await client.get('/audit-logs/export/csv', { responseType: 'blob' });
              const url = window.URL.createObjectURL(new Blob([res.data]));
              const a = document.createElement('a'); a.href = url; a.download = 'audit-logs.csv'; a.click();
              window.URL.revokeObjectURL(url);
            } catch { message.error('Export failed'); }
          }}>Export CSV</Button>
        <Table dataSource={auditLogs} rowKey="id" size="small"
          pagination={{ current: auditPage, total: auditTotal, pageSize: 20, onChange: (p) => { setAuditPage(p); loadAuditLogs(p); } }}>
          <Table.Column title="ID" dataIndex="id" width={60} />
          <Table.Column title="Admin" dataIndex="admin_user_id" width={70} />
          <Table.Column title="Action" dataIndex="action" />
          <Table.Column title="Target" dataIndex="target_type" width={100} />
          <Table.Column title="Target ID" dataIndex="target_id" width={80} />
          <Table.Column title="IP" dataIndex="ip_address" width={120} />
          <Table.Column title="Time" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
        </Table>
        </div>
      )}
    </div>
  );
};

export default DevopsPage;
