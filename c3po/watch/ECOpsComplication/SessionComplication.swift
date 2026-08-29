import SwiftUI
import WidgetKit

struct MetricEntry: TimelineEntry {
    let date: Date
    let metric: SessionMetric
}

struct MetricProvider: TimelineProvider {
    func placeholder(in context: Context) -> MetricEntry {
        MetricEntry(date: Date(), metric: .empty)
    }

    func getSnapshot(in context: Context, completion: @escaping (MetricEntry) -> Void) {
        completion(MetricEntry(date: Date(), metric: SharedMetricStore.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<MetricEntry>) -> Void) {
        let entry = MetricEntry(date: Date(), metric: SharedMetricStore.load())
        completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(30 * 60))))
    }
}

struct MetricView: View {
    let entry: MetricEntry
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("SESSION").font(.system(size: 8, weight: .bold))
            Text(entry.metric.display).font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .containerBackground(.fill.tertiary, for: .widget)
    }
}

@main
struct SessionComplication: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "session-metric", provider: MetricProvider()) { entry in
            MetricView(entry: entry)
        }
        .configurationDisplayName("Session Metric")
        .description("Current session conversion metric")
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryInline])
    }
}
