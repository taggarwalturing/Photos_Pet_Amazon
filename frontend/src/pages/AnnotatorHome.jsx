import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import CategoryGuideModal from '../components/CategoryGuideModal';
import SignedImage from '../components/SignedImage';

export default function AnnotatorHome() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilterState] = useState(() => searchParams.get('filter') || 'all');
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const setFilter = (f) => {
    setFilterState(f);
    setSearchParams((prev) => { prev.set('filter', f); return prev; }, { replace: true });
  };

  // Guide modal state
  const [showGuideModal, setShowGuideModal] = useState(false);

  // Folder filter
  const [selectedFolderIds, setSelectedFolderIds] = useState([]);
  const [folderDropdownOpen, setFolderDropdownOpen] = useState(false);
  const [folderDropdownPos, setFolderDropdownPos] = useState({ top: 0, left: 0 });

  // Duplicate selection
  const [selectedImageIds, setSelectedImageIds] = useState([]);
  const [markingDup, setMarkingDup] = useState(false);

  // Notifications state
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);

  // Notifications are not currently supported in the simplified backend
  const loadNotifications = () => {};
  const loadUnreadCount = () => {};
  const markAsRead = () => {};
  const markAllAsRead = () => {};

  const pollRef = useRef(null);
  const wsRef = useRef(null);
  const loadImagesRef = useRef(null);
  const [checkingLock, setCheckingLock] = useState(null); // image_id being checked

  const loadImages = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page_size', '0'); // fetch all images — no pagination
      if (filter !== 'all') params.set('filter_status', filter);
      
      const res = await api.get(`/annotator/images?${params.toString()}`);
      setData(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [filter]);

  // Keep loadImages ref in sync for use inside WebSocket handler
  useEffect(() => { loadImagesRef.current = loadImages; }, [loadImages]);

  useEffect(() => {
    loadImages();
  }, [loadImages]);

  // ── WebSocket for INSTANT lock updates ──────────────────────────
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${window.location.host}/ws/locks?token=${token}`;

    let ws;
    let reconnectTimer;
    let pingTimer;

    const connect = () => {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Send periodic pings to keep the connection alive (every 20s)
        if (pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 20000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'lock') {
            // Instantly update the specific image to show locked status
            setData(prev => {
              if (!prev || !prev.images) return prev;
              const updated = prev.images.map(img => {
                if (img.id !== msg.image_id) return img;
                return {
                  ...img,
                  locked_by_other: true,
                  lock_type: msg.lock_type, // "in_progress" or "completed"
                  held_by: msg.held_by || '',
                  overall_status: 'locked',
                };
              });
              return { ...prev, images: updated };
            });
          } else if (msg.type === 'unlock') {
            // Image released — do a full silent refresh to restore correct status
            if (loadImagesRef.current) loadImagesRef.current(true);
          }
        } catch {}
      };

      ws.onclose = () => {
        if (pingTimer) clearInterval(pingTimer);
        // Auto-reconnect after 2s
        reconnectTimer = setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
      }
    };
  }, []);

  // Fallback poll every 15s for any missed updates (WS handles real-time)
  useEffect(() => {
    pollRef.current = setInterval(() => {
      loadImages(true);
    }, 15000);
    return () => clearInterval(pollRef.current);
  }, [loadImages]);

  const handleFilterChange = (f) => {
    setFilter(f); // setFilter already resets page to 1
  };

  const toggleFolder = (folderId) => {
    setSelectedFolderIds(prev =>
      prev.includes(folderId) ? prev.filter(id => id !== folderId) : [...prev, folderId]
    );
  };

  const toggleImageSelect = (imgId, e) => {
    e.stopPropagation();
    e.preventDefault();
    setSelectedImageIds(prev =>
      prev.includes(imgId) ? prev.filter(id => id !== imgId) : [...prev, imgId]
    );
  };

  const handleMarkAsDuplicate = async () => {
    if (selectedImageIds.length < 2) return alert('Select at least 2 images (first = parent, rest = duplicates)');
    setMarkingDup(true);
    try {
      await api.post('/annotator/images/mark-duplicates', { image_ids: selectedImageIds });
      setSelectedImageIds([]);
      loadImages();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to mark duplicates');
    }
    setMarkingDup(false);
  };

  // Close folder dropdown on outside click
  useEffect(() => {
    if (!folderDropdownOpen) return;
    const handleClick = (e) => {
      if (!e.target.closest('.annotator-folder-dropdown')) setFolderDropdownOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [folderDropdownOpen]);

  // Pre-check lock status before navigating to image detail
  const handleImageClick = async (imgId) => {
    setCheckingLock(imgId);
    try {
      const res = await api.get(`/annotator/images/${imgId}/lock-status`);
      if (res.data.locked_by_other) {
        loadImages(true);
        const msg = res.data.lock_type === 'in_progress'
          ? `This image is currently being annotated by ${res.data.held_by || 'another annotator'}. The list has been refreshed.`
          : 'This image has already been annotated by another annotator. The list has been refreshed.';
        alert(msg);
        return;
      }
      navigate(`/annotator/image/${imgId}${filter !== 'all' ? `?filter=${filter}` : ''}`);
    } catch (err) {
      // On error, navigate anyway — the detail page will handle it
      navigate(`/annotator/image/${imgId}${filter !== 'all' ? `?filter=${filter}` : ''}`);
    } finally {
      setCheckingLock(null);
    }
  };

  // Stable stats from backend (never change with filter)
  const totalAssigned = data?.total_assigned_to_user || 0;
  const totalCompleted = data?.total_completed_by_user || 0;
  const totalRemaining = data?.total_remaining || 0;

  // Derive unique folders from images for the dropdown
  const allImages = data?.images || [];
  const folderMap = useMemo(() => {
    const m = {};
    allImages.forEach(img => {
      const fid = img.source_folder_id;
      if (fid) m[fid] = (m[fid] || 0) + 1;
    });
    return m;
  }, [allImages]);
  const folderList = useMemo(() =>
    Object.entries(folderMap).map(([id, count]) => ({ folder_id: id, image_count: count })).sort((a, b) => a.folder_id.localeCompare(b.folder_id)),
    [folderMap]
  );

  // Apply folder filter on frontend (images already loaded)
  const filteredImages = useMemo(() => {
    if (selectedFolderIds.length === 0) return allImages;
    return allImages.filter(img => selectedFolderIds.includes(img.source_folder_id));
  }, [allImages, selectedFolderIds]);

  return (
    <div className="min-h-screen mesh-bg">
      {/* Header */}
      <header className="glass sticky top-0 z-10 border-b border-white/30">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center shadow-sm">
              <span className="text-white text-lg">🐾</span>
            </div>
          <div>
              <h1 className="text-lg font-bold text-gray-900">Photo Pets</h1>
              <p className="text-sm text-gray-500">Welcome back, <span className="font-medium text-indigo-600">{user?.username}</span></p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Notification Bell */}
            <div className="relative">
              <button
                onClick={() => {
                  setShowNotifications(!showNotifications);
                  if (!showNotifications) loadNotifications();
                }}
                className="relative p-2 text-gray-500 hover:text-gray-900 hover:bg-white/60 rounded-xl transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center shadow-sm">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              
              {/* Notification Dropdown */}
              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden z-50">
                  <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                    <h3 className="font-semibold text-gray-900 text-sm">Notifications</h3>
                    {unreadCount > 0 && (
                      <button
                        onClick={markAllAsRead}
                        className="text-xs text-indigo-600 hover:text-indigo-700 font-medium cursor-pointer"
                      >
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-80 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <div className="py-8 text-center text-gray-400 text-sm">
                        <svg className="w-8 h-8 mx-auto mb-2 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                        </svg>
                        No notifications yet
                      </div>
                    ) : (
                      notifications.map((n) => (
                        <div
                          key={n.id}
                          onClick={() => {
                            if (!n.is_read) markAsRead(n.id);
                            if (n.image_id) {
                              setShowNotifications(false);
                              navigate(`/annotator/image/${n.image_id}`);
                            }
                          }}
                          className={`px-4 py-3 border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition ${
                            !n.is_read ? 'bg-indigo-50/50' : ''
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                              n.type === 'rework_request' 
                                ? 'bg-amber-100 text-amber-600' 
                                : 'bg-indigo-100 text-indigo-600'
                            }`}>
                              {n.type === 'rework_request' ? (
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                              ) : (
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-900">{n.title}</p>
                              <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.message}</p>
                              <p className="text-[10px] text-gray-400 mt-1">
                                {new Date(n.created_at).toLocaleDateString()}
                              </p>
                            </div>
                            {!n.is_read && (
                              <div className="w-2 h-2 bg-indigo-500 rounded-full shrink-0 mt-1.5" />
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
            
          <button
            onClick={logout}
              className="flex items-center gap-2 px-4 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-white/60 rounded-xl transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            Sign Out
          </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {loading && !data ? (
          <div className="text-center py-16 animate-fade-in">
            <div className="w-10 h-10 border-3 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500 text-sm">Loading images...</p>
          </div>
        ) : !data || (data.assigned_categories || data.categories || []).length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-16 text-center animate-fade-in">
            <div className="w-16 h-16 mx-auto mb-5 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center">
              <svg className="w-8 h-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-700">No categories assigned yet</h3>
            <p className="text-gray-500 mt-1">Ask your admin to assign categories to you.</p>
          </div>
        ) : data.images.length === 0 && data.total === 0 && (data.total_assigned_to_user || 0) === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-16 text-center animate-fade-in">
            <div className="w-16 h-16 mx-auto mb-5 bg-gradient-to-br from-emerald-100 to-teal-100 rounded-2xl flex items-center justify-center">
              <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 13l4 4L19 7" /></svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-700">No images available</h3>
            <p className="text-gray-500 mt-1">All images have been claimed by other annotators.</p>
            <p className="text-sm text-gray-400 mt-2">Check back later for new images.</p>
          </div>
        ) : (
          <>
            {/* Stats Row */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6 stagger-children">
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm animate-slide-up relative overflow-hidden">
                <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-500 opacity-10 rounded-bl-[32px] -mr-1 -mt-1" />
                <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                </div>
                <p className="text-2xl font-bold text-gray-900">{totalAssigned}</p>
                <p className="text-xs text-gray-500 font-medium">Assigned to You</p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm animate-slide-up relative overflow-hidden">
                <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-br from-emerald-500 to-teal-500 opacity-10 rounded-bl-[32px] -mr-1 -mt-1" />
                <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-teal-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                </div>
                <p className="text-2xl font-bold text-emerald-600">{totalCompleted}</p>
                <p className="text-xs text-gray-500 font-medium">Annotated</p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm animate-slide-up relative overflow-hidden">
                
                <div className="w-8 h-8 bg-gradient-to-br from-amber-500 to-orange-500 rounded-lg flex items-center justify-center text-white text-sm mb-2 shadow-sm">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </div>
                <p className="text-2xl font-bold text-amber-600">{totalRemaining}</p>
                <p className="text-xs text-gray-500 font-medium">Remaining</p>
              </div>
            </div>

            {/* Filters & Categories */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 animate-fade-in">
              <div className="flex items-center gap-3">
              <div>
                <h2 className="text-lg font-bold text-gray-800">Your Images</h2>
                <p className="text-sm text-gray-500">
                  {data.total} images &middot; {(data.assigned_categories || data.categories || []).length} categories assigned
                </p>
                </div>
                <button
                  onClick={() => setShowGuideModal(true)}
                  className="px-3 py-1.5 bg-indigo-50 text-indigo-600 border border-indigo-200 rounded-lg text-xs font-semibold hover:bg-indigo-100 transition cursor-pointer flex items-center gap-1.5 self-start mt-0.5"
                  title="View category definitions"
                >
                  📖 Guide
                </button>
              </div>
              
              <div className="flex items-center gap-2 flex-wrap">
                {/* Folder filter dropdown */}
                <div className="relative annotator-folder-dropdown">
                  <button
                    onClick={(e) => {
                      if (folderDropdownOpen) {
                        setFolderDropdownOpen(false);
                      } else {
                        const rect = e.currentTarget.getBoundingClientRect();
                        setFolderDropdownPos({ top: rect.bottom + 4, left: Math.min(rect.left, window.innerWidth - 360) });
                        setFolderDropdownOpen(true);
                      }
                    }}
                    className={`px-3 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer flex items-center gap-1.5 ${
                      selectedFolderIds.length > 0
                        ? 'bg-indigo-100 text-indigo-700 border-indigo-300'
                        : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
                    }`}
                  >
                    <span>📁</span>
                    <span>{selectedFolderIds.length > 0 ? `${selectedFolderIds.length} folder${selectedFolderIds.length > 1 ? 's' : ''}` : 'All Folders'}</span>
                    <svg className={`w-3 h-3 text-gray-400 transition-transform ${folderDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {folderDropdownOpen && (
                    <div
                      className="fixed z-[9999] w-[340px] bg-white border border-gray-200 rounded-xl shadow-2xl max-h-72 overflow-y-auto annotator-folder-dropdown"
                      style={{ top: folderDropdownPos.top, left: folderDropdownPos.left }}
                    >
                      <div className="sticky top-0 px-3 py-2 border-b border-gray-100 bg-gray-50/95 backdrop-blur rounded-t-xl flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Filter by Folder</span>
                        {selectedFolderIds.length > 0 && (
                          <button onClick={() => setSelectedFolderIds([])} className="text-[10px] font-semibold text-red-500 hover:text-red-700 cursor-pointer">Clear</button>
                        )}
                      </div>
                      {folderList.length === 0 ? (
                        <div className="px-3 py-4 text-xs text-gray-400 text-center">No folders</div>
                      ) : (
                        folderList.map(f => {
                          const isSelected = selectedFolderIds.includes(f.folder_id);
                          return (
                            <label key={f.folder_id} className={`flex items-center gap-2.5 px-3 py-2 text-xs border-b border-gray-50 last:border-0 transition-colors cursor-pointer ${isSelected ? 'bg-indigo-50/50' : 'hover:bg-gray-50'}`}>
                              <input type="checkbox" checked={isSelected} onChange={() => toggleFolder(f.folder_id)} className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer shrink-0" />
                              <span className="flex-1 min-w-0 font-medium text-gray-800 truncate" title={f.folder_id}>{f.folder_id}</span>
                              <span className="text-[10px] text-gray-400 font-medium shrink-0">{f.image_count} imgs</span>
                            </label>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>

                <div className="h-4 border-l border-gray-200" />

                {['all', 'pending', 'completed', 'improper'].map((f) => (
                <button
                    key={f}
                    onClick={() => handleFilterChange(f)}
                    className={`px-4 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer capitalize ${
                      filter === f
                        ? f === 'improper'
                          ? 'bg-gradient-to-r from-red-500 to-orange-500 text-white border-red-500 shadow-sm'
                          : 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white border-indigo-500 shadow-sm'
                        : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
                    }`}
                  >
                    {f === 'improper' ? '⚠ Improper' : f}
                  </button>
                ))}
              </div>
            </div>

            {/* Assigned Categories */}
            <div className="bg-gradient-to-r from-indigo-50/80 via-purple-50/50 to-pink-50/30 rounded-xl border border-indigo-100 p-4 mb-6 animate-fade-in">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Your Assigned Categories</p>
              <div className="flex flex-wrap gap-2">
                {(data.assigned_categories || data.categories || []).map((cat) => (
                  <span
                  key={cat.id || cat.key}
                    className="px-3 py-1.5 bg-white/80 text-indigo-700 text-sm font-medium rounded-lg border border-indigo-200/60 shadow-sm"
                >
                    {cat.name}
                  </span>
                ))}
              </div>
            </div>

            {/* Duplicate Selection Action Bar */}
            {selectedImageIds.length > 0 && (
              <div className="flex items-center gap-3 px-4 py-2.5 bg-indigo-50 border border-indigo-200 rounded-xl mb-4 animate-fade-in">
                <span className="text-sm font-medium text-indigo-700">
                  {selectedImageIds.length} image{selectedImageIds.length > 1 ? 's' : ''} selected
                  <span className="ml-1 text-xs text-indigo-500">(1st = parent)</span>
                </span>
                <button
                  onClick={handleMarkAsDuplicate}
                  disabled={markingDup || selectedImageIds.length < 2}
                  className="px-3 py-1.5 text-xs font-semibold text-white bg-red-500 hover:bg-red-600 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition"
                >
                  {markingDup ? 'Marking…' : 'Mark as Duplicate'}
                </button>
                <button
                  onClick={() => setSelectedImageIds([])}
                  className="px-3 py-1.5 text-xs font-semibold text-gray-600 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg cursor-pointer transition"
                >
                  Clear
                </button>
              </div>
            )}

            {/* Image Grid */}
            {filteredImages.length === 0 ? (
              <div className="bg-white rounded-2xl border border-gray-200 p-16 text-center animate-fade-in">
                <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-emerald-100 to-teal-100 rounded-2xl flex items-center justify-center">
                  <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 13l4 4L19 7" /></svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-700">
                  {filter === 'pending' ? 'No pending images' : filter === 'improper' ? 'No improper images' : 'No images found'}
                  </h3>
                <p className="text-gray-500 mt-1">
                  {filter === 'pending' ? 'All pending images have been annotated or marked improper.' : filter === 'improper' ? 'No images have been marked as improper.' : 'Try changing the filter.'}
                </p>
                    </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 stagger-children">
                {filteredImages.map((img) => {
                  const isLockedByOther = img.locked_by_other === true;
                  const lockType = img.lock_type; // "completed" | "in_progress" | null
                  const heldBy = img.held_by || '';
                  const isComplete = img.overall_status === 'completed';
                  const isPartial = img.overall_status === 'partial';
                  const isImproper = img.is_improper;
                  const hasRework = img.has_rework;
                  const isHumanValidated = img.annotation_status === 'completed' && img.review_status === 'approved';
                  const categoryLabels = img.category_labels || {};
                  
                  const isSelected = selectedImageIds.includes(img.id);
                  const selectionIdx = selectedImageIds.indexOf(img.id);

                  return (
                    <button
                      key={img.id}
                      onClick={() => {
                        if (isLockedByOther) return; // Cannot open locked images
                        handleImageClick(img.id);
                      }}
                      disabled={isLockedByOther || checkingLock === img.id}
                      className={`group relative rounded-xl overflow-hidden shadow-md text-left animate-slide-up transition-all duration-300 ${
                        isSelected ? 'ring-3 ring-indigo-500 ' : ''
                      }${
                        checkingLock === img.id
                          ? 'ring-2 ring-indigo-400 opacity-80 cursor-wait'
                          : lockType === 'completed'
                          ? 'ring-2 ring-gray-400 opacity-60 cursor-not-allowed'
                          : lockType === 'in_progress'
                          ? 'ring-2 ring-yellow-400 opacity-70 cursor-not-allowed'
                          : hasRework 
                          ? 'ring-3 ring-orange-400 hover:shadow-xl cursor-pointer' 
                          : isHumanValidated
                            ? 'ring-2 ring-emerald-500 hover:shadow-xl cursor-pointer'
                          : isComplete 
                            ? 'ring-2 ring-blue-400 hover:shadow-xl cursor-pointer' 
                            : 'ring-1 ring-gray-200 hover:ring-indigo-400 hover:shadow-xl cursor-pointer'
                      }`}
                    >
                      {/* Large Image */}
                      <div className="relative aspect-[4/3]">
                        <SignedImage
                          imageId={img.id}
                          alt={img.filename}
                          className="w-full h-full object-cover"
                          loading="lazy"
                          thumbnail
                        />
                        
                        {/* Selection checkbox for duplicate marking */}
                        <div
                          className="absolute bottom-2 right-2 z-20"
                          onClick={(e) => toggleImageSelect(img.id, e)}
                        >
                          <div className={`w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all cursor-pointer shadow-sm ${
                            isSelected ? 'bg-indigo-500 border-indigo-500 text-white' : 'bg-white/80 border-gray-300 hover:border-indigo-400'
                          }`}>
                            {isSelected && <span className="text-[10px] font-bold">{selectionIdx + 1}</span>}
                          </div>
                        </div>
                        {isSelected && selectionIdx === 0 && (
                          <div className="absolute bottom-2 right-10 z-20">
                            <span className="px-1.5 py-0.5 text-[9px] font-bold text-white bg-green-500 rounded-md shadow-sm">PARENT</span>
                          </div>
                        )}

                        {/* Dark gradient overlay for text readability */}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent pointer-events-none" />
                        
                        {/* Status badge - top left */}
                        <div className="absolute top-3 left-3">
                          {lockType === 'completed' ? (
                            <span className="px-2.5 py-1 bg-gray-600 text-white text-xs font-bold rounded-lg shadow-lg flex items-center gap-1">
                              🔒 Taken
                            </span>
                          ) : lockType === 'in_progress' ? (
                            <span className="px-2.5 py-1 bg-yellow-500 text-white text-xs font-bold rounded-lg shadow-lg flex items-center gap-1 animate-pulse" title={heldBy ? `Being annotated by ${heldBy}` : 'Being annotated by another user'}>
                              ⏳ In Progress
                            </span>
                          ) : isImproper ? (
                            <span className="px-2.5 py-1 bg-red-500 text-white text-xs font-bold rounded-lg shadow-lg">
                              ⚠ Improper
                            </span>
                          ) : hasRework ? (
                            <span className="px-2.5 py-1 bg-orange-500 text-white text-xs font-bold rounded-lg shadow-lg animate-pulse">
                              🔄 Rework
                            </span>
                          ) : isHumanValidated ? (
                            <span className="px-2.5 py-1 bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-lg flex items-center gap-1">
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                              </svg>
                              Validated
                            </span>
                          ) : isComplete ? (
                            <span className="px-2.5 py-1 bg-blue-500 text-white text-xs font-bold rounded-lg shadow-lg">
                              📝 To Review
                            </span>
                          ) : isPartial ? (
                            <span className="px-2.5 py-1 bg-amber-500 text-white text-xs font-bold rounded-lg shadow-lg">
                              {img.completed_count}/{img.total_categories}
                            </span>
                          ) : (
                            <span className="px-2.5 py-1 bg-gray-800/80 text-white text-xs font-medium rounded-lg shadow-lg backdrop-blur-sm">
                              Pending
                            </span>
                          )}
                        </div>
                        
                        {/* Filename - top right */}
                        <div className="absolute top-3 right-3 max-w-[65%] flex flex-col items-end gap-0.5">
                          {img.source_folder_id && (
                            <span className="px-2 py-0.5 bg-blue-600/70 text-white text-[9px] font-mono rounded-md backdrop-blur-sm truncate block max-w-full" title={`Folder: ${img.source_folder_id}`}>
                              {img.source_folder_id.slice(0, 16)}…
                            </span>
                          )}
                          <span className="px-2 py-1 bg-black/50 text-white text-[10px] font-medium rounded-lg backdrop-blur-sm truncate block" title={img.filename}>
                            {img.filename}
                          </span>
                        </div>
                        
                        {/* Labels overlay - bottom */}
                        <div className="absolute bottom-0 left-0 right-0 p-3">
                          <div className="flex flex-wrap gap-1.5">
                            {(data.assigned_categories || data.categories || []).map((cat) => {
                              const catKey = cat.key || String(cat.id);
                              const labels = categoryLabels[catKey] || [];
                              const labelSource = (img.category_label_source || {})[catKey];
                              const status = (img.category_status || {})[catKey];
                              const needsRework = status === 'in_progress' && hasRework;
                              const isAiLabel = labelSource === 'ai';
                              
                              if (labels.length === 0) {
                                return (
                                  <span 
                                    key={catKey}
                                    className="px-2 py-1 bg-gray-900/60 text-gray-400 text-[10px] rounded-md backdrop-blur-sm border border-gray-600/50"
                                    title={`${cat.name}: Not set`}
                                  >
                                    {cat.name.split(' ')[0]}: <span className="italic">?</span>
                                  </span>
                                );
                              }
                              
                              return labels.map((label, i) => (
                                <span 
                                  key={`${catKey}-${i}`}
                                  className={`px-2 py-1 text-[11px] font-medium rounded-md backdrop-blur-sm border ${
                                    needsRework
                                      ? 'bg-orange-500/80 text-white border-orange-400'
                                      : isAiLabel
                                        ? 'bg-purple-500/80 text-white border-purple-400'
                                      : label === 'None of the Above'
                                        ? 'bg-gray-700/80 text-gray-300 border-gray-600'
                                        : 'bg-indigo-500/80 text-white border-indigo-400'
                                  }`}
                                  title={`${cat.name}${isAiLabel ? ' (AI predicted)' : ''}`}
                                >
                                  {label}
                                </span>
                              ));
                            })}
                          </div>
                        </div>
                        
                        {/* Hover overlay with edit icon */}
                        <div className="absolute inset-0 bg-indigo-600/30 opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-center justify-center">
                          <span className="w-14 h-14 bg-white rounded-full flex items-center justify-center shadow-2xl transform scale-90 group-hover:scale-100 transition-transform">
                            <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                            </svg>
                          </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
            )}

          </>
        )}
      </main>

      <CategoryGuideModal isOpen={showGuideModal} onClose={() => setShowGuideModal(false)} />
    </div>
  );
}
