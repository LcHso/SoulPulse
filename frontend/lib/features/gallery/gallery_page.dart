import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import '../../shared/widgets/lazy_cached_image.dart';
import 'gallery_models.dart';
import 'gallery_service.dart';

// ─── Providers ────────────────────────────────────────────────────────────────

/// Provider for CG illustrations, keyed by persona ID
final galleryProvider =
    FutureProvider.family<List<CGIllustration>, int>((ref, personaId) async {
  final service = GalleryService();
  return service.getCGsForPersona(personaId);
});

// ─── Page ─────────────────────────────────────────────────────────────────────

enum _GalleryFilter { all, collected, locked }

/// CG Gallery page showing all illustrations for a persona.
///
/// Features:
/// - Grid view of CGs (collected = full color, locked = blurred + lock icon)
/// - Filter tabs: All | Collected | Locked
/// - Collection counter ("已收集 3/15")
/// - Tap collected CG for full-screen swipe viewer
class GalleryPage extends ConsumerStatefulWidget {
  final int personaId;
  final String personaName;

  const GalleryPage({
    super.key,
    required this.personaId,
    required this.personaName,
  });

  @override
  ConsumerState<GalleryPage> createState() => _GalleryPageState();
}

class _GalleryPageState extends ConsumerState<GalleryPage> {
  _GalleryFilter _filter = _GalleryFilter.all;

  List<CGIllustration> _applyFilter(List<CGIllustration> allCGs) {
    switch (_filter) {
      case _GalleryFilter.collected:
        return allCGs.where((cg) => cg.isCollected).toList();
      case _GalleryFilter.locked:
        return allCGs.where((cg) => !cg.isCollected).toList();
      case _GalleryFilter.all:
        return allCGs;
    }
  }

  void _openFullScreen(List<CGIllustration> allCGs, CGIllustration cg) {
    if (!cg.isCollected) return;
    final collectedCGs = allCGs.where((c) => c.isCollected).toList();
    final initialIndex = collectedCGs.indexOf(cg);
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _FullScreenCGViewer(
          cgs: collectedCGs,
          initialIndex: initialIndex >= 0 ? initialIndex : 0,
          service: GalleryService(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final asyncCGs = ref.watch(galleryProvider(widget.personaId));

    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.personaName} · CG相册'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 20),
          onPressed: () => context.pop(),
        ),
      ),
      body: asyncCGs.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline,
                  size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text(error.toString(), style: theme.textTheme.bodyMedium),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: () =>
                    ref.invalidate(galleryProvider(widget.personaId)),
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('重试'),
              ),
            ],
          ),
        ),
        data: (allCGs) {
          final filteredCGs = _applyFilter(allCGs);
          final collectedCount =
              allCGs.where((cg) => cg.isCollected).length;
          return Column(
            children: [
              _buildHeader(allCGs, collectedCount, theme, isDark),
              Expanded(
                  child: _buildGrid(allCGs, filteredCGs, theme, isDark)),
            ],
          );
        },
      ),
    );
  }

  Widget _buildHeader(List<CGIllustration> allCGs, int collectedCount,
      ThemeData theme, bool isDark) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Collection counter
          Row(
            children: [
              Icon(Icons.collections_outlined,
                  size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Text(
                '已收集 $collectedCount/${allCGs.length}',
                style: theme.textTheme.titleSmall?.copyWith(
                  color: theme.colorScheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              // Quality tier legend
              _tierBadge('SR', Colors.blueGrey),
              const SizedBox(width: 6),
              _tierBadge('SSR', Colors.amber.shade700),
              const SizedBox(width: 6),
              _tierBadge('限定', Colors.purple),
            ],
          ),
          const SizedBox(height: 12),
          // Filter tabs
          Row(
            children: [
              _filterChip('全部', _GalleryFilter.all, theme),
              const SizedBox(width: 8),
              _filterChip('已收集', _GalleryFilter.collected, theme),
              const SizedBox(width: 8),
              _filterChip('未解锁', _GalleryFilter.locked, theme),
            ],
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }

  Widget _tierBadge(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.bold,
          color: color,
        ),
      ),
    );
  }

  Widget _filterChip(String label, _GalleryFilter filter, ThemeData theme) {
    final selected = _filter == filter;
    return GestureDetector(
      onTap: () => setState(() => _filter = filter),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: selected
              ? theme.colorScheme.primary
              : theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
            color: selected
                ? Colors.white
                : theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ),
    );
  }

  Widget _buildGrid(List<CGIllustration> allCGs,
      List<CGIllustration> items, ThemeData theme, bool isDark) {
    if (items.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.image_not_supported_outlined,
                size: 56, color: theme.colorScheme.outline),
            const SizedBox(height: 12),
            Text(
              _filter == _GalleryFilter.collected
                  ? '暂无已收集的CG'
                  : _filter == _GalleryFilter.locked
                      ? '全部CG已解锁!'
                      : '暂无CG',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: theme.colorScheme.outline,
              ),
            ),
          ],
        ),
      );
    }
    return GridView.builder(
      padding: const EdgeInsets.all(12),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 0.75,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) =>
          _buildCGCard(allCGs, items[index], theme, isDark),
    );
  }

  Widget _buildCGCard(List<CGIllustration> allCGs, CGIllustration cg,
      ThemeData theme, bool isDark) {
    final imageUrl = ApiClient.proxyImageUrl(cg.thumbnailUrl ?? cg.imageUrl);

    return GestureDetector(
      onTap: () => _openFullScreen(allCGs, cg),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(isDark ? 0.3 : 0.08),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Stack(
            fit: StackFit.expand,
            children: [
              // Image
              LazyCachedImage(
                imageUrl: imageUrl,
                fit: BoxFit.cover,
                placeholder: (context) => Container(
                  color:
                      isDark ? Colors.grey.shade800 : Colors.grey.shade200,
                  child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2)),
                ),
                errorWidget: (context, url, error) => Container(
                  color:
                      isDark ? Colors.grey.shade800 : Colors.grey.shade200,
                  child: Icon(Icons.image,
                      size: 40, color: Colors.grey.shade500),
                ),
              ),
              // Blur overlay for locked CGs
              if (!cg.isCollected)
                ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                    child: Container(
                      color: Colors.black.withOpacity(0.3),
                    ),
                  ),
                ),
              // Lock icon + condition for locked CGs
              if (!cg.isCollected)
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.black.withOpacity(0.5),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.lock_outline,
                            color: Colors.white70, size: 28),
                      ),
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          _unlockText(cg.unlockCondition),
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 10,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ],
                  ),
                ),
              // Title + quality badge at bottom
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        Colors.black.withOpacity(0.7)
                      ],
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          cg.title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      _tierBadge(
                          cg.qualityLabel, _tierColor(cg.qualityTier)),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Color _tierColor(String tier) {
    switch (tier) {
      case 'premium':
        return Colors.amber.shade700;
      case 'limited':
        return Colors.purple;
      default:
        return Colors.blueGrey;
    }
  }

  String _unlockText(Map<String, dynamic> condition) {
    if (condition.isEmpty) return '暂未开放';
    if (condition.containsKey('intimacy_level')) {
      return '亲密度 Lv.${condition['intimacy_level']}';
    }
    if (condition.containsKey('streak_days')) {
      return '连续互动${condition['streak_days']}天';
    }
    if (condition.containsKey('gem_cost')) {
      return '${condition['gem_cost']} 星钻';
    }
    return '特殊条件';
  }
}

// ─── Full-screen CG Viewer ────────────────────────────────────────────────

class _FullScreenCGViewer extends StatefulWidget {
  final List<CGIllustration> cgs;
  final int initialIndex;
  final GalleryService service;

  const _FullScreenCGViewer({
    required this.cgs,
    required this.initialIndex,
    required this.service,
  });

  @override
  State<_FullScreenCGViewer> createState() => _FullScreenCGViewerState();
}

class _FullScreenCGViewerState extends State<_FullScreenCGViewer> {
  late PageController _pageController;
  late int _currentIndex;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _pageController = PageController(initialPage: _currentIndex);
    // Mark initial CG as viewed
    _markViewed(widget.cgs[_currentIndex]);
    // Hide system UI for immersion
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void dispose() {
    _pageController.dispose();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  void _markViewed(CGIllustration cg) {
    widget.service.markAsViewed(cg.id);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        onTap: () => Navigator.of(context).pop(),
        child: Stack(
          children: [
            PageView.builder(
              controller: _pageController,
              itemCount: widget.cgs.length,
              onPageChanged: (index) {
                setState(() => _currentIndex = index);
                _markViewed(widget.cgs[index]);
              },
              itemBuilder: (context, index) {
                final cg = widget.cgs[index];
                final imageUrl = ApiClient.proxyImageUrl(cg.imageUrl);
                return InteractiveViewer(
                  minScale: 1.0,
                  maxScale: 3.0,
                  child: Center(
                    child: CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.contain,
                      placeholder: (_, __) => const Center(
                          child: CircularProgressIndicator(
                              color: Colors.white54)),
                      errorWidget: (_, __, ___) => const Icon(
                          Icons.broken_image,
                          color: Colors.white38,
                          size: 64),
                    ),
                  ),
                );
              },
            ),
            // Info overlay at bottom
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: SafeArea(
                child: Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        Colors.black.withOpacity(0.7)
                      ],
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        widget.cgs[_currentIndex].title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      if (widget.cgs[_currentIndex].description !=
                          null) ...[
                        const SizedBox(height: 4),
                        Text(
                          widget.cgs[_currentIndex].description!,
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 13),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text(
                        '${_currentIndex + 1} / ${widget.cgs.length}',
                        style: const TextStyle(
                            color: Colors.white54, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            // Close button
            Positioned(
              top: MediaQuery.of(context).padding.top + 8,
              right: 12,
              child: IconButton(
                icon: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: const BoxDecoration(
                    color: Colors.black45,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.close,
                      color: Colors.white, size: 22),
                ),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
