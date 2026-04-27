import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';

/// Interaction state for a single AI relationship
class InteractionState {
  final int aiId;
  final String aiName;
  final String aiAvatar;
  final double intimacyScore;
  final String intimacyLevel;
  final Map<String, dynamic>? emotionHint;
  final bool isLoading;
  final String? error;

  const InteractionState({
    required this.aiId,
    required this.aiName,
    this.aiAvatar = '',
    this.intimacyScore = 0.0,
    this.intimacyLevel = 'Stranger',
    this.emotionHint,
    this.isLoading = false,
    this.error,
  });

  InteractionState copyWith({
    int? aiId,
    String? aiName,
    String? aiAvatar,
    double? intimacyScore,
    String? intimacyLevel,
    Map<String, dynamic>? emotionHint,
    bool? isLoading,
    String? error,
  }) {
    return InteractionState(
      aiId: aiId ?? this.aiId,
      aiName: aiName ?? this.aiName,
      aiAvatar: aiAvatar ?? this.aiAvatar,
      intimacyScore: intimacyScore ?? this.intimacyScore,
      intimacyLevel: intimacyLevel ?? this.intimacyLevel,
      emotionHint: emotionHint ?? this.emotionHint,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

/// Interactions list state
class InteractionsListState {
  final List<InteractionState> interactions;
  final bool isLoading;
  final String? error;

  const InteractionsListState({
    this.interactions = const [],
    this.isLoading = false,
    this.error,
  });

  InteractionsListState copyWith({
    List<InteractionState>? interactions,
    bool? isLoading,
    String? error,
  }) {
    return InteractionsListState(
      interactions: interactions ?? this.interactions,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  /// Get intimacy score for a specific AI
  double? getIntimacy(int aiId) {
    final interaction = interactions.firstWhere(
      (i) => i.aiId == aiId,
      orElse: () => const InteractionState(aiId: -1, aiName: ''),
    );
    return interaction.aiId == -1 ? null : interaction.intimacyScore;
  }

  /// Get interaction state for a specific AI
  InteractionState? getInteraction(int aiId) {
    try {
      return interactions.firstWhere((i) => i.aiId == aiId);
    } catch (_) {
      return null;
    }
  }
}

/// Notifier for managing all AI interactions
class InteractionsNotifier extends Notifier<InteractionsListState> {
  @override
  InteractionsListState build() {
    return const InteractionsListState();
  }

  /// Load all interactions summary from the API
  Future<void> loadInteractions() async {
    state = state.copyWith(isLoading: true, error: null);

    try {
      final data = await ApiClient.getList('/api/ai/interactions/summary');
      final interactions = data.map<InteractionState>((item) {
        final map = item as Map<String, dynamic>;
        return InteractionState(
          aiId: map['ai_id'] as int,
          aiName: map['ai_name'] as String? ?? 'AI',
          aiAvatar: map['ai_avatar'] as String? ?? '',
          intimacyScore: (map['intimacy_score'] as num?)?.toDouble() ?? 0.0,
          intimacyLevel: map['intimacy_level'] as String? ?? 'Stranger',
          emotionHint: map['emotion_hint'] as Map<String, dynamic>?,
        );
      }).toList();

      state = state.copyWith(
        interactions: interactions,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString(),
      );
    }
  }

  /// Get intimacy score for a specific AI
  /// Returns null if not found
  double? getIntimacy(int aiId) {
    return state.getIntimacy(aiId);
  }

  /// Get full interaction data for a specific AI
  InteractionState? getInteraction(int aiId) {
    return state.getInteraction(aiId);
  }

  /// Refresh a single interaction by AI ID
  Future<void> refreshInteraction(int aiId) async {
    try {
      final data = await ApiClient.get('/api/ai/interactions/$aiId');
      final updated = InteractionState(
        aiId: aiId,
        aiName: data['ai_name'] as String? ?? 'AI',
        aiAvatar: data['ai_avatar'] as String? ?? '',
        intimacyScore: (data['intimacy_score'] as num?)?.toDouble() ?? 0.0,
        intimacyLevel: data['intimacy_level'] as String? ?? 'Stranger',
        emotionHint: data['emotion_hint'] as Map<String, dynamic>?,
      );

      final newInteractions = List<InteractionState>.from(state.interactions);
      final idx = newInteractions.indexWhere((i) => i.aiId == aiId);
      if (idx >= 0) {
        newInteractions[idx] = updated;
      } else {
        newInteractions.add(updated);
      }

      state = state.copyWith(interactions: newInteractions);
    } catch (_) {
      // Silently fail on refresh
    }
  }
}

/// Main interactions provider
final interactionsProvider =
    NotifierProvider<InteractionsNotifier, InteractionsListState>(
        InteractionsNotifier.new);

/// Provider for a single AI's interaction data
/// Usage: ref.watch(interactionByIdProvider(123))
final interactionByIdProvider =
    Provider.family<InteractionState?, int>((ref, aiId) {
  final interactions = ref.watch(interactionsProvider);
  return interactions.getInteraction(aiId);
});

/// Provider for a single AI's intimacy score
/// Usage: ref.watch(intimacyProvider(123))
final intimacyProvider = Provider.family<double?, int>((ref, aiId) {
  final interactions = ref.watch(interactionsProvider);
  return interactions.getIntimacy(aiId);
});
