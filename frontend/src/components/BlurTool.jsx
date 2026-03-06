import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001';

/**
 * BlurTool — simple rectangle drawing overlay.
 * User draws regions → backend applies actual blur → image reloads.
 * No canvas pixel manipulation — avoids all CORS / performance issues.
 */
export default function BlurTool({ imageId, imageUrl, onBlurApplied }) {
  const [isActive, setIsActive] = useState(false);
  const [regions, setRegions] = useState([]);
  const [currentRegion, setCurrentRegion] = useState(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState('');

  const containerRef = useRef(null);

  // Load existing blur regions when tool is activated
  useEffect(() => {
    if (isActive && imageId) {
      loadExistingRegions();
    }
  }, [isActive, imageId]);

  const loadExistingRegions = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/annotator/blur/${imageId}/regions`);
      if (response.data && response.data.length > 0) {
        setRegions(response.data);
      }
    } catch (error) {
      console.error('Failed to load blur regions:', error);
    }
  };

  // ── Mouse handlers (draw rectangles as % of image) ──

  const getRelativePos = (e) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
    };
  };

  const handleMouseDown = (e) => {
    e.preventDefault();
    const pos = getRelativePos(e);
    setIsDrawing(true);
    setCurrentRegion({ x: pos.x, y: pos.y, width: 0, height: 0 });
  };

  const handleMouseMove = (e) => {
    if (!isDrawing || !currentRegion) return;
    const pos = getRelativePos(e);
    setCurrentRegion(prev => ({
      ...prev,
      width: pos.x - prev.x,
      height: pos.y - prev.y,
    }));
  };

  const handleMouseUp = () => {
    if (!isDrawing || !currentRegion) return;
    if (Math.abs(currentRegion.width) > 0.01 && Math.abs(currentRegion.height) > 0.01) {
      // Normalize negative dimensions
      const normalized = {
        x: currentRegion.width < 0 ? currentRegion.x + currentRegion.width : currentRegion.x,
        y: currentRegion.height < 0 ? currentRegion.y + currentRegion.height : currentRegion.y,
        width: Math.abs(currentRegion.width),
        height: Math.abs(currentRegion.height),
      };
      setRegions(prev => [...prev, normalized]);
    }
    setIsDrawing(false);
    setCurrentRegion(null);
  };

  // ── Apply blur on backend ──

  const handleApplyBlur = async () => {
    if (regions.length === 0) return;
    setLoading(true);
    setProgress('Sending regions to server…');

    try {
      setProgress('Applying blur on server… this may take a moment');
      await axios.post(`${API_BASE}/api/annotator/blur/apply/${imageId}`, { regions });

      setProgress('Done! Reloading image…');

      // Small delay so user sees the "Done" message
      await new Promise(r => setTimeout(r, 600));

      setIsActive(false);
      setRegions([]);
      if (onBlurApplied) onBlurApplied();
    } catch (error) {
      console.error('Failed to apply blur:', error);
      alert('❌ Failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
      setProgress('');
    }
  };

  const handleClose = () => {
    setIsActive(false);
    setRegions([]);
    setCurrentRegion(null);
    setIsDrawing(false);
  };

  // Render a single rectangle overlay
  const renderRegion = (region, idx, isCurrent = false) => {
    if (!region) return null;
    const n = {
      x: region.width < 0 ? region.x + region.width : region.x,
      y: region.height < 0 ? region.y + region.height : region.y,
      width: Math.abs(region.width),
      height: Math.abs(region.height),
    };
    if (n.width < 0.005 || n.height < 0.005) return null;

    return (
      <div
        key={isCurrent ? 'current' : idx}
        className="absolute pointer-events-none"
        style={{
          left: `${n.x * 100}%`,
          top: `${n.y * 100}%`,
          width: `${n.width * 100}%`,
          height: `${n.height * 100}%`,
          border: isCurrent ? '2px dashed #3b82f6' : '2px solid #ef4444',
          backgroundColor: isCurrent ? 'rgba(59,130,246,0.15)' : 'rgba(239,68,68,0.12)',
          backdropFilter: isCurrent ? 'none' : 'blur(0px)', // visual hint
        }}
      >
        {!isCurrent && (
          <span className="absolute top-0.5 left-1 text-[10px] font-bold text-red-600 bg-white/80 px-1 rounded">
            #{idx + 1}
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="blur-tool">
      <button
        onClick={() => setIsActive(!isActive)}
        className={`w-full px-4 py-2 rounded-lg font-medium transition cursor-pointer ${
          isActive
            ? 'bg-red-500 text-white hover:bg-red-600'
            : 'bg-blue-500 text-white hover:bg-blue-600'
        }`}
      >
        {isActive ? '✕ Cancel Blur' : '🎨 Manual Blur Tool'}
      </button>

      {isActive && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[95vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="px-5 py-3 border-b flex items-center justify-between bg-gradient-to-r from-blue-50 to-indigo-50 shrink-0">
              <div>
                <h3 className="text-lg font-bold text-gray-900">🎨 Manual Blur Tool</h3>
                <p className="text-xs text-gray-500">
                  Draw rectangles over areas to blur. Backend will process the actual blurring.
                </p>
              </div>
              <button
                onClick={handleClose}
                disabled={loading}
                className="text-gray-400 hover:text-gray-600 p-1.5 hover:bg-white/60 rounded-lg transition cursor-pointer disabled:opacity-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Image + overlay area */}
            <div className="flex-1 min-h-0 overflow-auto bg-gray-100 flex items-center justify-center p-4">
              {loading ? (
                // Progress overlay
                <div className="text-center py-16">
                  <div className="relative mx-auto w-16 h-16 mb-4">
                    <div className="absolute inset-0 border-4 border-blue-200 rounded-full" />
                    <div className="absolute inset-0 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                  <p className="text-lg font-semibold text-gray-800 mb-1">Processing…</p>
                  <p className="text-sm text-gray-500">{progress}</p>
                </div>
              ) : (
                <div
                  ref={containerRef}
                  className="relative inline-block select-none"
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={() => isDrawing && handleMouseUp()}
                  style={{ cursor: 'crosshair' }}
                >
                  <img
                    src={imageUrl}
                    alt="Image to blur"
                    className="block max-w-full rounded-lg shadow-lg"
                    style={{ maxHeight: '70vh' }}
                    draggable={false}
                  />
                  {/* Saved region overlays */}
                  {regions.map((r, i) => renderRegion(r, i))}
                  {/* Current region being drawn */}
                  {renderRegion(currentRegion, -1, true)}
                </div>
              )}
            </div>

            {/* Footer controls */}
            {!loading && (
              <div className="px-5 py-3 border-t bg-gray-50 shrink-0">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm text-gray-700">
                    <span className="font-bold text-gray-900 text-base">{regions.length}</span>
                    {' '}region{regions.length !== 1 ? 's' : ''} marked
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setRegions(r => r.slice(0, -1))}
                      disabled={regions.length === 0}
                      className="px-3 py-1.5 text-xs bg-white border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed font-medium transition cursor-pointer"
                    >
                      ↶ Undo
                    </button>
                    <button
                      onClick={() => setRegions([])}
                      disabled={regions.length === 0}
                      className="px-3 py-1.5 text-xs bg-white border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed font-medium transition cursor-pointer"
                    >
                      Clear All
                    </button>
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleClose}
                    className="flex-1 h-10 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-semibold transition cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleApplyBlur}
                    disabled={regions.length === 0}
                    className="flex-[1.5] h-10 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-lg hover:from-blue-600 hover:to-indigo-700 font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition shadow-md cursor-pointer"
                  >
                    ✓ Apply Blur ({regions.length} region{regions.length !== 1 ? 's' : ''})
                  </button>
                </div>

                <p className="text-[11px] text-gray-400 mt-2 text-center">
                  Click &amp; drag to mark areas → Click "Apply" → Backend blurs the image
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
