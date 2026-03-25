import { useState, useEffect, useMemo } from 'react';
import api from '../api/client';
import { getThumbUrl } from '../hooks/useSignedUrl';

const CATEGORIES = ['lighting', 'viewpoint', 'environment', 'occlusion', 'activity', 'multipet'];
const CATEGORY_ICONS = {
  lighting: '💡', viewpoint: '📷', environment: '🏠',
  occlusion: '🚧', activity: '🏃', multipet: '🐾',
};
const CATEGORY_NAMES = {
  lighting: 'Lighting', viewpoint: 'Viewpoint', environment: 'Environment',
  occlusion: 'Occlusion', activity: 'Activity', multipet: 'Multi-Pet',
};

function ProgressRing({ pct, size = 64, color = '#6366f1' }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e5e7eb" strokeWidth={5} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={5}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-700" />
    </svg>
  );
}

export default function ValidationTab() {
  const [stats, setStats] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  // Config state
  const [scope, setScope] = useState('all');
  const [selectedFolders, setSelectedFolders] = useState([]);
  const [selectedAnnotator, setSelectedAnnotator] = useState('');
  const [revalidate, setRevalidate] = useState(false);

  // Results filter
  const [resultFilter, setResultFilter] = useState('all'); // all, aligned, misaligned
  const [expandedRow, setExpandedRow] = useState(null);

  // Fetch stats on mount
  useEffect(() => {
    fetchStats();
    fetchStatus();
  }, []);

  // Poll status while running
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [running]);

  const fetchStats = async () => {
    try {
      const res = await api.get('/api/admin/validation/stats');
      setStats(res.data);
    } catch (e) {
      console.error('Failed to fetch validation stats:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchStatus = async () => {
    try {
      const res = await api.get('/api/admin/validation/status');
      setStatus(res.data);
      setRunning(res.data.is_running);
    } catch (e) {
      console.error('Failed to fetch validation status:', e);
    }
  };

  const startValidation = async () => {
    const payload = { scope, revalidate };
    if (scope === 'folder') payload.folder_ids = selectedFolders;
    if (scope === 'annotator') payload.annotator_id = parseInt(selectedAnnotator);

    try {
      await api.post('/api/admin/validation/run', payload);
      setRunning(true);
      fetchStatus();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to start validation');
    }
  };

  const stopValidation = async () => {
    try {
      await api.post('/api/admin/validation/stop');
    } catch (e) {
      console.error('Failed to stop:', e);
    }
  };

  const clearResults = async () => {
    try {
      await api.post('/api/admin/validation/clear');
      setStatus(null);
    } catch (e) {
      console.error('Failed to clear:', e);
    }
  };

  // Filtered results
  const filteredResults = useMemo(() => {
    if (!status?.results) return [];
    if (resultFilter === 'aligned') return status.results.filter(r => r.aligned);
    if (resultFilter === 'misaligned') return status.results.filter(r => !r.aligned);
    return status.results;
  }, [status?.results, resultFilter]);

  const summary = status?.summary || {};
  const hasResults = status?.results?.length > 0;
  const progressPct = status?.total > 0 ? Math.round((status.processed / status.total) * 100) : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Annotation Validation</h2>
          <p className="text-sm text-gray-500 mt-1">
            Verify human annotations against Gemini VLM analysis
          </p>
        </div>
        {hasResults && !running && (
          <button onClick={clearResults}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition cursor-pointer">
            Clear Results
          </button>
        )}
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">📝</div>
            <p className="text-2xl font-bold text-gray-900">{stats.total_annotated}</p>
            <p className="text-xs text-gray-500 font-medium">Total Annotated</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <div className="w-8 h-8 bg-gradient-to-br from-green-500 to-emerald-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">✅</div>
            <p className="text-2xl font-bold text-green-600">{stats.total_approved}</p>
            <p className="text-xs text-gray-500 font-medium">Approved</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <div className="w-8 h-8 bg-gradient-to-br from-amber-500 to-orange-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">⏳</div>
            <p className="text-2xl font-bold text-amber-600">{stats.total_pending_review}</p>
            <p className="text-xs text-gray-500 font-medium">Pending Review</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <div className="w-8 h-8 bg-gradient-to-br from-purple-500 to-violet-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">🔍</div>
            <p className="text-2xl font-bold text-purple-600">{stats.total_validated || 0}</p>
            <p className="text-xs text-gray-500 font-medium">Already Validated</p>
          </div>
        </div>
      )}

      {/* Configuration Panel */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Validation Configuration</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* Scope */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Scope</label>
            <select value={scope} onChange={e => setScope(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
              <option value="all">All Annotated</option>
              <option value="folder">By Folder</option>
              <option value="annotator">By Annotator</option>
            </select>
          </div>

          {/* Folder selector */}
          {scope === 'folder' && stats?.folders && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Folders</label>
              <select multiple value={selectedFolders}
                onChange={e => setSelectedFolders(Array.from(e.target.selectedOptions, o => o.value))}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 h-20">
                {stats.folders.map(f => (
                  <option key={f.folder_id} value={f.folder_id}>
                    {f.folder_name} ({f.annotated_count})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Annotator selector */}
          {scope === 'annotator' && stats?.annotators && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Annotator</label>
              <select value={selectedAnnotator} onChange={e => setSelectedAnnotator(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500">
                <option value="">Select annotator</option>
                {stats.annotators.map(a => (
                  <option key={a.id} value={a.id}>{a.username} ({a.count})</option>
                ))}
              </select>
            </div>
          )}

          {/* Action button */}
          <div className="flex flex-col items-start justify-end gap-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={revalidate} onChange={e => setRevalidate(e.target.checked)}
                className="rounded border-gray-300 text-indigo-500 focus:ring-indigo-500" />
              <span className="text-xs text-gray-600">Re-validate already validated</span>
            </label>
            {running ? (
              <button onClick={stopValidation}
                className="w-full px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition cursor-pointer">
                ⬛ Stop
              </button>
            ) : (
              <button onClick={startValidation}
                disabled={scope === 'annotator' && !selectedAnnotator}
                className="w-full px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 rounded-lg transition cursor-pointer disabled:opacity-50">
                🔍 Run Validation
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      {running && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="flex items-center gap-4">
            <ProgressRing pct={progressPct} size={56} />
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-900">
                  Validating... {status?.processed || 0} / {status?.total || 0}
                </span>
                <span className="text-sm font-bold text-indigo-600">{progressPct}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${progressPct}%` }} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary Cards */}
      {hasResults && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-gray-900">{summary.total_validated}</p>
            <p className="text-xs text-gray-500 font-medium">Total Validated</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm cursor-pointer hover:border-green-300 transition"
            onClick={() => setResultFilter('aligned')}>
            <p className="text-2xl font-bold text-green-600">{summary.aligned}</p>
            <p className="text-xs text-gray-500 font-medium">✅ Aligned</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm cursor-pointer hover:border-red-300 transition"
            onClick={() => setResultFilter('misaligned')}>
            <p className="text-2xl font-bold text-red-600">{summary.misaligned}</p>
            <p className="text-xs text-gray-500 font-medium">❌ Misaligned</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-indigo-600">{summary.accuracy_pct}%</p>
            <p className="text-xs text-gray-500 font-medium">Accuracy</p>
          </div>
        </div>
      )}

      {/* Category-wise Contradiction Breakdown */}
      {hasResults && summary.misaligned > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Contradictions by Category</h3>
          <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
            {CATEGORIES.map(cat => {
              const count = summary.category_contradictions?.[cat] || 0;
              return (
                <div key={cat} className={`p-3 rounded-lg border text-center ${count > 0 ? 'border-red-200 bg-red-50' : 'border-gray-100 bg-gray-50'}`}>
                  <span className="text-lg">{CATEGORY_ICONS[cat]}</span>
                  <p className={`text-lg font-bold mt-1 ${count > 0 ? 'text-red-600' : 'text-gray-400'}`}>{count}</p>
                  <p className="text-[10px] text-gray-500 font-medium">{CATEGORY_NAMES[cat]}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Filter bar */}
      {hasResults && (
        <div className="flex items-center gap-2">
          {['all', 'aligned', 'misaligned'].map(f => (
            <button key={f} onClick={() => setResultFilter(f)}
              className={`px-4 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer capitalize ${
                resultFilter === f
                  ? (f === 'misaligned' ? 'bg-red-500 text-white border-red-500' : f === 'aligned' ? 'bg-green-500 text-white border-green-500' : 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white border-indigo-500')
                  : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
              }`}>
              {f === 'all' ? `All (${status?.results?.length || 0})` :
               f === 'aligned' ? `✅ Aligned (${summary.aligned || 0})` :
               `❌ Misaligned (${summary.misaligned || 0})`}
            </button>
          ))}
        </div>
      )}

      {/* Results Table */}
      {hasResults && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-12">#</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Image</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Filename</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Annotator</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  {CATEGORIES.map(cat => (
                    <th key={cat} className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      {CATEGORY_ICONS[cat]}
                    </th>
                  ))}
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredResults.map((row, idx) => {
                  const isExpanded = expandedRow === row.image_id;
                  const catDetails = row.category_details || {};
                  const contradictionKeys = new Set((row.contradictions || []).map(c => c.category_key));

                  return (
                    <>
                      <tr key={row.image_id}
                        className={`hover:bg-gray-50 cursor-pointer transition ${!row.aligned ? 'bg-red-50/30' : ''}`}
                        onClick={() => setExpandedRow(isExpanded ? null : row.image_id)}>
                        <td className="px-4 py-3 text-gray-400 font-mono text-xs">{idx + 1}</td>
                        <td className="px-4 py-3">
                          <img src={getThumbUrl(row.image_id)} alt=""
                            className="w-10 h-10 rounded-lg object-cover border border-gray-200"
                            onError={e => { e.target.style.display = 'none'; }} />
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-xs font-mono text-gray-700 truncate block max-w-[200px]" title={row.filename}>
                            {row.filename}
                          </span>
                          <span className="text-[10px] text-gray-400">{row.source_folder_id?.slice(0, 12)}...</span>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-600">{row.annotator}</td>
                        <td className="px-4 py-3 text-center">
                          {row.aligned ? (
                            <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-semibold rounded-full bg-green-100 text-green-700 border border-green-200">
                              ✅ Aligned
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-semibold rounded-full bg-red-100 text-red-700 border border-red-200">
                              ❌ Misaligned
                            </span>
                          )}
                        </td>
                        {CATEGORIES.map(cat => {
                          const catData = catDetails[cat];
                          const isContradiction = contradictionKeys.has(cat);
                          return (
                            <td key={cat} className="px-4 py-3 text-center">
                              {catData ? (
                                <span className={`inline-block w-5 h-5 rounded-full text-xs leading-5 ${
                                  isContradiction ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'
                                }`}>
                                  {isContradiction ? '✗' : '✓'}
                                </span>
                              ) : (
                                <span className="text-gray-300">—</span>
                              )}
                            </td>
                          );
                        })}
                        <td className="px-4 py-3 text-center">
                          <span className={`text-xs font-bold ${row.contradictions?.length > 0 ? 'text-red-600' : 'text-green-600'}`}>
                            {row.contradictions?.length || 0}
                          </span>
                        </td>
                      </tr>

                      {/* Expanded row with contradiction details */}
                      {isExpanded && row.contradictions?.length > 0 && (
                        <tr key={`${row.image_id}-detail`} className="bg-red-50/50">
                          <td colSpan={6 + CATEGORIES.length + 1} className="px-6 py-4">
                            <div className="space-y-3">
                              <h4 className="text-xs font-semibold text-red-700 uppercase tracking-wider">Contradiction Details</h4>
                              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {row.contradictions.map((c, ci) => (
                                  <div key={ci} className="bg-white rounded-lg border border-red-200 p-3 shadow-sm">
                                    <div className="flex items-center gap-2 mb-2">
                                      <span className="text-sm">{CATEGORY_ICONS[c.category_key] || '📋'}</span>
                                      <span className="text-xs font-semibold text-gray-900">{c.category}</span>
                                    </div>
                                    <div className="space-y-1">
                                      <div className="flex items-start gap-2">
                                        <span className="text-[10px] font-medium text-red-500 whitespace-nowrap mt-0.5">Human:</span>
                                        <span className="text-xs text-gray-700">{c.human_label || '—'}</span>
                                      </div>
                                      <div className="flex items-start gap-2">
                                        <span className="text-[10px] font-medium text-blue-500 whitespace-nowrap mt-0.5">VLM:</span>
                                        <span className="text-xs text-gray-700">{c.vlm_suggestion || '—'}</span>
                                      </div>
                                      {c.reason && (
                                        <p className="text-[10px] text-gray-500 mt-1 italic border-t border-gray-100 pt-1">
                                          {c.reason}
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}

                      {/* Expanded row - all categories details (when aligned or no contradictions) */}
                      {isExpanded && (!row.contradictions?.length) && (
                        <tr key={`${row.image_id}-detail`} className="bg-green-50/30">
                          <td colSpan={6 + CATEGORIES.length + 1} className="px-6 py-4">
                            <div className="space-y-2">
                              <h4 className="text-xs font-semibold text-green-700 uppercase tracking-wider">All Categories Aligned ✅</h4>
                              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                                {CATEGORIES.map(cat => {
                                  const d = catDetails[cat];
                                  return (
                                    <div key={cat} className="bg-white rounded-lg border border-green-100 p-2 text-center">
                                      <span className="text-sm">{CATEGORY_ICONS[cat]}</span>
                                      <p className="text-[10px] font-medium text-gray-700 mt-1">{d?.human_label || '—'}</p>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>

          {filteredResults.length === 0 && (
            <div className="text-center py-12 text-gray-400 text-sm">
              No results match the current filter.
            </div>
          )}
        </div>
      )}

      {/* Errors */}
      {status?.errors?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-red-700 uppercase tracking-wider mb-2">
            Errors ({status.errors.length})
          </h3>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {status.errors.map((err, i) => (
              <p key={i} className="text-xs text-red-600 font-mono">{err}</p>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!hasResults && !running && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <div className="text-4xl mb-3">🔍</div>
          <h3 className="text-sm font-semibold text-gray-900 mb-1">No Validation Results Yet</h3>
          <p className="text-xs text-gray-500">
            Configure the scope above and click "Run Validation" to verify human annotations using Gemini VLM.
          </p>
        </div>
      )}
    </div>
  );
}
