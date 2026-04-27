import React, { useEffect, useState, useRef } from 'react';
import { Row, Col, Card, Statistic, Table, Spin, Typography, Tag, Select, Progress } from 'antd';
import { UserOutlined, MessageOutlined, PictureOutlined, RobotOutlined, ClockCircleOutlined, WifiOutlined, WarningOutlined, FieldTimeOutlined, RiseOutlined } from '@ant-design/icons';
import { Line, Pie } from '@ant-design/charts';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;

interface Overview {
  total_users: number;
  total_personas: number;
  pending_posts: number;
  published_posts: number;
  total_messages: number;
  total_stories: number;
  active_users_24h: number;
  online_now: number;
  active_users_30d: number;
  dau_mau_ratio: number;
  avg_session_length_min: number;
}

interface CharacterDistribution {
  ai_id: number;
  ai_name: string;
  message_count: number;
  percentage: number;
}

interface DailyStats {
  date: string;
  new_users: number;
  messages: number;
  posts_generated: number;
  api_calls: number;
}

interface LeaderEntry {
  persona_id: number;
  persona_name: string;
  avatar_url: string;
  total_messages: number;
  unique_users: number;
}

interface RetentionData {
  period: string;
  registered: number;
  returned: number;
  rate: number;
}

interface RealtimeData {
  total_connections: number;
  per_persona: Record<string, number>;
}

interface ApiError {
  id: number;
  service: string;
  model_name: string;
  error_message: string;
  latency_ms: number;
  created_at: string;
}

const DashboardPage: React.FC = () => {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [daily, setDaily] = useState<DailyStats[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderEntry[]>([]);
  const [retention, setRetention] = useState<RetentionData[]>([]);
  const [realtime, setRealtime] = useState<RealtimeData | null>(null);
  const [errors, setErrors] = useState<ApiError[]>([]);
  const [charDistribution, setCharDistribution] = useState<CharacterDistribution[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartDays, setChartDays] = useState(14);
  const realtimeTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRealtime = async () => {
    try {
      const res = await client.get('/analytics/realtime');
      setRealtime(res.data);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    Promise.all([
      client.get('/analytics/overview'),
      client.get(`/analytics/daily-stats?days=${chartDays}`),
      client.get('/analytics/leaderboard'),
      client.get('/analytics/retention').catch(() => ({ data: [] })),
      client.get('/analytics/realtime').catch(() => ({ data: null })),
      client.get('/analytics/errors?limit=20').catch(() => ({ data: [] })),
      client.get('/analytics/character-distribution?days=30').catch(() => ({ data: [] })),
    ]).then(([ovRes, dailyRes, lbRes, retRes, rtRes, errRes, charRes]) => {
      setOverview(ovRes.data);
      setDaily(dailyRes.data);
      setLeaderboard(lbRes.data);
      setRetention(retRes.data || []);
      setRealtime(rtRes.data);
      setErrors(errRes.data || []);
      setCharDistribution(charRes.data || []);
    }).finally(() => setLoading(false));

    realtimeTimer.current = setInterval(loadRealtime, 10000);
    return () => { if (realtimeTimer.current) clearInterval(realtimeTimer.current); };
  }, []);

  useEffect(() => {
    if (!loading) {
      client.get(`/analytics/daily-stats?days=${chartDays}`).then(res => setDaily(res.data));
    }
  }, [chartDays]);

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 100 }} />;

  const chartData = [...daily].reverse().flatMap(d => [
    { date: d.date, value: d.messages, category: 'Messages' },
    { date: d.date, value: d.new_users, category: 'New Users' },
    { date: d.date, value: d.posts_generated, category: 'Posts' },
  ]);

  return (
    <div>
      <Title level={4}>Dashboard</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}><Card><Statistic title="Total Users" value={overview?.total_users} prefix={<UserOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="AI Personas" value={overview?.total_personas} prefix={<RobotOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="Total Messages" value={overview?.total_messages} prefix={<MessageOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="Online Now" value={overview?.online_now} prefix={<WifiOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="Pending Posts" value={overview?.pending_posts} prefix={<PictureOutlined />} valueStyle={overview?.pending_posts ? { color: '#fa8c16' } : undefined} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="Published Posts" value={overview?.published_posts} prefix={<PictureOutlined />} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="Stories" value={overview?.total_stories} /></Card></Col>
        <Col xs={12} sm={6}><Card><Statistic title="Active (24h)" value={overview?.active_users_24h} prefix={<ClockCircleOutlined />} /></Card></Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="DAU/MAU Stickiness"
              value={overview?.dau_mau_ratio ?? 0}
              suffix="%"
              prefix={<RiseOutlined />}
              valueStyle={{ color: (overview?.dau_mau_ratio ?? 0) >= 20 ? '#52c41a' : (overview?.dau_mau_ratio ?? 0) >= 10 ? '#fa8c16' : '#ff4d4f' }}
            />
            <Progress percent={overview?.dau_mau_ratio ?? 0} size="small" showInfo={false} strokeColor={(overview?.dau_mau_ratio ?? 0) >= 20 ? '#52c41a' : (overview?.dau_mau_ratio ?? 0) >= 10 ? '#fa8c16' : '#ff4d4f'} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="Avg Session Length"
              value={overview?.avg_session_length_min ?? 0}
              suffix="min"
              prefix={<FieldTimeOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Daily Trend Chart */}
      <Card title="Daily Trend" size="small" style={{ marginBottom: 16 }}
        extra={<Select value={chartDays} onChange={setChartDays} size="small" options={[{ value: 7, label: '7 days' }, { value: 14, label: '14 days' }, { value: 30, label: '30 days' }]} />}>
        {chartData.length > 0 ? (
          <Line data={chartData} xField="date" yField="value" colorField="category" height={280}
            axis={{ x: { labelAutoRotate: false } }}
            interaction={{ tooltip: { render: (_: unknown, { title, items }: { title: string; items: { name: string; value: number; color: string }[] }) => (
              `<div style="padding:4px 8px"><div style="margin-bottom:4px;font-weight:500">${title}</div>${items.map((i: { name: string; value: number; color: string }) => `<div><span style="color:${i.color}">${i.name}</span>: ${i.value}</div>`).join('')}</div>`
            )}}}
          />
        ) : <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>No data</div>}
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* Leaderboard */}
        <Col xs={24} lg={12}>
          <Card title="AI Leaderboard" size="small">
            <Table dataSource={leaderboard} rowKey="persona_id" size="small" pagination={false} scroll={{ y: 300 }}>
              <Table.Column title="Persona" dataIndex="persona_name" render={(name: string, record: LeaderEntry) => (
                <span><img src={record.avatar_url} alt="" style={{ width: 24, height: 24, borderRadius: 12, marginRight: 8, verticalAlign: 'middle' }} />{name}</span>
              )} />
              <Table.Column title="Messages" dataIndex="total_messages" sorter={(a: LeaderEntry, b: LeaderEntry) => a.total_messages - b.total_messages} />
              <Table.Column title="Users" dataIndex="unique_users" />
            </Table>
          </Card>
        </Col>
        {/* Character Distribution Pie Chart */}
        <Col xs={24} lg={12}>
          <Card title="Message Distribution by Character" size="small">
            {charDistribution.length > 0 ? (
              <Pie
                data={charDistribution.map(c => ({ name: c.ai_name, value: c.message_count }))}
                angleField="value"
                colorField="name"
                radius={0.8}
                innerRadius={0.6}
                height={280}
                label={{
                  type: 'outer',
                  content: '{name}: {percentage}',
                }}
                legend={{
                  position: 'bottom',
                  maxRowHeight: 3,
                }}
                interactions={[{ type: 'element-active' }]}
              />
            ) : <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>No data</div>}
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* Retention */}
        <Col xs={24} lg={12}>
          <Card title="User Retention" size="small">
            {retention.length > 0 ? (
              <Table dataSource={retention} rowKey="period" size="small" pagination={false}>
                <Table.Column title="Period" dataIndex="period" />
                <Table.Column title="Registered" dataIndex="registered" />
                <Table.Column title="Returned" dataIndex="returned" />
                <Table.Column title="Rate" dataIndex="rate" render={(v: number) => (
                  <Tag color={v >= 50 ? 'green' : v >= 20 ? 'orange' : 'red'}>{v?.toFixed(1)}%</Tag>
                )} />
              </Table>
            ) : <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>No retention data</div>}
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {/* Realtime */}
        <Col xs={24} lg={8}>
          <Card title={<span><WifiOutlined style={{ color: '#52c41a', marginRight: 8 }} />Realtime</span>} size="small">
            <Statistic title="Active Connections" value={realtime?.total_connections ?? 0} valueStyle={{ color: '#52c41a' }} />
            {realtime?.per_persona && Object.keys(realtime.per_persona).length > 0 && (
              <div style={{ marginTop: 12 }}>
                {Object.entries(realtime.per_persona).map(([pid, count]) => (
                  <Tag key={pid} style={{ marginBottom: 4 }}>Persona #{pid}: {count}</Tag>
                ))}
              </div>
            )}
          </Card>
        </Col>
        {/* Recent Errors */}
        <Col xs={24} lg={16}>
          <Card title={<span><WarningOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />Recent Errors</span>} size="small">
            {errors.length > 0 ? (
              <Table dataSource={errors} rowKey="id" size="small" pagination={{ pageSize: 5 }} scroll={{ y: 200 }}>
                <Table.Column title="Service" dataIndex="service" width={120} />
                <Table.Column title="Model" dataIndex="model_name" width={120} />
                <Table.Column title="Error" dataIndex="error_message" ellipsis />
                <Table.Column title="Latency" dataIndex="latency_ms" width={80} render={(v: number) => `${v}ms`} />
                <Table.Column title="Time" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
              </Table>
            ) : <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>No recent errors</div>}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DashboardPage;
