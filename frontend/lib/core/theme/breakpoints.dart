import 'package:flutter/material.dart';

/// Responsive breakpoints for SoulPulse app.
///
/// 3-tier system:
/// - Mobile: < 600px (phone)
/// - Tablet: 600–1200px (tablet, small desktop)
/// - Desktop: > 1200px (large desktop)
class Breakpoints {
  Breakpoints._();

  static const double mobile = 600;
  static const double tablet = 900;
  static const double desktop = 1200;

  // Content max-width constraints
  static const double maxContentWidth = 700;
  static const double maxContentWidthWide = 960;
  static const double maxGridWidth = 1080;

  /// Determine the current layout tier
  static LayoutTier getTier(double width) {
    if (width < mobile) return LayoutTier.mobile;
    if (width < desktop) return LayoutTier.tablet;
    return LayoutTier.desktop;
  }

  /// Get adaptive grid cross-axis count based on width
  static int getGridColumns(double width) {
    if (width < mobile) return 2;
    if (width < tablet) return 3;
    if (width < desktop) return 4;
    return 5;
  }

  /// Check if the current width is at least tablet tier
  static bool isTabletOrLarger(BuildContext context) {
    return MediaQuery.sizeOf(context).width >= mobile;
  }

  /// Check if the current width is desktop tier
  static bool isDesktop(BuildContext context) {
    return MediaQuery.sizeOf(context).width >= desktop;
  }
}

enum LayoutTier {
  mobile,
  tablet,
  desktop,
}
