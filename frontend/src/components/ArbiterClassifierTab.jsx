import { useState, useEffect, useMemo } from 'react';
import api from '../api/client';

const CATEGORIES = ['lighting', 'viewpoint', 'environment', 'occlusion', 'activity', 'multipet'];

const CATEGORY_ICONS = {
  lighting: '💡',
  viewpoint: '📷',
  environment: '🏠',
  occlusion: '🚧',
  activity: '🏃',
  multipet: '🐾',
};

const STATUS_COLORS = {
  agree: 'bg-green-100 text-green-700 border-green-200',
  arbiter: 'bg-amber-100 text-amber-700 border-amber-200',
};

/* ─── Small helpers ──────────────────────────────────────── */
function formatLabel(label) {
  if (!label || label === 'None') return 'None';
  return label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function ProgressRing({ pct, size = 64 }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e5e7eb" strokeWidth={5} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="url(#grad)" strokeWidth={5}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-700" />
      <defs>
        <linearGradient id="grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
      </defs>
    </svg>
  );
}


export default function ArbiterClassifierTab() {
  // ─── State ───────────────────────────────────────────────
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [resetOnStart, setResetOnStart] = useState(false);

  // Filters
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedLabel, setSelectedLabel] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 30;

  // Detail modal
  const [detailImage, setDetailImage] = useState(null);

  // ─── Data fetchers ─────────────────────────────────────
  const fetchConfig = async () => {
    try {
      const res = await api.get('/admin/arbiter/config');
      setConfig(res.data);
    } catch (e) { console.error('Failed to fetch arbiter config', e); }
  };

  const fetchStatus = async () => {
    try {
      const res = await api.get('/admin/arbiter/status');
      setStatus(res.data);
    } catch (e) { console.error('Failed to fetch arbiter status', e); }
  };

  const fetchResults = async () => {
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (searchTerm) params.search = searchTerm;
      if (selectedCategory && selectedLabel) {
        params.category = selectedCategory;
        params.prediction = selectedLabel;
      }
      const res = await api.get('/admin/arbiter/results', { params });
      setResults(res.data);
    } catch (e) { console.error('Failed to fetch arbiter results', e); }
  };

  // ─── Lifecycle ────────────────────────────────────────
  useEffect(() => {
    Promise.all([fetchConfig(), fetchStatus(), fetchResults()]).finally(() => setLoading(false));
  }, []);

  // Auto-refresh when running
  useEffect(() => {
    if (!status?.is_running) return;
    const interval = setInterval(() => {
      fetchStatus();
      fetchResults();
    }, 3000);
    return () => clearInterval(interval);
  }, [status?.is_running]);

  // Refetch results on filter/page change
  useEffect(() => { fetchResults(); }, [page, searchTerm, selectedCategory, selectedLabel]);

  // ─── Actions ──────────────────────────────────────────
  const startPipeline = async () => {
    setStarting(true);
    try {
      await api.post('/admin/arbiter/start', { reset: resetOnStart });
      fetchStatus();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to start arbiter pipeline');
    } finally {
      setStarting(false);
    }
  };

  const stopPipeline = async () => {
    try {
      await api.post('/admin/arbiter/stop');
      fetchStatus();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to stop arbiter pipeline');
    }
  };

  // ─── Derived data ─────────────────────────────────────
  const summary = results?.summary || {};
  const catStats = summary.category_stats || {};
  const pct = status?.total > 0 ? Math.round((status.processed / status.total) * 100) : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">

      {/* ─── Header ─────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">⚖️ Arbiter Classifier</h1>
          <p className="text-sm text-gray-500 mt-1">
            3-model architecture: Gemini + GPT-4o → Arbiter (o3) on disagreements
          </p>
        </div>

        {status?.is_running ? (
          <button onClick={stopPipeline}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition flex items-center gap-2 cursor-pointer">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
            </svg>
            Stop Classifier
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" checked={resetOnStart} onChange={e => setResetOnStart(e.target.checked)}
                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
              Reset previous results
            </label>
            <button onClick={startPipeline} disabled={starting || !config?.available_images}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center gap-2 disabled:opacity-50 cursor-pointer">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {starting ? 'Starting…' : 'Run Classifier'}
            </button>
          </div>
        )}
      </div>

      {/* ─── Config cards ──────────────────────────── */}
      {config && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ConfigCard label="Model 1" value={config.gemini_model} sub={config.gemini_provider} icon="🔵" />
          <ConfigCard label="Model 2" value={config.openai_model} sub={config.openai_provider} icon="🟢" />
          <ConfigCard label="Arbiter" value={config.arbiter_model} sub={config.arbiter_provider} icon="⚖️" />
          <ConfigCard label="Images Available" value={config.available_images} sub="in 04_final_output/" icon="🖼️" />
        </div>
      )}

      {/* ─── Progress (when running or just completed) ─── */}
      {(status?.is_running || status?.current_step === 'completed' || status?.current_step === 'stopped') && (
        <div className={`rounded-xl p-5 shadow-lg text-white ${
          status?.is_running ? 'bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600' :
          status?.current_step === 'completed' ? 'bg-gradient-to-r from-emerald-600 to-teal-600' :
          'bg-gradient-to-r from-amber-600 to-orange-600'
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-semibold text-lg">
                {status?.is_running ? '⏳ Classifying images…' :
                 status?.current_step === 'completed' ? '✅ Classification Complete' : '⏸️ Stopped'}
              </h3>
              {status?.current_image && (
                <p className="text-sm text-white/70 mt-0.5">Current: {status.current_image}</p>
              )}
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold">{pct}%</p>
              <p className="text-sm text-white/70">{status?.processed || 0} / {status?.total || 0}</p>
            </div>
          </div>
          <div className="w-full bg-white/20 rounded-full h-3">
            <div className="bg-white h-3 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          {status?.started_at && (
            <p className="text-xs text-white/60 mt-2">
              Started: {new Date(status.started_at).toLocaleString()}
              {status?.completed_at && ` · Finished: ${new Date(status.completed_at).toLocaleString()}`}
            </p>
          )}
        </div>
      )}

      {/* ─── Errors ──────────────────────────────── */}
      {status?.errors?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h3 className="font-semibold text-red-700 mb-2">⚠️ Errors ({status.errors.length})</h3>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {status.errors.map((e, i) => (
              <p key={i} className="text-sm text-red-600 font-mono">{e}</p>
            ))}
          </div>
        </div>
      )}

      {/* ─── Summary Stats ─────────────────────── */}
      {summary.total_images > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Classified" value={summary.total_images} icon="📊" />
          <StatCard label="Agreement Rate" value={`${summary.agreement_rate}%`}
            sub={`${summary.total_agreements} / ${summary.total_categories} categories`} icon="🤝" />
          <StatCard label="Arbiter Called" value={summary.total_arbiter_calls}
            sub={`for ${summary.total_categories - summary.total_agreements} disagreements`} icon="⚖️" />
          <StatCard label="Categories" value={CATEGORIES.length} sub="per image" icon="📋" />
        </div>
      )}

      {/* ─── Category Breakdown ───────────────── */}
      {summary.total_images > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Category Breakdown</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {CATEGORIES.map(cat => {
              const stats = catStats[cat] || {};
              const labels = stats.labels || {};
              const agreePct = summary.total_images > 0
                ? Math.round((stats.agree_count || 0) / summary.total_images * 100) : 0;
              const isActive = selectedCategory === cat;

              return (
                <div key={cat}
                  className={`bg-white rounded-xl border p-4 transition-all ${
                    isActive ? 'border-indigo-300 ring-2 ring-indigo-200 shadow-md' : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-semibold text-gray-800 flex items-center gap-1.5">
                      <span>{CATEGORY_ICONS[cat]}</span>
                      {formatLabel(cat)}
                    </h3>
                    <span className="text-xs text-gray-400">{agreePct}% agreed</span>
                  </div>

                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(labels).sort((a, b) => b[1] - a[1]).map(([label, count]) => (
                      <button key={label}
                        onClick={() => {
                          if (selectedCategory === cat && selectedLabel === label) {
                            setSelectedCategory(null); setSelectedLabel(null);
                          } else {
                            setSelectedCategory(cat); setSelectedLabel(label);
                          }
                          setPage(1);
                        }}
                        className={`px-2 py-1 text-xs rounded-full border transition cursor-pointer ${
                          selectedCategory === cat && selectedLabel === label
                            ? 'bg-indigo-100 text-indigo-700 border-indigo-300'
                            : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
                        }`}
                      >
                        {formatLabel(label)} <span className="font-semibold">{count}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── Results Table ─────────────────────── */}
      {results?.results?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900">
              Results
              {selectedCategory && selectedLabel && (
                <span className="ml-2 text-sm font-normal text-gray-500">
                  filtered: {formatLabel(selectedCategory)} = {formatLabel(selectedLabel)}
                  <button onClick={() => { setSelectedCategory(null); setSelectedLabel(null); setPage(1); }}
                    className="ml-2 text-indigo-600 hover:underline cursor-pointer">clear</button>
                </span>
              )}
            </h2>
            <div className="flex items-center gap-3">
              <input type="text" placeholder="Search filename…" value={searchTerm}
                onChange={e => { setSearchTerm(e.target.value); setPage(1); }}
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500 w-56" />
              <span className="text-sm text-gray-400">{results.total} images</span>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-4 py-3 text-left font-semibold text-gray-600">Image</th>
                    {CATEGORIES.map(cat => (
                      <th key={cat} className="px-3 py-3 text-center font-semibold text-gray-600">
                        <span className="inline-flex items-center gap-1">{CATEGORY_ICONS[cat]} {formatLabel(cat)}</span>
                      </th>
                    ))}
                    <th className="px-3 py-3 text-center font-semibold text-gray-600">Agree</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {results.results.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-50/50 transition-colors cursor-pointer"
                      onClick={() => setDetailImage(row)}>
                      <td className="px-4 py-2.5">
                        <span className="font-medium text-gray-900 truncate block max-w-[200px]" title={row.image}>
                          {row.image}
                        </span>
                      </td>
                      {CATEGORIES.map(cat => {
                        const detail = row.details?.[cat] || {};
                        const statusClass = STATUS_COLORS[detail.status] || 'bg-gray-100 text-gray-600 border-gray-200';
                        return (
                          <td key={cat} className="px-3 py-2.5 text-center">
                            <span className={`inline-block px-2 py-0.5 text-xs rounded-full border ${statusClass}`}>
                              {formatLabel(detail.final || row.predictions?.[cat] || '–')}
                            </span>
                          </td>
                        );
                      })}
                      <td className="px-3 py-2.5 text-center">
                        <span className={`font-semibold text-sm ${
                          row.agreement_count === 6 ? 'text-green-600' :
                          row.agreement_count >= 4 ? 'text-amber-600' : 'text-red-600'
                        }`}>
                          {row.agreement_count}/6
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {results.total > PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
                <span className="text-sm text-gray-500">
                  Page {results.page} of {Math.ceil(results.total / PAGE_SIZE)}
                </span>
                <div className="flex gap-2">
                  <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                    className="px-3 py-1 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 cursor-pointer">
                    ← Prev
                  </button>
                  <button disabled={page * PAGE_SIZE >= results.total} onClick={() => setPage(p => p + 1)}
                    className="px-3 py-1 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 cursor-pointer">
                    Next →
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {(!results || results.total === 0) && !status?.is_running && (
        <div className="py-16 text-center">
          <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center">
            <span className="text-2xl">⚖️</span>
          </div>
          <p className="text-lg font-medium text-gray-700">No classification results yet</p>
          <p className="text-sm text-gray-500 mt-1">Click "Run Classifier" to classify the final pipeline images.</p>
        </div>
      )}

      {/* ─── Detail Modal ───────────────────────── */}
      {detailImage && (
        <DetailModal image={detailImage} onClose={() => setDetailImage(null)} />
      )}
    </div>
  );
}

/* ───────────────────────────────────────────────────────────── */
/* Sub-components                                               */
/* ───────────────────────────────────────────────────────────── */

function ConfigCard({ label, value, sub, icon }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center text-lg shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-gray-400 font-medium">{label}</p>
        <p className="text-sm font-semibold text-gray-900 truncate">{value}</p>
        {sub && <p className="text-xs text-gray-400 truncate">{sub}</p>}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, icon }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{icon}</span>
        <span className="text-xs text-gray-400 font-medium">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function DetailModal({ image, onClose }) {
  const details = image.details || {};
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-y-auto m-4" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900 truncate max-w-md" title={image.image}>{image.image}</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Agreement: <span className={`font-semibold ${
                image.agreement_count === 6 ? 'text-green-600' :
                image.agreement_count >= 4 ? 'text-amber-600' : 'text-red-600'
              }`}>{image.agreement_count}/6</span>
              {image.arbiter_calls > 0 && <span className="ml-3">⚖️ Arbiter called</span>}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition cursor-pointer">
            <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Categories */}
        <div className="p-6 space-y-4">
          {CATEGORIES.map(cat => {
            const d = details[cat] || {};
            const isArbiter = d.status === 'arbiter';
            return (
              <div key={cat} className={`rounded-xl border p-4 ${isArbiter ? 'border-amber-200 bg-amber-50/30' : 'border-gray-200 bg-white'}`}>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-gray-800 flex items-center gap-1.5">
                    <span>{CATEGORY_ICONS[cat]}</span> {formatLabel(cat)}
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className={`px-2.5 py-0.5 text-xs rounded-full border font-medium ${STATUS_COLORS[d.status] || 'bg-gray-100 text-gray-600 border-gray-200'}`}>
                      {d.status === 'agree' ? '✓ Agreed' : '⚖️ Arbiter'}
                    </span>
                    <span className="px-2.5 py-0.5 text-xs rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200 font-semibold">
                      {formatLabel(d.final)}
                    </span>
                  </div>
                </div>

                {/* Model predictions */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <ModelBox label="Gemini" pred={d.gemini} reason={d.gemini_reason}
                    isWinner={isArbiter && d.arbiter_winner === 'A'} isFinal={d.final === d.gemini} />
                  <ModelBox label="OpenAI" pred={d.openai} reason={d.openai_reason}
                    isWinner={isArbiter && d.arbiter_winner === 'B'} isFinal={d.final === d.openai} />
                </div>

                {/* Arbiter rationale */}
                {isArbiter && d.arbiter_rationale && (
                  <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <p className="text-xs font-semibold text-amber-700 mb-1">
                      ⚖️ Arbiter Decision · Confidence: {d.arbiter_confidence || 'unknown'}
                    </p>
                    <p className="text-sm text-amber-800">{d.arbiter_rationale}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ModelBox({ label, pred, reason, isWinner, isFinal }) {
  return (
    <div className={`rounded-lg border p-3 text-sm ${
      isWinner ? 'border-green-300 bg-green-50' : 'border-gray-200 bg-gray-50'
    }`}>
      <div className="flex items-center justify-between mb-1">
        <span className="font-semibold text-gray-700">{label}</span>
        <span className="flex items-center gap-1">
          <span className={`px-2 py-0.5 text-xs rounded-full ${
            isFinal ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-200 text-gray-600'
          }`}>
            {formatLabel(pred)}
          </span>
          {isWinner && <span className="text-green-600 text-xs font-bold">★ Winner</span>}
        </span>
      </div>
      {reason && <p className="text-xs text-gray-500 leading-relaxed">{reason}</p>}
    </div>
  );
}
