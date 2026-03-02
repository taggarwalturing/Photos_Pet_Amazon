import { useState, useEffect } from 'react';
import api from '../api/client';

function PipelineStatistics() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  useEffect(() => {
    loadStats();
    // Poll for updates every 10 seconds
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, []);
  
  const loadStats = async () => {
    try {
      const response = await api.get('/admin/pipeline/stats');
      setStats(response.data);
      setLoading(false);
      setError(null);
    } catch (error) {
      console.error('Failed to load pipeline stats:', error);
      setError('Failed to load statistics');
      setLoading(false);
    }
  };
  
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
  
  return (
    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-900">Pipeline Statistics</h2>
        <button
          onClick={loadStats}
          className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
        >
          🔄 Refresh
        </button>
      </div>
      
      {/* Main Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {/* Total Images */}
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium mb-1">Total Images</div>
          <div className="text-3xl font-bold text-blue-900">{stats.total_images}</div>
        </div>
        
        {/* Processed */}
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium mb-1">Processed</div>
          <div className="text-3xl font-bold text-green-900">{stats.processed}</div>
          {stats.total_images > 0 && (
            <div className="text-xs text-green-600 mt-1">
              {((stats.processed / stats.total_images) * 100).toFixed(1)}%
            </div>
          )}
        </div>
        
        {/* Pending */}
        <div className="bg-yellow-50 rounded-lg p-4">
          <div className="text-sm text-yellow-600 font-medium mb-1">Pending</div>
          <div className="text-3xl font-bold text-yellow-900">{stats.pending}</div>
          {stats.total_images > 0 && (
            <div className="text-xs text-yellow-600 mt-1">
              {((stats.pending / stats.total_images) * 100).toFixed(1)}%
            </div>
          )}
        </div>
        
        {/* Failed */}
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
      
      {/* Deduplication Stats - Show if duplicates were found */}
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
      
      {/* Biometric Processing Stats - Show if processing was done */}
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

export default PipelineStatistics;
