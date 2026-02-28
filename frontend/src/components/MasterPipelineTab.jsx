import { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function MasterPipelineTab() {
  const [status, setStatus] = useState(null);
  const [errors, setErrors] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  
  // Pipeline options
  const [options, setOptions] = useState({
    download: false,
    deduplicate: false,
    biometric: true,
    use_llm: false,
    threshold: 0.85
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
      await axios.post(`${API_BASE}/api/admin/pipeline/start`, options, {
        headers: { Authorization: `Bearer ${token}` }
      });
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

  // Auto-refresh status when running
  useEffect(() => {
    fetchStatus();
    fetchErrors();
    fetchSummary();
    
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
                  <span className="text-sm font-medium text-gray-900">Download from Drive</span>
                  <p className="text-xs text-gray-500">Download images from Google Drive</p>
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
                  <p className="text-xs text-gray-500">Remove duplicate images using perceptual hashing</p>
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
              
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={options.use_llm}
                  onChange={(e) => setOptions({...options, use_llm: e.target.checked})}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-900">LLM Validation</span>
                  <p className="text-xs text-gray-500">Use AI to validate duplicate detection</p>
                </div>
              </label>

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

      {/* Current Status */}
      {status && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Pipeline Status</h2>
          
          <div className="space-y-4">
            {/* Download Step */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{getStepIcon(getStepStatus('download'))}</span>
                  <div>
                    <h3 className={`font-medium ${getStepColor(getStepStatus('download'))}`}>
                      Step 1: Download from Drive
                    </h3>
                    <p className="text-xs text-gray-500 capitalize">{status.progress?.download?.status || 'pending'}</p>
                  </div>
                </div>
                {status.progress?.download?.current > 0 && (
                  <span className="text-sm text-gray-600">
                    {status.progress.download.current} / {status.progress.download.total || '?'}
                  </span>
                )}
              </div>
              {status.progress?.download?.current > 0 && status.progress?.download?.total > 0 && (
                <div className="ml-11">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all"
                      style={{width: `${(status.progress.download.current / status.progress.download.total) * 100}%`}}
                    ></div>
                  </div>
                </div>
              )}
              {status.progress?.download?.message && (
                <p className="text-xs text-gray-600 ml-11">{status.progress.download.message}</p>
              )}
            </div>

            {/* Deduplicate Step */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{getStepIcon(getStepStatus('deduplicate'))}</span>
                  <div>
                    <h3 className={`font-medium ${getStepColor(getStepStatus('deduplicate'))}`}>
                      Step 2: Deduplicate Images
                    </h3>
                    <p className="text-xs text-gray-500 capitalize">{status.progress?.deduplicate?.status || 'pending'}</p>
                  </div>
                </div>
                {status.progress?.deduplicate?.current > 0 && (
                  <span className="text-sm text-gray-600">
                    {status.progress.deduplicate.current} / {status.progress.deduplicate.total || '?'}
                  </span>
                )}
              </div>
              {status.progress?.deduplicate?.current > 0 && status.progress?.deduplicate?.total > 0 && (
                <div className="ml-11">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-purple-600 h-2 rounded-full transition-all"
                      style={{width: `${(status.progress.deduplicate.current / status.progress.deduplicate.total) * 100}%`}}
                    ></div>
                  </div>
                </div>
              )}
              {status.progress?.deduplicate?.message && (
                <p className="text-xs text-gray-600 ml-11">{status.progress.deduplicate.message}</p>
              )}
            </div>

            {/* Biometric Step */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{getStepIcon(getStepStatus('biometric'))}</span>
                  <div>
                    <h3 className={`font-medium ${getStepColor(getStepStatus('biometric'))}`}>
                      Step 3: Biometric Compliance
                    </h3>
                    <p className="text-xs text-gray-500 capitalize">{status.progress?.biometric?.status || 'pending'}</p>
                  </div>
                </div>
                {status.progress?.biometric?.current > 0 && (
                  <span className="text-sm text-gray-600">
                    {status.progress.biometric.current} / {status.progress.biometric.total || '?'}
                  </span>
                )}
              </div>
              {status.progress?.biometric?.current > 0 && status.progress?.biometric?.total > 0 && (
                <div className="ml-11">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-green-600 h-2 rounded-full transition-all"
                      style={{width: `${(status.progress.biometric.current / status.progress.biometric.total) * 100}%`}}
                    ></div>
                  </div>
                </div>
              )}
              {status.progress?.biometric?.message && (
                <p className="text-xs text-gray-600 ml-11">{status.progress.biometric.message}</p>
              )}
            </div>
          </div>

          {status.current_step && (
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
                    <p className="text-xs text-blue-700">
                      Started: {new Date(status.started_at).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              </div>
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

      {/* Summary Statistics */}
      {summary && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Pipeline Statistics</h2>
          
          <div className="grid grid-cols-4 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-blue-600 font-medium">Total Images</p>
              <p className="text-2xl font-bold text-blue-900 mt-1">{summary.total_images || 0}</p>
            </div>
            
            <div className="p-4 bg-green-50 rounded-lg">
              <p className="text-sm text-green-600 font-medium">Processed</p>
              <p className="text-2xl font-bold text-green-900 mt-1">{summary.processed || 0}</p>
            </div>
            
            <div className="p-4 bg-yellow-50 rounded-lg">
              <p className="text-sm text-yellow-600 font-medium">Pending</p>
              <p className="text-2xl font-bold text-yellow-900 mt-1">{summary.pending || 0}</p>
            </div>
            
            <div className="p-4 bg-red-50 rounded-lg">
              <p className="text-sm text-red-600 font-medium">Failed</p>
              <p className="text-2xl font-bold text-red-900 mt-1">{summary.failed || 0}</p>
            </div>
          </div>
        </div>
      )}

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
