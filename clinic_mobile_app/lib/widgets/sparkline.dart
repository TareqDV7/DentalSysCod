import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

/// A compact, axis-less trend line for dashboard metric cards.
///
/// Renders real historical values (oldest → newest). Touch/drag scrubs the
/// series and surfaces the value for the touched day — the mobile-appropriate
/// version of a hover scrub. Below ~2 points there is no meaningful trend, so
/// nothing is drawn.
class Sparkline extends StatelessWidget {
  final List<double> data;
  final Color color;
  final double height;

  /// Formats the touched value into the tooltip label (e.g. currency).
  final String Function(double value)? labelFormat;

  const Sparkline({
    super.key,
    required this.data,
    required this.color,
    this.height = 26,
    this.labelFormat,
  });

  String _format(double v) =>
      labelFormat?.call(v) ?? v.round().toString();

  @override
  Widget build(BuildContext context) {
    if (data.length < 2) return SizedBox(height: height);

    final maxV = data.reduce((a, b) => a > b ? a : b);
    final minV = data.reduce((a, b) => a < b ? a : b);
    // Degenerate (flat) series → give a small symmetric range so the line
    // sits mid-card instead of pinned to an edge.
    final range = (maxV - minV).abs() < 1e-9 ? 1.0 : (maxV - minV);
    final pad = range * 0.15;

    final spots = <FlSpot>[
      for (var i = 0; i < data.length; i++) FlSpot(i.toDouble(), data[i]),
    ];

    return SizedBox(
      height: height,
      child: LineChart(
        LineChartData(
          minY: minV - pad,
          maxY: maxV + pad,
          minX: 0,
          maxX: (data.length - 1).toDouble(),
          gridData: const FlGridData(show: false),
          titlesData: const FlTitlesData(show: false),
          borderData: FlBorderData(show: false),
          lineTouchData: LineTouchData(
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => color.withAlpha(235),
              tooltipPadding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              getTooltipItems: (spots) => spots
                  .map((s) => LineTooltipItem(
                        _format(s.y),
                        const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 11,
                        ),
                      ))
                  .toList(),
            ),
            getTouchedSpotIndicator: (bar, indexes) => indexes
                .map((i) => TouchedSpotIndicatorData(
                      FlLine(color: color.withAlpha(110), strokeWidth: 1),
                      FlDotData(
                        getDotPainter: (s, p, b, idx) => FlDotCirclePainter(
                          radius: 3,
                          color: color,
                          strokeWidth: 0,
                        ),
                      ),
                    ))
                .toList(),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              curveSmoothness: 0.3,
              color: color,
              barWidth: 1.6,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [color.withAlpha(46), color.withAlpha(0)],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
