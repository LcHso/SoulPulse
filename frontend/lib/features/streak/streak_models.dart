/// Streak & Ritual configuration data models

class StreakInfo {
  final int currentStreak;
  final int totalDays;
  final String? lastStreakDate;
  final int nextMilestone;
  final Map<String, dynamic> nextMilestoneReward;

  const StreakInfo({
    required this.currentStreak,
    required this.totalDays,
    this.lastStreakDate,
    required this.nextMilestone,
    required this.nextMilestoneReward,
  });

  factory StreakInfo.fromJson(Map<String, dynamic> json) {
    return StreakInfo(
      currentStreak: json['current_streak'] as int? ?? 0,
      totalDays: json['total_days'] as int? ?? 0,
      lastStreakDate: json['last_streak_date'] as String?,
      nextMilestone: json['next_milestone'] as int? ?? 7,
      nextMilestoneReward:
          (json['next_milestone_reward'] as Map<String, dynamic>?) ?? {},
    );
  }

  /// Days remaining until next milestone
  int get daysToNextMilestone =>
      (nextMilestone - currentStreak).clamp(0, nextMilestone);

  /// Progress fraction [0..1] toward next milestone
  double get milestoneProgress {
    if (nextMilestone <= 0) return 1.0;
    return (currentStreak / nextMilestone).clamp(0.0, 1.0);
  }
}

class RitualConfig {
  bool morningGreeting;
  String morningTime;
  bool nightGreeting;
  String nightTime;
  bool moodCheckin;
  String? sharedHabit;

  RitualConfig({
    this.morningGreeting = false,
    this.morningTime = '08:00',
    this.nightGreeting = false,
    this.nightTime = '22:00',
    this.moodCheckin = false,
    this.sharedHabit,
  });

  factory RitualConfig.fromJson(Map<String, dynamic> json) {
    return RitualConfig(
      morningGreeting: json['morning_greeting'] as bool? ?? false,
      morningTime: json['morning_time'] as String? ?? '08:00',
      nightGreeting: json['night_greeting'] as bool? ?? false,
      nightTime: json['night_time'] as String? ?? '22:00',
      moodCheckin: json['mood_checkin'] as bool? ?? false,
      sharedHabit: json['shared_habit'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'morning_greeting': morningGreeting,
      'morning_time': morningTime,
      'night_greeting': nightGreeting,
      'night_time': nightTime,
      'mood_checkin': moodCheckin,
      'shared_habit': sharedHabit,
    };
  }
}
