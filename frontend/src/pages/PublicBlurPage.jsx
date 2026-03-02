import { useState, useRef, useCallback } from 'react';
import axios from 'axios';
import BoundingBoxCanvas from '../components/BoundingBoxCanvas';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function PublicBlurPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [boxes, setBoxes] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const imageContainerRef = useRef(null);
  const fileInputRef = useRef(null);

  const handleFile = useCallback((f) => {
    if (!f || !f.type.startsWith('image/')) {
      setError('Please select a valid image file.');
      return;
    }
    setError('');
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setBoxes([]);
    setDone(false);
  }, []);

  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  const handleApplyAndDownload = async () => {
    if (!file || !boxes.length) return;
    setProcessing(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('regions', JSON.stringify(boxes));

      const res = await axios.post(`${API_BASE}/api/public/blur`, form, {
        responseType: 'blob',
      });

      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `blurred_${file.name.replace(/\.[^.]+$/, '')}.jpg`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setDone(true);
    } catch (err) {
      setError('Failed to process image. Please try again.');
    } finally {
      setProcessing(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setPreview(null);
    setBoxes([]);
    setError('');
    setDone(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Image Blur Tool</h1>
            <p className="text-sm text-gray-500 mt-0.5">Draw regions to blur and download the result</p>
          </div>
          {file && (
            <button
              onClick={handleReset}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition cursor-pointer"
            >
              Start Over
            </button>
          )}
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {!file ? (
          /* Upload Area */
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-gray-300 hover:border-indigo-400 rounded-2xl p-16 text-center cursor-pointer transition-colors bg-white"
          >
            <div className="w-16 h-16 mx-auto mb-4 bg-indigo-50 rounded-2xl flex items-center justify-center">
              <svg className="w-8 h-8 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <p className="text-lg font-semibold text-gray-700 mb-1">Drop an image here or click to upload</p>
            <p className="text-sm text-gray-400">Supports JPEG, PNG, WebP</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
          </div>
        ) : (
          /* Drawing Area */
          <div className="space-y-4">
            {/* Instructions */}
            <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center shrink-0">
                  <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-800">
                    {boxes.length === 0
                      ? 'Draw bounding boxes on the image to mark regions for blurring'
                      : `${boxes.length} region${boxes.length > 1 ? 's' : ''} selected — click the X on a box to remove it`}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">Click and drag to create a rectangle. File: {file.name}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {boxes.length > 0 && (
                  <button
                    onClick={() => setBoxes([])}
                    className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition cursor-pointer"
                  >
                    Clear All
                  </button>
                )}
                <button
                  onClick={handleApplyAndDownload}
                  disabled={processing || boxes.length === 0}
                  className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {processing ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Processing...
                    </span>
                  ) : done ? (
                    'Download Again'
                  ) : (
                    'Apply Blur & Download'
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
            )}

            {done && (
              <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm font-medium">
                Blurred image downloaded successfully. You can draw more regions or start over.
              </div>
            )}

            {/* Image + Canvas */}
            <div className="bg-gray-900 rounded-xl p-4 flex items-center justify-center min-h-[400px]">
              <div ref={imageContainerRef} className="relative inline-block">
                <img
                  src={preview}
                  alt="Upload"
                  className="max-w-full max-h-[70vh] object-contain rounded-lg"
                  onLoad={() => {
                    // Force canvas resize after image loads
                    window.dispatchEvent(new Event('resize'));
                  }}
                />
                <BoundingBoxCanvas
                  containerRef={imageContainerRef}
                  boxes={boxes}
                  setBoxes={setBoxes}
                  disabled={processing}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
