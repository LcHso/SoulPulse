// ============================================================================
// SoulPulse 信息流页面
// ============================================================================
//
// 本文件提供应用的主信息流页面，展示 AI 人设发布的帖子内容，包含：
// - 故事条（Story Bar）展示区域
// - 帖子列表的加载与分页
// - 下拉刷新功能
// - 骨架屏加载动画
// - 帖子卡片交互（点赞、保存、评论、私信）
// - 导航到 AI 详情页、聊天页、帖子详情页
//
// 主要组件：
// - FeedPage: 页面根组件（使用 AutomaticKeepAliveClientMixin 保持状态）
//
// 功能说明：
// - 页面进入时自动加载帖子数据
// - 滚动到底部时自动加载更多帖子
// - 支持下拉刷新更新内容
// - 未读通知数量显示在 AppBar 图标上
//
// ============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import '../../core/providers/feed_provider.dart';
import '../../core/providers/notification_provider.dart';
import 'widgets/story_bar.dart';
import 'widgets/post_card.dart';

/// 信息流页面组件
///
/// 继承 ConsumerStatefulWidget 以支持 Riverpod 状态管理。
/// 使用 AutomaticKeepAliveClientMixin 保持页面状态，
/// 在底部导航切换时不重新加载数据。
class FeedPage extends ConsumerStatefulWidget {
  /// 构造函数
  const FeedPage({super.key});

  @override
  ConsumerState<FeedPage> createState() => _FeedPageState();
}

/// 信息流页面状态类
///
/// 使用 AutomaticKeepAliveClientMixin 保持页面状态，
/// 避免底部导航切换时重新初始化。
class _FeedPageState extends ConsumerState<FeedPage>
    with AutomaticKeepAliveClientMixin {
  /// 滚动控制器
  ///
  /// 用于监听滚动事件实现分页加载
  final _scrollCtrl = ScrollController();

  /// 保持页面状态标志
  ///
  /// 返回 true 表示切换页面时保持当前状态
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();

    // 监听滚动事件，实现滚动到底部时加载更多
    _scrollCtrl.addListener(_onScroll);

    // 使用 microtask 确保初始化完成后加载帖子
    Future.microtask(
        () => ref.read(feedProvider.notifier).loadPosts(refresh: true));
  }

  @override
  void dispose() {
    // 清理滚动监听器和控制器
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  /// 滚动监听回调
  ///
  /// 当用户滚动到接近底部时（距离底部 300 像素以内），
  /// 触发加载更多帖子的操作。
  void _onScroll() {
    if (_scrollCtrl.position.pixels >=
        _scrollCtrl.position.maxScrollExtent - 300) {
      final state = ref.read(feedProvider);

      // 如果不在加载中且还有更多数据，加载下一页
      if (!state.isLoading && state.hasMore) {
        ref.read(feedProvider.notifier).loadPosts();
      }
    }
  }

  /// 打开与 AI 的聊天页面
  ///
  /// 从帖子发起聊天时，将帖子内容作为上下文传递
  ///
  /// [post] 帖子数据对象
  void _openChat(Map<String, dynamic> post) {
    final aiId = post['ai_id'];
    final aiName = Uri.encodeComponent(post['ai_name'] ?? 'AI');
    final caption = post['caption'] as String?;

    // 构造聊天页面路径
    var path = '/chat/$aiId?name=$aiName';

    // 如果帖子有内容，作为上下文传递
    if (caption != null && caption.isNotEmpty) {
      path += '&context=${Uri.encodeComponent(caption)}';
    }

    context.push(path);
  }

  /// 打开 AI 详情页面
  ///
  /// 显示 AI 人设的详细信息和情绪状态
  ///
  /// [post] 帖子数据对象（用于获取 AI ID 和名称）
  void _openProfile(Map<String, dynamic> post) {
    final aiId = post['ai_id'];
    final aiName = Uri.encodeComponent(post['ai_name'] ?? 'AI');
    context.push('/ai/$aiId?name=$aiName');
  }

  /// 打开故事播放器页面
  ///
  /// 播放指定 AI 发布的故事内容
  ///
  /// [stories] 故事列表数据
  /// [aiId] AI ID
  void _openStoryPlayer(List<dynamic> stories, int aiId) {
    if (stories.isEmpty) return;

    final aiName = stories.first['ai_name'] as String? ?? 'AI';

    // 使用 extra 参数传递故事数据
    context.push('/story', extra: {
      'stories': stories,
      'aiName': aiName,
      'aiId': aiId,
    });
  }

  /// 打开帖子详情页面
  ///
  /// 显示帖子的完整内容和评论列表
  ///
  /// [post] 帖子数据对象
  void _openPostDetail(Map<String, dynamic> post) async {
    await context.push('/post-detail', extra: {
      'post': post,
      'aiName': post['ai_name'] ?? 'AI',
      'aiAvatar': post['ai_avatar'] ?? '',
    });
  }

  @override
  Widget build(BuildContext context) {
    // 调用父类 build 方法（AutomaticKeepAliveClientMixin 需要）
    super.build(context);

    // 监听信息流状态
    final feedState = ref.watch(feedProvider);

    // 监听通知状态（用于显示未读数量）
    final notifState = ref.watch(notificationProvider);
    final notifUnread = notifState.unreadCount;

    return Scaffold(
      appBar: AppBar(
        title: const Text('SoulPulse'),
        actions: [
          /// 通知按钮
          ///
          /// 显示未读数量的 Badge 图标
          IconButton(
            icon: Badge(
              isLabelVisible: notifUnread > 0, // 有未读时显示 Badge
              label: Text('$notifUnread'), // 未读数量
              child: const Icon(Icons.notifications_none),
            ),
            onPressed: () => context.push('/notifications'),
          ),
        ],
      ),
      body: RefreshIndicator(
        /// 下拉刷新回调
        ///
        /// 刷新帖子列表和故事数据
        onRefresh: () async {
          await ref.read(feedProvider.notifier).loadPosts(refresh: true);
          ref.invalidate(storiesProvider); // 刷新故事数据
        },

        /// 根据状态显示不同内容
        child: feedState.isLoading && feedState.posts.isEmpty
            // 加载中且无数据：显示骨架屏
            ? _buildShimmerLoading()
            : feedState.error != null && feedState.posts.isEmpty
                // 有错误且无数据：显示错误状态
                ? _buildErrorState(feedState.error!)
                : feedState.posts.isEmpty
                    // 无数据且无错误：显示空状态
                    ? _buildEmptyState()
                    // 有数据：显示帖子列表
                    : ListView.builder(
                        controller: _scrollCtrl,
                        itemCount:
                            feedState.posts.length + 2, // +1 故事条, +1 加载指示器
                        itemBuilder: (context, index) {
                          // 第一项：故事条
                          if (index == 0) {
                            return StoryBar(onStoryTap: _openStoryPlayer);
                          }

                          // 最后一项：加载状态指示器
                          if (index == feedState.posts.length + 1) {
                            // 正在加载中
                            if (feedState.isLoading) {
                              return const Padding(
                                padding: EdgeInsets.all(16),
                                child: Center(
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2)),
                              );
                            }

                            // 没有更多数据
                            if (!feedState.hasMore) {
                              return Padding(
                                padding: const EdgeInsets.all(24),
                                child: Center(
                                  child: Text(
                                    'You\'re all caught up',
                                    style: TextStyle(
                                        color: Colors.grey[500], fontSize: 13),
                                  ),
                                ),
                              );
                            }

                            // 其他情况不显示
                            return const SizedBox.shrink();
                          }

                          // 帖子卡片
                          final post = feedState.posts[index - 1];
                          return PostCard(
                            post: post,

                            /// 点赞回调
                            onLike: () => ref
                                .read(feedProvider.notifier)
                                .toggleLike(post['id']),

                            /// 保存回调
                            onSave: () => ref
                                .read(feedProvider.notifier)
                                .toggleSave(post['id']),

                            /// 私信回调
                            onDM: () => _openChat(post),

                            /// 打开 AI 详情回调
                            onProfileTap: () => _openProfile(post),

                            /// 打开帖子详情回调（用于评论）
                            onComment: () => _openPostDetail(post),
                          );
                        },
                      ),
      ),
    );
  }

  // ================== 骨架屏加载动画 ==================

  /// 构建骨架屏加载动画
  ///
  /// 使用 Shimmer 效果模拟加载中的内容布局
  Widget _buildShimmerLoading() {
    return ListView.builder(
      itemCount: 4, // 显示 4 个骨架项
      itemBuilder: (context, index) {
        if (index == 0) {
          // 第一项：故事条骨架
          return _buildStoryBarShimmer();
        }
        // 其他项：帖子骨架
        return _buildPostShimmer();
      },
    );
  }

  /// 构建故事条骨架屏
  ///
  /// 模拟故事头像和名称的加载状态
  Widget _buildStoryBarShimmer() {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Shimmer.fromColors(
      baseColor: isDark ? Colors.grey[800]! : Colors.grey[300]!,
      highlightColor: isDark ? Colors.grey[700]! : Colors.grey[100]!,
      child: Container(
        height: 110,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          // 模拟 5 个故事头像
          children: List.generate(
              5,
              (_) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CircleAvatar(radius: 30), // 头像骨架
                        const SizedBox(height: 4),
                        Container(
                            width: 40, height: 10, color: Colors.white), // 名称骨架
                      ],
                    ),
                  )),
        ),
      ),
    );
  }

  /// 构建帖子骨架屏
  ///
  /// 模拟帖子卡片各部分的加载状态
  Widget _buildPostShimmer() {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Shimmer.fromColors(
      baseColor: isDark ? Colors.grey[800]! : Colors.grey[300]!,
      highlightColor: isDark ? Colors.grey[700]! : Colors.grey[100]!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          /// 头部区域（头像 + AI 名称）
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                const CircleAvatar(radius: 16), // 头像骨架
                const SizedBox(width: 10),
                Container(width: 80, height: 12, color: Colors.white), // 名称骨架
              ],
            ),
          ),

          /// 图片区域
          AspectRatio(
            aspectRatio: 4 / 5, // 帖子图片比例
            child: Container(color: Colors.white),
          ),

          /// 底部区域（操作按钮 + 文字）
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(width: 60, height: 12, color: Colors.white), // 操作按钮骨架
                const SizedBox(height: 8),
                Container(
                    width: double.infinity,
                    height: 10,
                    color: Colors.white), // 文字骨架
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ================== 状态提示页面 ==================

  /// 构建错误状态页面
  ///
  /// 当帖子加载失败且无缓存数据时显示
  ///
  /// [error] 错误信息字符串
  Widget _buildErrorState(String error) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 48, color: Colors.grey[400]),
          const SizedBox(height: 16),
          Text('Failed to load feed',
              style: TextStyle(color: Colors.grey[500])),
          const SizedBox(height: 8),

          /// 重试按钮
          TextButton(
            onPressed: () =>
                ref.read(feedProvider.notifier).loadPosts(refresh: true),
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }

  /// 构建空状态页面
  ///
  /// 当没有帖子数据时显示引导提示
  Widget _buildEmptyState() {
    return ListView(
      children: [
        // 仍然显示故事条
        StoryBar(onStoryTap: _openStoryPlayer),

        const SizedBox(height: 80),

        // 空状态提示
        Center(
          child: Column(
            children: [
              Icon(Icons.photo_library_outlined,
                  size: 64, color: Colors.grey[300]),
              const SizedBox(height: 16),
              Text('No posts yet',
                  style: TextStyle(fontSize: 16, color: Colors.grey[500])),
              const SizedBox(height: 8),
              Text('Discover AI personas and start connecting!',
                  style: TextStyle(fontSize: 13, color: Colors.grey[400])),
            ],
          ),
        ),
      ],
    );
  }
}
