import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/api_client.dart';
import 'outfit_models.dart';
import 'outfit_service.dart';

/// Outfit selector page for a persona.
///
/// Features:
/// - Grid/carousel of outfits
/// - Category filter tabs: All | Daily | Formal | Workout | Intimate | Event
/// - Locked outfits show unlock condition
/// - Equipped outfit highlighted
/// - "装备" (equip) button for available outfits
class OutfitsPage extends StatefulWidget {
  final int personaId;
  final String personaName;

  const OutfitsPage({
    super.key,
    required this.personaId,
    required this.personaName,
  });

  @override
  State<OutfitsPage> createState() => _OutfitsPageState();
}

class _OutfitsPageState extends State<OutfitsPage> {
  final OutfitService _service = OutfitService();
  List<Outfit> _allOutfits = [];
  bool _loading = true;
  String? _error;
  String _selectedCategory = 'all';
  int? _equippingId;

  static const _categories = [
    ('all', '全部'),
    ('daily', '日常'),
    ('formal', '正装'),
    ('workout', '运动'),
    ('intimate', '私密'),
    ('event', '活动'),
  ];

  @override
  void initState() {
    super.initState();
    _loadOutfits();
  }

  Future<void> _loadOutfits() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final outfits = await _service.getOutfitsForPersona(widget.personaId);
      if (mounted) setState(() { _allOutfits = outfits; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  List<Outfit> get _filteredOutfits {
    if (_selectedCategory == 'all') return _allOutfits;
    return _allOutfits.where((o) => o.category == _selectedCategory).toList();
  }

  Future<void> _equipOutfit(Outfit outfit) async {
    if (_equippingId != null) return;
    setState(() => _equippingId = outfit.id);
    final success = await _service.equipOutfit(widget.personaId, outfit.id);
    if (success && mounted) {
      HapticFeedback.mediumImpact();
      // Refresh outfit list to reflect new equipped state
      await _loadOutfits();
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('装备失败，请稍后重试')),
      );
    }
    if (mounted) setState(() => _equippingId = null);
  }

  Future<void> _tryUnlock(Outfit outfit) async {
    final condition = outfit.unlockCondition;
    String message = '确定要解锁这套衣装吗？';
    if (condition.containsKey('gem_cost')) {
      message = '花费 ${condition['gem_cost']} 星钻解锁?';
    } else if (condition.containsKey('intimacy_level')) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('需要亲密度达到 Lv.${condition['intimacy_level']}')),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('解锁衣装'),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确定'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      final success = await _service.unlockOutfit(widget.personaId, outfit.id);
      if (success) {
        HapticFeedback.heavyImpact();
        await _loadOutfits();
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('解锁失败')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.personaName} · 衣柜'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 20),
          onPressed: () => context.pop(),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.error_outline,
                          size: 48, color: theme.colorScheme.error),
                      const SizedBox(height: 12),
                      Text(_error!),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: _loadOutfits,
                        icon: const Icon(Icons.refresh, size: 18),
                        label: const Text('重试'),
                      ),
                    ],
                  ),
                )
              : Column(
                  children: [
                    _buildCategoryTabs(theme),
                    Expanded(child: _buildGrid(theme, isDark)),
                  ],
                ),
    );
  }

  Widget _buildCategoryTabs(ThemeData theme) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _categories.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final (key, label) = _categories[index];
          final selected = _selectedCategory == key;
          return GestureDetector(
            onTap: () => setState(() => _selectedCategory = key),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
              decoration: BoxDecoration(
                color: selected
                    ? theme.colorScheme.primary
                    : theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Center(
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
            ),
          );
        },
      ),
    );
  }

  Widget _buildGrid(ThemeData theme, bool isDark) {
    final items = _filteredOutfits;
    if (items.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.checkroom_outlined,
                size: 56, color: theme.colorScheme.outline),
            const SizedBox(height: 12),
            Text('暂无衣装',
                style: theme.textTheme.bodyLarge?.copyWith(
                    color: theme.colorScheme.outline)),
          ],
        ),
      );
    }

    return GridView.builder(
      padding: const EdgeInsets.all(12),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 14,
        crossAxisSpacing: 14,
        childAspectRatio: 0.68,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) =>
          _buildOutfitCard(items[index], theme, isDark),
    );
  }

  Widget _buildOutfitCard(Outfit outfit, ThemeData theme, bool isDark) {
    final isEquipping = _equippingId == outfit.id;
    final imageUrl = outfit.thumbnailUrl != null
        ? ApiClient.proxyImageUrl(outfit.thumbnailUrl!)
        : '';

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: outfit.isEquipped
            ? Border.all(color: theme.colorScheme.primary, width: 2.5)
            : null,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.3 : 0.06),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Container(
          color: isDark ? Colors.grey.shade900 : Colors.white,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Thumbnail
              Expanded(
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (imageUrl.isNotEmpty)
                      CachedNetworkImage(
                        imageUrl: imageUrl,
                        fit: BoxFit.cover,
                        placeholder: (_, __) => Container(
                          color: isDark
                              ? Colors.grey.shade800
                              : Colors.grey.shade100,
                          child: const Center(
                              child:
                                  CircularProgressIndicator(strokeWidth: 2)),
                        ),
                        errorWidget: (_, __, ___) => _outfitPlaceholder(isDark),
                      )
                    else
                      _outfitPlaceholder(isDark),
                    // Equipped badge
                    if (outfit.isEquipped)
                      Positioned(
                        top: 6,
                        right: 6,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Text(
                            '穿着中',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.bold),
                          ),
                        ),
                      ),
                    // Category badge
                    Positioned(
                      top: 6,
                      left: 6,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          outfit.categoryLabel,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 10),
                        ),
                      ),
                    ),
                    // Locked overlay
                    if (!outfit.isAvailable)
                      Container(
                        color: Colors.black.withOpacity(0.5),
                        child: Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.lock_outline,
                                  color: Colors.white70, size: 28),
                              const SizedBox(height: 4),
                              Text(
                                _unlockText(outfit.unlockCondition),
                                style: const TextStyle(
                                    color: Colors.white70, fontSize: 10),
                                textAlign: TextAlign.center,
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              // Bottom section: name + action
              Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      outfit.outfitName,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 6),
                    // Action button
                    if (outfit.isEquipped)
                      const SizedBox.shrink()
                    else if (outfit.isAvailable)
                      SizedBox(
                        width: double.infinity,
                        height: 30,
                        child: FilledButton(
                          onPressed: isEquipping
                              ? null
                              : () => _equipOutfit(outfit),
                          style: FilledButton.styleFrom(
                            padding: EdgeInsets.zero,
                            textStyle: const TextStyle(fontSize: 12),
                          ),
                          child: isEquipping
                              ? const SizedBox(
                                  width: 14,
                                  height: 14,
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2, color: Colors.white),
                                )
                              : const Text('装备'),
                        ),
                      )
                    else
                      SizedBox(
                        width: double.infinity,
                        height: 30,
                        child: OutlinedButton(
                          onPressed: () => _tryUnlock(outfit),
                          style: OutlinedButton.styleFrom(
                            padding: EdgeInsets.zero,
                            textStyle: const TextStyle(fontSize: 12),
                          ),
                          child: const Text('解锁'),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _outfitPlaceholder(bool isDark) {
    return Container(
      color: isDark ? Colors.grey.shade800 : Colors.grey.shade100,
      child: Center(
        child: Icon(Icons.checkroom,
            size: 40,
            color: isDark ? Colors.grey.shade600 : Colors.grey.shade400),
      ),
    );
  }

  String _unlockText(Map<String, dynamic> condition) {
    if (condition.isEmpty) return '暂未开放';
    if (condition.containsKey('intimacy_level')) {
      return '亲密度 Lv.${condition['intimacy_level']}';
    }
    if (condition.containsKey('gem_cost')) {
      return '${condition['gem_cost']} 星钻';
    }
    return '特殊条件';
  }
}
