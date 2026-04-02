import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:shimmer/shimmer.dart';
import '../../core/api/api_client.dart';

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
                  return Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.person_search,
                            size: 64, color: Colors.grey[300]),
                        const SizedBox(height: 16),
                        Text('No AI personas found',
                            style: GoogleFonts.inter(
                                fontSize: 16, color: Colors.grey)),
                      ],
                    ),
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
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
      child: FilterChip(
        label: Text(label),
        selected: isSelected,
        onSelected: (_) {
          setState(() => _selectedCategory = category);
        },
        selectedColor: const Color(0xFF0095F6).withAlpha(40),
        checkmarkColor: const Color(0xFF0095F6),
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
    final avatar = persona['avatar_url'] as String? ?? '';
    final archetype = persona['archetype'] as String? ?? '';

    return GestureDetector(
      onTap: () {
        final aiId = persona['id'] as int;
        context.push('/ai/$aiId?name=${Uri.encodeComponent(name)}');
      },
      child: Container(
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1C1C1E) : Colors.white,
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
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              flex: 3,
              child: ClipRRect(
                borderRadius:
                    const BorderRadius.vertical(top: Radius.circular(16)),
                child: avatar.isNotEmpty
                    ? CachedNetworkImage(
                        imageUrl: avatar,
                        fit: BoxFit.cover,
                        placeholder: (_, __) => Container(
                          color: isDark
                              ? const Color(0xFF2C2C2E)
                              : Colors.grey[200],
                          child: const Center(
                              child: CircularProgressIndicator(strokeWidth: 2)),
                        ),
                        errorWidget: (_, __, ___) => Container(
                          color: isDark
                              ? const Color(0xFF2C2C2E)
                              : Colors.grey[200],
                          child: Icon(Icons.person,
                              size: 48, color: Colors.grey[400]),
                        ),
                      )
                    : Container(
                        color:
                            isDark ? const Color(0xFF2C2C2E) : Colors.grey[200],
                        child: Center(
                          child: Text(name[0],
                              style: GoogleFonts.inter(
                                  fontSize: 40,
                                  fontWeight: FontWeight.w700,
                                  color: Colors.grey[500])),
                        ),
                      ),
              ),
            ),
            Expanded(
              flex: 2,
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(name,
                        style: GoogleFonts.inter(
                            fontWeight: FontWeight.w700, fontSize: 14),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                    if (profession.isNotEmpty)
                      Text(profession,
                          style: GoogleFonts.inter(
                              fontSize: 11, color: Colors.grey[500]),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                    if (archetype.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFF0095F6).withAlpha(25),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(archetype,
                              style: GoogleFonts.inter(
                                  fontSize: 10,
                                  color: const Color(0xFF0095F6),
                                  fontWeight: FontWeight.w500),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                        ),
                      ),
                    const SizedBox(height: 4),
                    Flexible(
                      child: Text(bio,
                          style: GoogleFonts.inter(
                              fontSize: 11, color: Colors.grey[500]),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
