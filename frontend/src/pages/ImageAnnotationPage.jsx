import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';

// Helper to get proxied image URL for Google Drive images
const getImageUrl = (imageId) => {
  if (!imageId) return '';
  // Add timestamp to prevent caching of processed images
  return `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/images/proxy/${imageId}?t=${Date.now()}`;
};

function CategoryDropdown({ category, annotation, completedByOther, onChange, disabled }) {
  const [isOpen, setIsOpen] = useState(false);
  // Single selection - store only one option ID (or null)
  const [selectedOption, setSelectedOption] = useState(
    annotation?.selected_option_ids?.[0] || null
  );

  useEffect(() => {
    setSelectedOption(annotation?.selected_option_ids?.[0] || null);
  }, [annotation]);

  const selectOption = (optionId) => {
    if (disabled) return;
    // Single selection - clicking the same option deselects it, otherwise select the new one
    const newSelected = selectedOption === optionId ? null : optionId;
    setSelectedOption(newSelected);
    // Still pass as array for API compatibility
    onChange(category.id, { selected_option_ids: newSelected ? [newSelected] : [] });
  };

  const handleToggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOpen(!isOpen);
  };

  const isCompleted = annotation?.status === 'completed' || completedByOther;
  const hasSelection = selectedOption !== null;
  const selectedLabel = category.options.find((o) => o.id === selectedOption)?.label || null;

  return (
    <div className={`border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm transition-all hover:shadow-md ${disabled ? 'opacity-50' : ''}`}>
      <button
        type="button"
        onClick={handleToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50/80 transition cursor-pointer"
        disabled={disabled}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-3 h-3 rounded-full shrink-0 ${
              isCompleted ? 'bg-green-500' : hasSelection ? 'bg-amber-400' : 'bg-gray-300'
            }`}
          />
          <div className="text-left">
            <h3 className="font-medium text-gray-900 text-sm">{category.name}</h3>
            {selectedLabel ? (
              <p className="text-xs text-gray-500 mt-0.5 truncate max-w-xs">
                {selectedLabel}
              </p>
            ) : completedByOther ? (
              <p className="text-xs text-green-600 mt-0.5">Completed by another annotator</p>
            ) : (
              <p className="text-xs text-gray-400 mt-0.5">No option selected</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasSelection && (
            <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-[10px] font-bold rounded-full">✓</span>
          )}
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {isOpen && (
        <div className="border-t border-gray-200 px-4 py-3 bg-gray-50/50">
          {completedByOther && !annotation ? (
            <p className="text-sm text-gray-500 italic mb-2">
              Completed by another annotator. You can still add your own annotation.
            </p>
          ) : null}
          
          <div className="space-y-2">
            {category.options.map((opt) => {
              const isSelected = selectedOption === opt.id;
              return (
                <div
                  key={opt.id}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    selectOption(opt.id);
                  }}
                  className={`
                    flex items-center gap-3 px-3 py-2.5 rounded-lg border-2 cursor-pointer transition-all select-none
                    ${disabled ? 'cursor-not-allowed' : ''}
                    ${isSelected
                      ? 'border-indigo-500 bg-indigo-50 text-indigo-900'
                      : 'border-gray-200 hover:border-gray-300 bg-white text-gray-700'
                    }
                  `}
                >
                  {/* Radio button style (circle) for single selection */}
                  <div
                    className={`
                      w-5 h-5 rounded-full flex items-center justify-center border-2 shrink-0 transition-all
                      ${isSelected ? 'border-indigo-500' : 'border-gray-300'}
                    `}
                  >
                    {isSelected && (
                      <div className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
                    )}
                  </div>
                  <span className="text-sm font-medium flex-1">{opt.label}</span>
                  {opt.is_typical && (
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">typical</span>
                  )}
                </div>
              );
            })}
          </div>

        </div>
      )}
    </div>
  );
}

// Modal for marking image as improper
function MarkImproperModal({ isOpen, onClose, onConfirm, loading }) {
  const [reason, setReason] = useState('');
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Mark Image as Improper</h3>
        <p className="text-sm text-gray-600 mb-4">
          This image will be flagged for admin review and no annotations will be saved.
        </p>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g., Image is blurry, contains inappropriate content..."
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-red-500 resize-none"
            rows={3}
          />
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} disabled={loading} className="flex-1 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition disabled:opacity-50 cursor-pointer">Cancel</button>
          <button onClick={() => onConfirm(reason)} disabled={loading || !reason.trim()} className="flex-1 px-4 py-2.5 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition disabled:opacity-50 cursor-pointer">
            {loading ? 'Marking...' : 'Mark Improper'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Modal for requesting edit permission
function RequestEditModal({ isOpen, onClose, onConfirm, loading }) {
  const [reason, setReason] = useState('');
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Request Edit Permission</h3>
        <p className="text-sm text-gray-600 mb-4">
          This image has been annotated. Request permission from admin to make changes.
        </p>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Reason for edit</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g., Made a mistake in selection, need to update category..."
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            rows={3}
          />
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} disabled={loading} className="flex-1 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition disabled:opacity-50 cursor-pointer">Cancel</button>
          <button onClick={() => { onConfirm(reason); setReason(''); }} disabled={loading || !reason.trim()} className="flex-1 px-4 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50 cursor-pointer">
            {loading ? 'Submitting...' : 'Submit Request'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ImageAnnotationPage() {
  const { imageId } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [pendingChanges, setPendingChanges] = useState({});
  
  const [showImproperModal, setShowImproperModal] = useState(false);
  const [markingImproper, setMarkingImproper] = useState(false);
  
  const [showEditRequestModal, setShowEditRequestModal] = useState(false);
  const [requestingEdit, setRequestingEdit] = useState(false);
  
  // AI-generated detection state
  const [isAIGenerated, setIsAIGenerated] = useState(null); // null, true, or false
  const [savingAIStatus, setSavingAIStatus] = useState(false);

  // Time limit settings (fetched from API)
  const [maxAnnotationTime, setMaxAnnotationTime] = useState(120);
  const [maxReworkTime, setMaxReworkTime] = useState(120);
  const [isReworkMode, setIsReworkMode] = useState(false);

  // Timer state — tracks time per image, persists to DB automatically
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [showTimeWarning, setShowTimeWarning] = useState(false);
  const elapsedRef = useRef(0); // mirrors elapsedSeconds for use in non-reactive callbacks
  const imageIdRef = useRef(imageId); // current imageId for use in cleanup/beforeunload

  // Compute the current max time based on mode
  const currentMaxTime = isReworkMode ? maxReworkTime : maxAnnotationTime;

  // Keep refs in sync with state
  useEffect(() => { elapsedRef.current = elapsedSeconds; }, [elapsedSeconds]);
  useEffect(() => { imageIdRef.current = imageId; }, [imageId]);

  // Persist time to DB (fire-and-forget)
  const persistTime = useCallback((imgId, seconds) => {
    if (!imgId || seconds <= 0) return;
    api.patch(`/annotator/images/${imgId}/time`, { time_spent_seconds: seconds }).catch(() => {});
  }, []);

  // Persist time using fetch+keepalive (works even during page unload)
  const persistTimeBeacon = useCallback((imgId, seconds) => {
    if (!imgId || seconds <= 0) return;
    const token = localStorage.getItem('token');
    const url = `/api/annotator/images/${imgId}/time`;
    try {
      fetch(url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ time_spent_seconds: seconds }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      // ignore
    }
  }, []);

  // Auto-save time to DB every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      persistTime(imageIdRef.current, elapsedRef.current);
    }, 10000);
    return () => clearInterval(interval);
  }, [persistTime]);

  // Save time on window/tab close or browser navigation
  useEffect(() => {
    const handleBeforeUnload = () => {
      persistTimeBeacon(imageIdRef.current, elapsedRef.current);
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [persistTimeBeacon]);

  // Save time when navigating away from this image (imageId changes)
  const prevImageIdRef = useRef(imageId);
  useEffect(() => {
    const prevId = prevImageIdRef.current;
    if (prevId && prevId !== imageId) {
      persistTime(prevId, elapsedRef.current);
    }
    prevImageIdRef.current = imageId;
  }, [imageId, persistTime]);

  // Fetch time limit settings from API on mount
  useEffect(() => {
    api.get('/annotator/settings/time-limits')
      .then(res => {
        setMaxAnnotationTime(res.data.max_annotation_time_seconds || 120);
        setMaxReworkTime(res.data.max_rework_time_seconds || 120);
      })
      .catch(() => {
        // Use defaults if API fails
        setMaxAnnotationTime(120);
        setMaxReworkTime(120);
      });
  }, []);

  // Timer tick
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedSeconds((prev) => {
        const next = prev + 1;
        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Check for time warning whenever elapsed changes
  useEffect(() => {
    if (elapsedSeconds >= currentMaxTime && !showTimeWarning) {
      setShowTimeWarning(true);
    }
  }, [elapsedSeconds, currentMaxTime, showTimeWarning]);

  const formatTime = (seconds) => {
    const absSeconds = Math.abs(seconds);
    const mins = Math.floor(absSeconds / 60);
    const secs = absSeconds % 60;
    const prefix = seconds < 0 ? '-' : '';
    return `${prefix}${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Compute remaining time for countdown display
  const remainingSeconds = currentMaxTime - elapsedSeconds;

  const loadImage = useCallback(async (id) => {
    setLoading(true);
    setError('');
    setPendingChanges({});
    try {
      const res = await api.get(`/annotator/images/${id}`);
      setData(res.data);
      
      const initial = {};
      let maxSavedTime = 0;
      res.data.categories.forEach((cat) => {
        if (cat.annotation) {
          initial[cat.id] = {
            selected_option_ids: cat.annotation.selected_option_ids,
          };
          // Track the max time_spent_seconds across all categories for this image
          if (cat.annotation.time_spent_seconds > maxSavedTime) {
            maxSavedTime = cat.annotation.time_spent_seconds;
          }
        }
      });
      setPendingChanges(initial);
      
      // Load AI-generated status
      try {
        const aiRes = await api.get(`/annotator/images/${id}/ai-detection`);
        setIsAIGenerated(aiRes.data.is_ai_generated);
      } catch (err) {
        setIsAIGenerated(null); // Default to unknown
      }
      
      // Detect if this is a rework - check both top-level flag and category annotations
      const hasRework = res.data.is_rework || res.data.categories.some(cat => 
        cat.annotation?.review_status === 'rework_requested' || cat.annotation?.is_rework
      );
      setIsReworkMode(hasRework);
      
      // For rework, use rework_time_seconds, otherwise use time_spent_seconds
      // Resume timer from DB-saved value
      setElapsedSeconds(maxSavedTime);
      
      // Check if we're already over the limit
      const effectiveMaxTime = hasRework ? maxReworkTime : maxAnnotationTime;
      setShowTimeWarning(maxSavedTime >= effectiveMaxTime);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load image');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadImage(imageId);
  }, [imageId, loadImage]);

  const handleCategoryChange = (categoryId, value) => {
    setPendingChanges((prev) => ({ ...prev, [categoryId]: value }));
  };

  // Check if all categories have at least one option selected
  const validateAllCategoriesSelected = () => {
    if (!data?.categories) return { valid: false, missing: [] };
    
    const missing = [];
    for (const cat of data.categories) {
      // Skip if completed by other annotator
      if (cat.completed_by_other && !pendingChanges[cat.id]) continue;
      
      const pending = pendingChanges[cat.id];
      if (!pending || !pending.selected_option_ids || pending.selected_option_ids.length === 0) {
        missing.push(cat.name);
      }
    }
    
    return { valid: missing.length === 0, missing };
  };

  const handleSave = async () => {
    if (saving || !data?.can_edit || data?.is_improper) return false;
    
    // Validate all categories have selections
    const validation = validateAllCategoriesSelected();
    if (!validation.valid) {
      setError(`Please select an option for: ${validation.missing.join(', ')}`);
      return false;
    }
    
    setSaving(true);
    setError('');
    
    try {
      await api.put(`/annotator/images/${imageId}/annotations`, { annotations: pendingChanges, time_spent_seconds: elapsedSeconds });
      await loadImage(imageId);
      return true;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndNext = async () => {
    const success = await handleSave();
    if (success) {
      if (data?.next_image_id) {
        navigate(`/annotator/image/${data.next_image_id}`);
      } else {
        handleBack();
      }
    }
  };

  const handleNavigate = (id) => {
    if (id) {
      persistTime(imageId, elapsedSeconds);
      navigate(`/annotator/image/${id}`);
    }
  };

  const handleBack = () => {
    persistTime(imageId, elapsedSeconds);
    navigate('/annotator');
  };

  const handleMarkImproper = async (reason) => {
    setMarkingImproper(true);
    try {
      await api.post(`/annotator/images/${imageId}/mark-improper`, { reason });
      setShowImproperModal(false);
      if (data?.next_image_id) {
        navigate(`/annotator/image/${data.next_image_id}`);
      } else {
        await loadImage(imageId);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to mark as improper');
    } finally {
      setMarkingImproper(false);
    }
  };

  const handleRequestEdit = async (reason) => {
    setRequestingEdit(true);
    try {
      await api.post(`/annotator/images/${imageId}/request-edit`, { reason });
      setShowEditRequestModal(false);
      await loadImage(imageId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit request');
    } finally {
      setRequestingEdit(false);
    }
  };

  const handleAIStatusChange = async (value) => {
    setSavingAIStatus(true);
    try {
      await api.put(`/annotator/images/${imageId}/ai-detection`, {
        is_ai_generated: value
      });
      setIsAIGenerated(value);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update AI status');
    } finally {
      setSavingAIStatus(false);
    }
  };

  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (saving || !data?.can_edit || data?.is_improper) return;
      
      if (e.key === 'ArrowLeft' && data?.prev_image_id) {
        e.preventDefault();
        handleNavigate(data.prev_image_id);
      } else if (e.key === 'ArrowRight' && data?.next_image_id) {
        e.preventDefault();
        handleNavigate(data.next_image_id);
      } else if ((e.key === 'Enter' || e.key === 's') && e.ctrlKey) {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  const hasChanges = Object.keys(pendingChanges).some((catId) => {
    const cat = data?.categories?.find((c) => c.id === parseInt(catId));
    if (!cat) return false;
    const existing = cat.annotation;
    const pending = pendingChanges[catId];
    
    if (!existing && pending.selected_option_ids?.length > 0) return true;
    if (!existing) return false;
    
    const existingIds = new Set(existing.selected_option_ids || []);
    const pendingIds = new Set(pending.selected_option_ids || []);
    
    if (existingIds.size !== pendingIds.size) return true;
    for (const id of existingIds) {
      if (!pendingIds.has(id)) return true;
    }
    return false;
  });

  const completedCount = data?.categories?.filter((cat) => {
    const pending = pendingChanges[cat.id];
    return (pending?.selected_option_ids?.length > 0) || cat.completed_by_other;
  }).length || 0;

  if (loading) {
    return (
      <div className="min-h-screen mesh-bg flex items-center justify-center">
        <div className="text-center animate-fade-in">
          <div className="w-10 h-10 border-3 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-500 text-sm">Loading image...</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen mesh-bg flex flex-col items-center justify-center gap-4 animate-fade-in">
        <div className="w-14 h-14 bg-red-100 rounded-2xl flex items-center justify-center mb-2">
          <svg className="w-7 h-7 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
        </div>
        <p className="text-red-500 font-medium">{error}</p>
        <button onClick={handleBack} className="text-indigo-600 hover:underline cursor-pointer text-sm font-medium">Back to images</button>
      </div>
    );
  }

  const isImproper = data?.is_improper;
  const isLocked = data?.is_locked && !data?.can_edit;
  const hasPendingRequest = data?.pending_edit_request;
  const canEdit = data?.can_edit && !isImproper;

  return (
    <div className="h-screen bg-gray-50 flex flex-col overflow-hidden">
      <header className="glass border-b border-white/30 sticky top-0 z-10">
        <div className="px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={handleBack} className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition cursor-pointer">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-bold text-gray-900">{data?.filename}</h1>
                {isImproper && <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full text-xs font-semibold">Improper</span>}
                {isReworkMode && !isImproper && <span className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded-full text-xs font-semibold">Rework</span>}
                {isLocked && <span className="px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full text-xs font-semibold">Locked</span>}
                {hasPendingRequest && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold">Request Pending</span>}
              </div>
              <p className="text-xs text-gray-500">Image {(data?.current_index || 0) + 1} of {data?.total_images} &middot; <span className="font-medium text-indigo-600">{user?.username}</span></p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Countdown Timer */}
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
              remainingSeconds <= 0
                ? 'bg-red-100 text-red-700 animate-pulse' 
                : remainingSeconds <= 30 
                  ? 'bg-amber-100 text-amber-700' 
                  : 'bg-emerald-100 text-emerald-700'
            }`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {remainingSeconds >= 0 ? formatTime(remainingSeconds) : `+${formatTime(Math.abs(remainingSeconds))}`}
              {isReworkMode && <span className="ml-1 text-[10px] opacity-70">rework</span>}
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-full text-xs font-semibold">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
              {completedCount}/{data?.categories?.length}
            </div>
            <button onClick={logout} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 cursor-pointer">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            </button>
          </div>
        </div>
        <div className="h-1 bg-gray-200">
          <div className="h-1 bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-300" style={{ width: `${((data?.current_index || 0) + 1) / (data?.total_images || 1) * 100}%` }} />
        </div>
      </header>

      <main className="flex-1 w-full min-h-0 overflow-hidden">
        <div className="h-full grid grid-cols-1 lg:grid-cols-[1fr_420px]">
          <div className="bg-gray-900 relative flex items-center justify-center p-4 h-full">
            {isImproper && (
              <div className="absolute inset-0 bg-red-900/20 z-10 flex items-center justify-center">
                <div className="bg-red-50 rounded-xl p-6 max-w-md mx-4 text-center">
                  <div className="text-red-500 text-4xl mb-3">⚠️</div>
                  <h3 className="text-lg font-semibold text-red-800 mb-2">Image Marked as Improper</h3>
                  <p className="text-sm text-red-600 mb-3">{data?.improper_reason}</p>
                  <p className="text-xs text-red-500">Pending admin review.</p>
                </div>
              </div>
            )}
            
            {/* Fixed position navigation buttons */}
            {data?.prev_image_id && (
              <button 
                onClick={() => handleNavigate(data.prev_image_id)} 
                className="fixed left-4 top-1/2 -translate-y-1/2 w-14 h-14 bg-black/40 hover:bg-black/60 backdrop-blur-sm rounded-full flex items-center justify-center text-white transition cursor-pointer z-30 shadow-xl border border-white/20"
              >
                <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              </button>
            )}
            
            <img src={getImageUrl(data?.id)} alt={data?.filename} className={`max-w-full max-h-full object-contain rounded-lg ${isImproper ? 'opacity-50' : ''}`} />
            
            {data?.next_image_id && (
              <button 
                onClick={() => handleNavigate(data.next_image_id)} 
                className="fixed top-1/2 -translate-y-1/2 w-14 h-14 bg-black/40 hover:bg-black/60 backdrop-blur-sm rounded-full flex items-center justify-center text-white transition cursor-pointer z-30 shadow-xl border border-white/20 right-4 lg:right-[440px]"
              >
                <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </button>
            )}
          </div>

          <div className="bg-white border-l border-gray-200 flex flex-col overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-white">
              <h2 className="font-bold text-gray-900">Categories</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                {isLocked && !canEdit ? 'View your annotations (read-only)' : 'Select one option for each category'}
              </p>
            </div>

            {error && <div className="mx-4 mt-3 bg-red-50 text-red-700 px-4 py-2 rounded-lg text-sm">{error}</div>}

            {showTimeWarning && !isLocked && (
              <div className="mx-4 mt-3 bg-red-50 border border-red-300 rounded-lg px-4 py-3 animate-pulse">
                <div className="flex items-center gap-2">
                  <svg className="w-5 h-5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <p className="text-sm text-red-700 font-semibold">⏱️ Performance Warning</p>
                    <p className="text-xs text-red-600 mt-0.5">You've spent over 2 minutes on this image. Please complete your annotation.</p>
                  </div>
                </div>
              </div>
            )}

            {isImproper && (
              <div className="mx-4 mt-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                <p className="text-sm text-red-700 font-medium">Image marked as improper</p>
                <p className="text-xs text-red-600 mt-1">Annotations are disabled.</p>
              </div>
            )}

            {isReworkMode && !isImproper && (
              <div className="mx-4 mt-3 bg-orange-50 border border-orange-300 rounded-lg px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">🔄</span>
                  <div>
                    <p className="text-sm text-orange-700 font-medium">Rework Requested</p>
                    <p className="text-xs text-orange-600 mt-0.5">Please review and update your annotations as needed.</p>
                  </div>
                </div>
              </div>
            )}

            {isLocked && !isImproper && (
              <div className="mx-4 mt-3 bg-gradient-to-r from-amber-50 to-orange-50 border-2 border-amber-300 rounded-xl px-5 py-4 shadow-sm">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
                      <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm text-amber-800 font-semibold">This image is validated & locked</p>
                      <p className="text-xs text-amber-600 mt-0.5">
                        {hasPendingRequest 
                          ? '⏳ Your edit request is pending admin approval' 
                          : 'You can view annotations but cannot make changes'}
                      </p>
                    </div>
                  </div>
                  {!hasPendingRequest && (
                    <button
                      onClick={() => setShowEditRequestModal(true)}
                      className="shrink-0 px-5 py-2.5 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-xl text-sm font-semibold hover:from-amber-600 hover:to-orange-600 transition shadow-md cursor-pointer flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                      </svg>
                      Request Edit
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {data?.categories?.map((cat) => (
                <CategoryDropdown
                  key={cat.id}
                  category={cat}
                  annotation={cat.annotation}
                  completedByOther={cat.completed_by_other}
                  onChange={handleCategoryChange}
                  disabled={!canEdit}
                />
              ))}
            </div>

            <div className="border-t border-gray-200 px-5 py-4 bg-gradient-to-t from-gray-50 to-white space-y-3">
              {/* AI-Generated Detection Toggle */}
              {!isImproper && (
                <div className="bg-white border-2 border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <svg className="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      <h3 className="font-semibold text-gray-900 text-sm">Is this image AI-generated?</h3>
                    </div>
                    {savingAIStatus && (
                      <span className="text-xs text-gray-500 italic">Saving...</span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleAIStatusChange(false)}
                      disabled={savingAIStatus || !canEdit}
                      className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition border-2 cursor-pointer ${
                        isAIGenerated === false
                          ? 'bg-green-50 border-green-500 text-green-700'
                          : 'bg-white border-gray-200 text-gray-700 hover:border-gray-300'
                      } disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                      <div className="flex items-center justify-center gap-2">
                        <div className={`w-4 h-4 rounded-full flex items-center justify-center border-2 ${
                          isAIGenerated === false ? 'border-green-500' : 'border-gray-300'
                        }`}>
                          {isAIGenerated === false && (
                            <div className="w-2 h-2 rounded-full bg-green-500" />
                          )}
                        </div>
                        <span>Real</span>
                      </div>
                    </button>
                    <button
                      onClick={() => handleAIStatusChange(true)}
                      disabled={savingAIStatus || !canEdit}
                      className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition border-2 cursor-pointer ${
                        isAIGenerated === true
                          ? 'bg-purple-50 border-purple-500 text-purple-700'
                          : 'bg-white border-gray-200 text-gray-700 hover:border-gray-300'
                      } disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                      <div className="flex items-center justify-center gap-2">
                        <div className={`w-4 h-4 rounded-full flex items-center justify-center border-2 ${
                          isAIGenerated === true ? 'border-purple-500' : 'border-gray-300'
                        }`}>
                          {isAIGenerated === true && (
                            <div className="w-2 h-2 rounded-full bg-purple-500" />
                          )}
                        </div>
                        <span>AI-Generated</span>
                      </div>
                    </button>
                    <button
                      onClick={() => handleAIStatusChange(null)}
                      disabled={savingAIStatus || !canEdit}
                      className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition border-2 cursor-pointer ${
                        isAIGenerated === null
                          ? 'bg-gray-50 border-gray-400 text-gray-700'
                          : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                      } disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                      <div className="flex items-center justify-center gap-2">
                        <div className={`w-4 h-4 rounded-full flex items-center justify-center border-2 ${
                          isAIGenerated === null ? 'border-gray-400' : 'border-gray-300'
                        }`}>
                          {isAIGenerated === null && (
                            <div className="w-2 h-2 rounded-full bg-gray-400" />
                          )}
                        </div>
                        <span>Unknown</span>
                      </div>
                    </button>
                  </div>
                </div>
              )}

              {!isImproper && !isLocked && (
                <button
                  onClick={() => setShowImproperModal(true)}
                  className="w-full px-4 py-2.5 border-2 border-red-200 text-red-600 rounded-lg hover:bg-red-50 hover:border-red-300 transition cursor-pointer text-sm font-medium flex items-center justify-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  Mark Improper
                </button>
              )}

              {isLocked && !isImproper && !hasPendingRequest && (
                <button
                  onClick={() => setShowEditRequestModal(true)}
                  className="w-full px-4 py-2.5 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition cursor-pointer text-sm font-medium flex items-center justify-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                  Request Edit Permission
                </button>
              )}
              
              <div className="flex gap-3">
                <button
                  onClick={() => handleNavigate(data?.prev_image_id)}
                  disabled={!data?.prev_image_id || saving}
                  className="px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer text-sm font-medium"
                >
                  ← Prev
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !canEdit}
                  className="flex-1 px-4 py-2.5 border border-indigo-200 text-indigo-700 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-sm font-semibold"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={handleSaveAndNext}
                  disabled={saving || !canEdit}
                  className="flex-1 px-4 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white rounded-xl transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-sm font-semibold"
                >
                  {saving ? 'Saving...' : data?.next_image_id ? 'Save & Next →' : 'Save & Finish'}
                </button>
              </div>

              <div className="flex items-center justify-center gap-4 text-xs text-gray-400">
                <span><kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">←</kbd> Prev</span>
                <span><kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">→</kbd> Next</span>
                <span><kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">Ctrl+S</kbd> Save</span>
              </div>
            </div>
          </div>
        </div>
      </main>

      <MarkImproperModal isOpen={showImproperModal} onClose={() => setShowImproperModal(false)} onConfirm={handleMarkImproper} loading={markingImproper} />
      <RequestEditModal isOpen={showEditRequestModal} onClose={() => setShowEditRequestModal(false)} onConfirm={handleRequestEdit} loading={requestingEdit} />
    </div>
  );
}
