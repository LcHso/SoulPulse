import React, { useEffect, useState } from 'react';
import {
  Tabs, Table, Button, Image, Tag, Space, Modal, Input, Select, Typography,
  Card, Empty, Row, Col, Checkbox, message, Timeline,
} from 'antd';
import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface Persona { id: number; name: string }

interface Asset {
  id: number;
  asset_type: string;
  persona_id: number | null;
  version: number;
  url: string;
  thumbnail_url: string | null;
  metadata_json: Record<string, unknown> | null;
  status: string;
  consistency_score: number | null;
  review_notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

interface ConsistencyReport {
  persona_id?: number;
  total_assets?: number;
  active_assets?: number;
  flagged?: Array<{
    id: number;
    persona_id: number | null;
    asset_type: string;
    consistency_score: number | null;
    url: string;
  }>;
  per_persona?: Array<{
    persona_id: number;
    average_score: number;
    asset_count: number;
  }>;
  [k: string]: unknown;
}

const statusColor: Record<string, string> = {
  draft: 'default',
  review: 'gold',
  active: 'green',
  archived: 'red',
};

const AssetsPage: React.FC = () => {
  const [tab, setTab] = useState('queue');
  const [personas, setPersonas] = useState<Persona[]>([]);

  // Review queue
  const [queue, setQueue] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [rejectModal, setRejectModal] = useState<{ visible: boolean; asset: Asset | null }>({ visible: false, asset: null });
  const [rejectReason, setRejectReason] = useState('');
  const [approveNotes, setApproveNotes] = useState('');

  // History
  const [historyPersona, setHistoryPersona] = useState<number | undefined>();
  const [history, setHistory] = useState<Asset[]>([]);

  // Consistency
  const [report, setReport] = useState<ConsistencyReport | null>(null);

  const loadPersonas = async () => {
    const res = await client.get('/personas');
    setPersonas(res.data);
  };

  const loadQueue = async () => {
    const res = await client.get('/assets/review-queue');
    setQueue(res.data.queue || []);
    setSelected([]);
  };

  const loadHistory = async (pid: number) => {
    const res = await client.get(`/assets/${pid}/history`);
    setHistory(res.data.history || []);
  };

  const loadReport = async () => {
    const res = await client.get('/assets/consistency-report');
    setReport(res.data);
  };

  useEffect(() => { loadPersonas(); loadQueue(); }, []);
  useEffect(() => {
    if (tab === 'history' && historyPersona !== undefined) loadHistory(historyPersona);
    if (tab === 'consistency') loadReport();
  }, [tab, historyPersona]);

  const personaName = (id: number | null) =>
    id ? (personas.find((p) => p.id === id)?.name || `#${id}`) : '—';

  const approve = async (id: number) => {
    try {
      await client.post(`/assets/${id}/approve`, null, {
        params: approveNotes ? { notes: approveNotes } : undefined,
      });
      message.success('Approved');
      setApproveNotes('');
      loadQueue();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Approve failed');
    }
  };

  const reject = async () => {
    if (!rejectModal.asset) return;
    try {
      await client.post(`/assets/${rejectModal.asset.id}/reject`, { reason: rejectReason });
      message.success('Rejected');
      setRejectModal({ visible: false, asset: null });
      setRejectReason('');
      loadQueue();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Reject failed');
    }
  };

  const bulkApprove = async () => {
    if (selected.length === 0) return;
    try {
      await client.post('/assets/bulk-approve', { asset_ids: selected });
      message.success(`Approved ${selected.length} assets`);
      loadQueue();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Bulk approve failed');
    }
  };

  const renderAssetCard = (a: Asset) => (
    <Card
      size="small"
      key={a.id}
      style={{ width: 240 }}
      cover={
        <div style={{ position: 'relative', height: 200, background: '#fafafa' }}>
          <Image src={a.thumbnail_url || a.url} alt={a.asset_type}
            style={{ height: 200, width: '100%', objectFit: 'cover' }} />
          <Checkbox
            checked={selected.includes(a.id)}
            onChange={(e) => setSelected(
              e.target.checked ? [...selected, a.id] : selected.filter((s) => s !== a.id),
            )}
            style={{ position: 'absolute', top: 8, left: 8, background: '#fff', padding: '0 4px', borderRadius: 4 }}
          />
        </div>
      }
      actions={[
        <Button key="approve" type="text" icon={<CheckOutlined style={{ color: '#52c41a' }} />}
          onClick={() => approve(a.id)} title="Approve" />,
        <Button key="reject" type="text" icon={<CloseOutlined style={{ color: '#ff4d4f' }} />}
          onClick={() => setRejectModal({ visible: true, asset: a })} title="Reject" />,
      ]}
    >
      <Card.Meta
        title={
          <Space size={4}>
            <Tag color="blue">{a.asset_type}</Tag>
            <Tag>v{a.version}</Tag>
          </Space>
        }
        description={
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            <Text style={{ fontSize: 12 }}>{personaName(a.persona_id)}</Text>
            {a.consistency_score !== null && (
              <Text style={{ fontSize: 11, color: '#666' }}>
                Score: {a.consistency_score?.toFixed(2)}
              </Text>
            )}
            <Text style={{ fontSize: 11, color: '#999' }}>{formatDateTime(a.updated_at)}</Text>
          </Space>
        }
      />
    </Card>
  );

  return (
    <div>
      <Title level={4}>Asset Review</Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'queue', label: `Review Queue (${queue.length})` },
        { key: 'history', label: 'Version History' },
        { key: 'consistency', label: 'Consistency Report' },
      ]} />

      {tab === 'queue' && (
        <div>
          <Space style={{ marginBottom: 16 }}>
            <Button icon={<ReloadOutlined />} onClick={loadQueue}>Refresh</Button>
            <Button type="primary" disabled={selected.length === 0} onClick={bulkApprove}>
              Bulk Approve ({selected.length})
            </Button>
            <Input placeholder="Approval notes (optional)"
              value={approveNotes} onChange={(e) => setApproveNotes(e.target.value)}
              style={{ width: 280 }} />
          </Space>
          {queue.length === 0 ? (
            <Empty description="No assets pending review" />
          ) : (
            <Row gutter={[12, 12]}>
              {queue.map((a) => <Col key={a.id}>{renderAssetCard(a)}</Col>)}
            </Row>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div>
          <Space style={{ marginBottom: 16 }}>
            <Select
              placeholder="Select persona"
              style={{ width: 240 }}
              value={historyPersona}
              onChange={setHistoryPersona}
              options={personas.map((p) => ({ value: p.id, label: p.name }))}
            />
          </Space>
          {historyPersona === undefined ? (
            <Empty description="Select a persona to view its visual evolution" />
          ) : (
            <Timeline mode="left" items={history.map((a) => ({
              color: a.status === 'active' ? 'green' : a.status === 'review' ? 'orange' : 'gray',
              label: formatDateTime(a.updated_at),
              children: (
                <Card size="small" style={{ maxWidth: 360 }}>
                  <Space>
                    <Image src={a.thumbnail_url || a.url} width={80} height={80}
                      style={{ objectFit: 'cover' }} />
                    <Space direction="vertical" size={2}>
                      <Space size={4}>
                        <Tag color="blue">{a.asset_type}</Tag>
                        <Tag>v{a.version}</Tag>
                        <Tag color={statusColor[a.status]}>{a.status}</Tag>
                      </Space>
                      {a.consistency_score !== null && (
                        <Text style={{ fontSize: 11 }}>Score: {a.consistency_score?.toFixed(2)}</Text>
                      )}
                      {a.review_notes && (
                        <Text style={{ fontSize: 11, color: '#666' }}>{a.review_notes}</Text>
                      )}
                    </Space>
                  </Space>
                </Card>
              ),
            }))} />
          )}
        </div>
      )}

      {tab === 'consistency' && (
        <div>
          <Button icon={<ReloadOutlined />} onClick={loadReport} style={{ marginBottom: 16 }}>
            Refresh
          </Button>
          {report?.per_persona && (
            <Card title="Per-Persona Scores" size="small" style={{ marginBottom: 16 }}>
              <Table dataSource={report.per_persona} rowKey="persona_id" size="small" pagination={false}>
                <Table.Column title="Persona" dataIndex="persona_id"
                  render={(id: number) => personaName(id)} />
                <Table.Column title="Average Score" dataIndex="average_score"
                  render={(v: number) => v?.toFixed(3)} />
                <Table.Column title="Assets" dataIndex="asset_count" />
              </Table>
            </Card>
          )}
          {report?.flagged && report.flagged.length > 0 && (
            <Card title={`Flagged Items (${report.flagged.length})`} size="small">
              <Table dataSource={report.flagged} rowKey="id" size="small" pagination={false}>
                <Table.Column title="ID" dataIndex="id" width={60} />
                <Table.Column title="Persona" dataIndex="persona_id"
                  render={(id: number | null) => personaName(id)} />
                <Table.Column title="Type" dataIndex="asset_type"
                  render={(t: string) => <Tag color="blue">{t}</Tag>} />
                <Table.Column title="Score" dataIndex="consistency_score"
                  render={(v: number | null) => (
                    <Tag color={v !== null && v < 0.6 ? 'red' : 'orange'}>
                      {v !== null ? v.toFixed(2) : '—'}
                    </Tag>
                  )} />
                <Table.Column title="Preview" dataIndex="url"
                  render={(u: string) => <Image src={u} width={48} height={48} style={{ objectFit: 'cover' }} />} />
              </Table>
            </Card>
          )}
          {!report && <Empty description="No report available" />}
        </div>
      )}

      <Modal
        title={`Reject asset #${rejectModal.asset?.id ?? ''}`}
        open={rejectModal.visible}
        onOk={reject}
        onCancel={() => { setRejectModal({ visible: false, asset: null }); setRejectReason(''); }}
        okButtonProps={{ danger: true, disabled: !rejectReason.trim() }}
      >
        <TextArea rows={4} placeholder="Reason for rejection..."
          value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
      </Modal>
    </div>
  );
};

export default AssetsPage;
