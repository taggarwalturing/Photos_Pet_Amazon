import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import BlurTool from '../components/BlurTool';
import SignedImage from '../components/SignedImage';
import { getProxyUrl } from '../hooks/useSignedUrl';

const getImageUrl = (imageId) => {
  if (!imageId) return '';
  return getProxyUrl(imageId);
};

export default function AnnotationPage() {
  const { categoryId } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [task, setTask] = useState(null);
  const [selectedOptions, setSelectedOptions] = useState([]);
  const [isDuplicate, setIsDuplicate] = useState(null);
  const [isAIGenerated, setIsAIGenerated] = useState(false); // default Real
  const [humanVisible, setHumanVisible] = useState(null); // null=Unknown, true=Visible, false=Not Visible
  const [queueIndex, setQueueIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [allDone, setAllDone] = useState(false);
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
      } else {
        setSelectedOptions([]);
        setIsDuplicate(null);
        setIsAIGenerated(false); // default Real
        setHumanVisible(null);
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
        is_ai_generated: isAIGenerated,
        human_visible: humanVisible,
        status,
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
    <div className="fixed inset-0 bg-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200/80 z-10 shadow-sm shrink-0">
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

      {/* Main Content - takes ALL remaining space */}
      <div className="flex-1 min-h-0 flex gap-3 px-3 py-2">
          {/* Left: Image — fills all remaining space */}
        <div className="flex-1 min-w-0 bg-gray-900 rounded-xl overflow-hidden relative ring-1 ring-gray-800">
            <img
              src={getImageUrl(task?.image_id)}
              alt={task?.image_filename}
              className="absolute inset-0 w-full h-full object-contain"
              loading="eager"
            />
          </div>

        {/* Right: Options form — fixed width sidebar, MUST NOT exceed parent height */}
        <div className="w-[380px] shrink-0 flex flex-col bg-white rounded-xl shadow-sm border border-gray-200/80 overflow-hidden">
          {/* Fixed Header Section */}
          <div className="px-4 py-3 shrink-0 border-b border-gray-100">
            <h2 className="text-sm font-bold text-gray-900">{task?.category_name}</h2>
            <p className="text-xs text-gray-500">Select all that apply</p>
          </div>

          {/* Scrollable Content Section - ONLY this section scrolls */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="p-4">
              {/* Blur Tool */}
              {task?.image_id && (
                <div className="mb-3">
                  <BlurTool 
                    imageId={task.image_id} 
                    imageUrl={getImageUrl(task.image_id)}
                    onBlurApplied={() => {
                      console.log('Blur applied successfully');
                    }}
                  />
                </div>
              )}

            {error && (
                <div className="bg-red-50 text-red-700 px-3 py-2 rounded-lg text-xs mb-3">
                {error}
              </div>
            )}

            {/* Options as pill-like checkboxes */}
              <div className="space-y-1.5">
              {task?.options.map((opt) => {
                const isSelected = selectedOptions.includes(opt.id);
                return (
                  <label
                    key={opt.id}
                    className={`
                        flex items-center gap-2.5 px-3 py-2 rounded-lg border-2 cursor-pointer transition-all
                      ${isSelected
                          ? 'border-indigo-500 bg-indigo-50/80 text-indigo-900'
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
                          w-4 h-4 rounded flex items-center justify-center border-2 shrink-0 transition-all
                        ${isSelected ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300'}
                      `}
                    >
                      {isSelected && (
                          <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                      <span className="text-xs font-medium">{opt.label}</span>
                    {opt.is_typical && (
                        <span className="ml-auto text-[9px] font-semibold bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full uppercase">
                        typical
                      </span>
                    )}
                  </label>
                );
              })}
              </div>
            </div>
            </div>

          {/* Fixed Footer Section - ALWAYS VISIBLE at bottom of sidebar */}
          <div className="shrink-0 border-t-2 border-gray-200 p-3 bg-gray-50">
            {/* Classification Toggles */}
            <div className="space-y-1.5 mb-2">
              {/* Row: Duplicate */}
              <div className="flex items-center">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider w-14 shrink-0">Dup</span>
                <div className="flex rounded-md overflow-hidden border border-gray-200 flex-1">
                {[
                    { value: null, label: '?', activeClass: 'bg-gray-500 text-white' },
                    { value: false, label: 'No', activeClass: 'bg-green-500 text-white' },
                    { value: true, label: 'Yes', activeClass: 'bg-red-500 text-white' },
                  ].map((opt, idx) => (
                  <button
                    key={String(opt.value)}
                    onClick={() => setIsDuplicate(opt.value)}
                      className={`flex-1 py-1 text-[10px] font-bold transition-all cursor-pointer
                        ${idx > 0 ? 'border-l border-gray-200' : ''}
                        ${isDuplicate === opt.value ? opt.activeClass : 'bg-white text-gray-400 hover:bg-gray-50'}
                      `}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Row: AI Detection */}
              <div className="flex items-center">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider w-14 shrink-0">AI</span>
                <div className="flex rounded-md overflow-hidden border border-gray-200 flex-1">
                  {[
                    { value: false, label: 'Real', activeClass: 'bg-green-500 text-white' },
                    { value: null, label: '?', activeClass: 'bg-gray-500 text-white' },
                    { value: true, label: 'AI', activeClass: 'bg-purple-500 text-white' },
                  ].map((opt, idx) => (
                    <button
                      key={String(opt.value)}
                      onClick={() => setIsAIGenerated(opt.value)}
                      className={`flex-1 py-1 text-[10px] font-bold transition-all cursor-pointer
                        ${idx > 0 ? 'border-l border-gray-200' : ''}
                        ${isAIGenerated === opt.value ? opt.activeClass : 'bg-white text-gray-400 hover:bg-gray-50'}
                    `}
                  >
                    {opt.label}
                  </button>
                ))}
                </div>
              </div>

              {/* Row: Human Visible */}
              <div className="flex items-center">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider w-14 shrink-0">Human</span>
                <div className="flex rounded-md overflow-hidden border border-gray-200 flex-1">
                  {[
                    { value: true, label: 'Visible', activeClass: 'bg-blue-500 text-white' },
                    { value: null, label: '?', activeClass: 'bg-gray-500 text-white' },
                    { value: false, label: 'Not Visible', activeClass: 'bg-orange-500 text-white' },
                  ].map((opt, idx) => (
                    <button
                      key={String(opt.value)}
                      onClick={() => setHumanVisible(opt.value)}
                      className={`flex-1 py-1 text-[10px] font-bold transition-all cursor-pointer
                        ${idx > 0 ? 'border-l border-gray-200' : ''}
                        ${humanVisible === opt.value ? opt.activeClass : 'bg-white text-gray-400 hover:bg-gray-50'}
                      `}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Already annotated indicator */}
            {task?.current_annotation?.status === 'completed' && (
              <div className="mb-2 flex items-center gap-1.5 px-2 py-1 bg-green-50 border border-green-200 rounded text-[9px] text-green-700 font-medium">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Already completed
              </div>
            )}

            {/* Navigation buttons */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleBack}
                disabled={queueIndex === 0 || saving}
                className="px-2.5 py-1.5 border border-gray-300 text-gray-600 rounded hover:bg-gray-100 transition disabled:opacity-25 cursor-pointer text-xs font-medium"
              >
                ←
              </button>
              <button
                onClick={handleSkip}
                disabled={saving}
                className="px-2.5 py-1.5 border border-amber-300 text-amber-700 bg-amber-50 rounded hover:bg-amber-100 transition disabled:opacity-50 cursor-pointer text-xs font-medium"
              >
                Skip
              </button>
              <button
                onClick={handleNext}
                disabled={saving || selectedOptions.length === 0}
                className="flex-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded transition-all disabled:opacity-40 cursor-pointer text-xs font-bold"
              >
                {saving ? '...' : 'Save & Next →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
