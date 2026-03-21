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
    final data = await ApiClient.getList('/api/chat/conversations', useCache: false);
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
