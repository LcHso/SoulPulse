import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/services/app_monitor.dart';

/// Developer debug page showing error logs, performance traces, and API stats.
///
/// Accessible from Settings in debug mode or for admin users.
class DebugMonitorPage extends StatefulWidget {
  const DebugMonitorPage({super.key});

  @override
  State<DebugMonitorPage> createState() => _DebugMonitorPageState();
}

class _DebugMonitorPageState extends State<DebugMonitorPage>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'App Monitor',
          style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => setState(() {}),
            tooltip: 'Refresh',
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: 'Errors'),
            Tab(text: 'Performance'),
            Tab(text: 'API Stats'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: const [
          _ErrorsTab(),
          _PerformanceTab(),
          _ApiStatsTab(),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Errors Tab
// ---------------------------------------------------------------------------

class _ErrorsTab extends StatelessWidget {
  const _ErrorsTab();

  @override
  Widget build(BuildContext context) {
    final errors = AppMonitor.instance.recentErrors.reversed.toList();

    if (errors.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle_outline, size: 64, color: Colors.green),
            SizedBox(height: 16),
            Text('No errors recorded', style: TextStyle(fontSize: 16)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: errors.length,
      itemBuilder: (context, index) {
        final error = errors[index];
        return _ErrorCard(record: error);
      },
    );
  }
}

class _ErrorCard extends StatelessWidget {
  final ErrorRecord record;
  const _ErrorCard({required this.record});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final timeStr =
        '${record.timestamp.hour.toString().padLeft(2, '0')}:'
        '${record.timestamp.minute.toString().padLeft(2, '0')}:'
        '${record.timestamp.second.toString().padLeft(2, '0')}';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      color: record.isFatal
          ? Colors.red.shade50
          : theme.cardColor,
      child: ExpansionTile(
        leading: Icon(
          record.isFatal ? Icons.error : Icons.warning_amber,
          color: record.isFatal ? Colors.red : Colors.orange,
        ),
        title: Text(
          record.error.toString(),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
        ),
        subtitle: Text(
          '$timeStr${record.context != null ? ' • ${record.context}' : ''}',
          style: TextStyle(fontSize: 11, color: Colors.grey[600]),
        ),
        children: [
          if (record.stackTrace != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: SelectableText(
                record.stackTrace.toString().split('\n').take(12).join('\n'),
                style: GoogleFonts.firaCode(fontSize: 10),
              ),
            ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Performance Tab
// ---------------------------------------------------------------------------

class _PerformanceTab extends StatelessWidget {
  const _PerformanceTab();

  @override
  Widget build(BuildContext context) {
    final monitor = AppMonitor.instance;
    final traces = monitor.recentTraces
        .where((t) => !t.name.startsWith('api_'))
        .toList()
        .reversed
        .toList();

    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        // Startup metrics card
        _MetricCard(
          title: 'App Startup',
          icon: Icons.rocket_launch,
          value: monitor.startupDuration != null
              ? '${monitor.startupDuration!.inMilliseconds}ms'
              : 'Not measured',
        ),
        const SizedBox(height: 16),

        // Page load times
        if (monitor.pageLoadTimes.isNotEmpty) ...[
          _SectionTitle('Page Load Times'),
          ...monitor.pageLoadTimes.entries.map((e) => _MetricCard(
                title: e.key.replaceFirst('page_', ''),
                icon: Icons.web,
                value: '${e.value.inMilliseconds}ms',
              )),
          const SizedBox(height: 16),
        ],

        // Recent traces
        _SectionTitle('Recent Traces (${traces.length})'),
        if (traces.isEmpty)
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text('No traces recorded yet'),
          ),
        ...traces.take(30).map((trace) => ListTile(
              dense: true,
              leading: _durationIcon(trace.duration),
              title: Text(trace.name, style: const TextStyle(fontSize: 13)),
              trailing: Text(
                '${trace.duration.inMilliseconds}ms',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: _durationColor(trace.duration),
                ),
              ),
            )),
      ],
    );
  }

  Widget _durationIcon(Duration d) {
    if (d.inMilliseconds > 3000) {
      return const Icon(Icons.slow_motion_video, color: Colors.red, size: 20);
    }
    if (d.inMilliseconds > 1000) {
      return const Icon(Icons.timer, color: Colors.orange, size: 20);
    }
    return const Icon(Icons.flash_on, color: Colors.green, size: 20);
  }

  Color _durationColor(Duration d) {
    if (d.inMilliseconds > 3000) return Colors.red;
    if (d.inMilliseconds > 1000) return Colors.orange;
    return Colors.green;
  }
}

// ---------------------------------------------------------------------------
// API Stats Tab
// ---------------------------------------------------------------------------

class _ApiStatsTab extends StatelessWidget {
  const _ApiStatsTab();

  @override
  Widget build(BuildContext context) {
    final stats = AppMonitor.instance.apiStats;

    if (stats.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text('No API calls recorded', style: TextStyle(fontSize: 16)),
          ],
        ),
      );
    }

    // Sort by total call count descending
    final sortedEntries = stats.entries.toList()
      ..sort((a, b) => b.value.callCount.compareTo(a.value.callCount));

    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: sortedEntries.length,
      itemBuilder: (context, index) {
        final entry = sortedEntries[index];
        final stat = entry.value;
        return _ApiStatCard(stat: stat);
      },
    );
  }
}

class _ApiStatCard extends StatelessWidget {
  final ApiEndpointStats stat;
  const _ApiStatCard({required this.stat});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              stat.endpoint,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _StatChip('Calls', '${stat.callCount}', Colors.blue),
                const SizedBox(width: 8),
                _StatChip(
                  'Avg',
                  '${stat.averageDuration.inMilliseconds}ms',
                  Colors.green,
                ),
                const SizedBox(width: 8),
                if (stat.maxDuration != null)
                  _StatChip(
                    'Max',
                    '${stat.maxDuration!.inMilliseconds}ms',
                    stat.maxDuration!.inMilliseconds > 3000
                        ? Colors.red
                        : Colors.orange,
                  ),
              ],
            ),
            if (stat.slowCallCount > 0)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  '⚠️ ${stat.slowCallCount} slow call${stat.slowCallCount > 1 ? 's' : ''} (>3s)',
                  style: const TextStyle(color: Colors.red, fontSize: 11),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _StatChip(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '$label: $value',
        style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Shared Widgets
// ---------------------------------------------------------------------------

class _SectionTitle extends StatelessWidget {
  final String title;
  const _SectionTitle(this.title);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final String value;
  const _MetricCard({
    required this.title,
    required this.icon,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: Theme.of(context).colorScheme.primary),
        title: Text(title, style: const TextStyle(fontSize: 13)),
        trailing: Text(
          value,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
        ),
      ),
    );
  }
}
