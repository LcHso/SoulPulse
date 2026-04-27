import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/api_client.dart';

/// Chat conversations list provider.
final conversationsProvider =
    AsyncNotifierProvider<ConversationsNotifier, List<Map<String, dynamic>>>(
        ConversationsNotifier.new);

class ConversationsNotifier extends AsyncNotifier<List<Map<String, dynamic>>> {
  @override
  Future<List<Map<String, dynamic>>> build() async {
    return _fetch();
  }

  Future<List<Map<String, dynamic>>> _fetch() async {
    final data =
        await ApiClient.getList('/api/chat/conversations', useCache: false);
    return data.cast<Map<String, dynamic>>();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(_fetch);
  }
}

/// Total unread message count.
final unreadCountProvider = FutureProvider<int>((ref) async {
  final data = await ApiClient.get('/api/chat/unread-count', useCache: false);
  return (data['unread_count'] as int?) ?? 0;
});

/// Chat messages state for a specific AI conversation
class ChatMessagesState {
  final int aiId;
  final List<Map<String, dynamic>> messages;
  final bool isLoading;
  final String? error;

  const ChatMessagesState({
    required this.aiId,
    this.messages = const [],
    this.isLoading = false,
    this.error,
  });

  ChatMessagesState copyWith({
    int? aiId,
    List<Map<String, dynamic>>? messages,
    bool? isLoading,
    String? error,
  }) {
    return ChatMessagesState(
      aiId: aiId ?? this.aiId,
      messages: messages ?? this.messages,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

/// Notifier for managing chat messages with a specific AI
class ChatMessagesNotifier extends FamilyNotifier<ChatMessagesState, int> {
  @override
  ChatMessagesState build(int aiId) {
    return ChatMessagesState(aiId: aiId);
  }

  int get _aiId => arg;

  /// Load messages for this AI conversation
  Future<void> loadMessages() async {
    if (state.isLoading) return;

    state = state.copyWith(isLoading: true, error: null);

    try {
      final data = await ApiClient.getList(
        '/api/chat/history?ai_id=$_aiId&limit=100',
        useCache: false,
      );
      final messages = data.cast<Map<String, dynamic>>();

      state = state.copyWith(
        messages: messages,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString(),
      );
    }
  }

  /// Add a new message to the conversation
  /// Used for optimistic updates when sending a message
  void addMessage(Map<String, dynamic> message) {
    final newMessages = List<Map<String, dynamic>>.from(state.messages);
    newMessages.add(message);
    state = state.copyWith(messages: newMessages);
  }

  /// Add multiple messages (e.g., when receiving stream)
  void addMessages(List<Map<String, dynamic>> messages) {
    final newMessages = List<Map<String, dynamic>>.from(state.messages);
    newMessages.addAll(messages);
    state = state.copyWith(messages: newMessages);
  }

  /// Clear all messages
  void clearMessages() {
    state = state.copyWith(messages: []);
  }

  /// Update a message by ID (e.g., when message is confirmed by server)
  void updateMessage(int messageId, Map<String, dynamic> updates) {
    final newMessages = List<Map<String, dynamic>>.from(state.messages);
    final idx = newMessages.indexWhere((m) => m['id'] == messageId);
    if (idx >= 0) {
      newMessages[idx] = {...newMessages[idx], ...updates};
      state = state.copyWith(messages: newMessages);
    }
  }

  /// Remove a message by ID
  void removeMessage(int messageId) {
    final newMessages = List<Map<String, dynamic>>.from(state.messages);
    newMessages.removeWhere((m) => m['id'] == messageId);
    state = state.copyWith(messages: newMessages);
  }
}

/// Family provider for chat messages per AI
/// Usage: ref.watch(chatMessagesProvider(123))
final chatMessagesProvider =
    NotifierProvider.family<ChatMessagesNotifier, ChatMessagesState, int>(
  ChatMessagesNotifier.new,
);
