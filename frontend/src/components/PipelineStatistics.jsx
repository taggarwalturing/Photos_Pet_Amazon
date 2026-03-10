import { useState, useEffect, useCallback } from 'react';
import api from '../api/client';

function PipelineStatistics() {
  const [stats, setStats] = useState(null);
  const [folderStats, setFolderStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('folder'); // 'folder' | 'aggregate'
  
  const loadStats = useCallback(async () => {
    try {
      const [statsRes, folderRes] = await Promise.all([
        api.get('/admin/pipeline/stats'),
        api.get('/admin/pipeline/folders/stats-table').catch(() => ({ data: null })),
      ]);
      setStats(statsRes.data);
      setFolderStats(folderRes.data);
      setLoading(false);
      setError(null);
    } catch (err) {
      console.error('Failed to load pipeline stats:', err);
      setError('Failed to load statistics');
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, [loadStats]);
  
  if (loading && !stats) {
    return (
      <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-48 mb-4"></div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-24 bg-gray-100 rounded-lg"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
        <div className="text-red-600">{error}</div>
      </div>
    );
  }
  
  if (!stats) return null;

  const hasFolderData = folderStats?.table?.length > 0;
  
  return (
    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-900">Pipeline Statistics</h2>
        <div className="flex items-center gap-3">
          {hasFolderData && (
            <div className="flex bg-gray-100 rounded-lg p-0.5">
              <button
                onClick={() => setViewMode('folder')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                  viewMode === 'folder'
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📂 Per Folder
              </button>
              <button
                onClick={() => setViewMode('aggregate')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                  viewMode === 'aggregate'
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📊 Aggregate
              </button>
            </div>
          )}
          <button
            onClick={loadStats}
            className="px-3 py-1.5 bg-gray-100 text-gray-600 text-sm rounded-lg hover:bg-gray-200 border border-gray-300 transition flex items-center gap-1.5 font-medium"
            title="Refresh statistics"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* ── Per-Folder Tabular View ── */}
      {hasFolderData && viewMode === 'folder' && (
        <div className="mb-6">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-3 py-2.5 text-left font-semibold text-gray-700 sticky left-0 bg-gray-50">Folder</th>
                  <th className="px-3 py-2.5 text-center font-semibold text-sky-700 cursor-help">
                    <span title="Total image files found in GCS bucket (includes within-folder duplicate filenames)">☁️ GCS</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-gray-700 cursor-help">
                    <span title="Unique images imported into the database after download, deduplication, and biometric processing">📥 In DB</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-blue-700 cursor-help">
                    <span title="Images where the biometric pipeline detected human faces and automatically applied blur/obfuscation">🔵 Blurred</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-green-700 cursor-help">
                    <span title="Images with no human faces detected — no blur needed, ready for annotation as-is">🟢 Clean</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-red-700 cursor-help">
                    <span title="Images that failed during pipeline processing (download, dedup, or biometric errors)">🔴 Failed</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-orange-700 cursor-help">
                    <span title="Images flagged as improper by an annotator (not suitable for the task)">⚠️ Improper</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-purple-700 cursor-help">
                    <span title="Images where at least one human face was detected by the biometric pipeline">👤 Faces</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-indigo-700 cursor-help">
                    <span title="Images classified by the Arbiter AI pipeline (Gemini + GPT-4o + Arbiter) with predicted labels">🤖 AI</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-teal-700 cursor-help">
                    <span title="Images that have been annotated by at least one annotator with completed category labels">📝 Annotated</span>
                  </th>
                  <th className="px-3 py-2.5 text-center font-semibold text-emerald-700 cursor-help">
                    <span title="Images whose annotations have been reviewed and approved by an admin reviewer">✅ Approved</span>
                  </th>
                  <th className="px-3 py-2.5 text-left font-semibold text-gray-600">
                    <span title="Pipeline status and notes for this folder">Status / Notes</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {folderStats.table.map((row, idx) => {
                  const isUnassigned = !row.folder_id;
                  return (
                    <tr
                      key={idx}
                      className={`hover:bg-gray-50 transition ${isUnassigned ? 'bg-amber-50/40' : ''}`}
                    >
                      <td className="px-3 py-2.5 sticky left-0 bg-white">
                        <div className="flex items-center gap-1.5 max-w-[220px]">
                          <span className="font-medium text-gray-900 truncate" title={row.folder_id || 'No folder assigned'}>
                            {row.folder_name}
                          </span>
                          {isUnassigned && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-600 rounded-full whitespace-nowrap">
                              no folder
                            </span>
                          )}
                        </div>
                      </td>
                      <CellValue value={row.total_in_drive} color="sky" dash />
                      <CellValue value={row.total_in_db} color="gray" bold />
                      <CellValue value={row.blurred} color="blue" />
                      <CellValue value={row.clean} color="green" />
                      <CellValue value={row.failed} color="red" highlight />
                      <CellValue value={row.improper} color="orange" />
                      <CellValue value={row.with_faces} color="purple" />
                      <CellValue value={row.ai_classified} color="indigo" />
                      <CellValue value={row.annotated_images} color="teal" />
                      <CellValue value={row.approved_annotations} color="emerald" />
                      <td className="px-3 py-2.5 text-left">
                        <div className="flex items-center gap-1.5">
                          <span className={`inline-block w-2 h-2 rounded-full ${
                            row.status === 'completed' ? 'bg-green-500' :
                            row.status === 'failed' ? 'bg-red-500' :
                            row.status === 'processing' ? 'bg-blue-500 animate-pulse' :
                            'bg-gray-300'
                          }`}></span>
                          <span className={`text-xs font-medium ${
                            row.status === 'completed' ? 'text-green-700' :
                            row.status === 'failed' ? 'text-red-700' :
                            'text-gray-600'
                          }`}>
                            {row.status || 'pending'}
                          </span>
                        </div>
                        {row.notes && (
                          <p className="text-[10px] text-amber-600 mt-0.5 leading-tight max-w-[200px]" title={row.notes}>
                            {row.notes.length > 50 ? row.notes.slice(0, 50) + '…' : row.notes}
                          </p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {/* Totals Footer */}
              <tfoot>
                <tr className="bg-gray-100 font-semibold border-t-2 border-gray-300">
                  <td className="px-3 py-2.5 text-gray-800 sticky left-0 bg-gray-100">
                    Total ({folderStats.table.length} folder{folderStats.table.length !== 1 ? 's' : ''})
                  </td>
                  <td className="px-3 py-2.5 text-center text-sky-700">
                    {folderStats.totals?.total_in_drive || '—'}
                  </td>
                  <td className="px-3 py-2.5 text-center text-gray-900">
                    {folderStats.totals?.total || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-blue-700">
                    {folderStats.totals?.blurred || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-green-700">
                    {folderStats.totals?.clean || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-red-700">
                    {folderStats.totals?.failed || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-orange-700">
                    {folderStats.totals?.improper || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-purple-700">
                    {folderStats.totals?.with_faces || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-indigo-700">
                    {folderStats.totals?.ai_classified || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-teal-700">
                    {folderStats.totals?.annotated_images || 0}
                  </td>
                  <td className="px-3 py-2.5 text-center text-emerald-700">
                    {folderStats.totals?.approved || 0}
                  </td>
                  <td className="px-3 py-2.5"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}

      {/* ── Aggregate View (cards) ── */}
      {(viewMode === 'aggregate' || !hasFolderData) && (
        <>
          {/* GCS Source */}
          {stats.total_in_drive > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">☁️ GCS Source</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-sky-50 rounded-lg p-4">
                  <div className="text-sm text-sky-600 font-medium mb-1">Total in GCS</div>
                  <div className="text-2xl font-bold text-sky-900">{stats.total_in_drive}</div>
                  <div className="text-xs text-sky-600 mt-1">All files found in GCS bucket</div>
                </div>
                <div className="bg-blue-50 rounded-lg p-4">
                  <div className="text-sm text-blue-600 font-medium mb-1">Unique Filenames</div>
                  <div className="text-2xl font-bold text-blue-900">{stats.drive_unique_filenames}</div>
                  <div className="text-xs text-blue-600 mt-1">Downloaded to disk</div>
                </div>
                {stats.drive_duplicate_filenames > 0 && (
                  <div className="bg-amber-50 rounded-lg p-4">
                    <div className="text-sm text-amber-600 font-medium mb-1">Duplicate Filenames</div>
                    <div className="text-2xl font-bold text-amber-900">{stats.drive_duplicate_filenames}</div>
                    <details className="text-xs text-amber-600 mt-1 cursor-pointer">
                      <summary>Same name in different subfolders</summary>
                      <ul className="mt-1 space-y-0.5 pl-2 max-h-32 overflow-y-auto">
                        {Object.entries(stats.drive_duplicate_details || {}).map(([name, count]) => (
                          <li key={name} className="font-mono text-[10px]">{name} (×{count})</li>
                        ))}
                      </ul>
                    </details>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Main Stats Row */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="text-sm text-blue-600 font-medium mb-1">Total in Database</div>
              <div className="text-3xl font-bold text-blue-900">{stats.total_images}</div>
            </div>
            <div className="bg-green-50 rounded-lg p-4">
              <div className="text-sm text-green-600 font-medium mb-1">Processed</div>
              <div className="text-3xl font-bold text-green-900">{stats.processed}</div>
              {stats.total_images > 0 && (
                <div className="text-xs text-green-600 mt-1">
                  {((stats.processed / stats.total_images) * 100).toFixed(1)}%
                </div>
              )}
            </div>
            <div className="bg-yellow-50 rounded-lg p-4">
              <div className="text-sm text-yellow-600 font-medium mb-1">Pending</div>
              <div className="text-3xl font-bold text-yellow-900">{stats.pending}</div>
              {stats.total_images > 0 && (
                <div className="text-xs text-yellow-600 mt-1">
                  {((stats.pending / stats.total_images) * 100).toFixed(1)}%
                </div>
              )}
            </div>
            <div className="bg-red-50 rounded-lg p-4">
              <div className="text-sm text-red-600 font-medium mb-1">Failed</div>
              <div className="text-3xl font-bold text-red-900">{stats.failed}</div>
              {stats.failed > 0 && (
                <div className="text-xs text-red-600 mt-1">
                  {((stats.failed / stats.total_images) * 100).toFixed(1)}%
                </div>
              )}
            </div>
          </div>
          
          {/* Deduplication Stats */}
          {stats.duplicate_images > 0 && (
            <div className="border-t border-gray-200 pt-6 mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Deduplication Results</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-purple-50 rounded-lg p-4">
                  <div className="text-sm text-purple-600 font-medium mb-1">Unique Images</div>
                  <div className="text-2xl font-bold text-purple-900">{stats.unique_images}</div>
                  <div className="text-xs text-purple-600 mt-1">Kept for annotation</div>
                </div>
                <div className="bg-orange-50 rounded-lg p-4">
                  <div className="text-sm text-orange-600 font-medium mb-1">Duplicates Found</div>
                  <div className="text-2xl font-bold text-orange-900">{stats.duplicate_images}</div>
                  <div className="text-xs text-orange-600 mt-1">
                    Saved {stats.duplicate_images} × 1 hour = {stats.duplicate_images}h annotation time
                  </div>
                </div>
                <div className="bg-indigo-50 rounded-lg p-4">
                  <div className="text-sm text-indigo-600 font-medium mb-1">Duplicate Clusters</div>
                  <div className="text-2xl font-bold text-indigo-900">{stats.duplicate_clusters}</div>
                  <div className="text-xs text-indigo-600 mt-1">Similar image groups</div>
                </div>
              </div>
            </div>
          )}
          
          {/* Biometric Processing Stats */}
          {(stats.images_with_faces > 0 || stats.images_without_faces > 0) && (
            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Biometric Compliance</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-red-50 rounded-lg p-4">
                  <div className="text-sm text-red-600 font-medium mb-1">
                    🔐 Images with Faces (Blurred)
                  </div>
                  <div className="text-2xl font-bold text-red-900">{stats.images_with_faces}</div>
                  {stats.processed > 0 && (
                    <div className="text-xs text-red-600 mt-1">
                      {((stats.images_with_faces / stats.processed) * 100).toFixed(1)}% of processed
                    </div>
                  )}
                </div>
                <div className="bg-green-50 rounded-lg p-4">
                  <div className="text-sm text-green-600 font-medium mb-1">
                    ✅ Images without Faces
                  </div>
                  <div className="text-2xl font-bold text-green-900">{stats.images_without_faces}</div>
                  {stats.processed > 0 && (
                    <div className="text-xs text-green-600 mt-1">
                      {((stats.images_without_faces / stats.processed) * 100).toFixed(1)}% of processed
                    </div>
                  )}
                </div>
                {stats.screenshots_skipped > 0 && (
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="text-sm text-gray-600 font-medium mb-1">
                      ⏭️ Screenshots Skipped
                    </div>
                    <div className="text-2xl font-bold text-gray-900">{stats.screenshots_skipped}</div>
                    <div className="text-xs text-gray-600 mt-1">Detected as screenshots</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
      
      {/* Last Run Timestamp */}
      {stats.last_run && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <div className="text-xs text-gray-500">
            Last pipeline run: {new Date(stats.last_run).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Helper: table cell value ── */
function CellValue({ value, color, bold, dash, highlight }) {
  const v = value || 0;
  const colorClass = `text-${color}-600`;
  const boldClass = bold ? 'font-semibold' : '';
  const highlightClass = highlight && v > 0 ? `bg-${color}-50 rounded px-1` : '';
  
  return (
    <td className={`px-3 py-2.5 text-center ${colorClass} ${boldClass} ${highlightClass}`}>
      {dash && v === 0 ? '—' : v}
    </td>
  );
}

export default PipelineStatistics;
