import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'streak_models.dart';
import 'streak_service.dart';

/// Streak & Daily Ritual configuration page.
///
/// Features:
/// - Large flame icon with streak count
/// - Total days counter
/// - Next milestone progress bar
/// - Milestone reward preview
/// - Ritual configuration toggles + time pickers
class StreakPage extends StatefulWidget {
  final int personaId;
  final String personaName;

  const StreakPage({
    super.key,
    required this.personaId,
    required this.personaName,
  });

  @override
  State<StreakPage> createState() => _StreakPageState();
}

class _StreakPageState extends State<StreakPage> {
  final StreakService _service = StreakService();
  StreakInfo? _streakInfo;
  RitualConfig? _ritualConfig;
  bool _loading = true;
  bool _saving = false;
  bool _ritualDirty = false;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _loading = true);
    final streak = await _service.getStreakInfo(widget.personaId);
    final rituals = await _service.getRitualConfig(widget.personaId);
    if (mounted) {
      setState(() {
        _streakInfo = streak;
        _ritualConfig = rituals;
        _loading = false;
      });
    }
  }

  Future<void> _saveRituals() async {
    if (_ritualConfig == null || _saving) return;
    setState(() => _saving = true);
    final success =
        await _service.configureRituals(widget.personaId, _ritualConfig!);
    if (mounted) {
      setState(() => _saving = false);
      if (success) {
        HapticFeedback.lightImpact();
        setState(() => _ritualDirty = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('已保存'),
            duration: Duration(seconds: 1),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('保存失败，请稍后重试')),
        );
      }
    }
  }

  Future<void> _pickTime(bool isMorning) async {
    final current = isMorning
        ? _ritualConfig!.morningTime
        : _ritualConfig!.nightTime;
    final parts = current.split(':');
    final initialTime = TimeOfDay(
      hour: int.tryParse(parts[0]) ?? (isMorning ? 8 : 22),
      minute: int.tryParse(parts.length > 1 ? parts[1] : '0') ?? 0,
    );

    final picked = await showTimePicker(
      context: context,
      initialTime: initialTime,
    );

    if (picked != null && mounted) {
      final timeStr =
          '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
      setState(() {
        if (isMorning) {
          _ritualConfig!.morningTime = timeStr;
        } else {
          _ritualConfig!.nightTime = timeStr;
        }
        _ritualDirty = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.personaName} · 互动记录'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 20),
          onPressed: () => context.pop(),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _buildStreakCard(theme, isDark),
                  const SizedBox(height: 20),
                  _buildMilestoneCard(theme, isDark),
                  const SizedBox(height: 20),
                  _buildRitualSection(theme, isDark),
                ],
              ),
            ),
    );
  }

  // ─── Streak display ──────────────────────────────────────────

  Widget _buildStreakCard(ThemeData theme, bool isDark) {
    final streak = _streakInfo!;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isDark
              ? [const Color(0xFF3D1F2B), const Color(0xFF2A1A38)]
              : [const Color(0xFFFFF0F0), const Color(0xFFF8E8FF)],
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.primary.withOpacity(0.15),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          // Flame icon + streak count
          Stack(
            alignment: Alignment.center,
            children: [
              Icon(
                Icons.local_fire_department,
                size: 80,
                color: streak.currentStreak > 0
                    ? Colors.orange.shade400
                    : Colors.grey.shade400,
              ),
              Positioned(
                bottom: 0,
                child: Text(
                  '${streak.currentStreak}',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    color: streak.currentStreak > 0
                        ? Colors.deepOrange
                        : Colors.grey,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '连续 ${streak.currentStreak} 天',
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.primary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '累计互动 ${streak.totalDays} 天',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  // ─── Milestone progress ──────────────────────────────────────

  Widget _buildMilestoneCard(ThemeData theme, bool isDark) {
    final streak = _streakInfo!;
    final reward = streak.nextMilestoneReward;
    final gems = reward['gems'] as int? ?? 0;
    final intimacyBonus = reward['intimacy_bonus'] as int? ?? 0;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2A45) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.2 : 0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.emoji_events_outlined,
                  size: 20, color: Colors.amber.shade700),
              const SizedBox(width: 6),
              Text(
                '下一个里程碑：${streak.nextMilestone}天',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Progress bar
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: streak.milestoneProgress,
              minHeight: 10,
              backgroundColor:
                  isDark ? Colors.grey.shade700 : Colors.grey.shade200,
              valueColor:
                  AlwaysStoppedAnimation(theme.colorScheme.primary),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            streak.daysToNextMilestone > 0
                ? '距离${streak.nextMilestone}天奖励还差${streak.daysToNextMilestone}天'
                : '即将达成!',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (gems > 0 || intimacyBonus > 0) ...[
            const SizedBox(height: 10),
            const Divider(),
            const SizedBox(height: 6),
            Text('奖励预览', style: theme.textTheme.labelMedium),
            const SizedBox(height: 6),
            Wrap(
              spacing: 12,
              children: [
                if (gems > 0)
                  _rewardChip(Icons.diamond_outlined, '$gems 星钻', Colors.cyan),
                if (intimacyBonus > 0)
                  _rewardChip(
                      Icons.favorite_outline, '+$intimacyBonus 亲密度', Colors.pink),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _rewardChip(IconData icon, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(label,
              style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }

  // ─── Ritual configuration ────────────────────────────────────

  Widget _buildRitualSection(ThemeData theme, bool isDark) {
    final config = _ritualConfig!;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2A2A45) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(isDark ? 0.2 : 0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_awesome, size: 20, color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Text(
                '每日仪式',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Morning greeting
          _ritualToggle(
            icon: Icons.wb_sunny_outlined,
            title: '早安问候',
            subtitle: '每天 ${config.morningTime} 收到TA的早安',
            value: config.morningGreeting,
            onChanged: (v) {
              setState(() {
                config.morningGreeting = v;
                _ritualDirty = true;
              });
            },
            onTimeTap: () => _pickTime(true),
            theme: theme,
          ),
          const Divider(height: 24),
          // Night greeting
          _ritualToggle(
            icon: Icons.nightlight_outlined,
            title: '晚安问候',
            subtitle: '每天 ${config.nightTime} 收到TA的晚安',
            value: config.nightGreeting,
            onChanged: (v) {
              setState(() {
                config.nightGreeting = v;
                _ritualDirty = true;
              });
            },
            onTimeTap: () => _pickTime(false),
            theme: theme,
          ),
          const Divider(height: 24),
          // Mood check-in
          _ritualToggle(
            icon: Icons.mood_outlined,
            title: '心情签到',
            subtitle: 'TA会每天问你今天心情如何',
            value: config.moodCheckin,
            onChanged: (v) {
              setState(() {
                config.moodCheckin = v;
                _ritualDirty = true;
              });
            },
            theme: theme,
          ),
          const Divider(height: 24),
          // Shared habit
          Text('共同习惯',
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w500,
              )),
          const SizedBox(height: 4),
          Text(
            '例如：每天一首歌推荐、互相分享一句话',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: TextEditingController(text: config.sharedHabit ?? ''),
            decoration: InputDecoration(
              hintText: '输入共同习惯...',
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            ),
            onChanged: (v) {
              config.sharedHabit = v.isEmpty ? null : v;
              _ritualDirty = true;
            },
          ),
          const SizedBox(height: 20),
          // Save button
          SizedBox(
            width: double.infinity,
            height: 44,
            child: FilledButton(
              onPressed: _ritualDirty && !_saving ? _saveRituals : null,
              child: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('保存设置'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _ritualToggle({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
    VoidCallback? onTimeTap,
    required ThemeData theme,
  }) {
    return Row(
      children: [
        Icon(icon, size: 22, color: theme.colorScheme.primary),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w500,
              )),
              const SizedBox(height: 2),
              GestureDetector(
                onTap: onTimeTap,
                child: Text(
                  subtitle,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                    decoration: onTimeTap != null
                        ? TextDecoration.underline
                        : null,
                  ),
                ),
              ),
            ],
          ),
        ),
        Switch.adaptive(
          value: value,
          onChanged: onChanged,
          activeColor: theme.colorScheme.primary,
        ),
      ],
    );
  }
}
