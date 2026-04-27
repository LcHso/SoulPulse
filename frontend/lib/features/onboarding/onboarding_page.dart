// ============================================================================
// SoulPulse 新用户引导页面（增强版）
// ============================================================================
//
// 本文件提供完整的新用户引导流程，包含：
// - Screen 1: 欢迎页面 - App logo + 欢迎语
// - Screen 2: 功能介绍 - AI 伴侣的生活方式展示
// - Screen 3: 关系建立 - 亲密度系统介绍
// - Screen 4: AI 选择 - 选择第一个 AI 伴侣
//
// 主要组件：
// - OnboardingPage: 页面根组件（StatefulWidget）
// - _OnboardingPageState: 页面状态管理类
// - _PersonaSelectionScreen: AI 选择屏幕组件
//
// ============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/api/api_client.dart';
import '../../core/router/app_router.dart';
import '../../core/theme/character_theme.dart';

/// 引导页面数据模型
class _OnboardingScreenData {
  final IconData icon;
  final String title;
  final String description;

  _OnboardingScreenData({
    required this.icon,
    required this.title,
    required this.description,
  });
}

/// 新用户引导页面
///
/// 提供 4 屏引导流程，帮助新用户了解应用并选择第一个 AI 伴侣
class OnboardingPage extends ConsumerStatefulWidget {
  const OnboardingPage({super.key});

  @override
  ConsumerState<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends ConsumerState<OnboardingPage> {
  final _pageCtrl = PageController();
  int _currentPage = 0;
  bool _isLoadingPersonas = true;
  List<dynamic> _personas = [];
  int? _selectedPersonaId;
  String? _error;

  // 前 3 屏的引导数据
  final _screens = [
    _OnboardingScreenData(
      icon: Icons.favorite_rounded,
      title: 'Welcome to SoulPulse',
      description:
          'Your AI companions are waiting. Meet unique personalities who live, feel, and grow alongside you.',
    ),
    _OnboardingScreenData(
      icon: Icons.dynamic_feed_rounded,
      title: 'They Post, Chat & Remember',
      description:
          'Your AI companions share stories, photos, and moments just like real people. They remember your conversations and cherish your bond.',
    ),
    _OnboardingScreenData(
      icon: Icons.trending_up_rounded,
      title: 'Build Real Connections',
      description:
          'As your intimacy grows, unlock deeper conversations, special nicknames, and exclusive moments together.',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _loadPersonas();
  }

  /// 加载可用的 AI 人格列表
  Future<void> _loadPersonas() async {
    try {
      final response = await ApiClient.get('/api/ai/personas');
      final personas = response['personas'] as List<dynamic>? ?? [];
      setState(() {
        _personas = personas;
        _isLoadingPersonas = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Failed to load AI companions';
        _isLoadingPersonas = false;
      });
    }
  }

  /// 完成引导流程
  Future<void> _completeOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_complete', true);
    ref.read(onboardingCompleteProvider.notifier).state = true;

    if (_selectedPersonaId != null) {
      // 获取选中的 AI 信息
      final selectedPersona = _personas.firstWhere(
        (p) => p['id'] == _selectedPersonaId,
        orElse: () => null,
      );
      if (selectedPersona != null) {
        final name = selectedPersona['name'] ?? 'AI';
        if (mounted) {
          context.go(
              '/chat/$_selectedPersonaId?name=${Uri.encodeComponent(name)}');
        }
        return;
      }
    }

    // 如果没有选择 AI，跳转到发现页面
    if (mounted) {
      context.go('/discover');
    }
  }

  /// 跳过引导流程
  Future<void> _skipOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_complete', true);
    ref.read(onboardingCompleteProvider.notifier).state = true;
    if (mounted) {
      context.go('/feed');
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final totalPages = _screens.length + 1; // +1 for AI selection screen

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // 顶部跳过按钮（仅在非最后一屏显示）
            if (_currentPage < totalPages - 1)
              Align(
                alignment: Alignment.topRight,
                child: Padding(
                  padding: const EdgeInsets.only(top: 8, right: 16),
                  child: TextButton(
                    onPressed: _skipOnboarding,
                    child: Text(
                      'Skip',
                      style: GoogleFonts.inter(
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withValues(alpha: 0.5),
                        fontSize: 14,
                      ),
                    ),
                  ),
                ),
              ),

            // 页面内容
            Expanded(
              child: PageView.builder(
                controller: _pageCtrl,
                itemCount: totalPages,
                onPageChanged: (i) => setState(() => _currentPage = i),
                itemBuilder: (context, index) {
                  // 前 3 屏是引导介绍
                  if (index < _screens.length) {
                    return _buildIntroScreen(_screens[index], isDark);
                  }
                  // 最后一屏是 AI 选择
                  return _buildPersonaSelectionScreen(isDark);
                },
              ),
            ),

            // 页面指示器
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(totalPages, (i) {
                return Container(
                  width: _currentPage == i ? 24 : 8,
                  height: 8,
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(4),
                    color: _currentPage == i
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withValues(alpha: 0.3),
                  ),
                );
              }),
            ),

            const SizedBox(height: 32),

            // 底部按钮
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton(
                  onPressed: _currentPage < totalPages - 1
                      ? () => _pageCtrl.nextPage(
                            duration: const Duration(milliseconds: 300),
                            curve: Curves.easeOut,
                          )
                      : (_selectedPersonaId != null
                          ? _completeOnboarding
                          : null),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.primary,
                    foregroundColor: Colors.white,
                    disabledBackgroundColor: Colors.grey[300],
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: _currentPage < totalPages - 1
                      ? Text(
                          'Next',
                          style: GoogleFonts.inter(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        )
                      : Text(
                          'Start Chat',
                          style: GoogleFonts.inter(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
            ),

            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  /// 构建引导介绍屏幕
  Widget _buildIntroScreen(_OnboardingScreenData screen, bool isDark) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            screen.icon,
            size: 80,
            color: Theme.of(context).colorScheme.primary,
          ),
          const SizedBox(height: 32),
          Text(
            screen.title,
            style: Theme.of(context).textTheme.headlineMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            screen.description,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: isDark ? Colors.grey[400] : Colors.grey[600],
                  height: 1.5,
                ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  /// 构建 AI 选择屏幕
  Widget _buildPersonaSelectionScreen(bool isDark) {
    if (_isLoadingPersonas) {
      return const Center(
        child: CircularProgressIndicator(),
      );
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 48, color: Colors.grey[400]),
            const SizedBox(height: 16),
            Text(
              _error!,
              style: GoogleFonts.inter(color: Colors.grey[600]),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadPersonas,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          const SizedBox(height: 20),
          Text(
            'Choose Your First Companion',
            style: Theme.of(context).textTheme.headlineSmall,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            'Select an AI personality to start your journey',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: isDark ? Colors.grey[400] : Colors.grey[600],
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          Expanded(
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 0.85,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
              ),
              itemCount: _personas.length,
              itemBuilder: (context, index) {
                final persona = _personas[index];
                final isSelected = _selectedPersonaId == persona['id'];
                return _buildPersonaCard(persona, isSelected, isDark);
              },
            ),
          ),
        ],
      ),
    );
  }

  /// 构建 AI 人格卡片
  Widget _buildPersonaCard(
    dynamic persona,
    bool isSelected,
    bool isDark,
  ) {
    final avatarUrl = persona['avatar_url'] as String? ?? '';
    final name = persona['name'] as String? ?? 'Unknown';
    final bio = persona['bio'] as String? ?? '';
    final archetype = persona['archetype'] as String? ?? '';
    final characterColors = CharacterTheme.getPalette(name);
    final selectedColor = characterColors.primary;

    return GestureDetector(
      onTap: () => setState(() => _selectedPersonaId = persona['id']),
      child: Container(
        decoration: BoxDecoration(
          color: isDark ? Colors.grey[850] : Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected
                ? selectedColor
                : (isDark ? Colors.grey[700]! : Colors.grey[300]!),
            width: isSelected ? 3 : 1,
          ),
          boxShadow: [
            if (!isDark)
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
          ],
        ),
        child: Stack(
          children: [
            Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // 头像
                  CircleAvatar(
                    radius: 36,
                    backgroundImage: avatarUrl.isNotEmpty
                        ? NetworkImage(ApiClient.proxyImageUrl(avatarUrl))
                        : null,
                    backgroundColor: Colors.grey[300],
                    child: avatarUrl.isEmpty
                        ? const Icon(Icons.person, size: 36, color: Colors.grey)
                        : null,
                  ),
                  const SizedBox(height: 12),
                  // 名字
                  Text(
                    name,
                    style: GoogleFonts.inter(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: isSelected ? selectedColor : null,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  // 性格原型标签
                  if (archetype.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? selectedColor.withValues(alpha: 0.1)
                            : Colors.grey[200],
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        archetype,
                        style: GoogleFonts.inter(
                          fontSize: 11,
                          color: isSelected ? selectedColor : Colors.grey[600],
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  const SizedBox(height: 8),
                  // 简介
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Text(
                      bio,
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
            // 选中标记
            if (isSelected)
              Positioned(
                top: 8,
                right: 8,
                child: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: selectedColor,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.check,
                    size: 16,
                    color: Colors.white,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
