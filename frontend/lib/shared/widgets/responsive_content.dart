import 'package:flutter/material.dart';
import '../../core/theme/breakpoints.dart';

/// A widget that constrains content width on larger screens and centers it.
///
/// Use this to wrap page content so it doesn't stretch on desktop.
/// On mobile, it takes full width with standard padding.
class ResponsiveContent extends StatelessWidget {
  final Widget child;
  final double? maxWidth;
  final EdgeInsetsGeometry? padding;

  /// If true, content uses the wider constraint (for grids, etc.)
  final bool wide;

  const ResponsiveContent({
    super.key,
    required this.child,
    this.maxWidth,
    this.padding,
    this.wide = false,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveMaxWidth = maxWidth ??
        (wide ? Breakpoints.maxGridWidth : Breakpoints.maxContentWidth);

    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
        child:
            padding != null ? Padding(padding: padding!, child: child) : child,
      ),
    );
  }
}

/// A sliver version of [ResponsiveContent] for use inside CustomScrollView.
class ResponsiveContentSliver extends StatelessWidget {
  final Widget sliver;
  final double? maxWidth;
  final bool wide;

  const ResponsiveContentSliver({
    super.key,
    required this.sliver,
    this.maxWidth,
    this.wide = false,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveMaxWidth = maxWidth ??
        (wide ? Breakpoints.maxGridWidth : Breakpoints.maxContentWidth);
    final screenWidth = MediaQuery.sizeOf(context).width;
    final horizontalPadding = screenWidth > effectiveMaxWidth
        ? (screenWidth - effectiveMaxWidth) / 2
        : 0.0;

    return SliverPadding(
      padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
      sliver: sliver,
    );
  }
}
