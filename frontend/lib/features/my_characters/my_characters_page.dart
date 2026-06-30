// ============================================================================
// SoulPulse - 我的角色 (My Characters) Page
// Lists AI personas the current user has imported via SillyTavern card import.
// Shows quota banner, grid of character cards with "Custom" badge, and empty
// state CTA that links to the import flow.
// ============================================================================

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:shimmer/shimmer.dart';

import '../../core/api/api_client.dart';
import '../../core/theme/breakpoints.dart';
import '../../core/theme/character_theme.dart';

// ── Providers ────────────────────────────────────────────────────────────────

/// Increment to force the imported-personas list to refetch.
final myCharactersRefreshProvider = StateProvider<int>((ref) => 0);

/// Fetches personas the current user has imported (creator_user_id == self).
final myPersonasProvider = FutureProvider<List<Map<String, dynamic>>>((ref) async {
  ref.watch(myCharactersRefreshProvider);
  final data = await ApiClient.get(
    '/api/ai/personas?mine_only=true',
    useCache: false,
  );
  final list = (data['personas'] as List<dynamic>?) ?? const [];
  return list
      .whereType<Map<String, dynamic>>()
      .toList(growable: false);
});

/// Fetches import quota status: { used, limit, is_subscriber }.
final importQuotaProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  ref.watch(myCharactersRefreshProvider);
  return ApiClient.get(
    '/character-cards/import-quota',
    useCache: false,
  );
});

// ── Page ─────────────────────────────────────────────────────────────────────

class MyCharactersPage extends ConsumerStatefulWidget {
  const MyCharactersPage({super.key});

  @override
  ConsumerState<MyCharactersPage> createState() => _MyCharactersPageState();
}

class _MyCharactersPageState extends ConsumerState<MyCharactersPage> {
  Future<void> _openImportPage() async {
    // Wait for the import page to pop, then refresh both providers so a
    // newly-imported character appears immediately.
    await context.push('/import-character');
    if (!mounted) return;
    _refresh();
  }

  void _refresh() {
    ref.read(myCharactersRefreshProvider.notifier).state++;
    // Bust the discover cache too — a new persona may now be visible there.
    ApiClient.invalidateCache('/api/ai/personas');
  }

  @override
  Widget build(BuildContext context) {
    final personasAsync = ref.watch(myPersonasProvider);
    final quotaAsync = ref.watch(importQuotaProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          '我的角色',
          style: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 20),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.file_upload_outlined),
            tooltip: '导入角色卡',
            onPressed: _openImportPage,
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Column(
        children: [
          _QuotaBanner(quotaAsync: quotaAsync),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                _refresh();
                // Wait for both providers to finish their next fetch.
                await Future.wait([
                  ref.read(myPersonasProvider.future),
                  ref.read(importQuotaProvider.future),
                ]);
              },
              child: personasAsync.when(
                loading: () => _buildShimmerGrid(),
                error: (e, _) => _buildError(e),
                data: (personas) {
                  if (personas.isEmpty) {
                    return _buildEmpty();
                  }
                  return _buildGrid(personas, isDark);
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── Body states ────────────────────────────────────────────────────────────

  Widget _buildGrid(List<Map<String, dynamic>> personas, bool isDark) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Mirror Discover's responsive column count, but keep 2 columns on
        // typical phones as the spec requests.
        final columns = Breakpoints.getGridColumns(constraints.maxWidth);
        return Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: Breakpoints.maxGridWidth,
            ),
            child: GridView.builder(
              padding: const EdgeInsets.all(12),
              physics: const AlwaysScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: columns,
                childAspectRatio: 0.65,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
              ),
              itemCount: personas.length,
              itemBuilder: (context, index) {
                return _MyCharacterCard(
                  persona: personas[index],
                  isDark: isDark,
                );
              },
            ),
          ),
        );
      },
    );
  }

  Widget _buildEmpty() {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final iconColor = isDark ? Colors.grey[600] : Colors.grey[300];
    final titleColor = isDark ? Colors.grey[300] : Colors.grey[700];
    final subtitleColor = isDark ? Colors.grey[500] : Colors.grey[500];

    // Wrap in a scrollable so RefreshIndicator still works on empty state.
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        SizedBox(height: MediaQuery.sizeOf(context).height * 0.12),
        Icon(
          Icons.people_alt_outlined,
          size: 80,
          color: iconColor,
        ),
        const SizedBox(height: 18),
        Text(
          '还没有导入的角色',
          textAlign: TextAlign.center,
          style: GoogleFonts.inter(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: titleColor,
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Text(
            '导入 SillyTavern 角色卡开始聊天',
            textAlign: TextAlign.center,
            style: GoogleFonts.inter(
              fontSize: 13,
              color: subtitleColor,
            ),
          ),
        ),
        const SizedBox(height: 24),
        Center(
          child: ElevatedButton.icon(
            onPressed: _openImportPage,
            icon: const Icon(Icons.file_upload_outlined, size: 18),
            label: const Text('导入角色卡'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(
                horizontal: 22,
                vertical: 12,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(24),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildError(Object error) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        SizedBox(height: MediaQuery.sizeOf(context).height * 0.18),
        Icon(Icons.error_outline, size: 48, color: Colors.grey[400]),
        const SizedBox(height: 12),
        Center(
          child: Text(
            '加载失败',
            style: GoogleFonts.inter(color: Colors.grey),
          ),
        ),
        Center(
          child: TextButton(
            onPressed: _refresh,
            child: const Text('重试'),
          ),
        ),
      ],
    );
  }

  Widget _buildShimmerGrid() {
    return Shimmer.fromColors(
      baseColor: Colors.grey[300]!,
      highlightColor: Colors.grey[100]!,
      child: GridView.builder(
        padding: const EdgeInsets.all(12),
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          childAspectRatio: 0.65,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
        ),
        itemCount: 4,
        itemBuilder: (_, __) => Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
    );
  }
}

// ── Quota banner ─────────────────────────────────────────────────────────────

class _QuotaBanner extends StatelessWidget {
  final AsyncValue<Map<String, dynamic>> quotaAsync;

  const _QuotaBanner({required this.quotaAsync});

  @override
  Widget build(BuildContext context) {
    return quotaAsync.when(
      loading: () => const _QuotaBannerShell(
        child: SizedBox(
          height: 18,
          child: LinearProgressIndicator(minHeight: 2),
        ),
      ),
      error: (_, __) => const SizedBox.shrink(),
      data: (data) {
        final isSubscriber = data['is_subscriber'] == true;
        final used = (data['used'] as num?)?.toInt() ?? 0;
        final limitRaw = data['limit'];
        final limit = limitRaw is num ? limitRaw.toInt() : null;

        if (isSubscriber) {
          return const _QuotaBannerShell(child: _PremiumQuotaRow());
        }

        final cap = limit ?? 3;
        final ratio = cap == 0 ? 0.0 : (used / cap).clamp(0.0, 1.0);
        return _QuotaBannerShell(
          child: _FreeQuotaRow(used: used, limit: cap, ratio: ratio),
        );
      },
    );
  }
}

class _QuotaBannerShell extends StatelessWidget {
  final Widget child;

  const _QuotaBannerShell({required this.child});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF22202E) : const Color(0xFFF5F0FA),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isDark
              ? Colors.white.withValues(alpha: 0.04)
              : const Color(0xFFE5DCF2),
        ),
      ),
      child: child,
    );
  }
}

class _FreeQuotaRow extends StatelessWidget {
  final int used;
  final int limit;
  final double ratio;

  const _FreeQuotaRow({
    required this.used,
    required this.limit,
    required this.ratio,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? Colors.grey[300] : Colors.grey[800];
    final accent = const Color(0xFF8E6FB8);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Icon(Icons.inventory_2_outlined, size: 16, color: accent),
            const SizedBox(width: 6),
            Text(
              '已导入 $used/$limit 个角色',
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: textColor,
              ),
            ),
            const Spacer(),
            if (used >= limit)
              Text(
                '已满',
                style: GoogleFonts.inter(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: Colors.redAccent[200],
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: ratio,
            minHeight: 4,
            backgroundColor:
                isDark ? Colors.white.withValues(alpha: 0.06) : Colors.white,
            valueColor: AlwaysStoppedAnimation(accent),
          ),
        ),
      ],
    );
  }
}

class _PremiumQuotaRow extends StatelessWidget {
  const _PremiumQuotaRow();

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textColor = isDark ? Colors.grey[200] : Colors.grey[900];
    return Row(
      children: [
        const Icon(Icons.workspace_premium,
            size: 18, color: Color(0xFFC4964A)),
        const SizedBox(width: 8),
        Text(
          '无限导入',
          style: GoogleFonts.inter(
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: textColor,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          '∞',
          style: GoogleFonts.inter(
            fontSize: 16,
            fontWeight: FontWeight.w800,
            color: const Color(0xFFC4964A),
          ),
        ),
        const Spacer(),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: const Color(0xFFC4964A).withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            'PREMIUM',
            style: GoogleFonts.inter(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: const Color(0xFFC4964A),
              letterSpacing: 0.5,
            ),
          ),
        ),
      ],
    );
  }
}

// ── Card ─────────────────────────────────────────────────────────────────────

class _MyCharacterCard extends StatelessWidget {
  final Map<String, dynamic> persona;
  final bool isDark;

  const _MyCharacterCard({required this.persona, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final id = persona['id'];
    final name = persona['name'] as String? ?? 'AI';
    final bio = persona['bio'] as String? ?? '';
    final profession = persona['profession'] as String? ?? '';
    final archetype = persona['archetype'] as String? ?? '';
    final avatar = ApiClient.proxyImageUrl(
      persona['avatar_url'] as String? ?? '',
    );
    final palette = CharacterTheme.getPalette(name);

    return GestureDetector(
      onTap: () {
        if (id is int) {
          context.push('/chat/$id');
        } else if (id != null) {
          context.push('/chat/$id');
        }
      },
      child: Stack(
        children: [
          // Card body
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  palette
                      .getGradient1(
                          isDark ? Brightness.dark : Brightness.light)
                      .withValues(alpha: 0.2),
                  Theme.of(context).colorScheme.surface,
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withAlpha(isDark ? 40 : 15),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const SizedBox(height: 16),
                CircleAvatar(
                  radius: 32,
                  backgroundColor: Colors.grey[300],
                  backgroundImage: avatar.isNotEmpty
                      ? CachedNetworkImageProvider(avatar)
                      : null,
                  child: avatar.isEmpty
                      ? Text(
                          name.isNotEmpty ? name[0] : '?',
                          style: GoogleFonts.inter(
                            fontSize: 28,
                            fontWeight: FontWeight.w700,
                            color: Colors.grey[500],
                          ),
                        )
                      : null,
                ),
                const SizedBox(height: 10),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  child: Text(
                    name,
                    style: GoogleFonts.inter(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                  ),
                ),
                if (profession.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: Text(
                      profession,
                      style: GoogleFonts.inter(
                        fontSize: 11,
                        color: Colors.grey[500],
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                    ),
                  ),
                if (archetype.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: palette.primary.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        archetype,
                        style: GoogleFonts.inter(
                          fontSize: 10,
                          color: palette.primary,
                          fontWeight: FontWeight.w500,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                const SizedBox(height: 6),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: Text(
                      bio,
                      style: Theme.of(context).textTheme.bodySmall,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
                const SizedBox(height: 10),
              ],
            ),
          ),
          // "Custom" ribbon
          Positioned(
            top: 8,
            left: 8,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: const Color(0xFF8E6FB8),
                borderRadius: BorderRadius.circular(8),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withAlpha(30),
                    blurRadius: 4,
                    offset: const Offset(0, 1),
                  ),
                ],
              ),
              child: Text(
                '自定义',
                style: GoogleFonts.inter(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                  letterSpacing: 0.3,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
