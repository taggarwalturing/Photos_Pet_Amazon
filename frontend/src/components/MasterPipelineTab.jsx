import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import api from '../api/client';
import PipelineStatistics from './PipelineStatistics';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001';

export default function MasterPipelineTab() {
  const [status, setStatus] = useState(null);
  const [errors, setErrors] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  
  // GCS folders (auto-discovered)
  const [folders, setFolders] = useState([]);
  const [unassignedCount, setUnassignedCount] = useState(0);
  
  // Per-folder force reprocess selection
  const [forceReprocessIds, setForceReprocessIds] = useState([]);
  
  // Pipeline options
  const [options, setOptions] = useState({
    download: true,
    deduplicate: true,
    biometric: true,
    use_llm: false,
    threshold: 0.85,
    source: 'gcs',
    force_reprocess: false, // kept for backend compat, not exposed in UI
  });

  // Fetch pipeline status
  const fetchStatus = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/api/admin/pipeline/status`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setStatus(response.data);
    } catch (error) {
      console.error('Failed to fetch status:', error);
    }
  };

  // Fetch errors
  const fetchErrors = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/api/admin/pipeline/errors`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setErrors(response.data.failed_images || []);
    } catch (error) {
      console.error('Failed to fetch errors:', error);
    }
  };

  // Fetch summary
  const fetchSummary = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/api/admin/pipeline/summary`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSummary(response.data);
    } catch (error) {
      console.error('Failed to fetch summary:', error);
    }
  };

  // Start pipeline
  const startPipeline = async () => {
    setStarting(true);
    try {
      const token = localStorage.getItem('token');
      const payload = { ...options };
      if (forceReprocessIds.length > 0 && !options.force_reprocess) {
        payload.force_reprocess_folder_ids = forceReprocessIds;
      }
      await axios.post(`${API_BASE}/api/admin/pipeline/start`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setForceReprocessIds([]);
      fetchStatus();
    } catch (error) {
      console.error('Failed to start pipeline:', error);
      alert(error.response?.data?.detail || 'Failed to start pipeline');
    } finally {
      setStarting(false);
    }
  };

  // Stop pipeline
  const stopPipeline = async () => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API_BASE}/api/admin/pipeline/stop`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchStatus();
    } catch (error) {
      console.error('Failed to stop pipeline:', error);
      alert(error.response?.data?.detail || 'Failed to stop pipeline');
    }
  };

  // Sync pipeline status from terminal run
  const syncPipelineStatus = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(`${API_BASE}/api/admin/pipeline/sync-status`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      alert(response.data.message || 'Pipeline status synced successfully!');
      fetchStatus();
      fetchSummary();
    } catch (error) {
      console.error('Failed to sync status:', error);
      alert(error.response?.data?.detail || 'Failed to sync pipeline status');
    } finally {
      setLoading(false);
    }
  };

  // Reprocess failed images
  const reprocessFailed = async () => {
    if (errors.length === 0) {
      alert('No failed images to reprocess');
      return;
    }
    
    const imageIds = errors.map(e => e.id);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API_BASE}/api/admin/pipeline/reprocess`, 
        { image_ids: imageIds },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert(`Reprocessing ${imageIds.length} images...`);
      fetchStatus();
      fetchErrors();
    } catch (error) {
      console.error('Failed to reprocess:', error);
      alert(error.response?.data?.detail || 'Failed to reprocess images');
    }
  };

  // ── Drive Folder Management ──
  const fetchFolders = useCallback(async () => {
    try {
      const res = await api.get('/admin/pipeline/folders');
      setFolders(res.data.folders || []);
      setUnassignedCount(res.data.unassigned_image_count || 0);
    } catch (e) { console.error('Failed to fetch folders:', e); }
  }, []);


  // Auto-refresh status when running
  useEffect(() => {
    fetchStatus();
    fetchErrors();
    fetchSummary();
    fetchFolders();
    
    const interval = setInterval(() => {
      fetchStatus();
      if (status?.is_running) {
        fetchErrors();
      }
    }, 3000); // Refresh every 3 seconds
    
    return () => clearInterval(interval);
  }, [status?.is_running]);

  const getStepStatus = (step) => {
    if (!status?.progress?.[step]) return 'pending';
    return status.progress[step].status;
  };

  const getStepIcon = (stepStatus) => {
    if (stepStatus === 'completed') return '✅';
    if (stepStatus === 'running') return '⏳';
    if (stepStatus === 'failed') return '❌';
    return '⭕';
  };

  const getStepColor = (stepStatus) => {
    if (stepStatus === 'completed') return 'text-green-600';
    if (stepStatus === 'running') return 'text-blue-600';
    if (stepStatus === 'failed') return 'text-red-600';
    return 'text-gray-400';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Master Pipeline Control</h1>
          <p className="text-sm text-gray-500 mt-1">Orchestrate image processing pipeline</p>
        </div>
        
        {status?.is_running ? (
          <button
            onClick={stopPipeline}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
            </svg>
            Stop Pipeline
          </button>
        ) : (
          <>
            <button
              onClick={startPipeline}
              disabled={starting}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center gap-2 disabled:opacity-50"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {starting ? 'Starting...' : 'Start Pipeline'}
            </button>
            
            <button
              onClick={syncPipelineStatus}
              disabled={loading}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition flex items-center gap-2 disabled:opacity-50"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11.418 5h-.581m0 0a8.001 8.001 0 01-15.357 2m15.357-2H15" />
              </svg>
              {loading ? 'Syncing...' : 'Sync Status from Terminal'}
            </button>
          </>
        )}
      </div>

      {/* Pipeline Options */}
      {!status?.is_running && (
        <>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <svg className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div className="flex-1">
                <h3 className="text-sm font-medium text-amber-900 mb-1">Development Mode Note</h3>
                <p className="text-xs text-amber-800">
                  The pipeline runs in the background. If the backend auto-reloads during execution (due to code changes), 
                  the pipeline will be interrupted. For production use, run the backend without --reload flag.
                </p>
              </div>
            </div>
          </div>
        
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Pipeline Options</h2>
          
          <div className="grid grid-cols-2 gap-4">
            {/* Step Selection */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-gray-700">Steps to Run:</h3>
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={options.download}
                  onChange={(e) => setOptions({...options, download: e.target.checked})}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">Sync from GCS</span>
                  <p className="text-xs text-gray-500">Pull images from GCS bucket to local workspace for processing</p>
                </div>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={options.deduplicate}
                  onChange={(e) => setOptions({...options, deduplicate: e.target.checked})}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">Deduplicate Images</span>
                  <p className="text-xs text-gray-500">Remove duplicates within each folder (no cross-folder comparison)</p>
                </div>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={options.biometric}
                  onChange={(e) => setOptions({...options, biometric: e.target.checked})}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">Biometric Compliance</span>
                  <p className="text-xs text-gray-500">Detect and obfuscate human faces</p>
                </div>
              </label>
            </div>

            {/* Advanced Options */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-gray-700">Advanced Options:</h3>
              
              <div>
                <label className="text-sm font-medium text-gray-900">
                  Similarity Threshold: {options.threshold}
                </label>
                <input
                  type="range"
                  min="0.7"
                  max="0.95"
                  step="0.05"
                  value={options.threshold}
                  onChange={(e) => setOptions({...options, threshold: parseFloat(e.target.value)})}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer mt-2"
                />
                <p className="text-xs text-gray-500 mt-1">Higher = more strict duplicate detection</p>
              </div>
            </div>
          </div>
        </div>
        </>
      )}

      {/* Skipped folders banner */}
      {status?.skipped_folders?.length > 0 && !status.is_running && (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <span className="text-lg">⏭️</span>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-gray-800">
                {status.skipped_folders.length} folder(s) skipped — already completed
              </h3>
              <p className="text-xs text-gray-500 mt-1">
                Use the <span className="font-medium">🔄 Reprocess</span> button in the folders table above to re-run specific folders.
              </p>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {status.skipped_folders.map(fid => (
                  <span key={fid} className="text-[10px] font-mono bg-gray-200 text-gray-600 px-2 py-0.5 rounded">
                    {fid.length > 16 ? `${fid.substring(0, 16)}…` : fid}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Current Status */}
      {status && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Pipeline Status</h2>
            {status.is_running && status.total_folders > 0 && (
              <span className="text-sm font-medium text-blue-700 bg-blue-50 px-3 py-1 rounded-full">
                Folder {status.current_folder_idx || 1} / {status.total_folders}
              </span>
            )}
          </div>

          {/* ── Overall current step indicator ── */}
          {status.is_running && status.current_step && status.current_step !== 'completed' && (
            <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-600 animate-spin flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <p className="text-sm font-medium text-blue-900">
                  {status.current_folder && (
                    <span className="font-mono text-xs bg-blue-100 px-1.5 py-0.5 rounded mr-2">{status.current_folder.substring(0, 12)}…</span>
                  )}
                  <span className="capitalize">{status.current_step}</span>
                </p>
                {status.started_at && (
                  <span className="text-xs text-blue-600 ml-auto">
                    Started {new Date(status.started_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* ── Per-folder progress ── */}
          {status.folder_progress && Object.keys(status.folder_progress).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(status.folder_progress).map(([folderId, fp], fIdx) => {
                const isActive = status.current_folder === folderId && status.is_running;
                const folderName = folders.find(f => f.folder_id === folderId)?.folder_name;
                const folderStatus = fp.status;
                const steps = fp.steps || {};

                return (
                  <div
                    key={folderId}
                    className={`rounded-lg border p-4 transition-all ${
                      isActive ? 'border-blue-400 bg-blue-50/50 shadow-sm' :
                      folderStatus === 'completed' ? 'border-green-200 bg-green-50/30' :
                      folderStatus === 'failed' ? 'border-red-200 bg-red-50/30' :
                      'border-gray-200 bg-gray-50/30'
                    }`}
                  >
                    {/* Folder header */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">
                          {folderStatus === 'completed' ? '✅' : folderStatus === 'failed' ? '❌' : isActive ? '⏳' : '⭕'}
                        </span>
                        <div>
                          <p className="text-sm font-semibold text-gray-800">
                            {folderName || `Folder ${fIdx + 1}`}
                          </p>
                          <p className="text-[10px] font-mono text-gray-400">{folderId}</p>
                  </div>
                </div>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${
                        folderStatus === 'completed' ? 'bg-green-100 text-green-700' :
                        folderStatus === 'failed' ? 'bg-red-100 text-red-700' :
                        folderStatus === 'running' ? 'bg-blue-100 text-blue-700' :
                        'bg-gray-100 text-gray-500'
                      }`}>
                        {folderStatus}
                      </span>
            </div>

                    {/* Steps within this folder */}
                    {(isActive || folderStatus === 'completed' || folderStatus === 'failed') && (
                      <div className="ml-7 space-y-1.5">
                        {[
                          { key: 'download', label: '☁️ Sync from GCS', textColor: 'text-blue-700', barColor: 'bg-blue-500' },
                          { key: 'deduplicate', label: '🔍 Deduplicate', textColor: 'text-purple-700', barColor: 'bg-purple-500' },
                          { key: 'biometric', label: '🔐 Biometric', textColor: 'text-green-700', barColor: 'bg-green-500' },
                        ].map(({ key, label, textColor, barColor }) => {
                          const s = steps[key] || {};
                          const pct = s.total > 0 ? Math.min(100, Math.round((s.current / s.total) * 100)) : 0;
                          return (
                            <div key={key}>
              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-xs">
                                    {s.status === 'completed' ? '✅' : s.status === 'running' ? '⏳' : '⭕'}
                                  </span>
                                  <span className={`text-xs font-medium ${
                                    s.status === 'completed' ? 'text-green-700' :
                                    s.status === 'running' ? textColor :
                                    'text-gray-400'
                                  }`}>
                                    {label}
                                  </span>
                  </div>
                                {s.current > 0 && (
                                  <span className="text-[10px] text-gray-500">
                                    {s.current}/{s.total} {pct > 0 && `(${pct}%)`}
                  </span>
                )}
              </div>
                              {s.status === 'running' && s.total > 0 && (
                                <div className="mt-0.5 ml-5 w-full bg-gray-200 rounded-full h-1.5">
                    <div 
                                    className={`${barColor} h-1.5 rounded-full transition-all`}
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                              )}
                              {s.status === 'running' && s.message && (
                                <p className="text-[10px] text-gray-500 ml-5 truncate mt-0.5">{s.message}</p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            /* Fallback: global-level progress (no folders) */
            <div className="space-y-4">
              {[
                { key: 'download', label: 'Step 1: Sync from GCS', barColor: 'bg-blue-600' },
                { key: 'deduplicate', label: 'Step 2: Deduplicate Images', barColor: 'bg-purple-600' },
                { key: 'biometric', label: 'Step 3: Biometric Compliance', barColor: 'bg-green-600' },
              ].map(({ key, label, barColor }) => {
                const stepStatus = getStepStatus(key);
                const s = status.progress?.[key] || {};
                const pct = s.total > 0 ? Math.min(100, Math.round((s.current / s.total) * 100)) : 0;
                return (
                  <div key={key} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                        <span className="text-2xl">{getStepIcon(stepStatus)}</span>
                  <div>
                          <h3 className={`font-medium ${getStepColor(stepStatus)}`}>{label}</h3>
                          <p className="text-xs text-gray-500 capitalize">{stepStatus}</p>
                  </div>
                </div>
                      {s.current > 0 && (
                        <span className="text-sm text-gray-600">{s.current} / {s.total || '?'}</span>
                )}
              </div>
                    {s.current > 0 && s.total > 0 && (
                <div className="ml-11">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                          <div className={`${barColor} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )}
                    {s.message && <p className="text-xs text-gray-600 ml-11">{s.message}</p>}
            </div>
                );
              })}

              {status.current_step && status.is_running && (
            <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-blue-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-blue-900">
                    Currently: <span className="capitalize">{status.current_step}</span>
                  </p>
                  {status.started_at && (
                        <p className="text-xs text-blue-700">Started: {new Date(status.started_at).toLocaleTimeString()}</p>
                  )}
                </div>
              </div>
                </div>
              )}
            </div>
          )}

          {/* Completed banner */}
          {!status.is_running && status.current_step === 'completed' && (
            <div className="mt-4 p-3 bg-green-50 rounded-lg border border-green-200">
              <p className="text-sm font-medium text-green-800">
                ✅ Pipeline completed successfully
                {status.completed_at && (
                  <span className="text-xs text-green-600 ml-2">at {new Date(status.completed_at).toLocaleTimeString()}</span>
                )}
              </p>
            </div>
          )}

          {status.errors && status.errors.length > 0 && (
            <div className="mt-4 p-3 bg-red-50 rounded-lg border border-red-200">
              <p className="text-sm font-medium text-red-800 mb-2">⚠️ Errors Encountered:</p>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {status.errors.map((error, idx) => (
                  <p key={idx} className="text-xs text-red-700 font-mono">{error}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── GCS Folders (auto-discovered) ── */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">📂 GCS Folders</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Folders are auto-discovered from the GCS bucket (<code className="bg-gray-100 px-1 rounded">input/</code> prefixes). Each folder is processed independently.
            </p>
          </div>
          <button
            onClick={() => { fetchFolders(); }}
            className="px-3 py-1.5 bg-gray-100 text-gray-600 text-sm rounded-lg hover:bg-gray-200 border border-gray-300 transition flex items-center gap-1.5"
            title="Refresh folder list"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        {/* Folders list */}
        {folders.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Name</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Folder ID</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Status</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">In GCS</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">In DB</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Blurred</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Clean</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Last Run</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Notes</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {folders.map(f => {
                  const isQueued = forceReprocessIds.includes(f.folder_id);
                  return (
                  <tr key={f.id} className={`hover:bg-gray-50 ${isQueued ? 'bg-amber-50/50' : f.status === 'completed' ? 'bg-green-50/30' : f.status === 'failed' ? 'bg-red-50/30' : ''}`}>
                    <td className="px-3 py-2 font-medium text-gray-900">{f.folder_name}</td>
                    <td className="px-3 py-2">
                      <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">{f.folder_id.slice(0, 20)}...</code>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        f.status === 'completed' ? 'bg-green-100 text-green-700' :
                        f.status === 'processing' || f.status === 'downloading' ? 'bg-blue-100 text-blue-700' :
                        f.status === 'failed' ? 'bg-red-100 text-red-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>
                        {f.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center text-gray-700">{f.total_in_drive || '—'}</td>
                    <td className="px-3 py-2 text-center font-medium text-gray-900">{f.total_in_db || 0}</td>
                    <td className="px-3 py-2 text-center text-blue-600">{f.blurred || 0}</td>
                    <td className="px-3 py-2 text-center text-green-600">{f.clean || 0}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">
                      {f.last_run_at ? new Date(f.last_run_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500 max-w-[180px]">
                      {f.error_log ? (
                        <span className="text-amber-600" title={f.error_log}>
                          {f.error_log.length > 40 ? f.error_log.slice(0, 40) + '…' : f.error_log}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {(f.status === 'completed' || f.status === 'failed') && (
                        <button
                          onClick={() => {
                            setForceReprocessIds(prev =>
                              prev.includes(f.folder_id)
                                ? prev.filter(id => id !== f.folder_id)
                                : [...prev, f.folder_id]
                            );
                          }}
                          className={`px-2 py-1 text-xs rounded font-medium transition ${
                            isQueued
                              ? 'bg-amber-100 text-amber-700 border border-amber-300'
                              : 'bg-gray-100 text-gray-600 hover:bg-amber-50 hover:text-amber-700 border border-gray-200'
                          }`}
                          title={isQueued ? 'Click to remove from reprocess queue' : 'Queue this folder for reprocessing'}
                        >
                          {isQueued ? '✓ Queued' : '🔄 Reprocess'}
                        </button>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            <p className="text-sm">No folders discovered yet.</p>
            <p className="text-xs mt-1">Upload images to <code className="bg-gray-100 px-1 rounded">input/{'<folder_id>'}/</code> in the GCS bucket, then run the pipeline.</p>
          </div>
        )}

        {unassignedCount > 0 && (
          <p className="mt-3 text-xs text-amber-600">
            ⚠️ {unassignedCount} image(s) in DB have no folder assignment (imported before folder tracking).
          </p>
        )}

        {forceReprocessIds.length > 0 && (
          <div className="mt-3 p-3 bg-amber-50 rounded-lg border border-amber-200 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-amber-800">
                🔄 {forceReprocessIds.length} folder{forceReprocessIds.length !== 1 ? 's' : ''} queued for reprocessing
              </p>
              <p className="text-xs text-amber-600 mt-0.5">
                {forceReprocessIds.map(id => folders.find(f => f.folder_id === id)?.folder_name || id.slice(0, 16) + '…').join(', ')}
              </p>
            </div>
            <button
              onClick={() => setForceReprocessIds([])}
              className="text-xs text-amber-600 hover:text-amber-800 underline"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Pipeline Statistics Component (includes per-folder tabular view) */}
      <PipelineStatistics />

      {/* Failed Images */}
      {errors.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Failed Images ({errors.length})
            </h2>
            <button
              onClick={reprocessFailed}
              className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition"
            >
              Reprocess All
            </button>
          </div>
          
          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-gray-700">Image</th>
                  <th className="px-4 py-2 text-left font-medium text-gray-700">Status</th>
                  <th className="px-4 py-2 text-left font-medium text-gray-700">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {errors.map((error, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-2">{error.filename}</td>
                    <td className="px-4 py-2">
                      <span className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs">
                        {error.compliance_status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-600">{error.processing_log || 'Unknown error'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
