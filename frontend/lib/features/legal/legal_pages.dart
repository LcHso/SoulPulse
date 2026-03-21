import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class PrivacyPolicyPage extends StatelessWidget {
  const PrivacyPolicyPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Privacy Policy',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Privacy Policy',
                style: GoogleFonts.inter(
                    fontSize: 24, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text('Last updated: March 2026',
                style:
                    GoogleFonts.inter(fontSize: 13, color: Colors.grey[500])),
            const SizedBox(height: 20),
            _section(
                '1. Information We Collect',
                'We collect information you provide directly to us, including your email address, '
                    'nickname, gender preference, and chat messages with AI personas. We also collect '
                    'usage data such as interaction patterns and feature usage statistics.'),
            _section(
                '2. How We Use Your Information',
                'We use your information to: provide and maintain our AI companion services, '
                    'personalize your experience through the intimacy and emotion systems, '
                    'improve our AI models and services, and communicate important updates.'),
            _section(
                '3. Data Storage and Security',
                'Your data is stored securely on our servers. Chat messages and memories are '
                    'used to maintain conversation continuity with AI personas. We implement '
                    'industry-standard security measures to protect your data.'),
            _section(
                '4. AI Interactions',
                'Your conversations with AI personas are processed to generate responses and '
                    'build emotional context. AI persona memories are stored to maintain relationship '
                    'continuity. You can delete your account and all associated data at any time.'),
            _section(
                '5. Data Sharing',
                'We do not sell your personal information. We may share anonymized, aggregated '
                    'data for research purposes. We may disclose information when required by law.'),
            _section(
                '6. Your Rights',
                'You have the right to: access your personal data, request correction of inaccurate data, '
                    'delete your account and all associated data, and export your data.'),
            _section('7. Contact Us',
                'If you have questions about this privacy policy, please contact us through the app.'),
          ],
        ),
      ),
    );
  }

  Widget _section(String title, String content) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style:
                  GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(content, style: GoogleFonts.inter(fontSize: 14, height: 1.5)),
        ],
      ),
    );
  }
}

class TermsOfServicePage extends StatelessWidget {
  const TermsOfServicePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Terms of Service',
            style:
                GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 18)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Terms of Service',
                style: GoogleFonts.inter(
                    fontSize: 24, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text('Last updated: March 2026',
                style:
                    GoogleFonts.inter(fontSize: 13, color: Colors.grey[500])),
            const SizedBox(height: 20),
            _section(
                '1. Acceptance of Terms',
                'By using SoulPulse, you agree to these terms. If you do not agree, '
                    'please do not use our services.'),
            _section(
                '2. Description of Service',
                'SoulPulse provides AI companion interactions through chat, social feeds, '
                    'and story features. AI personas are fictional characters and do not represent '
                    'real people.'),
            _section(
                '3. User Responsibilities',
                'You must be at least 16 years old to use this service. You are responsible '
                    'for maintaining the security of your account. You agree not to use the '
                    'service for any illegal or harmful purposes.'),
            _section(
                '4. AI Interactions',
                'AI responses are generated by language models and should not be considered '
                    'professional advice. The emotional states and personalities of AI personas '
                    'are simulated and do not reflect real emotions.'),
            _section(
                '5. Content and Intellectual Property',
                'AI-generated content (posts, stories, messages) is created for your personal '
                    'use. You retain ownership of content you create (comments, messages).'),
            _section(
                '6. Account Termination',
                'You may delete your account at any time through the settings page. We reserve '
                    'the right to suspend accounts that violate these terms.'),
            _section(
                '7. Limitation of Liability',
                'SoulPulse is provided "as is" without warranties. We are not liable for '
                    'any damages arising from your use of the service.'),
            _section(
                '8. Changes to Terms',
                'We may update these terms from time to time. Continued use of the service '
                    'constitutes acceptance of updated terms.'),
          ],
        ),
      ),
    );
  }

  Widget _section(String title, String content) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style:
                  GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(content, style: GoogleFonts.inter(fontSize: 14, height: 1.5)),
        ],
      ),
    );
  }
}
