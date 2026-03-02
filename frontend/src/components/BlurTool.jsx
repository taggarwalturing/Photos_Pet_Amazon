import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function BlurTool({ imageId, imageUrl, onBlurApplied }) {
  const [isActive, setIsActive] = useState(false);
  const [regions, setRegions] = useState([]);
  const [currentRegion, setCurrentRegion] = useState(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const originalImageData = useRef(null);

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

  const handleImageLoad = () => {
    const img = imageRef.current;
    const canvas = canvasRef.current;
    
    if (!img || !canvas) return;

    // Set canvas size to match image natural size (for quality)
    const maxWidth = 1200;
    const maxHeight = 800;
    let width = img.naturalWidth;
    let height = img.naturalHeight;
    
    // Scale down if too large
    if (width > maxWidth) {
      height = (maxWidth / width) * height;
      width = maxWidth;
    }
    if (height > maxHeight) {
      width = (maxHeight / height) * width;
      height = maxHeight;
    }
    
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, width, height);
    
    // Store original image data
    originalImageData.current = ctx.getImageData(0, 0, width, height);
    
    setImageLoaded(true);
    console.log('Image loaded successfully:', width, 'x', height);
  };

  const applyGaussianBlur = (pixels, width, height, x, y, w, h) => {
    const radius = 15;
    
    // Apply box blur multiple times for Gaussian-like effect
    for (let i = 0; i < 3; i++) {
      boxBlur(pixels, width, height, x, y, w, h, radius);
    }
  };

  const boxBlur = (pixels, width, height, x, y, w, h, radius) => {
    const tempPixels = new Uint8ClampedArray(pixels.length);
    tempPixels.set(pixels);

    for (let py = Math.max(0, y); py < Math.min(height, y + h); py++) {
      for (let px = Math.max(0, x); px < Math.min(width, x + w); px++) {
        let r = 0, g = 0, b = 0, count = 0;

        for (let dy = -radius; dy <= radius; dy++) {
          for (let dx = -radius; dx <= radius; dx++) {
            const nx = px + dx;
            const ny = py + dy;

            if (nx >= x && nx < x + w && ny >= y && ny < y + h &&
                nx >= 0 && nx < width && ny >= 0 && ny < height) {
              const idx = (ny * width + nx) * 4;
              r += tempPixels[idx];
              g += tempPixels[idx + 1];
              b += tempPixels[idx + 2];
              count++;
            }
          }
        }

        const idx = (py * width + px) * 4;
        pixels[idx] = r / count;
        pixels[idx + 1] = g / count;
        pixels[idx + 2] = b / count;
      }
    }
  };

  const redrawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas || !originalImageData.current) return;

    const ctx = canvas.getContext('2d');
    
    // Restore original image
    ctx.putImageData(originalImageData.current, 0, 0);
    
    // Get current image data to apply blurs
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const pixels = imageData.data;

    // Apply blur to each region
    [...regions, currentRegion].forEach((region, idx) => {
      if (!region) return;
      
      const normalized = {
        x: region.width < 0 ? region.x + region.width : region.x,
        y: region.height < 0 ? region.y + region.height : region.y,
        width: Math.abs(region.width),
        height: Math.abs(region.height)
      };

      if (normalized.width < 0.01 || normalized.height < 0.01) return;

      const x = Math.floor(normalized.x * canvas.width);
      const y = Math.floor(normalized.y * canvas.height);
      const w = Math.ceil(normalized.width * canvas.width);
      const h = Math.ceil(normalized.height * canvas.height);

      applyGaussianBlur(pixels, canvas.width, canvas.height, x, y, w, h);
    });

    // Put blurred image back
    ctx.putImageData(imageData, 0, 0);

    // Draw borders
    regions.forEach((region, idx) => {
      const x = region.x * canvas.width;
      const y = region.y * canvas.height;
      const w = region.width * canvas.width;
      const h = region.height * canvas.height;

      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, w, h);

      // Region number
      ctx.fillStyle = '#ef4444';
      ctx.font = 'bold 16px Arial';
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 4;
      ctx.strokeText(`#${idx + 1}`, x + 8, y + 24);
      ctx.fillText(`#${idx + 1}`, x + 8, y + 24);
    });

    // Draw current region
    if (currentRegion && Math.abs(currentRegion.width) > 0.01 && Math.abs(currentRegion.height) > 0.01) {
      const normalized = {
        x: currentRegion.width < 0 ? currentRegion.x + currentRegion.width : currentRegion.x,
        y: currentRegion.height < 0 ? currentRegion.y + currentRegion.height : currentRegion.y,
        width: Math.abs(currentRegion.width),
        height: Math.abs(currentRegion.height)
      };

      const x = normalized.x * canvas.width;
      const y = normalized.y * canvas.height;
      const w = normalized.width * canvas.width;
      const h = normalized.height * canvas.height;

      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 3;
      ctx.setLineDash([10, 5]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
    }
  };

  useEffect(() => {
    if (imageLoaded) {
      redrawCanvas();
    }
  }, [regions, currentRegion, imageLoaded]);

  const handleMouseDown = (e) => {
    if (!canvasRef.current) return;

    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;

    setIsDrawing(true);
    setCurrentRegion({ x, y, width: 0, height: 0 });
  };

  const handleMouseMove = (e) => {
    if (!isDrawing || !currentRegion || !canvasRef.current) return;

    const rect = canvasRef.current.getBoundingClientRect();
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

    if (Math.abs(currentRegion.width) > 0.01 && Math.abs(currentRegion.height) > 0.01) {
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
      await axios.post(`${API_BASE}/api/annotator/blur/apply/${imageId}`, {
        regions: regions
      });

      alert('✅ Blur applied successfully!');
      setIsActive(false);
      setRegions([]);
      setImageLoaded(false);
      
      if (onBlurApplied) {
        onBlurApplied();
      }
    } catch (error) {
      console.error('Failed to apply blur:', error);
      alert('❌ Failed to apply blur: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="blur-tool">
      <button
        onClick={() => setIsActive(!isActive)}
        className={`w-full px-4 py-2 rounded-lg font-medium transition ${
          isActive
            ? 'bg-red-500 text-white hover:bg-red-600'
            : 'bg-blue-500 text-white hover:bg-blue-600'
        }`}
      >
        {isActive ? '✕ Cancel Blur Tool' : '🎨 Manual Blur Tool'}
      </button>

      {isActive && (
        <div className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-7xl w-full max-h-[95vh] overflow-hidden flex flex-col">
            <div className="p-4 border-b flex items-center justify-between bg-gradient-to-r from-blue-50 to-indigo-50">
              <div>
                <h3 className="text-xl font-bold text-gray-900">🎨 Manual Blur Tool</h3>
                <p className="text-sm text-gray-600 mt-1">Draw rectangles to blur sensitive areas - see blur in real-time!</p>
              </div>
              <button
                onClick={() => {
                  setIsActive(false);
                  setRegions([]);
                  setImageLoaded(false);
                }}
                className="text-gray-500 hover:text-gray-700 p-2 hover:bg-gray-100 rounded-lg transition"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6 bg-gray-50">
              <div className="flex justify-center">
                <div className="relative inline-block">
                  <img
                    ref={imageRef}
                    src={imageUrl}
                    alt="Source"
                    onLoad={handleImageLoad}
                    className="hidden"
                    crossOrigin="anonymous"
                  />
                  <canvas
                    ref={canvasRef}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={() => isDrawing && handleMouseUp()}
                    className="max-w-full h-auto border-4 border-gray-300 rounded-lg shadow-xl cursor-crosshair bg-white"
                    style={{ maxHeight: '70vh' }}
                  />
                </div>
              </div>
            </div>

            <div className="p-4 border-t bg-gray-50">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm">
                  <span className="font-bold text-lg text-gray-900">{regions.length}</span>
                  <span className="text-gray-600 ml-1">region(s) selected</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setRegions(regions.slice(0, -1))}
                    disabled={regions.length === 0}
                    className="px-4 py-2 text-sm bg-white border-2 border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition"
                  >
                    ↶ Undo Last
                  </button>
                  <button
                    onClick={() => setRegions([])}
                    disabled={regions.length === 0}
                    className="px-4 py-2 text-sm bg-white border-2 border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition"
                  >
                    🗑️ Clear All
                  </button>
                </div>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setIsActive(false);
                    setRegions([]);
                    setImageLoaded(false);
                  }}
                  className="flex-1 px-6 py-3 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleApplyBlur}
                  disabled={regions.length === 0 || loading}
                  className="flex-1 px-6 py-3 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-lg hover:from-blue-600 hover:to-indigo-700 font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition shadow-lg"
                >
                  {loading ? '⏳ Applying Blur...' : `✓ Apply Blur to ${regions.length} Region${regions.length !== 1 ? 's' : ''}`}
                </button>
              </div>

              <p className="text-xs text-gray-500 mt-3 text-center italic">
                💡 Click and drag to draw blur rectangles. The blur effect is calculated in real-time!
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
