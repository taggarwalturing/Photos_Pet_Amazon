import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';

// Helper to get proxied image URL for Google Drive images
const getImageUrl = (imageId) => {
  if (!imageId) return '';
  return `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/images/proxy/${imageId}`;
};

export default function AnnotationPage() {
  const { categoryId } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [task, setTask] = useState(null);
  const [selectedOptions, setSelectedOptions] = useState([]);
  const [isDuplicate, setIsDuplicate] = useState(null);
  const [queueIndex, setQueueIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [allDone, setAllDone] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const savingRef = useRef(false);

  const loadTask = useCallback(async (index) => {
    setLoading(true);
    setError('');
    setAllDone(false);
    try {
      const res = await api.get(`/annotator/categories/${categoryId}/task/${index}`);
      const data = res.data;
      setTask(data);
      setQueueIndex(index);
      // Restore previous selections and timer if any
      if (data.current_annotation) {
        setSelectedOptions(data.current_annotation.selected_option_ids || []);
        setIsDuplicate(data.current_annotation.is_duplicate);
        setElapsedSeconds(data.current_annotation.time_spent_seconds || 0);
      } else {
        setSelectedOptions([]);
        setIsDuplicate(null);
        setElapsedSeconds(0);
      }
    } catch (err) {
      if (err.response?.status === 404) {
        // Could be "all done" or "index out of range"
        const detail = err.response?.data?.detail || '';
        if (detail.includes('all completed') || detail.includes('No images')) {
          setAllDone(true);
        } else {
          setError(detail || 'No more images.');
        }
      } else {
        setError(err.response?.data?.detail || 'Failed to load task');
      }
    } finally {
      setLoading(false);
    }
  }, [categoryId]);

  useEffect(() => {
    // Resume from where the annotator left off
    api.get(`/annotator/categories/${categoryId}/resume-index`)
      .then((res) => loadTask(res.data.index))
      .catch(() => loadTask(0));
  }, [categoryId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Timer tick
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const toggleOption = (optionId) => {
    setSelectedOptions((prev) =>
      prev.includes(optionId) ? prev.filter((id) => id !== optionId) : [...prev, optionId]
    );
  };

  const saveAnnotation = async (status) => {
    if (!task || savingRef.current) return false;
    savingRef.current = true;
    setSaving(true);
    try {
      await api.put(`/annotator/categories/${categoryId}/images/${task.image_id}/annotate`, {
        selected_option_ids: selectedOptions,
        is_duplicate: isDuplicate,
        status,
        time_spent_seconds: elapsedSeconds,
      });
      return true;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save');
      return false;
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  };

  const handleNext = async () => {
    const ok = await saveAnnotation('completed');
    if (!ok) return;

    // The completed image stays in the queue (annotator touched it),
    // so advance to the next index.
    const nextIndex = queueIndex + 1;
    try {
      const res = await api.get(`/annotator/categories/${categoryId}/queue-size`);
      const newSize = res.data.queue_size;

      if (newSize === 0 || nextIndex >= newSize) {
        // Check if there are unannotated images left via resume-index
        const resumeRes = await api.get(`/annotator/categories/${categoryId}/resume-index`);
        if (resumeRes.data.queue_size === 0) {
          setAllDone(true);
          return;
        }
        // If all images in the queue are completed, we're done
        const resumeIdx = resumeRes.data.index;
        // Check if the resume image is already completed (meaning all are done)
        loadTask(resumeIdx);
        return;
      }

      loadTask(nextIndex);
    } catch {
      navigate('/annotator');
    }
  };

  const handleSkip = async () => {
    // Only save as "skipped" if the image is NOT already completed.
    // Otherwise just navigate without overwriting the completed annotation.
    const alreadyCompleted = task?.current_annotation?.status === 'completed';
    if (!alreadyCompleted) {
      const ok = await saveAnnotation('skipped');
      if (!ok) return;
    }

    // Move to next image
    if (queueIndex < task.total_images - 1) {
      loadTask(queueIndex + 1);
    } else {
      // Past the end — use resume-index to find next unannotated, or finish
      try {
        const res = await api.get(`/annotator/categories/${categoryId}/resume-index`);
        if (res.data.queue_size === 0) {
          setAllDone(true);
        } else {
          loadTask(res.data.index);
        }
      } catch {
        navigate('/annotator');
      }
    }
  };

  const handleBack = () => {
    if (queueIndex > 0) {
      loadTask(queueIndex - 1);
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (savingRef.current) return;
      if ((e.key === 'ArrowRight' || e.key === 'Enter') && selectedOptions.length > 0) {
        e.preventDefault();
        handleNext();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        handleBack();
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        handleSkip();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3 animate-fade-in">
          <div className="w-10 h-10 border-3 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
          <p className="text-sm text-gray-500 font-medium">Loading image...</p>
        </div>
      </div>
    );
  }

  if (allDone) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-gradient-to-b from-gray-50 to-gray-100/50 animate-fade-in">
        <div className="w-20 h-20 bg-green-50 rounded-2xl flex items-center justify-center ring-1 ring-green-200">
          <svg className="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900">All done!</h2>
          <p className="text-gray-500 mt-2 text-sm">Every image for this category has been annotated. Great work!</p>
        </div>
        <button
          onClick={() => navigate('/annotator')}
          className="mt-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition cursor-pointer text-sm font-semibold shadow-sm shadow-indigo-200"
        >
          &larr; Back to categories
        </button>
      </div>
    );
  }

  if (error && !task) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-50 animate-fade-in">
        <div className="w-16 h-16 bg-red-50 rounded-2xl flex items-center justify-center ring-1 ring-red-200">
          <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        </div>
        <p className="text-red-600 font-medium">{error}</p>
        <button onClick={() => navigate('/annotator')} className="text-indigo-600 hover:underline cursor-pointer text-sm font-medium">
          &larr; Back to categories
        </button>
      </div>
    );
  }

  const progress = task ? Math.round(((queueIndex + 1) / task.total_images) * 100) : 0;

  return (
    <div className="h-screen bg-gray-100 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b border-gray-200/80 sticky top-0 z-10 shadow-sm">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3.5">
            <button
              onClick={() => navigate('/annotator')}
              className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div className="w-px h-6 bg-gray-200" />
            <div>
              <h1 className="font-semibold text-gray-900 text-sm">{task?.category_name}</h1>
              <p className="text-xs text-gray-500">
                Image <span className="font-medium text-gray-700">{queueIndex + 1}</span> of {task?.total_images} &middot; {user?.username}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Timer */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
              elapsedSeconds >= 120
                ? 'bg-red-100 text-red-700'
                : elapsedSeconds >= 90
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-gray-100 text-gray-600'
            }`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {formatTime(elapsedSeconds)}
            </div>
            <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full">
              {progress}%
            </span>
            <button
              onClick={logout}
              className="text-sm text-gray-400 hover:text-gray-700 cursor-pointer"
            >
              <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
              </svg>
            </button>
          </div>
        </div>
        {/* Progress bar */}
        <div className="h-0.5 bg-gray-100">
          <div
            className="h-0.5 bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full px-3 py-2 min-h-0" style={{ height: 'calc(100vh - 54px)' }}>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-3 h-full">
          {/* Left: Image — fills all remaining space */}
          <div className="bg-gray-900 rounded-xl overflow-hidden relative min-h-0 ring-1 ring-gray-800">
            <img
              src={getImageUrl(task?.image_id)}
              alt={task?.image_filename}
              className="absolute inset-0 w-full h-full object-contain"
              loading="eager"
            />
          </div>

          {/* Right: Options form — fixed width sidebar */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5 flex flex-col overflow-y-auto min-h-0">
            <h2 className="text-base font-bold text-gray-900 mb-0.5">{task?.category_name}</h2>
            <p className="text-xs text-gray-500 mb-4">Select all that apply</p>

            {error && (
              <div className="bg-red-50 text-red-700 px-4 py-2 rounded-lg text-sm mb-4">
                {error}
              </div>
            )}

            {/* Options as pill-like checkboxes */}
            <div className="flex-1 space-y-2">
              {task?.options.map((opt) => {
                const isSelected = selectedOptions.includes(opt.id);
                return (
                  <label
                    key={opt.id}
                    className={`
                      flex items-center gap-3 px-4 py-2.5 rounded-xl border-2 cursor-pointer transition-all
                      ${isSelected
                        ? 'border-indigo-500 bg-indigo-50/80 text-indigo-900 shadow-sm shadow-indigo-100'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/50 bg-white text-gray-700'
                      }
                    `}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleOption(opt.id)}
                      className="sr-only"
                    />
                    <div
                      className={`
                        w-4.5 h-4.5 rounded flex items-center justify-center border-2 shrink-0 transition-all
                        ${isSelected ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300'}
                      `}
                    >
                      {isSelected && (
                        <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span className="text-sm font-medium">{opt.label}</span>
                    {opt.is_typical && (
                      <span className="ml-auto text-[10px] font-semibold bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full uppercase tracking-wide">
                        typical
                      </span>
                    )}
                  </label>
                );
              })}
            </div>

            {/* Is Duplicate */}
            <div className="mt-5 pt-4 border-t border-gray-100">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Is Duplicate?</p>
              <div className="flex gap-2">
                {[
                  { value: null, label: 'Not set', color: 'gray' },
                  { value: false, label: 'No', color: 'green' },
                  { value: true, label: 'Yes', color: 'red' },
                ].map((opt) => (
                  <button
                    key={String(opt.value)}
                    onClick={() => setIsDuplicate(opt.value)}
                    className={`
                      px-3.5 py-1.5 rounded-xl text-xs font-semibold border-2 transition-all cursor-pointer
                      ${isDuplicate === opt.value
                        ? opt.color === 'red'
                          ? 'border-red-400 bg-red-50 text-red-700'
                          : opt.color === 'green'
                            ? 'border-green-400 bg-green-50 text-green-700'
                            : 'border-gray-400 bg-gray-100 text-gray-700'
                        : 'border-gray-200 text-gray-400 hover:border-gray-300 hover:text-gray-600'
                      }
                    `}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Already annotated indicator */}
            {task?.current_annotation?.status === 'completed' && (
              <div className="mt-4 flex items-center gap-2 px-3 py-2.5 bg-green-50/80 border border-green-200 rounded-xl text-xs text-green-700 font-medium">
                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Already completed. Changes will update your annotation.
              </div>
            )}

            {/* Navigation buttons */}
            <div className="mt-5 pt-4 border-t border-gray-100 flex items-center gap-2.5">
              <button
                onClick={handleBack}
                disabled={queueIndex === 0 || saving}
                className="px-4 py-2.5 border border-gray-200 text-gray-600 rounded-xl hover:bg-gray-50 hover:border-gray-300 transition disabled:opacity-25 disabled:cursor-not-allowed cursor-pointer text-sm font-medium"
              >
                &larr;
              </button>
              <button
                onClick={handleSkip}
                disabled={saving}
                className="px-4 py-2.5 border border-amber-200 text-amber-700 bg-amber-50/50 rounded-xl hover:bg-amber-100 hover:border-amber-300 transition disabled:opacity-50 cursor-pointer text-sm font-medium"
              >
                Skip
              </button>
              <button
                onClick={handleNext}
                disabled={saving || selectedOptions.length === 0}
                className="flex-1 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-sm font-semibold shadow-sm shadow-indigo-200 hover:shadow-md hover:shadow-indigo-200"
              >
                {saving ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Saving...
                  </span>
                ) : 'Save & Next \u2192'}
              </button>
            </div>

            {/* Keyboard shortcut hints */}
            <div className="mt-2.5 flex items-center justify-center gap-4 text-[10px] text-gray-400">
              <span><kbd className="px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded text-gray-500 font-mono">&larr;</kbd> Back</span>
              <span><kbd className="px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded text-gray-500 font-mono">S</kbd> Skip</span>
              <span><kbd className="px-1.5 py-0.5 bg-gray-50 border border-gray-200 rounded text-gray-500 font-mono">&rarr;</kbd> Save</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
