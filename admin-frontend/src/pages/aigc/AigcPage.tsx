import React, { useEffect, useState } from 'react';
import { Tabs, Table, Button, Image, Tag, Space, message, Modal, Input, Select, Form, Popconfirm, Typography } from 'antd';
import { CheckOutlined, CloseOutlined, ReloadOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import client from '../../api/client';
import { formatDateTime } from '../../utils/formatDate';

const { Title } = Typography;
const { TextArea } = Input;

interface Post {
  id: number;
  ai_id: number;
  ai_name: string;
  ai_avatar: string;
  media_url: string;
  caption: string;
  status: number;
  created_at: string;
}

interface Persona { id: number; name: string; }

interface VisualDna {
  id: number;
  persona_id: number;
  face_url: string;
  style_preset_json: string;
  version_note: string;
  created_by: number;
  created_at: string;
}

interface Story {
  id: number;
  ai_id: number;
  ai_name: string;
  media_url: string;
  media_type: string;
  caption: string;
  created_at: string;
}

const statusMap: Record<number, { text: string; color: string }> = {
  0: { text: 'Pending', color: 'orange' },
  1: { text: 'Published', color: 'green' },
  2: { text: 'Rejected', color: 'red' },
};

const AigcPage: React.FC = () => {
  const [mainTab, setMainTab] = useState('posts');

  // Posts state
  const [posts, setPosts] = useState<Post[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [postTab, setPostTab] = useState<string>('pending');
  const [page, setPage] = useState(1);
  const [regenModal, setRegenModal] = useState<{ visible: boolean; postId: number; caption: string }>({ visible: false, postId: 0, caption: '' });
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  // Visual DNA state
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<number | null>(null);
  const [visualDna, setVisualDna] = useState<VisualDna[]>([]);
  const [vdLoading, setVdLoading] = useState(false);
  const [vdModal, setVdModal] = useState(false);
  const [vdForm] = Form.useForm();

  // Stories state
  const [stories, setStories] = useState<Story[]>([]);
  const [storyTotal, setStoryTotal] = useState(0);
  const [storyPage, setStoryPage] = useState(1);
  const [storyLoading, setStoryLoading] = useState(false);

  // Posts
  const loadPosts = async (status?: number, p = 1) => {
    setLoading(true);
    try {
      const params: Record<string, number> = { limit: 20, offset: (p - 1) * 20 };
      if (status !== undefined) params.status = status;
      const res = await client.get('/posts/all', { params });
      setPosts(res.data.posts);
      setTotal(res.data.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const statusVal = postTab === 'pending' ? 0 : postTab === 'published' ? 1 : postTab === 'rejected' ? 2 : undefined;
    loadPosts(statusVal, page);
  }, [postTab, page]);

  useEffect(() => {
    client.get('/personas').then(res => setPersonas(res.data.map((p: { id: number; name: string }) => ({ id: p.id, name: p.name }))));
  }, []);

  const approve = async (id: number) => { await client.post(`/posts/${id}/approve`); message.success('Post approved'); loadPosts(0, page); };
  const reject = async (id: number) => { await client.post(`/posts/${id}/reject`); message.success('Post rejected'); loadPosts(0, page); };
  const deletePost = async (id: number) => {
    await client.delete(`/posts/${id}`);
    message.success('Post deleted');
    const statusVal = postTab === 'pending' ? 0 : postTab === 'published' ? 1 : postTab === 'rejected' ? 2 : undefined;
    loadPosts(statusVal, page);
  };
  const regenerate = async () => {
    try {
      await client.post(`/posts/${regenModal.postId}/regenerate`, { new_caption: regenModal.caption || null });
      message.success('Image regenerated');
      setRegenModal({ visible: false, postId: 0, caption: '' });
      loadPosts(0, page);
    } catch (err: any) { message.error(err.response?.data?.detail || 'Regeneration failed'); }
  };

  // Batch actions
  const handleBatchApprove = async () => {
    try {
      const res = await client.post('/posts/batch-approve', { post_ids: selectedRowKeys });
      message.success(`Approved ${res.data.approved_count} posts`);
      setSelectedRowKeys([]);
      const statusVal = postTab === 'pending' ? 0 : postTab === 'published' ? 1 : postTab === 'rejected' ? 2 : undefined;
      loadPosts(statusVal, page);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Batch approve failed');
    }
  };

  const handleBatchReject = async () => {
    try {
      const res = await client.post('/posts/batch-reject', { post_ids: selectedRowKeys });
      message.success(`Rejected ${res.data.rejected_count} posts`);
      setSelectedRowKeys([]);
      const statusVal = postTab === 'pending' ? 0 : postTab === 'published' ? 1 : postTab === 'rejected' ? 2 : undefined;
      loadPosts(statusVal, page);
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Batch reject failed');
    }
  };

  // Visual DNA
  const loadVisualDna = async (pid: number) => {
    setVdLoading(true);
    try {
      const res = await client.get(`/visual-dna/${pid}`);
      setVisualDna(res.data);
    } finally { setVdLoading(false); }
  };

  useEffect(() => { if (selectedPersona) loadVisualDna(selectedPersona); }, [selectedPersona]);

  const createVisualDna = async () => {
    const values = vdForm.getFieldsValue();
    values.persona_id = selectedPersona;
    await client.post('/visual-dna', values);
    message.success('Visual DNA version created');
    setVdModal(false); vdForm.resetFields();
    if (selectedPersona) loadVisualDna(selectedPersona);
  };

  const deleteVisualDna = async (id: number) => {
    await client.delete(`/visual-dna/${id}`);
    message.success('Deleted');
    if (selectedPersona) loadVisualDna(selectedPersona);
  };

  // Stories
  const loadStories = async (p = 1) => {
    setStoryLoading(true);
    try {
      const res = await client.get('/stories', { params: { limit: 20, offset: (p - 1) * 20 } });
      setStories(res.data.stories);
      setStoryTotal(res.data.total);
    } finally { setStoryLoading(false); }
  };

  useEffect(() => { if (mainTab === 'stories') loadStories(storyPage); }, [mainTab, storyPage]);

  const deleteStory = async (id: number) => {
    await client.delete(`/stories/${id}`);
    message.success('Story deleted');
    loadStories(storyPage);
  };

  const postColumns = [
    { title: 'Media', dataIndex: 'media_url', width: 80, render: (url: string) => <Image src={url} width={60} height={60} style={{ objectFit: 'cover', borderRadius: 4 }} /> },
    { title: 'AI', dataIndex: 'ai_name', render: (name: string, r: Post) => <span><img src={r.ai_avatar} alt="" style={{ width: 20, height: 20, borderRadius: 10, marginRight: 6 }} />{name}</span> },
    { title: 'Caption', dataIndex: 'caption', ellipsis: true },
    { title: 'Status', dataIndex: 'status', render: (s: number) => <Tag color={statusMap[s]?.color}>{statusMap[s]?.text}</Tag> },
    { title: 'Created', dataIndex: 'created_at', width: 160, render: (d: string) => formatDateTime(d) },
    { title: 'Actions', width: 220, render: (_: unknown, r: Post) => (
      <Space size="small">
        {r.status === 0 && (<>
          <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => approve(r.id)}>Approve</Button>
          <Button size="small" danger icon={<CloseOutlined />} onClick={() => reject(r.id)}>Reject</Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => setRegenModal({ visible: true, postId: r.id, caption: r.caption })}>Regen</Button>
        </>)}
        <Popconfirm title="Delete this post?" onConfirm={() => deletePost(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <div>
      <Title level={4}>AIGC Content Control</Title>
      <Tabs activeKey={mainTab} onChange={setMainTab} items={[
        { key: 'posts', label: 'Posts' },
        { key: 'visual-dna', label: 'Visual DNA' },
        { key: 'stories', label: 'Stories' },
      ]} />

      {mainTab === 'posts' && (
        <div>
          <Tabs activeKey={postTab} onChange={(k) => { setPostTab(k); setPage(1); setSelectedRowKeys([]); }} size="small"
            items={[
              { key: 'pending', label: 'Pending' },
              { key: 'published', label: 'Published' },
              { key: 'rejected', label: 'Rejected' },
              { key: 'all', label: 'All' },
            ]}
          />
          {selectedRowKeys.length > 0 && postTab === 'pending' && (
            <Space style={{ marginBottom: 16 }}>
              <Button type="primary" icon={<CheckOutlined />} onClick={handleBatchApprove}>
                Approve Selected ({selectedRowKeys.length})
              </Button>
              <Button danger icon={<CloseOutlined />} onClick={handleBatchReject}>
                Reject Selected ({selectedRowKeys.length})
              </Button>
            </Space>
          )}
          <Table
            rowSelection={postTab === 'pending' ? {
              selectedRowKeys,
              onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
            } : undefined}
            dataSource={posts}
            columns={postColumns}
            rowKey="id"
            loading={loading}
            pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); setSelectedRowKeys([]); } }}
            size="small"
          />
          <Modal title="Regenerate Image" open={regenModal.visible}
            onOk={regenerate} onCancel={() => setRegenModal({ visible: false, postId: 0, caption: '' })}>
            <p>Optionally update the caption before regenerating:</p>
            <TextArea rows={3} value={regenModal.caption} onChange={(e) => setRegenModal({ ...regenModal, caption: e.target.value })} />
          </Modal>
        </div>
      )}

      {mainTab === 'visual-dna' && (
        <div>
          <Space style={{ marginBottom: 16 }}>
            <Select placeholder="Select Persona" style={{ width: 200 }} value={selectedPersona}
              onChange={(v) => setSelectedPersona(v)}
              options={personas.map(p => ({ value: p.id, label: p.name }))} />
            {selectedPersona && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => { vdForm.resetFields(); setVdModal(true); }}>
                New Version
              </Button>
            )}
          </Space>
          {selectedPersona && (
            <Table dataSource={visualDna} rowKey="id" size="small" loading={vdLoading} pagination={false}>
              <Table.Column title="Face" dataIndex="face_url" width={80} render={(url: string) => url ? <Image src={url} width={50} height={50} style={{ objectFit: 'cover', borderRadius: 4 }} /> : '-'} />
              <Table.Column title="Style Preset" dataIndex="style_preset_json" ellipsis />
              <Table.Column title="Note" dataIndex="version_note" ellipsis />
              <Table.Column title="Created" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
              <Table.Column title="" width={60} render={(_: unknown, r: VisualDna) => (
                <Popconfirm title="Delete this version?" onConfirm={() => deleteVisualDna(r.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              )} />
            </Table>
          )}
          <Modal title="New Visual DNA Version" open={vdModal} onOk={createVisualDna} onCancel={() => setVdModal(false)}>
            <Form form={vdForm} layout="vertical">
              <Form.Item name="face_url" label="Face Reference URL"><Input placeholder="https://..." /></Form.Item>
              <Form.Item name="style_preset_json" label="Style Preset JSON" initialValue="{}"><TextArea rows={3} /></Form.Item>
              <Form.Item name="version_note" label="Version Note"><Input placeholder="e.g. v2.0 updated face" /></Form.Item>
            </Form>
          </Modal>
        </div>
      )}

      {mainTab === 'stories' && (
        <Table dataSource={stories} rowKey="id" size="small" loading={storyLoading}
          pagination={{ current: storyPage, total: storyTotal, pageSize: 20, onChange: setStoryPage }}>
          <Table.Column title="Media" dataIndex="media_url" width={80}
            render={(url: string) => <Image src={url} width={60} height={60} style={{ objectFit: 'cover', borderRadius: 4 }} />} />
          <Table.Column title="AI" dataIndex="ai_name" />
          <Table.Column title="Type" dataIndex="media_type" width={80} render={(t: string) => <Tag>{t}</Tag>} />
          <Table.Column title="Caption" dataIndex="caption" ellipsis />
          <Table.Column title="Created" dataIndex="created_at" width={140} render={(d: string) => formatDateTime(d)} />
          <Table.Column title="" width={60} render={(_: unknown, r: Story) => (
            <Popconfirm title="Delete this story?" onConfirm={() => deleteStory(r.id)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )} />
        </Table>
      )}
    </div>
  );
};

export default AigcPage;
