import { useState, useEffect, useCallback } from 'react';
import api from '../api/client';

/* ─── Reusable Helpers ─────────────────────────────────────── */

function Avatar({ name, size = 'sm' }) {
  const colors = [
    'from-indigo-500 to-purple-500',
    'from-emerald-500 to-teal-500',
    'from-amber-500 to-orange-500',
    'from-rose-500 to-pink-500',
    'from-cyan-500 to-blue-500',
    'from-violet-500 to-fuchsia-500',
  ];
  const idx = (name || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % colors.length;
  const dims = size === 'lg' ? 'w-10 h-10 text-sm' : size === 'md' ? 'w-8 h-8 text-xs' : 'w-6 h-6 text-[10px]';
  return (
    <div className={`${dims} rounded-full bg-gradient-to-br ${colors[idx]} flex items-center justify-center text-white font-bold shrink-0 shadow-sm`}>
      {(name || '?')[0].toUpperCase()}
    </div>
  );
}

const METRICS = [
  { key: 'annotated', label: 'Annotated', emoji: '📝', color: 'indigo', desc: 'Distinct images with completed annotations' },
  { key: 'blurred', label: 'Blurred', emoji: '🔲', color: 'amber', desc: 'Images manually blurred by this annotator' },
  { key: 'restored', label: 'Restored', emoji: '🔄', color: 'emerald', desc: 'Images restored (blur undone) by this annotator' },
  { key: 'approved', label: 'Approved', emoji: '✅', color: 'teal', desc: 'Annotations approved by reviewer' },
];

const COLOR_MAP = {
  indigo:  { bg: 'bg-indigo-50',  text: 'text-indigo-700',  badge: 'bg-indigo-100 text-indigo-700',  ring: 'ring-indigo-200' },
  amber:   { bg: 'bg-amber-50',   text: 'text-amber-700',   badge: 'bg-amber-100 text-amber-700',   ring: 'ring-amber-200' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-700', badge: 'bg-emerald-100 text-emerald-700', ring: 'ring-emerald-200' },
  teal:    { bg: 'bg-teal-50',    text: 'text-teal-700',    badge: 'bg-teal-100 text-teal-700',    ring: 'ring-teal-200' },
};

function StatCard({ emoji, label, value, color, desc }) {
  const c = COLOR_MAP[color] || COLOR_MAP.indigo;
  return (
    <div className={`${c.bg} rounded-xl p-4 border border-transparent hover:border-gray-200 transition`} title={desc}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{emoji}</span>
        <span className={`text-xs font-semibold uppercase tracking-wider ${c.text}`}>{label}</span>
      </div>
      <div className={`text-2xl font-bold ${c.text}`}>{value.toLocaleString()}</div>
    </div>
  );
}

/* ─── Main Component ───────────────────────────────────────── */

export default function AnnotatorStatsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);
  const [activeMetric, setActiveMetric] = useState('annotated');
  const [expandedAnnotator, setExpandedAnnotator] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/annotator-stats?days=${days}`);
      setData(res.data);
    } catch (err) {
      console.error('Failed to load annotator stats:', err);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 h-32" />
        ))}
      </div>
    );
  }

  if (!data || !data.annotators || Object.keys(data.annotators).length === 0) {
    return (
      <div className="py-16 text-center">
        <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center">
          <span className="text-3xl">📊</span>
        </div>
        <p className="text-lg font-medium text-gray-700">No annotator activity yet</p>
        <p className="text-sm text-gray-500 mt-1">Stats will appear once annotators start working.</p>
      </div>
    );
  }

  const dateRange = data.date_range || [];
  const annotators = data.annotators;
  const annotatorNames = Object.keys(annotators).sort();

  // Aggregate totals across all annotators for summary cards
  const globalTotals = { annotated: 0, blurred: 0, restored: 0, approved: 0 };
  for (const name of annotatorNames) {
    const t = annotators[name].totals || {};
    globalTotals.annotated += t.annotated || 0;
    globalTotals.blurred += t.blurred || 0;
    globalTotals.restored += t.restored || 0;
    globalTotals.approved += t.approved || 0;
  }

  const activeMetricInfo = METRICS.find((m) => m.key === activeMetric);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">📊 Annotator Stats</h2>
          <p className="text-sm text-gray-500 mt-0.5">Track daily activity across all annotators</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Day range selector */}
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
            {[7, 14, 30, 60].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition cursor-pointer ${
                  days === d
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          {/* Refresh */}
          <button
            onClick={load}
            className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition cursor-pointer flex items-center gap-1.5"
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Global Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        {METRICS.map((m) => (
          <StatCard key={m.key} emoji={m.emoji} label={m.label} value={globalTotals[m.key]} color={m.color} desc={m.desc} />
        ))}
      </div>

      {/* Metric Selector Tabs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-700 mr-2">View metric:</span>
          {METRICS.map((m) => {
            const c = COLOR_MAP[m.color];
            return (
              <button
                key={m.key}
                onClick={() => setActiveMetric(m.key)}
                className={`px-3 py-1.5 text-xs font-medium rounded-full transition cursor-pointer ${
                  activeMetric === m.key
                    ? `${c.badge} ring-1 ${c.ring}`
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
              >
                {m.emoji} {m.label}
              </button>
            );
          })}
        </div>

        {/* Daily Matrix Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-500">
                <th className="px-4 py-3 text-left font-semibold sticky left-0 bg-gray-50 z-10 min-w-[160px]">Turing ID</th>
                {dateRange.map((d) => {
                  const dateObj = new Date(d + 'T00:00:00');
                  const isToday = d === new Date().toISOString().split('T')[0];
                  return (
                    <th
                      key={d}
                      className={`px-3 py-3 text-center font-medium whitespace-nowrap ${isToday ? 'bg-indigo-50 text-indigo-700' : ''}`}
                    >
                      {dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      {isToday && <span className="block text-[9px] font-bold text-indigo-500">TODAY</span>}
                    </th>
                  );
                })}
                <th className="px-3 py-3 text-center font-semibold bg-gray-100 whitespace-nowrap" title="Sum of selected metric in the chosen date window">
                  Period Total
                </th>
                <th className="px-3 py-3 text-center font-semibold bg-gray-100 whitespace-nowrap" title="All-time cumulative total">
                  All-time
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {annotatorNames.map((name) => {
                const ad = annotators[name];
                const metricDaily = ad[activeMetric] || {};
                const periodTotal = dateRange.reduce((s, d) => s + (metricDaily[d] || 0), 0);
                const allTime = (ad.totals || {})[activeMetric] || 0;
                const c = COLOR_MAP[activeMetricInfo.color];

                return (
                  <tr key={name} className="hover:bg-gray-50/50 transition">
                    <td className="px-4 py-2.5 font-medium text-gray-900 sticky left-0 bg-white z-10">
                      <button
                        onClick={() => setExpandedAnnotator(expandedAnnotator === name ? null : name)}
                        className="flex items-center gap-2 cursor-pointer hover:text-indigo-600 transition"
                      >
                        <Avatar name={name} size="sm" />
                        <span>{name}</span>
                        <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${expandedAnnotator === name ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </td>
                    {dateRange.map((d) => {
                      const count = metricDaily[d] || 0;
                      const isToday = d === new Date().toISOString().split('T')[0];
                      return (
                        <td key={d} className={`px-3 py-2.5 text-center ${isToday ? 'bg-indigo-50/50' : ''}`}>
                          {count > 0 ? (
                            <span className={`inline-block min-w-[26px] px-1.5 py-0.5 rounded-full text-[10px] font-bold ${c.badge}`}>
                              {count}
                            </span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-3 py-2.5 text-center bg-gray-50">
                      <span className={`inline-block min-w-[30px] px-2 py-0.5 rounded-full text-[11px] font-bold ${periodTotal > 0 ? c.badge : 'text-gray-400'}`}>
                        {periodTotal}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-center bg-gray-50">
                      <span className="font-bold text-gray-700 text-[11px]">{allTime.toLocaleString()}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Expanded Annotator Detail */}
      {expandedAnnotator && annotators[expandedAnnotator] && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-3">
            <Avatar name={expandedAnnotator} size="md" />
            <div>
              <h3 className="text-sm font-bold text-gray-900">{expandedAnnotator} — All Metrics Breakdown</h3>
              <p className="text-xs text-gray-500">Per-day activity across all 4 metrics</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 text-gray-500">
                  <th className="px-4 py-3 text-left font-semibold sticky left-0 bg-gray-50 z-10 min-w-[120px]">Metric</th>
                  {dateRange.map((d) => {
                    const dateObj = new Date(d + 'T00:00:00');
                    const isToday = d === new Date().toISOString().split('T')[0];
                    return (
                      <th key={d} className={`px-3 py-3 text-center font-medium whitespace-nowrap ${isToday ? 'bg-indigo-50 text-indigo-700' : ''}`}>
                        {dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </th>
                    );
                  })}
                  <th className="px-3 py-3 text-center font-semibold bg-gray-100">Period</th>
                  <th className="px-3 py-3 text-center font-semibold bg-gray-100">All-time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {METRICS.map((m) => {
                  const daily = annotators[expandedAnnotator][m.key] || {};
                  const periodTotal = dateRange.reduce((s, d) => s + (daily[d] || 0), 0);
                  const allTime = (annotators[expandedAnnotator].totals || {})[m.key] || 0;
                  const c = COLOR_MAP[m.color];

                  return (
                    <tr key={m.key} className="hover:bg-gray-50/50 transition">
                      <td className={`px-4 py-2.5 font-medium sticky left-0 bg-white z-10 ${c.text}`}>
                        <span className="flex items-center gap-1.5">
                          <span>{m.emoji}</span> {m.label}
                        </span>
                      </td>
                      {dateRange.map((d) => {
                        const count = daily[d] || 0;
                        const isToday = d === new Date().toISOString().split('T')[0];
                        return (
                          <td key={d} className={`px-3 py-2.5 text-center ${isToday ? 'bg-indigo-50/50' : ''}`}>
                            {count > 0 ? (
                              <span className={`inline-block min-w-[24px] px-1.5 py-0.5 rounded-full text-[10px] font-bold ${c.badge}`}>
                                {count}
                              </span>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-3 py-2.5 text-center bg-gray-50">
                        <span className={`font-bold text-[11px] ${c.text}`}>{periodTotal}</span>
                      </td>
                      <td className="px-3 py-2.5 text-center bg-gray-50">
                        <span className="font-bold text-gray-700 text-[11px]">{allTime.toLocaleString()}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
