import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';

/// Personas management view for the admin console.
class PersonasManagementView extends ConsumerStatefulWidget {
  const PersonasManagementView({super.key});

  @override
  ConsumerState<PersonasManagementView> createState() =>
      _PersonasManagementViewState();
}

class _PersonasManagementViewState
    extends ConsumerState<PersonasManagementView> {
  List<Map<String, dynamic>> _personas = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadPersonas();
  }

  Future<void> _loadPersonas() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final response =
          await ApiClient.getList('/api/admin/personas', useCache: false);
      setState(() {
        _personas = List<Map<String, dynamic>>.from(response);
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _showEditDialog(Map<String, dynamic> persona) async {
    final tagsCtrl =
        TextEditingController(text: persona['visual_prompt_tags'] ?? '');
    final faceUrlCtrl =
        TextEditingController(text: persona['base_face_url'] ?? '');
    final avatarCtrl = TextEditingController(text: persona['avatar_url'] ?? '');
    int isActive = persona['is_active'] ?? 1;

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: Text('Edit ${persona['name']}'),
          content: SizedBox(
            width: 500,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (persona['avatar_url'] != null &&
                      (persona['avatar_url'] as String).isNotEmpty)
                    Center(
                      child: CircleAvatar(
                        radius: 40,
                        backgroundImage:
                            NetworkImage(persona['avatar_url'] as String),
                      ),
                    ),
                  const SizedBox(height: 16),
                  Text(
                    '${persona['profession']} | ${persona['category']} | ${persona['gender_tag']}',
                    style: TextStyle(color: Colors.grey[600], fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: avatarCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Avatar URL',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: faceUrlCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Base Face URL (ID Photo)',
                      border: OutlineInputBorder(),
                      helperText: 'Reference face for visual consistency',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: tagsCtrl,
                    maxLines: 3,
                    decoration: const InputDecoration(
                      labelText: 'Visual Prompt Tags',
                      border: OutlineInputBorder(),
                      helperText:
                          'e.g. "1boy, black hair, brown eyes, athletic build"',
                    ),
                  ),
                  const SizedBox(height: 12),
                  SwitchListTile(
                    title: const Text('Active'),
                    value: isActive == 1,
                    onChanged: (v) {
                      setDialogState(() => isActive = v ? 1 : 0);
                    },
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );

    if (saved == true) {
      try {
        await ApiClient.put('/api/admin/personas/${persona['id']}', {
          'visual_prompt_tags': tagsCtrl.text,
          'base_face_url': faceUrlCtrl.text,
          'avatar_url': avatarCtrl.text,
          'is_active': isActive,
        });
        _loadPersonas();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Save failed: $e')),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Error: $_error'),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: _loadPersonas,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Personas Management',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh),
                onPressed: _loadPersonas,
                tooltip: 'Refresh',
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SingleChildScrollView(
                child: DataTable(
                  columns: const [
                    DataColumn(label: Text('Avatar')),
                    DataColumn(label: Text('Name')),
                    DataColumn(label: Text('Profession')),
                    DataColumn(label: Text('Category')),
                    DataColumn(label: Text('Active')),
                    DataColumn(label: Text('Face Ref')),
                    DataColumn(label: Text('Actions')),
                  ],
                  rows: _personas.map((p) {
                    final hasAvatar = p['avatar_url'] != null &&
                        (p['avatar_url'] as String).isNotEmpty;
                    final hasFace = p['base_face_url'] != null &&
                        (p['base_face_url'] as String).isNotEmpty;
                    return DataRow(cells: [
                      DataCell(
                        hasAvatar
                            ? CircleAvatar(
                                radius: 18,
                                backgroundImage:
                                    NetworkImage(p['avatar_url'] as String),
                              )
                            : const CircleAvatar(
                                radius: 18,
                                child: Icon(Icons.person, size: 18)),
                      ),
                      DataCell(Text(p['name'] ?? '')),
                      DataCell(Text(p['profession'] ?? '')),
                      DataCell(Text(p['category'] ?? '')),
                      DataCell(
                        Icon(
                          p['is_active'] == 1
                              ? Icons.check_circle
                              : Icons.cancel,
                          color:
                              p['is_active'] == 1 ? Colors.green : Colors.red,
                          size: 20,
                        ),
                      ),
                      DataCell(
                        Icon(
                          hasFace ? Icons.face : Icons.face_outlined,
                          color: hasFace ? Colors.green : Colors.grey,
                          size: 20,
                        ),
                      ),
                      DataCell(
                        IconButton(
                          icon: const Icon(Icons.edit, size: 20),
                          tooltip: 'Edit',
                          onPressed: () => _showEditDialog(p),
                        ),
                      ),
                    ]);
                  }).toList(),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
