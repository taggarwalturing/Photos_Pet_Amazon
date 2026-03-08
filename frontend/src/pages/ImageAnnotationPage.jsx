import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import BoundingBoxCanvas from '../components/BoundingBoxCanvas';
import CategoryGuideModal from '../components/CategoryGuideModal';

// Helper to get proxied image URL for Google Drive images
const getImageUrl = (imageId) => {
  if (!imageId) return '';
  // Add timestamp to prevent caching of processed images
  return `${import.meta.env.VITE_API_URL || 'http://localhost:5001'}/api/images/proxy/${imageId}?t=${Date.now()}`;
};

function CategoryDropdown({ category, annotation, completedByOther, onChange, disabled, aiSuggestion }) {
  const [isOpen, setIsOpen] = useState(false);

  // Determine initial selection: existing annotation > AI suggestion
  // AI suggestion is used when there's no annotation OR annotation has empty selections (in_progress auto-save)
  const hasHumanSelection = annotation?.selected_option_ids?.length > 0;

  const getInitialSelection = () => {
    if (hasHumanSelection) return annotation.selected_option_ids[0];
    // Pre-fill AI suggestion if no human selection exists
    if (aiSuggestion?.option_id) return aiSuggestion.option_id;
    return null;
  };

  const [selectedOption, setSelectedOption] = useState(getInitialSelection);
  const [aiPreFilled, setAiPreFilled] = useState(
    !hasHumanSelection && aiSuggestion?.option_id ? true : false
  );

  useEffect(() => {
    if (hasHumanSelection) {
      setSelectedOption(annotation.selected_option_ids[0]);
      setAiPreFilled(false);
    } else if (aiSuggestion?.option_id) {
      setSelectedOption(aiSuggestion.option_id);
      setAiPreFilled(true);
    } else {
      setSelectedOption(null);
      setAiPreFilled(false);
    }
  }, [annotation, aiSuggestion, hasHumanSelection]);

  const selectOption = (optionId) => {
    if (disabled) return;
    const newSelected = selectedOption === optionId ? null : optionId;
    setSelectedOption(newSelected);
    setAiPreFilled(false); // Human made a selection, no longer AI pre-filled
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
  const isAiSuggested = (optId) => aiSuggestion?.option_id === optId;

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
            <h3 className="font-medium text-gray-900 text-sm">
              {category.name}
            </h3>
            {selectedLabel ? (
              <p className={`text-xs mt-0.5 truncate max-w-xs ${aiPreFilled ? 'text-purple-600' : 'text-gray-500'}`}>
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
              const isAiPick = isAiSuggested(opt.id);
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
                    ${isSelected && aiPreFilled
                      ? 'border-purple-400 bg-purple-50 text-purple-900'
                      : isSelected
                      ? 'border-indigo-500 bg-indigo-50 text-indigo-900'
                      : isAiPick
                      ? 'border-purple-200 hover:border-purple-300 bg-white text-gray-700'
                      : 'border-gray-200 hover:border-gray-300 bg-white text-gray-700'
                    }
                  `}
                >
                  {/* Radio button style (circle) for single selection */}
                  <div
                    className={`
                      w-5 h-5 rounded-full flex items-center justify-center border-2 shrink-0 transition-all
                      ${isSelected && aiPreFilled ? 'border-purple-500' : isSelected ? 'border-indigo-500' : 'border-gray-300'}
                    `}
                  >
                    {isSelected && (
                      <div className={`w-2.5 h-2.5 rounded-full ${aiPreFilled ? 'bg-purple-500' : 'bg-indigo-500'}`} />
                    )}
                  </div>
                  <span className="text-sm font-medium flex-1">{opt.label}</span>
                  <div className="flex items-center gap-1.5">
                  {opt.is_typical && (
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">typical</span>
                  )}
                  </div>
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
  const [showGuideModal, setShowGuideModal] = useState(false);
  const [markingImproper, setMarkingImproper] = useState(false);
  
  const [showEditRequestModal, setShowEditRequestModal] = useState(false);
  const [requestingEdit, setRequestingEdit] = useState(false);
  
  // AI-generated detection state
  const [isAIGenerated, setIsAIGenerated] = useState(false); // default to Real (false)
  const [savingAIStatus, setSavingAIStatus] = useState(false);

  // Human visibility state
  const [humanVisible, setHumanVisible] = useState(null); // null=Unknown, true=Yes, false=No
  const [savingHumanVisible, setSavingHumanVisible] = useState(false);

  // Blur tool state
  const [blurActive, setBlurActive] = useState(false);
  const [blurBoxes, setBlurBoxes] = useState([]);
  const [applyingBlur, setApplyingBlur] = useState(false);
  const [imageVersion, setImageVersion] = useState(Date.now()); // cache-buster for image reload
  const imageContainerRef = useRef(null);

  // Time limit settings (fetched from API)
  const [maxAnnotationTime, setMaxAnnotationTime] = useState(20);
  const [isReworkMode, setIsReworkMode] = useState(false);

  // Timer state — tracks time per image session (resets on every open)
  // Time is ONLY saved on submit — not on navigate, close, or auto-save
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const isReworkRef = useRef(false); // mirrors isReworkMode
  const isImproperRef = useRef(false); // mirrors improper status
  const maxTimeRef = useRef(20); // mirrors maxAnnotationTime for use in timer

  // Keep refs in sync with state
  useEffect(() => { isReworkRef.current = isReworkMode; }, [isReworkMode]);
  useEffect(() => { maxTimeRef.current = maxAnnotationTime; }, [maxAnnotationTime]);

  // Reset timer to 0 whenever the image changes (always start fresh)
  useEffect(() => {
    setElapsedSeconds(0);
  }, [imageId]);

  // Fetch time limit settings from API on mount
  useEffect(() => {
    api.get('/annotator/settings/time-limits')
      .then(res => {
        setMaxAnnotationTime(res.data.max_annotation_time_seconds || 20);
      })
      .catch(() => {
        setMaxAnnotationTime(20);
      });
  }, []);

  // Timer tick — stops at max time, does not run for rework/improper
  useEffect(() => {
    const interval = setInterval(() => {
      if (isReworkRef.current || isImproperRef.current) return;
      setElapsedSeconds((prev) => {
        if (prev >= maxTimeRef.current) return prev; // Stop at max
        return prev + 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds) => {
    const secs = Math.abs(seconds);
    return `${secs}s`;
  };

  // Compute remaining time for countdown display
  const remainingSeconds = maxAnnotationTime - elapsedSeconds;
  // Whether we should show the timer (not for rework or improper)
  const showTimer = !isReworkMode && !data?.is_improper;

  const loadImage = useCallback(async (id) => {
    setLoading(true);
    setError('');
    setPendingChanges({});
    setBlurBoxes([]);
    setBlurActive(false);
    setImageVersion(Date.now()); // fresh cache-buster for new image
    try {
      const res = await api.get(`/annotator/images/${id}`);
      setData(res.data);
      
      const initial = {};
      res.data.categories.forEach((cat) => {
        const hasHumanSelection = cat.annotation?.selected_option_ids?.length > 0;
        if (hasHumanSelection) {
          initial[cat.id] = {
            selected_option_ids: cat.annotation.selected_option_ids,
          };
        } else if (cat.ai_suggestion?.option_id) {
          initial[cat.id] = {
            selected_option_ids: [cat.ai_suggestion.option_id],
          };
        } else if (cat.annotation) {
          initial[cat.id] = {
            selected_option_ids: [],
          };
        }
      });
      setPendingChanges(initial);
      
      // Load AI-generated status (default to Real)
      try {
        const aiRes = await api.get(`/annotator/images/${id}/ai-detection`);
        setIsAIGenerated(aiRes.data.is_ai_generated ?? false); // default Real
      } catch (err) {
        setIsAIGenerated(false); // Default to Real
      }

      // Load human visibility status
      try {
        const hvRes = await api.get(`/annotator/images/${id}/human-visibility`);
        setHumanVisible(hvRes.data.human_visible);
      } catch (err) {
        setHumanVisible(null); // Default to Unknown
      }
      
      // Detect if this is a rework
      const hasRework = res.data.is_rework || res.data.categories.some(cat => 
        cat.annotation?.review_status === 'rework_requested' || cat.annotation?.is_rework
      );
      setIsReworkMode(hasRework);
      isReworkRef.current = hasRework;
      
      // Track improper status for timer
      isImproperRef.current = !!res.data.is_improper;
      
      // Always start timer fresh at 0 — time is only saved on submit
      setElapsedSeconds(0);
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
      // For rework/improper: send 0 time. For normal: send min(elapsed, max)
      const timeToSave = isReworkMode || data?.is_improper ? 0 : Math.min(elapsedSeconds, maxAnnotationTime);
      await api.put(`/annotator/images/${imageId}/annotations`, {
        annotations: pendingChanges,
        time_spent_seconds: timeToSave,
        is_rework: isReworkMode,
      });
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
      navigate(`/annotator/image/${id}`);
    }
  };

  const handleBack = () => {
    // Use browser back to preserve the page number on the annotator home
    if (window.history.length > 1) {
      navigate(-1);
    } else {
    navigate('/annotator');
    }
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

  const handleApplyBlur = async () => {
    if (!blurBoxes.length) return;
    setApplyingBlur(true);
    setError('');
    try {
      await api.post(`/annotator/blur/apply/${imageId}`, { regions: blurBoxes });
      setBlurBoxes([]);
      setBlurActive(false);
      // Force image to reload with fresh cache-buster
      setImageVersion(Date.now());
      // Refresh task data so the blur flags update in the UI (enables Undo Blur button)
      const refreshed = await api.get(`/annotator/images/${imageId}`);
      setData(refreshed.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to apply blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const handleUndoBlur = async () => {
    setApplyingBlur(true);
    setError('');
    try {
      const res = await api.delete(`/annotator/blur/${imageId}/blur`);
      if (res.data?.had_original) {
        // Original was found and written to cache — reload image
        setImageVersion(Date.now());
      } else {
        // No original found on disk — image will break. Warn user.
        setError('Original unblurred image not found on disk. Cannot undo.');
        setApplyingBlur(false);
        return;
      }
      // Refresh task data so the blur flags update in the UI
      const refreshed = await api.get(`/annotator/images/${imageId}`);
      setData(refreshed.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to undo blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const handleRestoreBlur = async () => {
    setApplyingBlur(true);
    setError('');
    try {
      await api.post(`/annotator/blur/${imageId}/restore-blur`);
      setImageVersion(Date.now());
      // Refresh task data so the blur flags update in the UI
      const refreshed = await api.get(`/annotator/images/${imageId}`);
      setData(refreshed.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to restore blur');
    } finally {
      setApplyingBlur(false);
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

  const handleHumanVisibleChange = async (value) => {
    setSavingHumanVisible(true);
    try {
      await api.put(`/annotator/images/${imageId}/human-visibility`, {
        human_visible: value
      });
      setHumanVisible(value);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update human visibility');
    } finally {
      setSavingHumanVisible(false);
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
    <div className="fixed inset-0 bg-gray-50 flex flex-col">
      <header className="glass border-b border-white/30 z-10 shrink-0">
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
            {/* Countdown Timer — hidden for rework & improper */}
            {showTimer && (
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
              remainingSeconds <= 0
                  ? 'bg-red-100 text-red-700' 
                  : remainingSeconds <= 5 
                  ? 'bg-amber-100 text-amber-700' 
                  : 'bg-emerald-100 text-emerald-700'
            }`}>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
                {formatTime(remainingSeconds)}
            </div>
            )}
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

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[1fr_420px] overflow-hidden">
          <div className="bg-gray-900 relative flex items-center justify-center p-4 min-h-0 overflow-hidden">
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
            
            {/* Blur tool floating toolbar */}
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2">
              {applyingBlur ? (
                <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-600 text-white text-xs font-semibold shadow-lg">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Processing on server…
                </div>
              ) : (
                <>
                  {/* Blur Tool toggle */}
              <button
                onClick={() => setBlurActive(!blurActive)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-sm border transition cursor-pointer ${
                  blurActive
                    ? 'bg-red-500/90 text-white border-red-400'
                    : 'bg-black/50 text-white border-white/20 hover:bg-black/70'
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4h16v16H4z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9h6v6H9z" /></svg>
                    {blurActive ? 'Drawing…' : 'Blur Tool'}
              </button>

                  {/* Drawing controls — visible when boxes are drawn */}
              {blurBoxes.length > 0 && (
                <>
                  <span className="px-2 py-1 rounded-full bg-black/50 text-white text-xs backdrop-blur-sm border border-white/20">
                    {blurBoxes.length} region{blurBoxes.length > 1 ? 's' : ''}
                  </span>
                  <button
                    onClick={handleApplyBlur}
                        className="px-3 py-1.5 rounded-full bg-green-600 text-white text-xs font-semibold hover:bg-green-700 transition cursor-pointer shadow-lg"
                  >
                        ✓ Apply Blur
                      </button>
                      <button
                        onClick={() => setBlurBoxes(prev => prev.slice(0, -1))}
                        className="px-2 py-1.5 rounded-full bg-black/50 text-white text-xs hover:bg-black/70 transition cursor-pointer backdrop-blur-sm border border-white/20"
                      >
                        ↶ Undo
                  </button>
                  <button
                    onClick={() => setBlurBoxes([])}
                    className="px-2 py-1.5 rounded-full bg-black/50 text-white text-xs hover:bg-black/70 transition cursor-pointer backdrop-blur-sm border border-white/20"
                  >
                    Clear
                  </button>
                    </>
                  )}

                  {/* Undo applied blur — visible when image is blurred (manual or pipeline) & no new boxes drawn */}
                  {data?.is_blurred && blurBoxes.length === 0 && (
                    <button
                      onClick={handleUndoBlur}
                      className="px-3 py-1.5 rounded-full bg-amber-500/90 text-white text-xs font-semibold hover:bg-amber-600 transition cursor-pointer backdrop-blur-sm border border-amber-400 shadow-lg"
                    >
                      ↶ Undo Blur
                    </button>
                  )}

                  {/* Restore blur — visible after undoing a pipeline-blurred image */}
                  {!data?.is_blurred && data?.compliance_status === 'blurred' && blurBoxes.length === 0 && (
                    <button
                      onClick={handleRestoreBlur}
                      className="px-3 py-1.5 rounded-full bg-indigo-500/90 text-white text-xs font-semibold hover:bg-indigo-600 transition cursor-pointer backdrop-blur-sm border border-indigo-400 shadow-lg"
                    >
                      ↻ Restore Blur
                    </button>
                  )}
                </>
              )}
            </div>

            <div ref={imageContainerRef} className="relative max-w-full max-h-full overflow-hidden flex items-center justify-center">
              <img
                key={`img-${imageId}`}
                src={imageId ? `${import.meta.env.VITE_API_URL || 'http://localhost:5001'}/api/images/proxy/${imageId}?t=${imageVersion}` : ''}
                alt={data?.filename || ''}
                className={`max-w-full max-h-full object-contain rounded-lg block ${isImproper ? 'opacity-50' : ''}`}
                onLoad={() => window.dispatchEvent(new Event('resize'))}
              />
              {blurActive && (
                <BoundingBoxCanvas
                  containerRef={imageContainerRef}
                  boxes={blurBoxes}
                  setBoxes={setBlurBoxes}
                  disabled={false}
                />
              )}
            </div>
            
            {data?.next_image_id && (
              <button 
                onClick={() => handleNavigate(data.next_image_id)} 
                className="fixed top-1/2 -translate-y-1/2 w-14 h-14 bg-black/40 hover:bg-black/60 backdrop-blur-sm rounded-full flex items-center justify-center text-white transition cursor-pointer z-30 shadow-xl border border-white/20 right-4 lg:right-[440px]"
              >
                <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </button>
            )}
          </div>

          <div className="bg-white border-l border-gray-200 flex flex-col overflow-hidden min-h-0">
            <div className="px-5 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-white shrink-0 flex items-center justify-between">
              <div>
              <h2 className="font-bold text-gray-900">Categories</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                {isLocked && !canEdit ? 'View your annotations (read-only)' : 'Select one option for each category'}
              </p>
              </div>
              <button
                onClick={() => setShowGuideModal(true)}
                className="px-3 py-1.5 bg-indigo-50 text-indigo-600 border border-indigo-200 rounded-lg text-xs font-semibold hover:bg-indigo-100 transition cursor-pointer flex items-center gap-1.5"
                title="View category definitions"
              >
                📖 Guide
              </button>
            </div>

            {error && <div className="mx-4 mt-3 bg-red-50 text-red-700 px-4 py-2 rounded-lg text-sm">{error}</div>}

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

            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
              {data?.categories?.map((cat) => (
                <CategoryDropdown
                  key={cat.id}
                  category={cat}
                  annotation={cat.annotation}
                  completedByOther={cat.completed_by_other}
                  onChange={handleCategoryChange}
                  disabled={!canEdit}
                  aiSuggestion={cat.ai_suggestion}
                />
              ))}
            </div>

            <div className="shrink-0 border-t border-gray-200 bg-white">
              {/* Classification toggles */}
              {!isImproper && (
                <div className="px-4 py-2.5 space-y-2 border-b border-gray-100">
                  {/* Row 1: AI Detection */}
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider w-20 shrink-0">AI</span>
                    <div className="flex rounded-lg overflow-hidden border border-gray-200 flex-1 max-w-[220px]">
                      {[
                        { value: false, label: 'Real', activeClass: 'bg-green-500 text-white' },
                        { value: null, label: 'Unknown', activeClass: 'bg-gray-500 text-white' },
                        { value: true, label: 'AI', activeClass: 'bg-purple-500 text-white' },
                      ].map((opt, idx) => (
                    <button
                          key={String(opt.value)}
                          onClick={() => handleAIStatusChange(opt.value)}
                      disabled={savingAIStatus || !canEdit}
                          className={`flex-1 py-1.5 text-[11px] font-semibold transition-all cursor-pointer
                            ${idx > 0 ? 'border-l border-gray-200' : ''}
                            ${isAIGenerated === opt.value
                              ? opt.activeClass
                              : 'bg-white text-gray-400 hover:bg-gray-50'
                      } disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                          {opt.label}
                    </button>
                      ))}
                        </div>
                    {/* Flag / Edit button aligned right */}
                    <div className="w-16 shrink-0 flex justify-end">
                      {!isLocked && (
                    <button
                          onClick={() => setShowImproperModal(true)}
                          className="px-2 py-1 border border-red-200 text-red-500 rounded-lg text-[10px] font-medium hover:bg-red-50 transition cursor-pointer"
                        >
                          ⚠️
                    </button>
              )}
                      {isLocked && !hasPendingRequest && (
                <button
                          onClick={() => setShowEditRequestModal(true)}
                          className="px-2 py-1 bg-amber-500 text-white rounded-lg text-[10px] font-medium hover:bg-amber-600 transition cursor-pointer"
                >
                          ✏️
                </button>
              )}
                    </div>
                  </div>

                  {/* Row 2: Human Visible */}
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider w-20 shrink-0">Human</span>
                    <div className="flex rounded-lg overflow-hidden border border-gray-200 flex-1 max-w-[220px]">
                      {[
                        { value: true, label: 'Visible', activeClass: 'bg-blue-500 text-white' },
                        { value: null, label: 'Unknown', activeClass: 'bg-gray-500 text-white' },
                        { value: false, label: 'Not Visible', activeClass: 'bg-orange-500 text-white' },
                      ].map((opt, idx) => (
                <button
                          key={String(opt.value)}
                          onClick={() => handleHumanVisibleChange(opt.value)}
                          disabled={savingHumanVisible || !canEdit}
                          className={`flex-1 py-1.5 text-[11px] font-semibold transition-all cursor-pointer
                            ${idx > 0 ? 'border-l border-gray-200' : ''}
                            ${humanVisible === opt.value
                              ? opt.activeClass
                              : 'bg-white text-gray-400 hover:bg-gray-50'
                            } disabled:opacity-50 disabled:cursor-not-allowed`}
                        >
                          {opt.label}
                </button>
                      ))}
                    </div>
                    <div className="w-16 shrink-0" />
                  </div>
                </div>
              )}
              
              {/* Navigation buttons */}
              <div className="px-4 py-3 flex gap-2">
                <button
                  onClick={() => handleNavigate(data?.prev_image_id)}
                  disabled={!data?.prev_image_id || saving}
                  className="w-10 h-10 flex items-center justify-center border border-gray-200 text-gray-600 rounded-xl hover:bg-gray-50 transition disabled:opacity-25 disabled:cursor-not-allowed cursor-pointer"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !canEdit}
                  className="flex-1 h-10 border border-indigo-200 text-indigo-700 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-sm font-semibold"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={handleSaveAndNext}
                  disabled={saving || !canEdit}
                  className="flex-[1.5] h-10 bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-600 hover:to-purple-600 text-white rounded-xl transition shadow-sm disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-sm font-semibold"
                >
                  {saving ? 'Saving...' : data?.next_image_id ? 'Save & Next →' : 'Save & Finish ✓'}
                </button>
              </div>
              </div>
            </div>
          </div>

      <MarkImproperModal isOpen={showImproperModal} onClose={() => setShowImproperModal(false)} onConfirm={handleMarkImproper} loading={markingImproper} />
      <RequestEditModal isOpen={showEditRequestModal} onClose={() => setShowEditRequestModal(false)} onConfirm={handleRequestEdit} loading={requestingEdit} />
      <CategoryGuideModal isOpen={showGuideModal} onClose={() => setShowGuideModal(false)} />
    </div>
  );
}
