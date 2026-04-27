import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:shimmer/shimmer.dart';
import '../../core/api/api_client.dart';
import '../../core/theme/character_theme.dart';
import '../../core/widgets/empty_state.dart';

/// Increment to force personasProvider to refetch.
final personasRefreshProvider = StateProvider<int>((ref) => 0);

final personasProvider =
    FutureProvider.family<List<dynamic>, ({String? category, String? query})>(
        (ref, params) async {
  ref.watch(
      personasRefreshProvider); // re-evaluate when refresh counter changes
  var path = '/api/ai/personas?';
  if (params.category != null) path += 'category=${params.category}&';
  if (params.query != null && params.query!.isNotEmpty) {
    path += 'q=${Uri.encodeComponent(params.query!)}&';
  }
  final data = await ApiClient.get(path, useCache: false);
  return (data['personas'] as List<dynamic>?) ?? [];
});

class DiscoverPage extends ConsumerStatefulWidget {
  const DiscoverPage({super.key});

  @override
  ConsumerState<DiscoverPage> createState() => _DiscoverPageState();
}

class _DiscoverPageState extends ConsumerState<DiscoverPage> {
  String? _selectedCategory;
  final _searchCtrl = TextEditingController();
  String? _searchQuery;

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final params = (category: _selectedCategory, query: _searchQuery);
    final personasAsync = ref.watch(personasProvider(params));
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text('Discover',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 22)),
      ),
      body: Column(
        children: [
          // Search bar
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: TextField(
              controller: _searchCtrl,
              decoration: InputDecoration(
                hintText: 'Search AI personas...',
                hintStyle:
                    GoogleFonts.inter(fontSize: 14, color: Colors.grey[400]),
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _searchQuery != null && _searchQuery!.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          _searchCtrl.clear();
                          setState(() => _searchQuery = null);
                        },
                      )
                    : null,
                filled: true,
                fillColor: isDark ? const Color(0xFF262626) : Colors.grey[100],
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              ),
              onSubmitted: (value) {
                setState(() =>
                    _searchQuery = value.trim().isEmpty ? null : value.trim());
              },
            ),
          ),
          // Category filter chips
          SizedBox(
            height: 48,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                _buildChip('All', null),
                _buildChip('Otome', 'otome'),
                _buildChip('BL', 'bl'),
                _buildChip('GL', 'gl'),
                _buildChip('General', 'general'),
              ],
            ),
          ),
          Expanded(
            child: personasAsync.when(
              loading: () => _buildShimmerGrid(),
              error: (e, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.error_outline,
                        size: 48, color: Colors.grey[400]),
                    const SizedBox(height: 12),
                    Text('Failed to load',
                        style: GoogleFonts.inter(color: Colors.grey)),
                    TextButton(
                      onPressed: () => ref.invalidate(personasProvider(params)),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
              data: (personas) {
                if (personas.isEmpty) {
                  return EmptyState(
                    icon: Icons.explore_outlined,
                    title: 'No companions found',
                    subtitle: 'Check back soon for new AI personalities',
                  );
                }
                return GridView.builder(
                  padding: const EdgeInsets.all(12),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    childAspectRatio: 0.65,
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                  ),
                  itemCount: personas.length,
                  itemBuilder: (context, index) {
                    final p = personas[index] as Map<String, dynamic>;
                    return _PersonaCard(persona: p, isDark: isDark);
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChip(String label, String? category) {
    final isSelected = _selectedCategory == category;
    final primary = Theme.of(context).colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
      child: FilterChip(
        label: Text(label),
        selected: isSelected,
        onSelected: (_) {
          setState(() => _selectedCategory = category);
        },
        selectedColor: primary.withAlpha(40),
        checkmarkColor: primary,
      ),
    );
  }

  Widget _buildShimmerGrid() {
    return Shimmer.fromColors(
      baseColor: Colors.grey[300]!,
      highlightColor: Colors.grey[100]!,
      child: GridView.builder(
        padding: const EdgeInsets.all(12),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          childAspectRatio: 0.75,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
        ),
        itemCount: 6,
        itemBuilder: (context, index) {
          return Container(
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
            ),
          );
        },
      ),
    );
  }
}

class _PersonaCard extends StatelessWidget {
  final Map<String, dynamic> persona;
  final bool isDark;

  const _PersonaCard({required this.persona, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final name = persona['name'] as String? ?? 'AI';
    final bio = persona['bio'] as String? ?? '';
    final profession = persona['profession'] as String? ?? '';
    final avatar =
        ApiClient.proxyImageUrl(persona['avatar_url'] as String? ?? '');
    final archetype = persona['archetype'] as String? ?? '';
    final characterColors = CharacterTheme.getPalette(name);

    return GestureDetector(
      onTap: () {
        final aiId = persona['id'] as int;
        context.push('/ai/$aiId?name=${Uri.encodeComponent(name)}');
      },
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              characterColors
                  .getGradient1(isDark ? Brightness.dark : Brightness.light)
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
            // Prominent avatar
            CircleAvatar(
              radius: 32,
              backgroundColor: Colors.grey[300],
              backgroundImage:
                  avatar.isNotEmpty ? CachedNetworkImageProvider(avatar) : null,
              child: avatar.isEmpty
                  ? Text(
                      name[0],
                      style: GoogleFonts.inter(
                        fontSize: 28,
                        fontWeight: FontWeight.w700,
                        color: Colors.grey[500],
                      ),
                    )
                  : null,
            ),
            const SizedBox(height: 10),
            // Name
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
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: characterColors.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    archetype,
                    style: GoogleFonts.inter(
                      fontSize: 10,
                      color: characterColors.primary,
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
            const SizedBox(height: 6),
            // Bio preview
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
    );
  }
}
