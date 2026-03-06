import { useState, useEffect, useMemo, Fragment } from 'react';
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
    Promise.all([fetchConfig(), fetchStatus(), fetchResults(), fetchFailed()]).finally(() => setLoading(false));
  }, []);

  // Auto-refresh when running
  useEffect(() => {
    if (!status?.is_running) return;
    const interval = setInterval(() => {
      fetchStatus();
      fetchResults();
      fetchFailed();
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

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [failedImages, setFailedImages] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const [showFailed, setShowFailed] = useState(false);

  const importLabels = async () => {
    if (!confirm('This will import AI-predicted labels into the database. Annotators will see them as pre-filled suggestions. Continue?')) return;
    setImporting(true);
    setImportResult(null);
    try {
      const res = await api.post('/admin/arbiter/import-labels');
      setImportResult(res.data);
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to import labels');
    } finally {
      setImporting(false);
    }
  };

  const fetchFailed = async () => {
    try {
      const res = await api.get('/admin/arbiter/failed');
      setFailedImages(res.data);
    } catch (e) { console.error('Failed to fetch failed images', e); }
  };

  const retryFailed = async () => {
    if (!confirm(`Retry classification for ${failedImages?.total || 0} failed images?`)) return;
    setRetrying(true);
    try {
      await api.post('/admin/arbiter/retry-failed');
      fetchStatus();
      fetchFailed();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to start retry');
    } finally {
      setRetrying(false);
    }
  };

  // ─── Derived data ─────────────────────────────────────
  const summary = results?.summary || {};
  const catStats = summary.category_stats || {};
  const pct = status?.total > 0 ? Math.round((status.processed / status.total) * 100) : 0;
  const failedCount = summary.failed_count || status?.failed_count || failedImages?.total || 0;

  // API error detection — surface from status, results summary, or failed images
  const apiErrorSummary =
    status?.api_error_summary?.is_api_issue ? status.api_error_summary :
    summary?.api_error_summary?.is_api_issue ? summary.api_error_summary :
    failedImages?.error_summary?.is_api_issue ? failedImages.error_summary :
    null;

  // Any error summary (even non-API) for enhanced display
  const anyErrorSummary =
    status?.api_error_summary?.total_errors > 0 ? status.api_error_summary :
    summary?.api_error_summary?.total_errors > 0 ? summary.api_error_summary :
    failedImages?.error_summary?.total_errors > 0 ? failedImages.error_summary :
    null;

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
            {results?.total > 0 && (
              <button onClick={importLabels} disabled={importing}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition flex items-center gap-2 disabled:opacity-50 cursor-pointer"
                title="Import predictions as initial labels for annotators">
                <span>🤖</span>
                {importing ? 'Importing…' : 'Import Labels to DB'}
              </button>
            )}
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

      {/* ─── Import result banner ─────────────────── */}
      {importResult && (
        <div className="rounded-xl p-4 bg-purple-50 border border-purple-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🤖</span>
            <div>
              <p className="text-sm font-semibold text-purple-900">{importResult.message}</p>
              {importResult.not_found_count > 0 && (
                <p className="text-xs text-purple-600 mt-0.5">
                  {importResult.not_found_count} images not found in DB (not yet imported to pipeline)
                </p>
              )}
            </div>
          </div>
          <button onClick={() => setImportResult(null)} className="text-purple-400 hover:text-purple-600 cursor-pointer">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* ─── API Error Banner ─────────────────────── */}
      {apiErrorSummary && (
        <div className="rounded-xl border-2 border-red-300 bg-red-50 p-5 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="shrink-0 w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center text-2xl">
              {apiErrorSummary.dominant_type === 'budget_exceeded' ? '💳' :
               apiErrorSummary.dominant_type === 'forbidden' ? '🔒' :
               apiErrorSummary.dominant_type === 'rate_limited' ? '⏱️' : '🚨'}
            </div>
            <div className="flex-1">
              <h3 className="text-base font-bold text-red-800 mb-1">
                {apiErrorSummary.dominant_type === 'budget_exceeded' ? 'API Budget Exceeded' :
                 apiErrorSummary.dominant_type === 'forbidden' ? 'API Access Forbidden' :
                 apiErrorSummary.dominant_type === 'rate_limited' ? 'API Rate Limited' : 'API Error Detected'}
              </h3>
              <p className="text-sm text-red-700 leading-relaxed">
                {apiErrorSummary.actionable_message}
              </p>
              {apiErrorSummary.categories && Object.keys(apiErrorSummary.categories).length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {Object.entries(apiErrorSummary.categories).map(([type, count]) => (
                    <span key={type}
                      className={`px-2.5 py-1 text-xs font-semibold rounded-full ${
                        type === 'budget_exceeded' ? 'bg-red-200 text-red-800' :
                        type === 'forbidden' ? 'bg-orange-200 text-orange-800' :
                        type === 'rate_limited' ? 'bg-amber-200 text-amber-800' :
                        type === 'timeout' ? 'bg-yellow-200 text-yellow-800' :
                        type === 'server_error' ? 'bg-pink-200 text-pink-800' :
                        'bg-gray-200 text-gray-700'
                      }`}>
                      {type === 'budget_exceeded' ? '💳 Budget (402)' :
                       type === 'forbidden' ? '🔒 Forbidden (403)' :
                       type === 'rate_limited' ? '⏱️ Rate Limit (429)' :
                       type === 'timeout' ? '⏰ Timeout' :
                       type === 'server_error' ? '🔥 Server Error' :
                       type === 'parse_error' ? '📄 Parse Error' :
                       `⚠️ ${type}`}: {count}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-xs text-red-500 mt-2 italic">
                ⚠️ Images that failed due to API errors will show as "Failed" — not as predictions.
                Predictions shown in the results table are only from successful API calls.
              </p>
            </div>
          </div>
        </div>
      )}

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
                {status?.is_running && status?.current_step === 'retrying_failed'
                  ? '🔄 Retrying failed images…'
                  : status?.is_running ? '⏳ Classifying images…'
                  : status?.current_step === 'completed' ? '✅ Classification Complete' : '⏸️ Stopped'}
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
          <div className="flex items-center justify-between mt-2">
            {status?.started_at && (
              <p className="text-xs text-white/60">
                Started: {new Date(status.started_at).toLocaleString()}
                {status?.completed_at && ` · Finished: ${new Date(status.completed_at).toLocaleString()}`}
              </p>
            )}
            {status?.failed_count > 0 && (
              <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-white/20 text-white">
                ⚠️ {status.failed_count} failed
                {status?.api_error_summary?.is_api_issue && ' (API error)'}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ─── Failed / Errored Images ──────────────── */}
      {(failedCount > 0 || status?.errors?.length > 0) && (
        <div className={`rounded-xl p-4 ${
          apiErrorSummary ? 'bg-red-50 border-2 border-red-300' : 'bg-red-50 border border-red-200'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-red-700 flex items-center gap-2">
              ⚠️ Failed Images ({failedCount})
              {anyErrorSummary?.dominant_type && (
                <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                  anyErrorSummary.dominant_type === 'budget_exceeded' ? 'bg-red-200 text-red-800' :
                  anyErrorSummary.dominant_type === 'forbidden' ? 'bg-orange-200 text-orange-800' :
                  anyErrorSummary.dominant_type === 'rate_limited' ? 'bg-amber-200 text-amber-800' :
                  'bg-gray-200 text-gray-700'
                }`}>
                  {anyErrorSummary.dominant_type === 'budget_exceeded' ? '💳 BUDGET EXCEEDED' :
                   anyErrorSummary.dominant_type === 'forbidden' ? '🔒 FORBIDDEN' :
                   anyErrorSummary.dominant_type === 'rate_limited' ? '⏱️ RATE LIMITED' :
                   anyErrorSummary.dominant_type === 'timeout' ? '⏰ TIMEOUT' :
                   anyErrorSummary.dominant_type === 'server_error' ? '🔥 SERVER ERROR' :
                   anyErrorSummary.dominant_type.toUpperCase()}
                </span>
              )}
            </h3>
            <div className="flex items-center gap-2">
              {failedCount > 0 && (
                <>
                  <button
                    onClick={() => { fetchFailed(); setShowFailed(v => !v); }}
                    className="px-3 py-1.5 bg-white border border-red-300 text-red-700 text-xs font-medium rounded-lg hover:bg-red-50 transition cursor-pointer"
                  >
                    {showFailed ? 'Hide Details' : 'Show Details'}
                  </button>
                  <button
                    onClick={retryFailed}
                    disabled={retrying || status?.is_running}
                    className="px-3 py-1.5 bg-red-600 text-white text-xs font-semibold rounded-lg hover:bg-red-700 transition disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                    title={apiErrorSummary ? 'Fix the API issue first before retrying' : 'Retry failed images'}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    {retrying ? 'Starting…' : `Retry ${failedCount} Failed`}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Error category breakdown badges */}
          {anyErrorSummary?.categories && Object.keys(anyErrorSummary.categories).length > 1 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {Object.entries(anyErrorSummary.categories).map(([type, count]) => (
                <span key={type}
                  className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-white border border-red-200 text-red-700">
                  {type === 'budget_exceeded' ? '💳 Budget' :
                   type === 'forbidden' ? '🔒 Forbidden' :
                   type === 'rate_limited' ? '⏱️ Rate Limit' :
                   type === 'timeout' ? '⏰ Timeout' :
                   type === 'server_error' ? '🔥 Server' :
                   type === 'parse_error' ? '📄 Parse' :
                   `⚠️ ${type}`}: {count}
                </span>
              ))}
            </div>
          )}

          {/* Current run errors (in-memory) */}
          {status?.errors?.length > 0 && (
            <div className="max-h-24 overflow-y-auto space-y-1 mb-2">
              {status.errors.slice(0, 10).map((e, i) => (
                <p key={i} className="text-xs text-red-600 font-mono truncate">{e}</p>
              ))}
              {status.errors.length > 10 && (
                <p className="text-xs text-red-500 italic">… and {status.errors.length - 10} more</p>
              )}
            </div>
          )}

          {/* Expandable failed images list from file */}
          {showFailed && failedImages?.failed?.length > 0 && (
            <div className="mt-3 border-t border-red-200 pt-3">
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-red-700 border-b border-red-200">
                      <th className="pb-1.5 font-semibold">Image</th>
                      <th className="pb-1.5 font-semibold">Error Type</th>
                      <th className="pb-1.5 font-semibold">Error Detail</th>
                      <th className="pb-1.5 font-semibold text-center">Retries</th>
                      <th className="pb-1.5 font-semibold">Last Failed</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-red-100">
                    {failedImages.failed.map((f, i) => {
                      const errLower = (f.error || '').toLowerCase();
                      const errType = errLower.includes('402') || errLower.includes('budget')
                        ? { label: '💳 Budget', cls: 'bg-red-200 text-red-800' }
                        : errLower.includes('403') || errLower.includes('forbidden')
                        ? { label: '🔒 Forbidden', cls: 'bg-orange-200 text-orange-800' }
                        : errLower.includes('429') || errLower.includes('rate')
                        ? { label: '⏱️ Rate Limit', cls: 'bg-amber-200 text-amber-800' }
                        : errLower.includes('timeout')
                        ? { label: '⏰ Timeout', cls: 'bg-yellow-200 text-yellow-800' }
                        : errLower.includes('500') || errLower.includes('502') || errLower.includes('503')
                        ? { label: '🔥 Server', cls: 'bg-pink-200 text-pink-800' }
                        : { label: '⚠️ Other', cls: 'bg-gray-200 text-gray-700' };
                      return (
                        <tr key={i} className="text-red-800">
                          <td className="py-1.5 font-mono font-medium truncate max-w-[160px]" title={f.image}>{f.image}</td>
                          <td className="py-1.5">
                            <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full ${errType.cls}`}>
                              {errType.label}
                            </span>
                          </td>
                          <td className="py-1.5 text-red-600 truncate max-w-[220px]" title={f.error}>{f.error}</td>
                          <td className="py-1.5 text-center">
                            <span className="px-1.5 py-0.5 bg-red-200 text-red-800 rounded-full text-[10px] font-bold">
                              {f.retry_count || 1}
                            </span>
                          </td>
                          <td className="py-1.5 text-red-500">
                            {f.failed_at ? new Date(f.failed_at).toLocaleString() : '—'}
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
      )}

      {/* ─── Summary Stats ─────────────────────── */}
      {summary.total_images > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard label="Total Classified" value={summary.total_images} icon="📊" />
          <StatCard label="Agreement Rate" value={`${summary.agreement_rate}%`}
            sub={`${summary.total_agreements} / ${summary.total_categories} categories`} icon="🤝" />
          <StatCard label="Arbiter Called" value={summary.total_arbiter_calls}
            sub={`for ${summary.total_categories - summary.total_agreements} disagreements`} icon="⚖️" />
          <StatCard label="Categories" value={CATEGORIES.length} sub="per image" icon="📋" />
          <StatCard label="Failed" value={failedCount}
            sub={failedCount > 0
              ? (apiErrorSummary?.dominant_type === 'budget_exceeded' ? '💳 API budget issue'
                : apiErrorSummary?.dominant_type === 'forbidden' ? '🔒 API access issue'
                : apiErrorSummary?.dominant_type === 'rate_limited' ? '⏱️ rate limited'
                : 'can retry ↑')
              : 'none'}
            icon={failedCount > 0 ? '❌' : '✅'} />
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

      {/* ─── Prediction Tracking Table ────────── */}
      {summary.total_images > 0 && (
        <PredictionTrackingSection />
      )}

      {/* Empty state */}
      {(!results || results.total === 0) && !status?.is_running && (
        <div className="py-16 text-center">
          <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center">
            <span className="text-2xl">{apiErrorSummary ? '🚨' : '⚖️'}</span>
          </div>
          {apiErrorSummary ? (
            <>
              <p className="text-lg font-medium text-red-700">All images failed due to API errors</p>
              <p className="text-sm text-red-500 mt-1">
                {apiErrorSummary.dominant_type === 'budget_exceeded'
                  ? 'The Turing API has no remaining budget. Please top up credits before running again.'
                  : apiErrorSummary.dominant_type === 'forbidden'
                  ? 'API access is forbidden. Check your API keys and authorization.'
                  : 'Resolve the API errors shown above, then retry.'}
              </p>
              <p className="text-xs text-gray-400 mt-3">
                No predictions were stored — there are no misleading "None" results.
              </p>
            </>
          ) : (
            <>
              <p className="text-lg font-medium text-gray-700">No classification results yet</p>
              <p className="text-sm text-gray-500 mt-1">Click "Run Classifier" to classify the final pipeline images.</p>
            </>
          )}
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
/* Prediction Tracking Section                                  */
/* ───────────────────────────────────────────────────────────── */

function PredictionTrackingSection() {
  const [tracking, setTracking] = useState(null);
  const [trackingLoading, setTrackingLoading] = useState(true);
  const [trackingPage, setTrackingPage] = useState(1);
  const [trackingFilter, setTrackingFilter] = useState(null); // matched | mismatched | corrected | pending
  const [trackingCategory, setTrackingCategory] = useState(null);
  const [trackingSearch, setTrackingSearch] = useState('');
  const [expandedRow, setExpandedRow] = useState(null);
  const TRACKING_PAGE_SIZE = 15;

  const fetchTracking = async () => {
    try {
      const params = { page: trackingPage, page_size: TRACKING_PAGE_SIZE };
      if (trackingFilter) params.filter_status = trackingFilter;
      if (trackingCategory) params.category = trackingCategory;
      if (trackingSearch) params.search = trackingSearch;
      const res = await api.get('/admin/arbiter/prediction-tracking', { params });
      setTracking(res.data);
    } catch (e) {
      console.error('Failed to fetch prediction tracking', e);
    } finally {
      setTrackingLoading(false);
    }
  };

  useEffect(() => {
    fetchTracking();
  }, [trackingPage, trackingFilter, trackingCategory, trackingSearch]);

  const tSummary = tracking?.summary || {};
  const rows = tracking?.rows || [];

  const STATUS_BADGE = {
    matched: { bg: 'bg-green-100 text-green-700 border-green-200', icon: '✅', label: 'Matched' },
    mismatched: { bg: 'bg-red-100 text-red-700 border-red-200', icon: '❌', label: 'Mismatched' },
    corrected: { bg: 'bg-amber-100 text-amber-700 border-amber-200', icon: '✏️', label: 'Corrected' },
    pending: { bg: 'bg-gray-100 text-gray-500 border-gray-200', icon: '⏳', label: 'Pending' },
  };

  const CELL_STATUS = {
    matched: 'bg-green-50 text-green-700 border-green-200',
    mismatched: 'bg-red-50 text-red-700 border-red-200',
    pending: 'bg-gray-50 text-gray-400 border-gray-200',
  };

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            📋 Prediction Tracking
            <span className="text-sm font-normal text-gray-500">AI Predictions vs Annotator Decisions</span>
          </h2>
        </div>
        <button onClick={fetchTracking} className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 transition cursor-pointer">
          🔄 Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-white rounded-xl border border-gray-200 p-3">
          <p className="text-[11px] text-gray-400 font-medium">AI Predicted</p>
          <p className="text-xl font-bold text-gray-900">{tSummary.total_predicted || 0}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-3">
          <p className="text-[11px] text-gray-400 font-medium">Annotator Reviewed</p>
          <p className="text-xl font-bold text-gray-900">{tSummary.total_annotated || 0}</p>
        </div>
        <div className="bg-white rounded-xl border border-green-200 p-3">
          <p className="text-[11px] text-green-600 font-medium">✅ Matched</p>
          <p className="text-xl font-bold text-green-700">{tSummary.total_matched || 0}</p>
        </div>
        <div className="bg-white rounded-xl border border-red-200 p-3">
          <p className="text-[11px] text-red-500 font-medium">❌ Corrected</p>
          <p className="text-xl font-bold text-red-700">{tSummary.total_mismatched || 0}</p>
        </div>
        <div className="bg-white rounded-xl border border-indigo-200 p-3">
          <p className="text-[11px] text-indigo-500 font-medium">🎯 Match Rate</p>
          <p className="text-xl font-bold text-indigo-700">{tSummary.match_rate || 0}%</p>
        </div>
      </div>

      {/* Per-category accuracy bars */}
      {tSummary.per_category && Object.keys(tSummary.per_category).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Per-Category Accuracy</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {CATEGORIES.map(cat => {
              const stats = tSummary.per_category[cat] || {};
              const total = (stats.matched || 0) + (stats.mismatched || 0);
              const pct = total > 0 ? Math.round((stats.matched / total) * 100) : 0;
              const isActive = trackingCategory === cat;
              return (
                <div key={cat}
                  onClick={() => { setTrackingCategory(isActive ? null : cat); setTrackingPage(1); }}
                  className={`rounded-lg border p-2.5 cursor-pointer transition-all ${
                    isActive ? 'border-indigo-400 ring-2 ring-indigo-200 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'
                  }`}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-medium text-gray-700">{CATEGORY_ICONS[cat]} {formatLabel(cat)}</span>
                    <span className={`text-xs font-bold ${
                      pct >= 80 ? 'text-green-600' : pct >= 50 ? 'text-amber-600' : total === 0 ? 'text-gray-400' : 'text-red-600'
                    }`}>{total > 0 ? `${pct}%` : '—'}</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-1.5">
                    <div className={`h-1.5 rounded-full transition-all ${
                      pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'
                    }`} style={{ width: `${pct}%` }} />
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                    <span>{stats.matched || 0} matched</span>
                    <span>{stats.mismatched || 0} corrected</span>
                    <span>{stats.pending || 0} pending</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Filters + search */}
      <div className="flex flex-wrap items-center gap-2">
        {[null, 'matched', 'corrected', 'pending'].map(f => (
          <button key={f || 'all'}
            onClick={() => { setTrackingFilter(f); setTrackingPage(1); }}
            className={`px-3 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer ${
              trackingFilter === f
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
            }`}>
            {f === null ? 'All' : f === 'matched' ? '✅ Matched' : f === 'corrected' ? '✏️ Corrected' : '⏳ Pending'}
          </button>
        ))}
        <div className="flex-1" />
        <input
          type="text"
          placeholder="Search by filename…"
          value={trackingSearch}
          onChange={e => { setTrackingSearch(e.target.value); setTrackingPage(1); }}
          className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg w-48 focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
        />
      </div>

      {/* Table */}
      {trackingLoading ? (
        <div className="py-8 text-center text-gray-400">Loading tracking data…</div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center text-gray-400">
          {tSummary.total_predicted > 0
            ? 'No results match the current filter.'
            : 'No predictions imported yet. Run the classifier and import labels first.'}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left font-semibold text-gray-600 w-[180px]">Image</th>
                  {CATEGORIES.map(cat => (
                    <th key={cat} className="px-2 py-3 text-center font-semibold text-gray-600 text-xs">
                      {CATEGORY_ICONS[cat]}<br/>{formatLabel(cat)}
                    </th>
                  ))}
                  <th className="px-3 py-3 text-center font-semibold text-gray-600">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((row) => {
                  const badge = STATUS_BADGE[row.overall_status] || STATUS_BADGE.pending;
                  const isExpanded = expandedRow === row.image_id;
                  return (
                    <Fragment key={row.image_id}>
                      <tr className="hover:bg-gray-50/50 transition-colors cursor-pointer"
                        onClick={() => setExpandedRow(isExpanded ? null : row.image_id)}>
                        <td className="px-4 py-2.5">
                          <span className="font-medium text-gray-900 truncate block max-w-[180px]" title={row.filename}>
                            {row.filename}
                          </span>
                        </td>
                        {CATEGORIES.map(cat => {
                          const catData = row.categories?.find(c => c.category_key === cat);
                          const cellStatus = catData?.status || 'pending';
                          const cellClass = CELL_STATUS[cellStatus] || CELL_STATUS.pending;
                          return (
                            <td key={cat} className="px-2 py-2.5 text-center">
                              {catData?.status === 'matched' ? (
                                <span className={`inline-block px-1.5 py-0.5 text-[10px] rounded border ${cellClass} font-medium`}>
                                  ✅ {formatLabel(catData.ai_prediction_short || '')}
                                </span>
                              ) : catData?.status === 'mismatched' ? (
                                <span className={`inline-block px-1.5 py-0.5 text-[10px] rounded border ${cellClass} font-medium`}>
                                  ✏️ {formatLabel(catData.human_label?.split(' ')[0] || '')}
                                </span>
                              ) : (
                                <span className="inline-block px-1.5 py-0.5 text-[10px] rounded border border-gray-200 text-gray-400">
                                  ⏳
                                </span>
                              )}
                            </td>
                          );
                        })}
                        <td className="px-3 py-2.5 text-center">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${badge.bg}`}>
                            {badge.icon} {row.matched_count}/{row.matched_count + row.mismatched_count + row.pending_count}
                          </span>
                        </td>
                      </tr>

                      {/* Expanded detail row */}
                      {isExpanded && (
                        <tr className="bg-indigo-50/30">
                          <td colSpan={CATEGORIES.length + 2} className="px-4 py-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {row.categories?.map((catData) => (
                                <div key={catData.category_key}
                                  className={`rounded-lg border p-3 text-sm ${
                                    catData.status === 'matched' ? 'border-green-200 bg-green-50/50' :
                                    catData.status === 'mismatched' ? 'border-red-200 bg-red-50/50' :
                                    'border-gray-200 bg-white'
                                  }`}>
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="font-semibold text-gray-700 text-xs">
                                      {CATEGORY_ICONS[catData.category_key]} {catData.category_name}
                                    </span>
                                    <span className={`px-1.5 py-0.5 text-[10px] rounded-full font-medium ${
                                      catData.status === 'matched' ? 'bg-green-100 text-green-700' :
                                      catData.status === 'mismatched' ? 'bg-red-100 text-red-700' :
                                      'bg-gray-100 text-gray-500'
                                    }`}>
                                      {catData.status === 'matched' ? '✅ Match' : catData.status === 'mismatched' ? '❌ Corrected' : '⏳ Pending'}
                                    </span>
                                  </div>
                                  <div className="space-y-1.5">
                                    <div className="flex items-center gap-2">
                                      <span className="text-[10px] text-gray-400 w-14 shrink-0">🤖 AI:</span>
                                      <span className="text-xs font-medium text-purple-700 bg-purple-50 px-2 py-0.5 rounded">
                                        {catData.ai_prediction || '—'}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className="text-[10px] text-gray-400 w-14 shrink-0">👤 Human:</span>
                                      {catData.human_label ? (
                                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                                          catData.status === 'matched'
                                            ? 'text-green-700 bg-green-50'
                                            : 'text-red-700 bg-red-50'
                                        }`}>
                                          {catData.human_label}
                                        </span>
                                      ) : (
                                        <span className="text-xs text-gray-400 italic">Not annotated yet</span>
                                      )}
                                    </div>
                                    {catData.annotator && (
                                      <p className="text-[10px] text-gray-400 mt-1">by {catData.annotator}</p>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {tracking.total > TRACKING_PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
              <span className="text-sm text-gray-500">
                Page {tracking.page} of {Math.ceil(tracking.total / TRACKING_PAGE_SIZE)} · {tracking.total} images
              </span>
              <div className="flex gap-2">
                <button disabled={trackingPage <= 1} onClick={() => setTrackingPage(p => p - 1)}
                  className="px-3 py-1 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 cursor-pointer">
                  ← Prev
                </button>
                <button disabled={trackingPage * TRACKING_PAGE_SIZE >= tracking.total} onClick={() => setTrackingPage(p => p + 1)}
                  className="px-3 py-1 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 cursor-pointer">
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
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
