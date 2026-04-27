import 'package:flutter/material.dart';
import 'post_card.dart';
import 'post_card_text.dart';

/// Post Card 工厂类
///
/// 根据 post_type 字段自动选择合适的卡片组件进行渲染：
/// - image_only: 使用 PostCard（图片帖子）
/// - text_only: 使用 PostCardText（纯文字帖子）
/// - quote: 使用 PostCardText（引用帖子，与 text_only 相同）
class PostCardFactory {
  /// 根据 post_type 构建对应的卡片组件
  ///
  /// [post] 帖子数据对象
  /// [onLike] 点赞回调
  /// [onSave] 保存回调
  /// [onDM] 私信回调
  /// [onProfileTap] 打开 AI 详情回调
  /// [onComment] 打开评论回调
  ///
  /// Returns: 对应类型的 Widget
  static Widget build({
    required Map<String, dynamic> post,
    required VoidCallback onLike,
    VoidCallback? onSave,
    required VoidCallback onDM,
    VoidCallback? onProfileTap,
    VoidCallback? onComment,
  }) {
    final postType = post['post_type'] as String? ?? 'image_only';

    switch (postType) {
      case 'text_only':
      case 'quote':
        return PostCardText(
          post: post,
          onLike: onLike,
          onSave: onSave,
          onDM: onDM,
          onProfileTap: onProfileTap,
          onComment: onComment,
        );
      case 'image_only':
      default:
        return PostCard(
          post: post,
          onLike: onLike,
          onSave: onSave,
          onDM: onDM,
          onProfileTap: onProfileTap,
          onComment: onComment,
        );
    }
  }
}
