import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/api_client.dart';
import '../../core/providers/auth_provider.dart';
import 'content/pending_posts_page.dart';
import 'personas_page.dart';
import 'users_page.dart';

/// Admin shell with side navigation for SoulPulse Developer Console.
class AdminShell extends ConsumerStatefulWidget {
  const AdminShell({super.key});

  @override
  ConsumerState<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends ConsumerState<AdminShell> {
  int _selectedIndex = 0;

  static const _navItems = [
    (icon: Icons.dashboard, label: 'Dashboard'),
    (icon: Icons.pending_actions, label: 'Pending Posts'),
    (icon: Icons.people, label: 'Personas'),
    (icon: Icons.group, label: 'Users'),
  ];

  @override
  Widget build(BuildContext context) {
    final isAdmin = ref.watch(isAdminProvider);

    // Redirect non-admins to feed
    if (!isAdmin) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        context.go('/feed');
      });
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('SoulPulse Developer Console'),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Back to App',
            onPressed: () => context.go('/feed'),
          ),
        ],
      ),
      body: Row(
        children: [
          // Side navigation
          NavigationRail(
            selectedIndex: _selectedIndex,
            onDestinationSelected: (index) {
              setState(() => _selectedIndex = index);
            },
            labelType: NavigationRailLabelType.all,
            destinations: _navItems.map((item) {
              return NavigationRailDestination(
                icon: Icon(item.icon),
                label: Text(item.label),
              );
            }).toList(),
          ),
          const VerticalDivider(thickness: 1, width: 1),
          // Main content area
          Expanded(
            child: Container(
              color: Colors.grey[100],
              child: _buildContent(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    switch (_selectedIndex) {
      case 1:
        return const PendingPostsPage();
      case 2:
        return const PersonasManagementView();
      case 3:
        return const UsersManagementView();
      default:
        return AdminDashboardView(
          onNavigate: (index) => setState(() => _selectedIndex = index),
        );
    }
  }
}

/// Dashboard overview showing analytics.
class AdminDashboardView extends ConsumerWidget {
  final void Function(int index)? onNavigate;

  const AdminDashboardView({super.key, this.onNavigate});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return FutureBuilder<Map<String, dynamic>>(
      future: ApiClient.get('/api/admin/analytics/overview', useCache: false),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: Text('Error: ${snapshot.error}'));
        }

        final data = snapshot.data ?? {};
        return Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Dashboard Overview',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 24),
              Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  _MetricCard(
                    title: 'Total Users',
                    value: data['total_users']?.toString() ?? '0',
                    icon: Icons.people,
                    color: Colors.blue,
                  ),
                  _MetricCard(
                    title: 'Active Personas',
                    value: data['total_personas']?.toString() ?? '0',
                    icon: Icons.smart_toy,
                    color: Colors.green,
                  ),
                  _MetricCard(
                    title: 'Pending Posts',
                    value: data['pending_posts']?.toString() ?? '0',
                    icon: Icons.pending,
                    color: Colors.orange,
                  ),
                  _MetricCard(
                    title: 'Published Posts',
                    value: data['published_posts']?.toString() ?? '0',
                    icon: Icons.publish,
                    color: Colors.purple,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              const Text(
                'Quick Actions',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              ElevatedButton.icon(
                icon: const Icon(Icons.pending_actions),
                label: const Text('Review Pending Posts'),
                onPressed: () => onNavigate?.call(1),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange,
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String title;
  final String value;
  final IconData icon;
  final Color color;

  const _MetricCard({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: color),
            const SizedBox(height: 12),
            Text(
              value,
              style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(title, style: TextStyle(color: Colors.grey[600])),
          ],
        ),
      ),
    );
  }
}
