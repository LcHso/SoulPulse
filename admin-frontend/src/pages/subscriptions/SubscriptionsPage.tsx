import React, { useEffect, useState } from 'react';
import {
  Tabs, Table, Button, Modal, Form, Input, InputNumber, DatePicker, Space, Tag,
  message, Popconfirm, Typography, Card, Row, Col, Statistic, Checkbox,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

interface Tier {
  id: number;
  tier_name: string;
  display_name: string;
  price_gems: number;
  duration_days: number;
  benefits_json: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
}

interface Campaign {
  id: number;
  event_name: string;
  description: string | null;
  event_type: string;
  start_date: string;
  end_date: string;
  reward_pool_json: Record<string, unknown>;
  participation_condition: string | null;
  progress_tracker_type: string;
  max_progress: number;
  is_active: boolean;
}

interface Stats {
  period_days: number;
  active_subscribers: number;
  new_subscriptions: number;
  subscription_revenue_gems: number;
  daily_reward_payout_gems: number;
  conversion_rate: number;
  by_tier: Array<{ tier_id: number; tier_name: string; display_name: string; active_subscribers: number }>;
}

const BENEFIT_OPTIONS = [
  { key: 'ad_free', label: 'Ad-free experience' },
  { key: 'daily_gems', label: 'Daily gem payout' },
  { key: 'unlimited_chat', label: 'Unlimited chat' },
  { key: 'priority_response', label: 'Priority response' },
  { key: 'exclusive_outfits', label: 'Exclusive outfits' },
  { key: 'archive_pass', label: 'Archive pass (limited characters)' },
  { key: 'gacha_discount', label: 'Gacha discount' },
];

const SubscriptionsPage: React.FC = () => {
  const [tab, setTab] = useState('tiers');

  // Tiers
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [tierModal, setTierModal] = useState(false);
  const [editingTier, setEditingTier] = useState<Tier | null>(null);
  const [tierForm] = Form.useForm();

  // Campaigns
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignModal, setCampaignModal] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [campaignForm] = Form.useForm();

  // Stats
  const [stats, setStats] = useState<Stats | null>(null);

  const loadTiers = async () => {
    const res = await client.get('/subscriptions/tiers');
    setTiers(res.data || []);
  };

  const loadCampaigns = async () => {
    const res = await client.get('/subscriptions/campaigns');
    setCampaigns(res.data || []);
  };

  const loadStats = async () => {
    const res = await client.get('/subscriptions/stats', { params: { days: 30 } });
    setStats(res.data);
  };

  useEffect(() => {
    if (tab === 'tiers') loadTiers();
    if (tab === 'campaigns') loadCampaigns();
    if (tab === 'stats') { loadStats(); loadTiers(); }
  }, [tab]);

  // ── Tier handlers ──
  const openTierCreate = () => {
    setEditingTier(null);
    tierForm.resetFields();
    tierForm.setFieldsValue({
      duration_days: 30, price_gems: 0, sort_order: 0, is_active: true, benefits: [],
    });
    setTierModal(true);
  };

  const openTierEdit = (t: Tier) => {
    setEditingTier(t);
    const benefits = Object.keys(t.benefits_json || {}).filter((k) => t.benefits_json[k]);
    tierForm.setFieldsValue({
      ...t,
      benefits,
      daily_gems_amount: (t.benefits_json?.daily_gems_amount as number) || 0,
    });
    setTierModal(true);
  };

  const saveTier = async () => {
    const values = await tierForm.validateFields();
    const benefits_json: Record<string, unknown> = {};
    (values.benefits || []).forEach((k: string) => { benefits_json[k] = true; });
    if (values.daily_gems_amount) benefits_json.daily_gems_amount = values.daily_gems_amount;
    const payload = {
      tier_name: values.tier_name,
      display_name: values.display_name,
      price_gems: values.price_gems,
      duration_days: values.duration_days,
      benefits_json,
      is_active: values.is_active,
      sort_order: values.sort_order,
    };
    try {
      if (editingTier) {
        await client.put(`/subscriptions/tiers/${editingTier.id}`, payload);
      } else {
        await client.post('/subscriptions/tiers', payload);
      }
      message.success('Saved');
      setTierModal(false);
      loadTiers();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Save failed');
    }
  };

  const deleteTier = async (id: number) => {
    await client.delete(`/subscriptions/tiers/${id}`);
    message.success('Archived');
    loadTiers();
  };

  // ── Campaign handlers ──
  const openCampaignCreate = () => {
    setEditingCampaign(null);
    campaignForm.resetFields();
    campaignForm.setFieldsValue({
      progress_tracker_type: 'counter', max_progress: 7, is_active: true,
    });
    setCampaignModal(true);
  };

  const openCampaignEdit = (c: Campaign) => {
    setEditingCampaign(c);
    campaignForm.setFieldsValue({
      ...c,
      date_range: [dayjs(c.start_date), dayjs(c.end_date)],
      reward_pool_json: JSON.stringify(c.reward_pool_json || {}, null, 2),
    });
    setCampaignModal(true);
  };

  const saveCampaign = async () => {
    const values = await campaignForm.validateFields();
    const [start, end]: [Dayjs, Dayjs] = values.date_range;
    let reward_pool: Record<string, unknown> = {};
    if (values.reward_pool_json) {
      try {
        reward_pool = JSON.parse(values.reward_pool_json);
      } catch {
        message.error('Reward pool JSON is invalid');
        return;
      }
    }
    const payload = {
      event_name: values.event_name,
      description: values.description || null,
      event_type: values.event_type,
      start_date: start.toISOString(),
      end_date: end.toISOString(),
      reward_pool_json: reward_pool,
      participation_condition: values.participation_condition || null,
      progress_tracker_type: values.progress_tracker_type,
      max_progress: values.max_progress,
      is_active: values.is_active,
    };
    try {
      if (editingCampaign) {
        await client.put(`/subscriptions/campaigns/${editingCampaign.id}`, payload);
      } else {
        await client.post('/subscriptions/campaigns', payload);
      }
      message.success('Saved');
      setCampaignModal(false);
      loadCampaigns();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Save failed');
    }
  };

  const deleteCampaign = async (id: number) => {
    await client.delete(`/subscriptions/campaigns/${id}`);
    message.success('Archived');
    loadCampaigns();
  };

  return (
    <div>
      <Title level={4}>Subscriptions & Events</Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'tiers', label: 'Subscription Tiers' },
        { key: 'campaigns', label: 'Event Campaigns' },
        { key: 'stats', label: 'Stats' },
      ]} />

      {tab === 'tiers' && (
        <div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openTierCreate} style={{ marginBottom: 16 }}>
            New Tier
          </Button>
          <Table dataSource={tiers} rowKey="id" size="small" pagination={false}>
            <Table.Column title="Tier" dataIndex="tier_name" />
            <Table.Column title="Display" dataIndex="display_name" />
            <Table.Column title="Price (gems)" dataIndex="price_gems" width={110} />
            <Table.Column title="Duration (days)" dataIndex="duration_days" width={130} />
            <Table.Column title="Benefits" dataIndex="benefits_json"
              render={(b: Record<string, unknown>) => (
                <Space wrap size={4}>
                  {Object.keys(b || {}).filter((k) => b[k] && k !== 'daily_gems_amount').map((k) => (
                    <Tag key={k} color="purple">{k}</Tag>
                  ))}
                </Space>
              )} />
            <Table.Column title="Active" dataIndex="is_active" width={80}
              render={(v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
            <Table.Column title="" width={120} render={(_: unknown, r: Tier) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => openTierEdit(r)} />
                <Popconfirm title="Archive?" onConfirm={() => deleteTier(r.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            )} />
          </Table>
        </div>
      )}

      {tab === 'campaigns' && (
        <div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCampaignCreate} style={{ marginBottom: 16 }}>
            New Campaign
          </Button>
          <Table dataSource={campaigns} rowKey="id" size="small" pagination={{ pageSize: 20 }}>
            <Table.Column title="Name" dataIndex="event_name" />
            <Table.Column title="Type" dataIndex="event_type" width={120}
              render={(t: string) => <Tag color="blue">{t}</Tag>} />
            <Table.Column title="Start" dataIndex="start_date" width={140}
              render={(d: string) => formatDateTime(d)} />
            <Table.Column title="End" dataIndex="end_date" width={140}
              render={(d: string) => formatDateTime(d)} />
            <Table.Column title="Tracker" dataIndex="progress_tracker_type" width={100} />
            <Table.Column title="Max" dataIndex="max_progress" width={70} />
            <Table.Column title="Active" dataIndex="is_active" width={80}
              render={(v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? 'Yes' : 'No'}</Tag>} />
            <Table.Column title="" width={120} render={(_: unknown, r: Campaign) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => openCampaignEdit(r)} />
                <Popconfirm title="Archive?" onConfirm={() => deleteCampaign(r.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            )} />
          </Table>
        </div>
      )}

      {tab === 'stats' && stats && (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Card><Statistic title="Active Subscribers" value={stats.active_subscribers} /></Card></Col>
            <Col span={6}><Card><Statistic title={`New (${stats.period_days}d)`} value={stats.new_subscriptions} /></Card></Col>
            <Col span={6}><Card><Statistic title={`Revenue Gems (${stats.period_days}d)`} value={stats.subscription_revenue_gems} /></Card></Col>
            <Col span={6}><Card><Statistic title="Conversion Rate" value={`${(stats.conversion_rate * 100).toFixed(2)}%`} /></Card></Col>
          </Row>
          <Card title="Per-Tier Active Subscribers" size="small">
            <Table dataSource={stats.by_tier} rowKey="tier_id" size="small" pagination={false}>
              <Table.Column title="Tier" dataIndex="tier_name" />
              <Table.Column title="Display" dataIndex="display_name" />
              <Table.Column title="Active Subscribers" dataIndex="active_subscribers" />
            </Table>
          </Card>
        </div>
      )}

      {/* Tier modal */}
      <Modal
        title={editingTier ? 'Edit Tier' : 'New Tier'}
        open={tierModal}
        onOk={saveTier}
        onCancel={() => setTierModal(false)}
        width={640}
        destroyOnClose
      >
        <Form form={tierForm} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="tier_name" label="Tier Name (slug)" rules={[{ required: true }]} style={{ flex: 1, marginRight: 12 }}>
              <Input placeholder="basic / premium / vip" />
            </Form.Item>
            <Form.Item name="display_name" label="Display Name" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </Space.Compact>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="price_gems" label="Price (gems)" style={{ flex: 1, marginRight: 12 }}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="duration_days" label="Duration (days)" style={{ flex: 1, marginRight: 12 }}>
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="sort_order" label="Sort Order" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="benefits" label="Benefits">
            <Checkbox.Group options={BENEFIT_OPTIONS.map((b) => ({ value: b.key, label: b.label }))} />
          </Form.Item>
          <Form.Item name="daily_gems_amount" label="Daily gem payout amount (if applicable)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Checkbox>Active</Checkbox>
          </Form.Item>
        </Form>
      </Modal>

      {/* Campaign modal */}
      <Modal
        title={editingCampaign ? 'Edit Campaign' : 'New Campaign'}
        open={campaignModal}
        onOk={saveCampaign}
        onCancel={() => setCampaignModal(false)}
        width={680}
        destroyOnClose
      >
        <Form form={campaignForm} layout="vertical">
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="event_name" label="Event Name" rules={[{ required: true }]} style={{ flex: 2, marginRight: 12 }}>
              <Input />
            </Form.Item>
            <Form.Item name="event_type" label="Event Type" rules={[{ required: true }]} style={{ flex: 1 }}>
              <Input placeholder="login_streak / spending / chat ..." />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="date_range" label="Date Range" rules={[{ required: true }]}>
            <RangePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="progress_tracker_type" label="Progress Tracker Type" style={{ flex: 1, marginRight: 12 }}>
              <Input placeholder="counter / streak / sum" />
            </Form.Item>
            <Form.Item name="max_progress" label="Max Progress" style={{ flex: 1 }}>
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="participation_condition" label="Participation Condition">
            <Input placeholder='e.g. "min_intimacy:30"' />
          </Form.Item>
          <Form.Item name="reward_pool_json" label="Reward Pool (JSON)">
            <TextArea rows={4} placeholder='{"day_3": {"gems": 50}, "day_7": {"outfit_id": 12}}'
              style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Checkbox>Active</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SubscriptionsPage;
