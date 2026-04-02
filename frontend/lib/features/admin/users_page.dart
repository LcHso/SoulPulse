import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';

/// Users management view for the admin console.
class UsersManagementView extends ConsumerStatefulWidget {
  const UsersManagementView({super.key});

  @override
  ConsumerState<UsersManagementView> createState() =>
      _UsersManagementViewState();
}

class _UsersManagementViewState extends ConsumerState<UsersManagementView> {
  List<Map<String, dynamic>> _users = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadUsers();
  }

  Future<void> _loadUsers() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final response =
          await ApiClient.getList('/api/admin/users', useCache: false);
      setState(() {
        _users = List<Map<String, dynamic>>.from(response);
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _toggleAdmin(int userId, int currentIsAdmin) async {
    final newValue = currentIsAdmin == 1 ? 0 : 1;
    final action = newValue == 1 ? 'grant admin' : 'remove admin';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Confirm $action'),
        content: Text('Are you sure you want to $action for user #$userId?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await ApiClient.post(
          '/api/admin/users/$userId/set-admin?is_admin=$newValue',
          {},
        );
        _loadUsers();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Failed: $e')),
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
              onPressed: _loadUsers,
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
                'Users Management',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              Text('${_users.length} users',
                  style: TextStyle(color: Colors.grey[600])),
              const SizedBox(width: 12),
              IconButton(
                icon: const Icon(Icons.refresh),
                onPressed: _loadUsers,
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
                    DataColumn(label: Text('ID')),
                    DataColumn(label: Text('Email')),
                    DataColumn(label: Text('Nickname')),
                    DataColumn(label: Text('Gems'), numeric: true),
                    DataColumn(label: Text('Admin')),
                    DataColumn(label: Text('Created')),
                    DataColumn(label: Text('Actions')),
                  ],
                  rows: _users.map((u) {
                    final isAdmin = u['is_admin'] == 1;
                    return DataRow(cells: [
                      DataCell(Text('${u['id']}')),
                      DataCell(Text(u['email'] ?? '')),
                      DataCell(Text(u['nickname'] ?? '')),
                      DataCell(Text('${u['gem_balance'] ?? 0}')),
                      DataCell(
                        Icon(
                          isAdmin ? Icons.admin_panel_settings : Icons.person,
                          color: isAdmin ? Colors.deepPurple : Colors.grey,
                          size: 20,
                        ),
                      ),
                      DataCell(Text(
                        _formatDate(u['created_at'] as String? ?? ''),
                      )),
                      DataCell(
                        TextButton.icon(
                          icon: Icon(
                            isAdmin ? Icons.remove_moderator : Icons.shield,
                            size: 16,
                          ),
                          label: Text(isAdmin ? 'Remove Admin' : 'Make Admin'),
                          onPressed: () => _toggleAdmin(
                              u['id'] as int, u['is_admin'] as int),
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

  String _formatDate(String isoDate) {
    if (isoDate.isEmpty) return '';
    try {
      final dt = DateTime.parse(isoDate);
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
    } catch (_) {
      return isoDate;
    }
  }
}
