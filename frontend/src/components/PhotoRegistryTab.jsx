import { useState, useEffect, useCallback } from 'react';
import api from '../api/client';

const FILTERS = [
  { key: 'all', label: 'All', icon: '📋' },
  { key: 'unique', label: 'Unique', icon: '✅' },
  { key: 'duplicate', label: 'Duplicates', icon: '📑' },
  { key: 'blurred', label: 'Pipeline Blurred', icon: '🔒' },
  { key: 'clean', label: 'Clean', icon: '🟢' },
  { key: 'manually_blurred', label: 'Manual Blur', icon: '✋' },
];

function StatCard({ icon, label, value, color, active, onClick, tooltip }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      title={tooltip || ''}
      className={`relative overflow-hidden p-4 rounded-xl border bg-white text-left transition-all shadow-sm hover:shadow-md ${
        onClick ? 'cursor-pointer' : ''
      } ${
        active ? 'ring-2 ring-offset-2 ' + color.ring : 'border-gray-200'
      }`}
    >
      <div className={`absolute top-0 right-0 w-16 h-16 ${color.bg} opacity-10 rounded-bl-[32px] -mr-1 -mt-1`} />
      <div className={`w-7 h-7 rounded-lg ${color.bg} flex items-center justify-center text-white text-xs mb-2 shadow-sm`}>
        {icon}
      </div>
      <p className="text-xl font-bold text-gray-900">{value}</p>
      <p className="text-[11px] text-gray-500 mt-0.5 font-medium">{label}</p>
    </Tag>
  );
}

function TruncatedPath({ path }) {
  if (!path) return <span className="text-gray-300">—</span>;
  // Show last 2 segments
  const parts = path.split('/');
  const short = parts.length > 2 ? '…/' + parts.slice(-2).join('/') : path;
  return (
    <span className="text-xs text-gray-600 font-mono" title={path}>
      {short}
    </span>
  );
}

export default function PhotoRegistryTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [filter, setFilter] = useState('all');
  const [perPage] = useState(50);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/photo-registry', {
        params: { page, per_page: perPage, search, status_filter: filter },
      });
      setData(res.data);
    } catch (err) {
      console.error('Failed to fetch photo registry:', err);
    }
    setLoading(false);
  }, [page, search, filter, perPage]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSearch = (e) => {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
  };

  const handleFilterChange = (f) => {
    setFilter(f);
    setPage(1);
  };

  const summary = data?.summary || {};

  const driveTotal = summary.total_in_drive || 0;
  const driveDupFilenames = summary.drive_duplicate_filenames || 0;
  const driveDupDetails = summary.drive_duplicate_details || {};

  const statCards = [
    { key: null, icon: '☁️', label: 'In Google Drive', value: driveTotal, color: { bg: 'bg-gradient-to-br from-sky-500 to-blue-600', ring: 'ring-sky-400' }, tooltip: driveDupFilenames > 0 ? `${driveDupFilenames} duplicate filenames in Drive` : '' },
    { key: 'all', icon: '📋', label: 'Downloaded (Unique Names)', value: summary.total_downloaded || 0, color: { bg: 'bg-gradient-to-br from-indigo-500 to-purple-500', ring: 'ring-indigo-400' } },
    { key: 'unique', icon: '✅', label: 'Unique', value: summary.total_unique || 0, color: { bg: 'bg-gradient-to-br from-emerald-500 to-teal-500', ring: 'ring-emerald-400' } },
    { key: 'duplicate', icon: '📑', label: 'Content Duplicates', value: summary.total_duplicate || 0, color: { bg: 'bg-gradient-to-br from-amber-500 to-orange-500', ring: 'ring-amber-400' } },
    { key: 'blurred', icon: '🔒', label: 'Pipeline Blurred', value: summary.total_pipeline_blurred || 0, color: { bg: 'bg-gradient-to-br from-red-500 to-rose-500', ring: 'ring-red-400' } },
    { key: 'manually_blurred', icon: '✋', label: 'Manual Blur', value: summary.total_manually_blurred || 0, color: { bg: 'bg-gradient-to-br from-violet-500 to-fuchsia-500', ring: 'ring-violet-400' } },
    { key: 'clean', icon: '🟢', label: 'Clean', value: summary.total_clean || 0, color: { bg: 'bg-gradient-to-br from-cyan-500 to-blue-500', ring: 'ring-cyan-400' } },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <svg className="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            Photo Registry
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Complete status of all downloaded photos — duplicates, paths, blur status
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition cursor-pointer disabled:opacity-50"
        >
          <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-7 gap-3">
        {statCards.map((s, idx) => (
          <StatCard
            key={s.key || `stat-${idx}`}
            icon={s.icon}
            label={s.label}
            value={s.value}
            color={s.color}
            active={s.key !== null && filter === s.key}
            onClick={s.key !== null ? () => handleFilterChange(s.key) : undefined}
            tooltip={s.tooltip}
          />
        ))}
      </div>

      {/* Drive Duplicate Filenames info */}
      {driveDupFilenames > 0 && (
        <details className="bg-sky-50 border border-sky-200 rounded-lg px-4 py-2 text-xs">
          <summary className="cursor-pointer text-sky-700 font-medium">
            ☁️ {driveDupFilenames} files in Google Drive have duplicate filenames (same name in different subfolders) — only one copy is downloaded
          </summary>
          <ul className="mt-2 space-y-0.5 text-sky-600 pl-4">
            {Object.entries(driveDupDetails).map(([name, count]) => (
              <li key={name}>• <span className="font-mono">{name}</span> — appears {count}× in Drive</li>
            ))}
          </ul>
        </details>
      )}

      {/* Search + Filter Bar */}
      <div className="flex items-center gap-3">
        <form onSubmit={handleSearch} className="flex-1 max-w-sm relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by filename…"
            className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
          />
        </form>

        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => handleFilterChange(f.key)}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md transition cursor-pointer ${
                filter === f.key
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <span className="text-[10px]">{f.icon}</span>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-8">#</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Filename</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Format</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Parent Image</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Original Path</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Processed Path</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Blur</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Manual Blur Path</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 9 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 bg-gray-100 rounded animate-pulse" style={{ width: `${60 + Math.random() * 40}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : data?.data?.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-gray-400">
                    No images found matching your criteria
                  </td>
                </tr>
              ) : (
                data?.data?.map((row, idx) => (
                  <tr key={row.filename} className="hover:bg-gray-50/50 transition">
                    {/* # */}
                    <td className="px-4 py-2.5 text-xs text-gray-400 font-mono">
                      {(page - 1) * perPage + idx + 1}
                    </td>

                    {/* Filename */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        {row.db_id && (
                          <img
                            src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/images/proxy/${row.db_id}?t=1`}
                            alt=""
                            className="w-8 h-8 rounded object-cover border border-gray-200 shrink-0"
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                        )}
                        <div className="min-w-0">
                          <span className="text-xs font-medium text-gray-800 truncate max-w-[200px] block" title={row.filename}>
                            {row.filename}
                          </span>
                          {row.heic_original && (
                            <span className="text-[9px] text-indigo-500 font-medium">
                              📷 from {row.heic_original}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Format */}
                    <td className="px-4 py-2.5">
                      {row.original_format ? (
                        <div className="flex flex-col gap-0.5">
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-indigo-100 text-indigo-700">
                            {row.original_format} → JPG
                          </span>
                          <span className="text-[9px] text-gray-400 font-mono truncate max-w-[140px]" title={row.original_filename}>
                            {row.original_filename}
                          </span>
                        </div>
                      ) : (
                        <span className="text-[10px] text-gray-400 font-medium">
                          {row.filename.split('.').pop().toUpperCase()}
                        </span>
                      )}
                    </td>

                    {/* Status */}
                    <td className="px-4 py-2.5">
                      {row.is_duplicate ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-700">
                          📑 Duplicate
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-700">
                          ✅ Unique
                        </span>
                      )}
                      {!row.in_database && (
                        <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-medium bg-gray-100 text-gray-500">
                          Not in DB
                        </span>
                      )}
                    </td>

                    {/* Parent Image */}
                    <td className="px-4 py-2.5">
                      {row.parent_image ? (
                        <span className="text-xs text-amber-700 font-mono truncate max-w-[160px] inline-block" title={row.parent_image}>
                          {row.parent_image}
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>

                    {/* Original Path */}
                    <td className="px-4 py-2.5">
                      <TruncatedPath path={row.original_path} />
                    </td>

                    {/* Processed Path */}
                    <td className="px-4 py-2.5">
                      <TruncatedPath path={row.processed_path} />
                    </td>

                    {/* Blur Status */}
                    <td className="px-4 py-2.5">
                      <div className="flex flex-col gap-0.5">
                        {row.pipeline_blurred && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-600">
                            🔒 Pipeline
                          </span>
                        )}
                        {row.manually_blurred && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-violet-50 text-violet-600">
                            ✋ Manual
                          </span>
                        )}
                        {!row.pipeline_blurred && !row.manually_blurred && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-50 text-green-600">
                            🟢 Clean
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Manual Blur Path */}
                    <td className="px-4 py-2.5">
                      <TruncatedPath path={row.annotated_blur_path} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50/50">
            <p className="text-xs text-gray-500">
              Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, data.total)} of {data.total} images
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-md hover:bg-gray-50 transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                ← Prev
              </button>
              {Array.from({ length: Math.min(data.total_pages, 7) }, (_, i) => {
                let pageNum;
                if (data.total_pages <= 7) {
                  pageNum = i + 1;
                } else if (page <= 4) {
                  pageNum = i + 1;
                } else if (page >= data.total_pages - 3) {
                  pageNum = data.total_pages - 6 + i;
                } else {
                  pageNum = page - 3 + i;
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`px-2.5 py-1.5 text-xs font-medium rounded-md transition cursor-pointer ${
                      page === pageNum
                        ? 'bg-indigo-500 text-white shadow-sm'
                        : 'text-gray-600 bg-white border border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
              <button
                onClick={() => setPage(p => Math.min(data.total_pages, p + 1))}
                disabled={page >= data.total_pages}
                className="px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-md hover:bg-gray-50 transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
