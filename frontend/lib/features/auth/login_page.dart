import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/providers/auth_provider.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _nicknameCtrl = TextEditingController();
  bool _isRegister = false;
  String? _error;
  String _gender = 'not_specified';
  String _orientation = 'male';

  Future<void> _submit() async {
    setState(() => _error = null);

    try {
      if (_isRegister) {
        await ref.read(authProvider.notifier).register(
              _emailCtrl.text.trim(),
              _passwordCtrl.text,
              _nicknameCtrl.text.trim().isEmpty
                  ? 'User'
                  : _nicknameCtrl.text.trim(),
              gender: _gender,
              orientation: _orientation,
            );
      } else {
        await ref.read(authProvider.notifier).login(
              _emailCtrl.text.trim(),
              _passwordCtrl.text,
            );
      }
      if (mounted) context.go('/feed');
    } catch (e) {
      setState(() => _error = e.toString().replaceAll('Exception: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 40),
                Text(
                  'SoulPulse',
                  style: GoogleFonts.inter(
                    fontSize: 36,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -1,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Your AI companion, redefined.',
                  style: GoogleFonts.inter(
                    fontSize: 14,
                    color: isDark ? Colors.grey[400] : Colors.grey[600],
                  ),
                ),
                const SizedBox(height: 40),
                TextField(
                  controller: _emailCtrl,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(hintText: 'Email'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _passwordCtrl,
                  obscureText: true,
                  decoration: const InputDecoration(hintText: 'Password'),
                ),
                if (_isRegister) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _nicknameCtrl,
                    decoration: const InputDecoration(hintText: 'Nickname'),
                  ),
                  const SizedBox(height: 12),
                  // Gender selection
                  DropdownButtonFormField<String>(
                    value: _gender,
                    decoration: const InputDecoration(labelText: 'Gender'),
                    items: const [
                      DropdownMenuItem(
                          value: 'not_specified',
                          child: Text('Prefer not to say')),
                      DropdownMenuItem(value: 'male', child: Text('Male')),
                      DropdownMenuItem(value: 'female', child: Text('Female')),
                      DropdownMenuItem(
                          value: 'non_binary', child: Text('Non-binary')),
                    ],
                    onChanged: (v) => setState(() => _gender = v!),
                  ),
                  const SizedBox(height: 12),
                  // Orientation
                  DropdownButtonFormField<String>(
                    value: _orientation,
                    decoration:
                        const InputDecoration(labelText: 'Interested in'),
                    items: const [
                      DropdownMenuItem(
                          value: 'male', child: Text('Male characters')),
                      DropdownMenuItem(
                          value: 'female', child: Text('Female characters')),
                      DropdownMenuItem(
                          value: 'both', child: Text('All characters')),
                    ],
                    onChanged: (v) => setState(() => _orientation = v!),
                  ),
                ],
                const SizedBox(height: 20),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      _error!,
                      style: const TextStyle(color: Colors.red, fontSize: 13),
                    ),
                  ),
                ElevatedButton(
                  onPressed: authState.isLoading ? null : _submit,
                  child: authState.isLoading
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : Text(_isRegister ? 'Sign Up' : 'Log In'),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      _isRegister
                          ? 'Already have an account?'
                          : "Don't have an account?",
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                      ),
                    ),
                    TextButton(
                      onPressed: () =>
                          setState(() => _isRegister = !_isRegister),
                      child: Text(
                        _isRegister ? 'Log In' : 'Sign Up',
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF0095F6),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
