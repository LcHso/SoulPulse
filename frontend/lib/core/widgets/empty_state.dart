import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// A reusable empty state widget for displaying placeholder content
/// when no data is available.
///
/// Features:
/// - Large muted icon
/// - Title text
/// - Optional subtitle text
/// - Optional action button
class EmptyState extends StatelessWidget {
  /// Icon to display (should be an outlined variant for subtle appearance)
  final IconData icon;

  /// Main title text
  final String title;

  /// Optional subtitle/description text
  final String subtitle;

  /// Optional action button label (if provided, shows action button)
  final String? actionLabel;

  /// Callback when action button is pressed
  final VoidCallback? onAction;

  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final iconColor = isDark ? Colors.grey[600] : Colors.grey[300];
    final titleColor = isDark ? Colors.grey[400] : Colors.grey[600];
    final subtitleColor = isDark ? Colors.grey[500] : Colors.grey[500];

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 64,
              color: iconColor,
            ),
            const SizedBox(height: 16),
            Text(
              title,
              style: GoogleFonts.inter(
                fontSize: 16,
                fontWeight: FontWeight.w500,
                color: titleColor,
              ),
              textAlign: TextAlign.center,
            ),
            if (subtitle.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                subtitle,
                style: GoogleFonts.inter(
                  fontSize: 13,
                  color: subtitleColor,
                ),
                textAlign: TextAlign.center,
              ),
            ],
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: onAction,
                child: Text(actionLabel!),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
