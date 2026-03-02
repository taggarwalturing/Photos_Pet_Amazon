import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function BlurTool({ imageId, imageUrl, onBlurApplied }) {
  const [isActive, setIsActive] = useState(false);
  const [regions, setRegions] = useState([]);
  const [currentRegion, setCurrentRegion] = useState(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [loading, setLoading] = useState(false);
  
  const canvasRef = useRef(null);
  const imageRef = useRef(null);

  // Load existing blur regions when tool is activated
  useEffect(() => {
    if (isActive && imageId) {
      loadExistingRegions();
    }
  }, [isActive, imageId]);

  const loadExistingRegions = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/annotator/blur/${imageId}/regions`);
      if (response.data.regions && response.data.regions.length > 0) {
        setRegions(response.data.regions);
      }
    } catch (error) {
      console.error('Failed to load blur regions:', error);
    }
  };

  const handleImageLoad = () => {
    if (imageRef.current && canvasRef.current) {
      const { naturalWidth, naturalHeight } = imageRef.current;
      setImageSize({ width: naturalWidth, height: naturalHeight });
      
      // Set canvas size to match image display size
      const canvas = canvasRef.current;
      const rect = imageRef.current.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
      
      redrawRegions();
    }
  };

  const redrawRegions = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw all existing regions
    regions.forEach((region, index) => {
      const x = region.x * canvas.width;
      const y = region.y * canvas.width;
      const w = region.width * canvas.width;
      const h = region.height * canvas.height;

      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);
      
      ctx.fillStyle = 'rgba(239, 68, 68, 0.1)';
      ctx.fillRect(x, y, w, h);
      
      // Draw region number
      ctx.fillStyle = '#ef4444';
      ctx.font = '12px Arial';
      ctx.fillText(`#${index + 1}`, x + 5, y + 15);
    });

    // Draw current region being drawn
    if (currentRegion) {
      const x = currentRegion.x * canvas.width;
      const y = currentRegion.y * canvas.height;
      const w = currentRegion.width * canvas.width;
      const h = currentRegion.height * canvas.height;

      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
      
      ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
      ctx.fillRect(x, y, w, h);
    }
  };

  useEffect(() => {
    redrawRegions();
  }, [regions, currentRegion]);

  const handleMouseDown = (e) => {
    if (!isActive) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;

    setIsDrawing(true);
    setCurrentRegion({ x, y, width: 0, height: 0 });
  };

  const handleMouseMove = (e) => {
    if (!isDrawing || !currentRegion) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const currentX = (e.clientX - rect.left) / rect.width;
    const currentY = (e.clientY - rect.top) / rect.height;

    setCurrentRegion({
      ...currentRegion,
      width: currentX - currentRegion.x,
      height: currentY - currentRegion.y
    });
  };

  const handleMouseUp = () => {
    if (!isDrawing || !currentRegion) return;

    // Only add if region has meaningful size
    if (Math.abs(currentRegion.width) > 0.01 && Math.abs(currentRegion.height) > 0.01) {
      // Normalize negative dimensions
      const normalized = {
        x: currentRegion.width < 0 ? currentRegion.x + currentRegion.width : currentRegion.x,
        y: currentRegion.height < 0 ? currentRegion.y + currentRegion.height : currentRegion.y,
        width: Math.abs(currentRegion.width),
        height: Math.abs(currentRegion.height)
      };
      
      setRegions([...regions, normalized]);
    }

    setIsDrawing(false);
    setCurrentRegion(null);
  };

  const handleApplyBlur = async () => {
    if (regions.length === 0) {
      alert('Please draw at least one region to blur');
      return;
    }

    setLoading(true);
    try {
      await axios.post(`${API_BASE}/api/annotator/blur/apply`, {
        image_id: imageId,
        regions: regions
      });

      alert('Blur applied successfully!');
      setIsActive(false);
      setRegions([]);
      
      if (onBlurApplied) {
        onBlurApplied();
      }
    } catch (error) {
      console.error('Failed to apply blur:', error);
      alert('Failed to apply blur: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveLastRegion = () => {
    setRegions(regions.slice(0, -1));
  };

  const handleClearAllRegions = () => {
    setRegions([]);
  };

  return (
    <div className="blur-tool">
      {/* Toggle Button */}
      <button
        onClick={() => setIsActive(!isActive)}
        className={`px-4 py-2 rounded-lg font-medium transition ${
          isActive
            ? 'bg-red-500 text-white hover:bg-red-600'
            : 'bg-blue-500 text-white hover:bg-blue-600'
        }`}
      >
        {isActive ? '✕ Cancel Blur Tool' : '🎨 Blur Tool'}
      </button>

      {/* Blur Tool Active Overlay */}
      {isActive && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center">
          <div className="bg-white rounded-lg shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col m-4">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-gray-50">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Manual Blur Tool</h3>
                <p className="text-sm text-gray-600">Draw rectangles over areas to blur</p>
              </div>
              <button
                onClick={() => setIsActive(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Image Canvas Area */}
            <div className="flex-1 overflow-auto p-4 bg-gray-100">
              <div className="relative inline-block">
                <img
                  ref={imageRef}
                  src={imageUrl}
                  alt="Image to blur"
                  onLoad={handleImageLoad}
                  className="max-w-full h-auto"
                  crossOrigin="anonymous"
                />
                <canvas
                  ref={canvasRef}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={() => {
                    if (isDrawing) handleMouseUp();
                  }}
                  className="absolute top-0 left-0 cursor-crosshair"
                  style={{ width: '100%', height: '100%' }}
                />
              </div>
            </div>

            {/* Controls */}
            <div className="p-4 border-t bg-gray-50">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm text-gray-700">
                  <span className="font-semibold">{regions.length}</span> region(s) selected
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleRemoveLastRegion}
                    disabled={regions.length === 0}
                    className="px-3 py-1.5 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    ↶ Undo Last
                  </button>
                  <button
                    onClick={handleClearAllRegions}
                    disabled={regions.length === 0}
                    className="px-3 py-1.5 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    🗑️ Clear All
                  </button>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setIsActive(false)}
                  className="flex-1 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApplyBlur}
                  disabled={regions.length === 0 || loading}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Applying...' : `✓ Apply Blur (${regions.length} regions)`}
                </button>
              </div>

              <p className="text-xs text-gray-500 mt-3 text-center">
                💡 Tip: Click and drag to draw rectangles over faces or sensitive areas
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
