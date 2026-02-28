import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import MasterPipelineTab from '../components/MasterPipelineTab';

const PAGE_SIZE = 10;

// Helper to get proxied image URL for Google Drive images
const getImageUrl = (imageId) => {
  if (!imageId) return '';
  // Add timestamp to prevent caching of processed images
  return `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/images/proxy/${imageId}?t=${Date.now()}`;
};

/* ─── Reusable UI Helpers ──────────────────────────────────── */

function Avatar({ name, size = 'sm' }) {
  const colors = [
    'from-indigo-500 to-purple-500',
    'from-emerald-500 to-teal-500',
    'from-amber-500 to-orange-500',
    'from-rose-500 to-pink-500',
    'from-cyan-500 to-blue-500',
    'from-violet-500 to-fuchsia-500',
  ];
  const idx = (name || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % colors.length;
  const dims = size === 'lg' ? 'w-10 h-10 text-sm' : size === 'md' ? 'w-8 h-8 text-xs' : 'w-6 h-6 text-[10px]';
  return (
    <div className={`${dims} rounded-full bg-gradient-to-br ${colors[idx]} flex items-center justify-center text-white font-bold shrink-0 shadow-sm`}>
      {(name || '?')[0].toUpperCase()}
    </div>
  );
}

function Badge({ children, variant = 'default' }) {
  const styles = {
    default: 'bg-gray-100 text-gray-600',
    primary: 'bg-indigo-100 text-indigo-700',
    success: 'bg-emerald-100 text-emerald-700',
    warning: 'bg-amber-100 text-amber-700',
    danger: 'bg-red-100 text-red-700',
    purple: 'bg-purple-100 text-purple-700',
    info: 'bg-sky-100 text-sky-700',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${styles[variant] || styles.default}`}>
      {children}
    </span>
  );
}

function LoadingSkeleton({ rows = 5 }) {
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="skeleton h-8 w-48" />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton h-14 w-full" style={{ animationDelay: `${i * 100}ms` }} />
        ))}
      </div>
    </div>
  );
}

function Pagination({ currentPage, totalPages, onPageChange }) {
  if (totalPages <= 1) return null;

  const getPages = () => {
    const pages = [];
    const maxVisible = 5;
    let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let end = Math.min(totalPages, start + maxVisible - 1);
    if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1);
    if (start > 1) { pages.push(1); if (start > 2) pages.push('...'); }
    for (let i = start; i <= end; i++) pages.push(i);
    if (end < totalPages) { if (end < totalPages - 1) pages.push('...'); pages.push(totalPages); }
    return pages;
  };

  return (
    <div className="flex items-center justify-center gap-1 pt-4">
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="px-2.5 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
      >
        &larr; Prev
      </button>
      {getPages().map((p, i) =>
        p === '...' ? (
          <span key={`ellipsis-${i}`} className="px-2 text-gray-400 text-sm">...</span>
        ) : (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            className={`w-8 h-8 text-sm rounded-lg cursor-pointer transition ${
              p === currentPage
                ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white font-medium shadow-sm'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {p}
          </button>
        )
      )}
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="px-2.5 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
      >
        Next &rarr;
      </button>
    </div>
  );
}

// ─── Users Tab ────────────────────────────────────────────────

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [categories, setCategories] = useState([]);
  const [imageAssignments, setImageAssignments] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editingAssignment, setEditingAssignment] = useState(null); // user id for category assignment
  const [editingImageAssignment, setEditingImageAssignment] = useState(null); // user id for image assignment
  const [imageCount, setImageCount] = useState(10);
  const [form, setForm] = useState({ username: '', password: '', full_name: '', role: 'annotator' });
  const [showPassword, setShowPassword] = useState(false);
  const [assignedCats, setAssignedCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);

  const generatePassword = () => {
    const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*';
    let pw = '';
    for (let i = 0; i < 14; i++) pw += chars[Math.floor(Math.random() * chars.length)];
    setForm((f) => ({ ...f, password: pw }));
    setShowPassword(true);
  };

  const load = async () => {
    try {
      const [usersRes, catsRes, assignmentsRes] = await Promise.all([
        api.get('/admin/users'),
        api.get('/admin/categories'),
        api.get('/admin/images/assignments'),
      ]);
      setUsers(usersRes.data);
      setCategories(catsRes.data);
      setImageAssignments(assignmentsRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const createUser = async (e) => {
    e.preventDefault();
    try {
      await api.post('/admin/users', form);
      setShowCreate(false);
      setShowPassword(false);
      setForm({ username: '', password: '', full_name: '', role: 'annotator' });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error');
    }
  };

  const toggleActive = async (user) => {
    await api.put(`/admin/users/${user.id}`, { is_active: !user.is_active });
    load();
  };

  const openAssignment = (user) => {
    setEditingAssignment(user.id);
    setAssignedCats(user.assigned_category_ids || []);
  };

  const saveAssignment = async () => {
    await api.put(`/admin/users/${editingAssignment}/categories`, { category_ids: assignedCats });
    setEditingAssignment(null);
    load();
  };

  const toggleCat = (catId) => {
    setAssignedCats((prev) =>
      prev.includes(catId) ? prev.filter((id) => id !== catId) : [...prev, catId]
    );
  };

  // Image assignment functions
  const getUserImageCount = (userId) => {
    if (!imageAssignments) return 0;
    const userAssignment = imageAssignments.by_user.find((u) => u.user_id === userId);
    return userAssignment?.count || 0;
  };

  const openImageAssignment = (user) => {
    setEditingImageAssignment(user.id);
    setImageCount(10);
  };

  const assignImages = async () => {
    if (assigning) return;
    setAssigning(true);
    try {
      await api.post(`/admin/users/${editingImageAssignment}/images/assign`, { count: imageCount });
      setEditingImageAssignment(null);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error assigning images');
    } finally {
      setAssigning(false);
    }
  };

  const unassignAllImages = async (userId) => {
    if (!confirm('Are you sure you want to unassign all images from this user?')) return;
    try {
      await api.delete(`/admin/users/${userId}/images/unassign`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error');
    }
  };

  if (loading) return <LoadingSkeleton rows={6} />;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Users & Assignments</h2>
          <p className="text-sm text-gray-500 mt-0.5">{users.filter(u => u.role === 'annotator').length} annotators, {users.filter(u => u.role === 'admin').length} admins</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white text-sm font-medium rounded-lg hover:from-indigo-600 hover:to-purple-600 transition shadow-sm cursor-pointer"
        >
          + New Annotator
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <form onSubmit={createUser} className="bg-gradient-to-br from-indigo-50/80 to-purple-50/50 rounded-xl border border-indigo-100 p-5 space-y-4 animate-slide-up">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                type="text"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-gray-700">Password</label>
                <button
                  type="button"
                  onClick={generatePassword}
                  className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Generate
                </button>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer"
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L6.59 6.59m7.532 7.532l3.29 3.29M3 3l18 18" />
                    </svg>
                  ) : (
                    <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="annotator">Annotator</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 cursor-pointer">
              Create
            </button>
            <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded-lg hover:bg-gray-300 cursor-pointer">
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Image Assignment Summary */}
      {imageAssignments && (
        <div className="bg-gradient-to-r from-indigo-50 via-purple-50 to-pink-50 rounded-xl border border-indigo-100 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-lg flex items-center justify-center text-white shadow-sm">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Image Assignment Summary</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  {imageAssignments.assigned_count} of {imageAssignments.total_images} images assigned
                  {imageAssignments.unassigned_count > 0 && (
                    <span className="text-amber-600 ml-1 font-medium">
                      ({imageAssignments.unassigned_count} available)
                    </span>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-32 bg-white/80 rounded-full h-2.5 shadow-inner">
                <div
                  className="bg-gradient-to-r from-indigo-500 to-purple-500 h-2.5 rounded-full transition-all animate-progress"
                  style={{ width: `${imageAssignments.total_images > 0 ? (imageAssignments.assigned_count / imageAssignments.total_images) * 100 : 0}%` }}
                />
              </div>
              <span className="text-xs font-medium text-indigo-600">
                {imageAssignments.total_images > 0 ? Math.round((imageAssignments.assigned_count / imageAssignments.total_images) * 100) : 0}%
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Users table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gradient-to-r from-gray-50 to-gray-50/80 text-gray-600 text-left">
              <th className="px-5 py-3.5 font-semibold">Username</th>
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Role</th>
              <th className="px-5 py-3 font-medium">Categories</th>
              <th className="px-5 py-3 font-medium">Images</th>
              <th className="px-5 py-3 font-medium">Progress</th>
              <th className="px-5 py-3 font-medium">Improper</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => {
              const userImageCount = getUserImageCount(u.id);
              return (
                <tr key={u.id} className={`transition-colors hover:bg-gray-50/50 ${!u.is_active ? 'opacity-50' : ''}`}>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={u.username} size="sm" />
                      <span className="font-medium text-gray-900">{u.username}</span>
                    </div>
                  </td>
                <td className="px-5 py-3 text-gray-600">{u.full_name || '—'}</td>
                <td className="px-5 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
                  }`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-600">
                  {u.role === 'annotator' ? (
                    <div className="flex flex-wrap gap-1">
                      {u.assigned_category_ids.length === 0 ? (
                        <span className="text-gray-400">None</span>
                      ) : (
                        u.assigned_category_ids.map((catId) => {
                          const cat = categories.find((c) => c.id === catId);
                          return (
                            <span key={catId} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full">
                              {cat?.name || catId}
                            </span>
                          );
                        })
                      )}
                    </div>
                  ) : '—'}
                </td>
                  <td className="px-5 py-3">
                    {u.role === 'annotator' ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        userImageCount > 0 ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {userImageCount} images
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-5 py-3">
                    {u.role === 'annotator' ? (
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <div className="w-20 bg-gray-200 rounded-full h-2">
                            <div
                              className="bg-indigo-500 h-2 rounded-full transition-all"
                              style={{ width: `${u.total_annotations_needed > 0 ? Math.min(100, (u.completed_annotations / u.total_annotations_needed) * 100) : 0}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">
                            {u.total_annotations_needed > 0 ? Math.round((u.completed_annotations / u.total_annotations_needed) * 100) : 0}%
                          </span>
                        </div>
                        <span className="text-[10px] text-gray-400">
                          {u.completed_annotations}/{u.total_annotations_needed} annotations
                        </span>
                      </div>
                    ) : '—'}
                  </td>
                  <td className="px-5 py-3">
                    {u.role === 'annotator' ? (
                      u.improper_marked_count > 0 ? (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                          {u.improper_marked_count} marked
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">None</span>
                      )
                    ) : '—'}
                  </td>
                <td className="px-5 py-3">
                  <span className={`text-xs font-medium ${u.is_active ? 'text-green-600' : 'text-red-500'}`}>
                    {u.is_active ? 'Active' : 'Disabled'}
                  </span>
                </td>
                <td className="px-5 py-3">
                    <div className="flex gap-2 flex-wrap">
                    {u.role === 'annotator' && (
                        <>
                      <button
                        onClick={() => openAssignment(u)}
                        className="text-indigo-600 hover:text-indigo-800 text-xs font-medium cursor-pointer"
                      >
                            Categories
                          </button>
                          <button
                            onClick={() => openImageAssignment(u)}
                            className="text-emerald-600 hover:text-emerald-800 text-xs font-medium cursor-pointer"
                          >
                            + Images
                          </button>
                          {userImageCount > 0 && (
                            <button
                              onClick={() => unassignAllImages(u.id)}
                              className="text-amber-600 hover:text-amber-800 text-xs font-medium cursor-pointer"
                            >
                              Clear
                      </button>
                          )}
                        </>
                    )}
                    <button
                      onClick={() => toggleActive(u)}
                      className={`text-xs font-medium cursor-pointer ${u.is_active ? 'text-red-500 hover:text-red-700' : 'text-green-600 hover:text-green-800'}`}
                    >
                      {u.is_active ? 'Disable' : 'Enable'}
                    </button>
                  </div>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Assignment modal */}
      {editingAssignment && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md animate-scale-in">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Assign Categories
            </h3>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {categories.map((cat) => {
                const checked = assignedCats.includes(cat.id);
                return (
                  <label
                    key={cat.id}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg border-2 cursor-pointer transition ${
                      checked ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleCat(cat.id)}
                      className="sr-only"
                    />
                    <div className={`w-5 h-5 rounded flex items-center justify-center border-2 shrink-0 ${
                      checked ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300'
                    }`}>
                      {checked && (
                        <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span className="text-sm font-medium text-gray-800">{cat.name}</span>
                  </label>
                );
              })}
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={saveAssignment}
                className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 cursor-pointer"
              >
                Save
              </button>
              <button
                onClick={() => setEditingAssignment(null)}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-300 cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Image Assignment modal */}
      {editingImageAssignment && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md animate-scale-in">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Assign Images
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Assign unassigned images to{' '}
              <span className="font-medium text-gray-900">
                {users.find((u) => u.id === editingImageAssignment)?.username}
              </span>
            </p>
            
            {imageAssignments && (
              <div className="bg-gray-50 rounded-lg p-3 mb-4">
                <p className="text-xs text-gray-600">
                  <span className="font-semibold text-emerald-600">{imageAssignments.unassigned_count}</span> images available for assignment
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Each image can only be assigned to one annotator
                </p>
              </div>
            )}

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Number of images to assign
              </label>
              <input
                type="number"
                min="1"
                max={imageAssignments?.unassigned_count || 100}
                value={imageCount}
                onChange={(e) => setImageCount(parseInt(e.target.value) || 1)}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                Images will be assigned in order (lowest ID first)
              </p>
            </div>

            {/* Quick buttons */}
            <div className="flex gap-2 mb-4">
              {[5, 10, 20, 50].map((n) => (
                <button
                  key={n}
                  onClick={() => setImageCount(n)}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition cursor-pointer ${
                    imageCount === n
                      ? 'bg-emerald-500 text-white border-emerald-500'
                      : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
                  }`}
                >
                  {n}
                </button>
              ))}
              {imageAssignments?.unassigned_count > 0 && (
                <button
                  onClick={() => setImageCount(imageAssignments.unassigned_count)}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition cursor-pointer ${
                    imageCount === imageAssignments.unassigned_count
                      ? 'bg-emerald-500 text-white border-emerald-500'
                      : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
                  }`}
                >
                  All ({imageAssignments.unassigned_count})
                </button>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={assignImages}
                disabled={assigning || imageCount <= 0 || (imageAssignments?.unassigned_count || 0) === 0}
                className="flex-1 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {assigning ? 'Assigning...' : `Assign ${imageCount} Images`}
              </button>
              <button
                onClick={() => setEditingImageAssignment(null)}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-300 cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Progress Tab ─────────────────────────────────────────────

function ProgressTab() {
  const [progress, setProgress] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/admin/progress').then((res) => {
      setProgress(res.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <LoadingSkeleton rows={6} />;

  if (progress.length === 0) {
    return (
      <div className="py-16 text-center animate-fade-in">
        <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-2xl flex items-center justify-center">
          <svg className="w-8 h-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
        </div>
        <p className="text-lg font-medium text-gray-700">No assignments yet</p>
        <p className="text-sm text-gray-500 mt-1">Create annotators and assign categories to see progress here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-lg font-bold text-gray-900">Annotation Progress</h2>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gradient-to-r from-gray-50 to-gray-50/80 text-gray-600 text-left">
              <th className="px-5 py-3.5 font-semibold">Annotator</th>
              <th className="px-5 py-3.5 font-semibold">Category</th>
              <th className="px-5 py-3.5 font-semibold">Progress</th>
              <th className="px-5 py-3.5 font-semibold">Completed</th>
              <th className="px-5 py-3.5 font-semibold">Skipped</th>
              <th className="px-5 py-3.5 font-semibold">Pending</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {progress.map((p, i) => {
              const pct = p.total_images > 0 ? Math.round((p.completed / p.total_images) * 100) : 0;
              return (
                <tr key={i} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <Avatar name={p.annotator_username} size="sm" />
                      <span className="font-medium text-gray-900">{p.annotator_username}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3"><Badge variant="primary">{p.category_name}</Badge></td>
                  <td className="px-5 py-3 w-48">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-200 rounded-full h-2">
                        <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-2 rounded-full animate-progress" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs text-gray-500 w-10 text-right">{pct}%</span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-green-600 font-medium">{p.completed}</td>
                  <td className="px-5 py-3 text-amber-600">{p.skipped}</td>
                  <td className="px-5 py-3 text-gray-500">{p.pending}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Image Completion Tab ─────────────────────────────────────

function ImageCompletionTab() {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all, complete, incomplete
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.get('/admin/images/completion').then((res) => {
      setImages(res.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <LoadingSkeleton rows={4} />;

  const filtered = images.filter((img) => {
    if (filter === 'complete') return img.is_fully_complete;
    if (filter === 'incomplete') return !img.is_fully_complete;
    return true;
  });

  const totalComplete = images.filter((img) => img.is_fully_complete).length;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paginatedImages = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const handleFilterChange = (f) => {
    setFilter(f);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Image Completion Status</h2>
          <p className="text-sm text-gray-500 mt-1">
            {totalComplete} / {images.length} images fully annotated across all categories
          </p>
        </div>
        <div className="flex gap-2">
          {['all', 'incomplete', 'complete'].map((f) => (
            <button
              key={f}
              onClick={() => handleFilterChange(f)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer ${
                filter === f
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
              }`}
            >
              {f === 'all' ? `All (${images.length})` : f === 'complete' ? `Complete (${totalComplete})` : `Incomplete (${images.length - totalComplete})`}
            </button>
          ))}
        </div>
      </div>

      {/* Overall progress bar */}
      <div className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-xl p-5 text-white shadow-lg">
        <div className="flex justify-between text-sm mb-3">
          <span className="font-medium">Overall Completion</span>
          <span className="text-lg font-bold">{images.length > 0 ? Math.round((totalComplete / images.length) * 100) : 0}%</span>
        </div>
        <div className="w-full bg-white/20 rounded-full h-3">
          <div
            className="bg-white h-3 rounded-full transition-all animate-progress"
            style={{ width: `${images.length > 0 ? (totalComplete / images.length) * 100 : 0}%` }}
          />
        </div>
        <p className="text-sm text-white/70 mt-2">{totalComplete} of {images.length} images fully annotated</p>
      </div>

      {/* Image cards */}
      <div className="space-y-3">
        {paginatedImages.map((img) => {
          const pct = img.total_categories > 0
            ? Math.round((img.completed_categories / img.total_categories) * 100)
            : 0;
          return (
            <div key={img.image_id} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-start gap-4">
                <img
                  src={getImageUrl(img.image_id)}
                  alt={img.image_filename}
                  className="w-20 h-20 rounded-lg object-cover shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 text-sm">{img.image_filename}</span>
                      {img.is_fully_complete ? (
                        <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs font-medium rounded-full">
                          Complete
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded-full">
                          {img.completed_categories}/{img.total_categories} categories
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-500">{pct}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mb-3">
                    <div
                      className={`h-1.5 rounded-full transition-all ${img.is_fully_complete ? 'bg-green-500' : 'bg-indigo-500'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {img.category_details.map((cat) => (
                      <span
                        key={cat.category_id}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                          cat.status === 'completed'
                            ? 'bg-green-50 text-green-700'
                            : cat.status === 'skipped'
                              ? 'bg-amber-50 text-amber-700'
                              : cat.status === 'in_progress'
                                ? 'bg-blue-50 text-blue-700'
                                : cat.status === 'unassigned'
                                  ? 'bg-red-50 text-red-500 border border-red-200 border-dashed'
                                  : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {cat.status === 'completed' && (
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {cat.category_name}
                        {cat.annotator_username && (
                          <span className="opacity-60">({cat.annotator_username})</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>Showing {((safePage - 1) * PAGE_SIZE) + 1}–{Math.min(safePage * PAGE_SIZE, filtered.length)} of {filtered.length}</span>
        <Pagination currentPage={safePage} totalPages={totalPages} onPageChange={setPage} />
      </div>
    </div>
  );
}

// ─── Images Tab ───────────────────────────────────────────────

function ImagesTab() {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const imagesPerPage = 20;

  useEffect(() => {
    api.get('/admin/images').then((res) => {
      setImages(res.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <LoadingSkeleton rows={3} />;

  const totalPages = Math.max(1, Math.ceil(images.length / imagesPerPage));
  const safePage = Math.min(page, totalPages);
  const paginatedImages = images.slice((safePage - 1) * imagesPerPage, safePage * imagesPerPage);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Images ({images.length})</h2>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {paginatedImages.map((img) => (
          <div key={img.id} className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
            <img src={getImageUrl(img.id)} alt={img.filename} className="w-full h-32 object-cover" />
            <div className="px-3 py-2">
              <p className="text-xs text-gray-500 truncate">{img.filename}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>Showing {((safePage - 1) * imagesPerPage) + 1}–{Math.min(safePage * imagesPerPage, images.length)} of {images.length}</span>
        <Pagination currentPage={safePage} totalPages={totalPages} onPageChange={setPage} />
      </div>
    </div>
  );
}

// ─── Review Tab ──────────────────────────────────────────────

function CellEditPopover({ cell, onSave, onApprove, onClose }) {
  const [selections, setSelections] = useState(cell.selected_options.map((o) => o.id));
  const [isDuplicate, setIsDuplicate] = useState(cell.is_duplicate);
  const popoverRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const toggleOpt = (id) => {
    setSelections((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  };

  const hasChanges = () => {
    const origIds = new Set(cell.selected_options.map((o) => o.id));
    if (selections.length !== origIds.size) return true;
    for (const id of selections) { if (!origIds.has(id)) return true; }
    if (isDuplicate !== cell.is_duplicate) return true;
    return false;
  };

  return (
    <div ref={popoverRef} className="absolute z-50 top-full left-0 mt-1 w-72 bg-white rounded-xl shadow-xl border border-gray-200 p-3" onClick={(e) => e.stopPropagation()}>
      <p className="text-xs font-semibold text-gray-700 mb-2">Edit selections:</p>
      <div className="space-y-1 max-h-52 overflow-y-auto mb-3">
        {cell.all_options.map((opt) => {
          const checked = selections.includes(opt.id);
          return (
            <label key={opt.id} className={`flex items-center gap-2 px-2 py-1.5 rounded-lg border cursor-pointer transition text-xs ${checked ? 'border-indigo-400 bg-indigo-50 text-indigo-900' : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'}`}>
              <input type="checkbox" checked={checked} onChange={() => toggleOpt(opt.id)} className="sr-only" />
              <div className={`w-3.5 h-3.5 rounded flex items-center justify-center border shrink-0 ${checked ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300'}`}>
                {checked && <svg className="w-2 h-2 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
              </div>
              <span>{opt.label}</span>
              {opt.is_typical && <span className="ml-auto text-[10px] bg-gray-100 text-gray-500 px-1 py-0.5 rounded-full">typical</span>}
            </label>
          );
        })}
      </div>
      <label className="flex items-center gap-2 px-2 py-1.5 rounded-lg border border-gray-200 cursor-pointer text-xs mb-3">
        <input type="checkbox" checked={isDuplicate || false} onChange={() => setIsDuplicate((v) => !v)} className="accent-red-500 w-3.5 h-3.5" />
        <span className="text-gray-700">Is Duplicate?</span>
      </label>
      <div className="flex gap-2">
        {hasChanges() ? (
          <button onClick={() => onSave(cell.annotation_id, selections, isDuplicate)} className="flex-1 px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 cursor-pointer">Save & Approve</button>
        ) : (
          <button onClick={() => onApprove(cell.annotation_id)} className="flex-1 px-3 py-1.5 bg-green-500 text-white text-xs font-medium rounded-lg hover:bg-green-600 cursor-pointer">Approve</button>
        )}
        <button onClick={onClose} className="px-3 py-1.5 bg-gray-200 text-gray-700 text-xs rounded-lg hover:bg-gray-300 cursor-pointer">Cancel</button>
      </div>
    </div>
  );
}

// ─── Image Detail Modal (split-view) ─────────────────────────

function ImageDetailModal({ row, categories, tableImages, onApprove, onSaveEdits, onRework, onClose, onNavigate }) {
  // Local edit state: map of category_id -> { selections: [...], isDuplicate }
  const [edits, setEdits] = useState({});
  const [saving, setSaving] = useState(false);

  // Reset edits when image changes
  useEffect(() => {
    setEdits({});
  }, [row.image_id]);

  const getEditsForCat = (catId) => {
    if (edits[catId]) return edits[catId];
    const cell = row.annotations[String(catId)];
    if (!cell) return null;
    return {
      selections: cell.selected_options.map((o) => o.id),
      isDuplicate: cell.is_duplicate,
    };
  };

  const setEditForCat = (catId, field, value) => {
    setEdits((prev) => {
      const cell = row.annotations[String(catId)];
      const current = prev[catId] || {
        selections: cell.selected_options.map((o) => o.id),
        isDuplicate: cell.is_duplicate,
      };
      return { ...prev, [catId]: { ...current, [field]: value } };
    });
  };

  const toggleOption = (catId, optId) => {
    const current = getEditsForCat(catId);
    if (!current) return;
    const newSels = current.selections.includes(optId)
      ? current.selections.filter((id) => id !== optId)
      : [...current.selections, optId];
    setEditForCat(catId, 'selections', newSels);
  };

  const hasChangesForCat = (catId) => {
    const cell = row.annotations[String(catId)];
    if (!cell || !edits[catId]) return false;
    const origIds = new Set(cell.selected_options.map((o) => o.id));
    const newIds = edits[catId].selections;
    if (newIds.length !== origIds.size) return true;
    for (const id of newIds) { if (!origIds.has(id)) return true; }
    if (edits[catId].isDuplicate !== cell.is_duplicate) return true;
    return false;
  };

  const hasAnyChanges = categories.some((cat) => hasChangesForCat(cat.id));

  const pendingAnnotations = categories
    .filter((cat) => {
      const cell = row.annotations[String(cat.id)];
      // Include null/undefined, rework_requested, and rework_completed as "pending" (approvable)
      return cell && cell.review_status !== 'approved';
    })
    .map((cat) => row.annotations[String(cat.id)]);

  // Get all completed annotations (including approved) for rework option
  const allAnnotations = categories
    .filter((cat) => {
      const cell = row.annotations[String(cat.id)];
      return cell && cell.annotation_id;
    })
    .map((cat) => row.annotations[String(cat.id)]);

  const handleApproveAll = async () => {
    setSaving(true);
    try {
      for (const cell of pendingAnnotations) {
        if (hasChangesForCat(String(cell.annotation_id))) continue;
        await onApprove(cell.annotation_id);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      // Save changed categories
      for (const cat of categories) {
        if (hasChangesForCat(cat.id)) {
          const cell = row.annotations[String(cat.id)];
          const e = edits[cat.id];
          await onSaveEdits(cell.annotation_id, e.selections, e.isDuplicate);
        }
      }
      // Approve unchanged pending ones
      for (const cell of pendingAnnotations) {
        const catId = categories.find((c) => row.annotations[String(c.id)]?.annotation_id === cell.annotation_id)?.id;
        if (catId && !hasChangesForCat(catId)) {
          await onApprove(cell.annotation_id);
        }
      }
    } finally {
      setSaving(false);
      setEdits({});
    }
  };

  // Current index for navigation
  const currentIdx = tableImages.findIndex((img) => img.image_id === row.image_id);

  return (
    <div className="fixed inset-0 z-50 flex bg-black/60" onClick={onClose}>
      <div className="flex w-full h-full" onClick={(e) => e.stopPropagation()}>
        {/* Left panel: Large image */}
        <div className="w-[55%] bg-gray-900 flex flex-col">
          <div className="flex items-center justify-between px-6 py-3">
            <span className="text-white/80 text-sm font-medium">{row.image_filename}</span>
            <span className="text-white/50 text-xs">{currentIdx + 1} / {tableImages.length}</span>
          </div>
          <div className="flex-1 flex items-center justify-center p-4 relative">
            {/* Nav arrows */}
            {currentIdx > 0 && (
              <button
                onClick={() => onNavigate(tableImages[currentIdx - 1])}
                className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              </button>
            )}
            <img src={getImageUrl(row.image_id)} alt={row.image_filename} className="max-w-full max-h-full object-contain rounded-lg" />
            {currentIdx < tableImages.length - 1 && (
              <button
                onClick={() => onNavigate(tableImages[currentIdx + 1])}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </button>
            )}
          </div>
        </div>

        {/* Right panel: Categories + options */}
        <div className="w-[45%] bg-white flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
            <div className="flex items-center gap-3">
            <h3 className="text-sm font-semibold text-gray-900">Annotations</h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-400 bg-gray-100 px-2 py-1 rounded">Esc to close</span>
              <button onClick={onClose} className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg cursor-pointer">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
          </div>

          {/* Scrollable category list */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
            {categories.map((cat) => {
              const cell = row.annotations[String(cat.id)];
              if (!cell) {
                return (
                  <div key={cat.id} className="opacity-50">
                    <h4 className="text-xs font-semibold text-gray-700 mb-1">{cat.name}</h4>
                    <p className="text-xs text-gray-400 italic">Not annotated</p>
                  </div>
                );
              }
              const currentEdits = getEditsForCat(cat.id);
              const changed = hasChangesForCat(cat.id);
              return (
                <div key={cat.id} className={`rounded-xl border p-3 ${changed ? 'border-indigo-300 bg-indigo-50/30' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <h4 className="text-xs font-semibold text-gray-800">{cat.name}</h4>
                    {cell.review_status === 'approved' ? (
                      <span className="px-1.5 py-0.5 bg-green-100 text-green-700 text-[10px] font-medium rounded-full">Approved</span>
                    ) : cell.review_status === 'rework_requested' ? (
                      <span className="px-1.5 py-0.5 bg-orange-100 text-orange-700 text-[10px] font-medium rounded-full">🔄 Awaiting Rework</span>
                    ) : cell.review_status === 'rework_completed' ? (
                      <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-[10px] font-medium rounded-full">✅ Rework Done</span>
                    ) : (
                      <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[10px] font-medium rounded-full">Pending</span>
                    )}
                    <span className="text-[10px] text-gray-400 ml-auto">
                      {cell.annotator_username}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {cell.all_options.map((opt) => {
                      const checked = currentEdits?.selections.includes(opt.id);
                      return (
                        <label key={opt.id} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border cursor-pointer transition text-xs ${checked ? 'border-indigo-400 bg-indigo-50 text-indigo-900' : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'}`}>
                          <input type="checkbox" checked={checked || false} onChange={() => toggleOption(cat.id, opt.id)} className="sr-only" />
                          <div className={`w-3.5 h-3.5 rounded flex items-center justify-center border shrink-0 ${checked ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300'}`}>
                            {checked && <svg className="w-2 h-2 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                          </div>
                          <span>{opt.label}</span>
                          {opt.is_typical && <span className="ml-auto text-[10px] bg-gray-100 text-gray-500 px-1 py-0.5 rounded-full">typical</span>}
                        </label>
                      );
                    })}
                  </div>
                  <label className="flex items-center gap-2 mt-2 px-2.5 py-1.5 rounded-lg border border-gray-200 cursor-pointer text-xs">
                    <input type="checkbox" checked={currentEdits?.isDuplicate || false} onChange={() => setEditForCat(cat.id, 'isDuplicate', !currentEdits?.isDuplicate)} className="accent-red-500 w-3.5 h-3.5" />
                    <span className="text-gray-700">Is Duplicate?</span>
                  </label>
                </div>
              );
            })}
          </div>

          {/* Bottom action bar */}
          <div className="border-t border-gray-200 px-5 py-3 flex items-center gap-3 bg-gray-50">
            {hasAnyChanges ? (
              <button
                onClick={handleSaveAll}
                disabled={saving}
                className="flex-1 px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 cursor-pointer"
              >
                {saving ? 'Saving...' : 'Save Changes & Approve All'}
              </button>
            ) : pendingAnnotations.length > 0 ? (
              <>
              <button
                onClick={handleApproveAll}
                disabled={saving}
                className="flex-1 px-4 py-2 bg-green-500 text-white text-sm font-medium rounded-lg hover:bg-green-600 disabled:opacity-50 cursor-pointer"
              >
                  {saving ? 'Approving...' : `Approve All (${pendingAnnotations.length})`}
              </button>
                <button
                  onClick={() => onRework(pendingAnnotations[0]?.annotation_id)}
                  disabled={saving}
                  className="px-4 py-2 border border-amber-300 text-amber-600 text-sm font-medium rounded-lg hover:bg-amber-50 disabled:opacity-50 cursor-pointer"
                >
                  Send for Rework
                </button>
              </>
            ) : (
              <>
                <span className="flex-1 text-center text-sm text-green-600 font-medium">✓ All categories approved</span>
                {allAnnotations.length > 0 && (
                  <button
                    onClick={() => onRework(allAnnotations[0]?.annotation_id)}
                    disabled={saving}
                    className="px-4 py-2 border border-amber-300 text-amber-600 text-sm font-medium rounded-lg hover:bg-amber-50 disabled:opacity-50 cursor-pointer"
                  >
                    Send for Rework
                  </button>
                )}
              </>
            )}
            <span className="text-[10px] text-gray-400 bg-gray-100 px-2 py-1 rounded">A = approve</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Keyboard shortcuts help ─────────────────────────────────

function ShortcutsHelp({ show, onClose }) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl p-5 w-80" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Keyboard Shortcuts</h3>
        <div className="space-y-2 text-xs">
          {[
            ['Up / Down', 'Navigate table rows'],
            ['Enter', 'Open image detail modal'],
            ['Escape', 'Close modal / clear selection'],
            ['Left / Right', 'Prev / next image (in modal)'],
            ['A', 'Approve all pending (in modal)'],
            ['?', 'Show this help'],
          ].map(([key, desc]) => (
            <div key={key} className="flex items-center gap-3">
              <kbd className="px-2 py-0.5 bg-gray-100 border border-gray-300 rounded text-[11px] font-mono font-medium text-gray-700 min-w-[80px] text-center">{key}</kbd>
              <span className="text-gray-600">{desc}</span>
            </div>
          ))}
        </div>
        <button onClick={onClose} className="mt-4 w-full px-3 py-1.5 bg-gray-200 text-gray-700 text-xs rounded-lg hover:bg-gray-300 cursor-pointer">Close</button>
      </div>
    </div>
  );
}

function ReviewTab() {
  const [viewMode, setViewMode] = useState('table'); // cards, table
  // ── Cards state ──
  const [annotations, setAnnotations] = useState([]);
  const [stats, setStats] = useState(null);
  const [categories, setCategories] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [catFilter, setCatFilter] = useState('');
  const [annotatorFilter, setAnnotatorFilter] = useState('');
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [editSelections, setEditSelections] = useState([]);
  const [editDuplicate, setEditDuplicate] = useState(null);
  // ── Table state ──
  const [tableData, setTableData] = useState(null);
  const [tablePage, setTablePage] = useState(1);
  const [tableLoading, setTableLoading] = useState(false);
  const [editingCell, setEditingCell] = useState(null);
  // ── Detail modal ──
  const [modalRow, setModalRow] = useState(null);
  // ── Bulk select ──
  const [selectedRows, setSelectedRows] = useState(new Set());
  // ── Keyboard navigation ──
  const [highlightedIdx, setHighlightedIdx] = useState(-1);
  const [showShortcuts, setShowShortcuts] = useState(false);
  // ── Bulk approve in progress ──
  const [bulkApproving, setBulkApproving] = useState(false);

  // ── Cards data loader ──
  const loadCards = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('review_status', filter);
      params.set('page', page);
      params.set('page_size', '15');
      if (catFilter) params.set('category_id', catFilter);
      if (annotatorFilter) params.set('annotator_id', annotatorFilter);

      const [annRes, statsRes, catsRes, usersRes] = await Promise.all([
        api.get(`/admin/review?${params.toString()}`),
        api.get('/admin/review/stats'),
        api.get('/admin/categories'),
        api.get('/admin/users'),
      ]);
      setAnnotations(annRes.data);
      setStats(statsRes.data);
      setCategories(catsRes.data);
      setUsers(usersRes.data.filter((u) => u.role === 'annotator'));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [filter, catFilter, annotatorFilter, page]);

  // ── Table data loader ──
  const loadTable = useCallback(async () => {
    setTableLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('review_status', filter);
      params.set('page', tablePage);
      params.set('page_size', '20');
      if (annotatorFilter) params.set('annotator_id', annotatorFilter);

      const [tableRes, statsRes, catsRes, usersRes] = await Promise.all([
        api.get(`/admin/review/table?${params.toString()}`),
        api.get('/admin/review/stats'),
        api.get('/admin/categories'),
        api.get('/admin/users'),
      ]);
      setTableData(tableRes.data);
      setStats(statsRes.data);
      setCategories(catsRes.data);
      setUsers(usersRes.data.filter((u) => u.role === 'annotator'));
      setSelectedRows(new Set());
      setHighlightedIdx(-1);
    } catch (err) {
      console.error(err);
    } finally {
      setTableLoading(false);
    }
  }, [filter, annotatorFilter, tablePage]);

  useEffect(() => {
    if (viewMode === 'cards') loadCards();
    else loadTable();
  }, [viewMode, loadCards, loadTable]);

  const refreshData = useCallback(() => {
    if (viewMode === 'cards') loadCards(); else loadTable();
  }, [viewMode, loadCards, loadTable]);

  // ── Sync modalRow with latest tableData after refresh ──
  useEffect(() => {
    if (modalRow && tableData?.images) {
      const updatedRow = tableData.images.find((img) => img.image_id === modalRow.image_id);
      if (updatedRow) {
        setModalRow(updatedRow);
      } else {
        // If item is no longer in filtered results (e.g., approved while viewing pending),
        // close the modal
        setModalRow(null);
      }
    }
  }, [tableData]);

  // ── Shared actions ──
  const handleApprove = async (annotationId) => {
    try {
      await api.put(`/admin/review/${annotationId}/approve`, {});
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed');
    }
  };

  const handleApproveAndRefresh = async (annotationId) => {
    await handleApprove(annotationId);
    refreshData();
  };

  const handleSaveEdits = async (annotationId, selectedIds, isDuplicate) => {
    try {
      await api.put(`/admin/review/${annotationId}/update`, {
        selected_option_ids: selectedIds,
        is_duplicate: isDuplicate,
      });
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save');
    }
  };

  const handleSaveEditsAndRefresh = async (annotationId, selectedIds, isDuplicate) => {
    await handleSaveEdits(annotationId, selectedIds, isDuplicate);
    setEditingCell(null);
    cancelEditing();
    refreshData();
  };

  // ── Send for Rework ──
  const [showReworkModal, setShowReworkModal] = useState(false);
  const [reworkAnnotationId, setReworkAnnotationId] = useState(null);
  const [reworkReason, setReworkReason] = useState('');
  const [sendingRework, setSendingRework] = useState(false);

  const openReworkModal = (annotationId) => {
    setReworkAnnotationId(annotationId);
    setReworkReason('');
    setShowReworkModal(true);
  };

  const handleSendRework = async () => {
    if (!reworkReason.trim()) {
      alert('Please provide a reason for rework');
      return;
    }
    setSendingRework(true);
    try {
      await api.post(`/admin/annotations/${reworkAnnotationId}/rework`, { reason: reworkReason });
      setShowReworkModal(false);
      setReworkAnnotationId(null);
      setReworkReason('');
      refreshData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to send for rework');
    }
    setSendingRework(false);
  };

  // ── Bulk approve ──
  const handleBulkApprove = async () => {
    if (!tableData) return;
    setBulkApproving(true);
    try {
      const promises = [];
      for (const imgId of selectedRows) {
        const row = tableData.images.find((r) => r.image_id === imgId);
        if (!row) continue;
        for (const cat of tableData.categories) {
          const cell = row.annotations[String(cat.id)];
          if (cell && !cell.review_status) {
            promises.push(api.put(`/admin/review/${cell.annotation_id}/approve`, {}));
          }
        }
      }
      await Promise.all(promises);
      setSelectedRows(new Set());
      refreshData();
    } catch (err) {
      alert('Some approvals failed');
    } finally {
      setBulkApproving(false);
    }
  };

  const toggleRowSelect = (imageId) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      if (next.has(imageId)) next.delete(imageId); else next.add(imageId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!tableData) return;
    if (selectedRows.size === tableData.images.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(tableData.images.map((r) => r.image_id)));
    }
  };

  // Count pending annotations in selected rows
  const selectedPendingCount = useMemo(() => {
    if (!tableData) return 0;
    let count = 0;
    for (const imgId of selectedRows) {
      const row = tableData.images.find((r) => r.image_id === imgId);
      if (!row) continue;
      for (const cat of tableData.categories) {
        const cell = row.annotations[String(cat.id)];
        if (cell && !cell.review_status) count++;
      }
    }
    return count;
  }, [selectedRows, tableData]);

  // ── Cards edit helpers ──
  const startEditing = (a) => {
    setEditingId(a.id);
    setEditSelections(a.selected_options.map((o) => o.id));
    setEditDuplicate(a.is_duplicate);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditSelections([]);
    setEditDuplicate(null);
  };

  const toggleEditOption = (optId) => {
    setEditSelections((prev) =>
      prev.includes(optId) ? prev.filter((id) => id !== optId) : [...prev, optId]
    );
  };

  const handleFilterChange = (f) => {
    setFilter(f);
    setPage(1);
    setTablePage(1);
  };

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't intercept when typing in inputs
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

      // Shortcuts help
      if (e.key === '?') {
        e.preventDefault();
        setShowShortcuts((v) => !v);
        return;
      }

      // Modal-specific shortcuts
      if (modalRow && tableData) {
        if (e.key === 'Escape') {
          e.preventDefault();
          setModalRow(null);
          return;
        }
        const idx = tableData.images.findIndex((r) => r.image_id === modalRow.image_id);
        if (e.key === 'ArrowLeft' && idx > 0) {
          e.preventDefault();
          setModalRow(tableData.images[idx - 1]);
          return;
        }
        if (e.key === 'ArrowRight' && idx < tableData.images.length - 1) {
          e.preventDefault();
          setModalRow(tableData.images[idx + 1]);
          return;
        }
        if (e.key === 'a' || e.key === 'A') {
          e.preventDefault();
          // Approve all pending for this image
          const pending = tableData.categories
            .map((cat) => modalRow.annotations[String(cat.id)])
            .filter((cell) => cell && !cell.review_status);
          if (pending.length > 0) {
            Promise.all(pending.map((cell) => handleApprove(cell.annotation_id))).then(() => refreshData());
          }
          return;
        }
        return;
      }

      // Table-specific shortcuts (no modal)
      if (viewMode === 'table' && tableData && tableData.images.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setHighlightedIdx((prev) => Math.min(prev + 1, tableData.images.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setHighlightedIdx((prev) => Math.max(prev - 1, 0));
          return;
        }
        if (e.key === 'Enter' && highlightedIdx >= 0) {
          e.preventDefault();
          setModalRow(tableData.images[highlightedIdx]);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setSelectedRows(new Set());
          setHighlightedIdx(-1);
          return;
        }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [modalRow, tableData, viewMode, highlightedIdx, refreshData]);

  if ((viewMode === 'cards' ? loading : tableLoading) && !stats) {
    return <div className="py-8 text-center text-gray-500">Loading...</div>;
  }

  const tableTotalPages = tableData ? Math.max(1, Math.ceil(tableData.total_images / tableData.page_size)) : 1;

  return (
    <div className="space-y-4">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 stagger-children">
          {[
            { label: 'Pending Review', value: stats.pending_review, key: 'pending', icon: '⏳', gradient: 'from-amber-500 to-orange-500', activeBorder: 'ring-2 ring-amber-400 ring-offset-2' },
            { label: 'Approved', value: stats.approved, key: 'approved', icon: '✓', gradient: 'from-emerald-500 to-teal-500', activeBorder: 'ring-2 ring-emerald-400 ring-offset-2' },
            { label: 'Total Completed', value: stats.total_completed, key: null, icon: '📊', gradient: 'from-indigo-500 to-purple-500', activeBorder: '' },
          ].map((s) => (
            <button
              key={s.label}
              onClick={() => s.key && handleFilterChange(s.key)}
              className={`relative overflow-hidden p-5 rounded-xl border border-gray-200 bg-white text-left transition-all animate-slide-up shadow-sm hover:shadow-md ${
                s.key === filter ? s.activeBorder : ''
              } ${s.key ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <div className={`absolute top-0 right-0 w-20 h-20 bg-gradient-to-br ${s.gradient} opacity-10 rounded-bl-[40px] -mr-2 -mt-2`} />
              <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${s.gradient} flex items-center justify-center text-white text-sm mb-3 shadow-sm`}>
                {s.icon}
              </div>
              <p className="text-2xl font-bold text-gray-900">{s.value}</p>
              <p className="text-xs text-gray-500 mt-1 font-medium">{s.label}</p>
            </button>
          ))}
        </div>
      )}

      {/* Filters + View Toggle */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* View toggle */}
        <div className="flex bg-gray-100 rounded-lg p-0.5">
          {[
            { key: 'table', icon: (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18M3 6h18M3 18h18" /></svg>
            ), label: 'Table' },
            { key: 'cards', icon: (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
            ), label: 'Cards' },
          ].map((v) => (
            <button
              key={v.key}
              onClick={() => setViewMode(v.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition cursor-pointer ${
                viewMode === v.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {v.icon}{v.label}
            </button>
          ))}
        </div>

        <div className="w-px h-6 bg-gray-300" />

        {/* Status filters */}
        <div className="flex gap-1.5">
          {['pending', 'approved'].map((f) => (
            <button
              key={f}
              onClick={() => handleFilterChange(f)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer capitalize ${
                filter === f
                  ? f === 'pending' ? 'bg-amber-500 text-white border-amber-500'
                    : 'bg-green-500 text-white border-green-500'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Category filter — only in cards mode */}
        {viewMode === 'cards' && (
          <select
            value={catFilter}
            onChange={(e) => { setCatFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-xs outline-none"
          >
            <option value="">All Categories</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
        <select
          value={annotatorFilter}
          onChange={(e) => { setAnnotatorFilter(e.target.value); setPage(1); setTablePage(1); }}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-xs outline-none"
        >
          <option value="">All Annotators</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
        </select>

        {/* Shortcuts hint */}
        <button
          onClick={() => setShowShortcuts(true)}
          className="ml-auto text-[10px] text-gray-400 bg-gray-100 px-2 py-1 rounded hover:bg-gray-200 cursor-pointer"
        >
          ? Shortcuts
        </button>
      </div>

      {/* ─── TABLE VIEW ──────────────────────────────────── */}
      {viewMode === 'table' && (
        <>
          {tableLoading ? (
            <div className="py-8 text-center text-gray-500">Loading...</div>
          ) : !tableData || tableData.images.length === 0 ? (
            <div className="py-12 text-center text-gray-500">No annotations found for this filter.</div>
          ) : (
            <>
              <div className="rounded-xl border border-gray-200 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-gray-50 text-gray-600 text-left">
                        {/* Select-all checkbox */}
                        <th className="px-2 py-3 w-10 sticky left-0 bg-gray-50 z-20">
                          <label className="flex items-center justify-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedRows.size === tableData.images.length && tableData.images.length > 0}
                              onChange={toggleSelectAll}
                              className="w-3.5 h-3.5 accent-indigo-600 cursor-pointer"
                            />
                          </label>
                        </th>
                        <th className="px-3 py-3 font-medium sticky left-10 bg-gray-50 z-20 min-w-[200px] border-r border-gray-200">Image</th>
                        {tableData.categories.map((cat) => (
                          <th key={cat.id} className="px-3 py-3 font-medium min-w-[170px] max-w-[240px]">
                            <span className="truncate block">{cat.name}</span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {tableData.images.map((row, rowIdx) => {
                        const isHighlighted = rowIdx === highlightedIdx;
                        const isSelected = selectedRows.has(row.image_id);
                        return (
                          <tr
                            key={row.image_id}
                            className={`transition-colors ${isHighlighted ? 'bg-indigo-50/60' : isSelected ? 'bg-indigo-50/30' : 'hover:bg-gray-50/50'}`}
                            onClick={() => setHighlightedIdx(rowIdx)}
                          >
                            {/* Row checkbox */}
                            <td className="px-2 py-2 sticky left-0 bg-white z-10" onClick={(e) => e.stopPropagation()}>
                              <label className="flex items-center justify-center cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleRowSelect(row.image_id)}
                                  className="w-3.5 h-3.5 accent-indigo-600 cursor-pointer"
                                />
                              </label>
                            </td>
                            {/* Sticky image column */}
                            <td className="px-3 py-2 sticky left-10 bg-white z-10 border-r border-gray-200">
                              <div
                                className="flex items-center gap-2.5 cursor-zoom-in"
                                onClick={() => setModalRow(row)}
                              >
                                <img src={getImageUrl(row.image_id)} alt={row.image_filename} className="w-14 h-14 rounded-lg object-cover shrink-0 ring-1 ring-gray-200" />
                                <span className="text-xs font-medium text-gray-800 truncate max-w-[110px]">{row.image_filename}</span>
                              </div>
                            </td>
                            {/* Category cells */}
                            {tableData.categories.map((cat) => {
                              const cell = row.annotations[String(cat.id)];
                              const isEditingThis = editingCell && editingCell.imageId === row.image_id && editingCell.catId === cat.id;
                              if (!cell) {
                                return (
                                  <td key={cat.id} className="px-3 py-2 text-center">
                                    <span className="text-gray-300">--</span>
                                  </td>
                                );
                              }
                              return (
                                <td key={cat.id} className="px-3 py-2 relative">
                                  <div
                                    onClick={(e) => { e.stopPropagation(); setEditingCell(isEditingThis ? null : { imageId: row.image_id, catId: cat.id }); }}
                                    className={`cursor-pointer rounded-lg p-1.5 transition border ${
                                      cell.review_status === 'approved'
                                        ? 'border-green-200 bg-green-50/50 hover:border-green-300'
                                        : cell.review_status === 'rework_requested'
                                          ? 'border-orange-300 bg-orange-50/50 hover:border-orange-400'
                                          : cell.review_status === 'rework_completed'
                                            ? 'border-purple-300 bg-purple-50/50 hover:border-purple-400'
                                        : 'border-amber-200 bg-amber-50/30 hover:border-amber-300'
                                    }`}
                                  >
                                    <div className="flex items-center gap-1 mb-1">
                                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cell.review_status === 'approved' ? 'bg-green-500' : cell.review_status === 'rework_requested' ? 'bg-orange-500' : cell.review_status === 'rework_completed' ? 'bg-purple-500' : 'bg-amber-400'}`} />
                                      <span className="text-[10px] text-gray-500 truncate">{cell.annotator_username}</span>
                                      {cell.is_duplicate === true && (
                                        <span className="ml-auto px-1 py-0.5 bg-red-100 text-red-600 text-[9px] font-bold rounded">D</span>
                                      )}
                                    </div>
                                    <div className="flex flex-wrap gap-0.5">
                                      {cell.selected_options.length === 0 ? (
                                        <span className="text-gray-400 italic">none</span>
                                      ) : (
                                        cell.selected_options.map((opt) => (
                                          <span key={opt.id} className="px-1.5 py-0.5 bg-indigo-100 text-indigo-800 rounded text-[10px] font-medium leading-tight">
                                            {opt.label}
                                          </span>
                                        ))
                                      )}
                                    </div>
                                  </div>
                                  {isEditingThis && (
                                    <CellEditPopover
                                      cell={cell}
                                      onSave={(annId, sels, dup) => handleSaveEditsAndRefresh(annId, sels, dup)}
                                      onApprove={(annId) => { setEditingCell(null); handleApproveAndRefresh(annId); }}
                                      onClose={() => setEditingCell(null)}
                                    />
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
              {/* Pagination */}
              <div className="flex items-center justify-between text-sm text-gray-500">
                <span>
                  Showing {((tablePage - 1) * (tableData.page_size)) + 1}--{Math.min(tablePage * tableData.page_size, tableData.total_images)} of {tableData.total_images} images
                </span>
                <Pagination currentPage={tablePage} totalPages={tableTotalPages} onPageChange={setTablePage} />
              </div>
            </>
          )}
        </>
      )}

      {/* ─── CARDS VIEW ──────────────────────────────────── */}
      {viewMode === 'cards' && (
        <>
          {loading ? (
            <div className="py-8 text-center text-gray-500">Loading...</div>
          ) : annotations.length === 0 ? (
            <div className="py-12 text-center text-gray-500">
              No annotations found for this filter.
            </div>
          ) : (
            <div className="space-y-3">
              {annotations.map((a) => {
                const isEditing = editingId === a.id;
                const selectedIds = a.selected_options.map((o) => o.id);
                return (
                  <div key={a.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    <div className="flex items-start gap-4 p-4">
                      <img
                        src={getImageUrl(a.image_id)}
                        alt={a.image_filename}
                        className="w-28 h-28 rounded-lg object-cover shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-gray-900 text-sm">{a.image_filename}</span>
                          <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full">{a.category_name}</span>
                          {a.review_status === 'approved' ? (
                            <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs font-medium rounded-full">Approved</span>
                          ) : a.review_status === 'rework_requested' ? (
                            <span className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs font-medium rounded-full">🔄 Awaiting Rework</span>
                          ) : a.review_status === 'rework_completed' ? (
                            <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs font-medium rounded-full">✅ Rework Done</span>
                          ) : (
                            <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs font-medium rounded-full">Pending</span>
                          )}
                          {a.is_duplicate === true && (
                            <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-medium rounded-full">Duplicate</span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mb-2 flex items-center gap-3">
                          <span>Annotated by <span className="font-medium">{a.annotator_username}</span></span>
                          {a.is_rework && (
                            <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-[10px] font-medium rounded-full">Rework</span>
                          )}
                        </p>

                        {!isEditing && (
                          <div className="flex flex-wrap gap-1.5">
                            {a.all_options.map((opt) => {
                              const isSelected = selectedIds.includes(opt.id);
                              return (
                                <span
                                  key={opt.id}
                                  className={`px-2 py-0.5 text-xs rounded-full ${
                                    isSelected
                                      ? 'bg-indigo-100 text-indigo-800 font-medium'
                                      : 'bg-gray-50 text-gray-400'
                                  }`}
                                >
                                  {isSelected && '✓ '}{opt.label}
                                </span>
                              );
                            })}
                          </div>
                        )}

                        {a.review_note && !isEditing && (
                          <div className="mt-2 px-3 py-1.5 bg-gray-50 rounded text-xs text-gray-600 border-l-2 border-gray-300">
                            <span className="font-medium">Note:</span> {a.review_note}
                            {a.reviewed_by_username && <span className="text-gray-400"> — {a.reviewed_by_username}</span>}
                          </div>
                        )}
                      </div>

                      {!isEditing && (
                        <div className="shrink-0 flex flex-col gap-2">
                          {!a.review_status && (
                            <button
                              onClick={() => handleApproveAndRefresh(a.id)}
                              className="px-3 py-1.5 bg-green-500 text-white text-xs font-medium rounded-lg hover:bg-green-600 cursor-pointer"
                            >
                              Approve
                            </button>
                          )}
                          <button
                            onClick={() => startEditing(a)}
                            className="px-3 py-1.5 border border-indigo-300 text-indigo-600 text-xs font-medium rounded-lg hover:bg-indigo-50 cursor-pointer"
                          >
                            Edit & Approve
                          </button>
                          {a.review_status !== 'rework_requested' && (
                            <button
                              onClick={() => openReworkModal(a.id)}
                              className="px-3 py-1.5 border border-amber-300 text-amber-600 text-xs font-medium rounded-lg hover:bg-amber-50 cursor-pointer"
                            >
                              Send for Rework
                            </button>
                          )}
                        </div>
                      )}
                    </div>

                    {isEditing && (
                      <div className="border-t border-gray-200 px-4 py-4 bg-indigo-50/50">
                        <p className="text-xs font-medium text-gray-700 mb-3">Edit selections (changes will be saved and approved):</p>
                        <div className="space-y-1.5 mb-4">
                          {a.all_options.map((opt) => {
                            const checked = editSelections.includes(opt.id);
                            return (
                              <label
                                key={opt.id}
                                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border cursor-pointer transition text-sm ${
                                  checked
                                    ? 'border-indigo-400 bg-indigo-50 text-indigo-900'
                                    : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => toggleEditOption(opt.id)}
                                  className="sr-only"
                                />
                                <div className={`w-4 h-4 rounded flex items-center justify-center border shrink-0 ${
                                  checked ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300'
                                }`}>
                                  {checked && (
                                    <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                    </svg>
                                  )}
                                </div>
                                <span className="text-sm">{opt.label}</span>
                                {opt.is_typical && (
                                  <span className="ml-auto text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">typical</span>
                                )}
                              </label>
                            );
                          })}
                        </div>
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => handleSaveEditsAndRefresh(a.id, editSelections, editDuplicate)}
                            className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 cursor-pointer"
                          >
                            Save & Approve
                          </button>
                          <button
                            onClick={cancelEditing}
                            className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded-lg hover:bg-gray-300 cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ─── Floating bulk approve bar ──────────────────── */}
      {selectedRows.size > 0 && viewMode === 'table' && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-gradient-to-r from-gray-900 to-gray-800 text-white rounded-2xl shadow-2xl px-6 py-3 flex items-center gap-4 animate-slide-up border border-gray-700">
          <span className="text-sm">
            <span className="font-bold">{selectedRows.size}</span> image{selectedRows.size > 1 ? 's' : ''} selected
            {selectedPendingCount > 0 && <span className="text-gray-400 ml-1">({selectedPendingCount} pending annotations)</span>}
          </span>
          {selectedPendingCount > 0 && (
            <button
              onClick={handleBulkApprove}
              disabled={bulkApproving}
              className="px-4 py-1.5 bg-green-500 text-white text-sm font-medium rounded-lg hover:bg-green-600 disabled:opacity-50 cursor-pointer"
            >
              {bulkApproving ? 'Approving...' : `Approve ${selectedPendingCount} Annotations`}
            </button>
          )}
          <button
            onClick={() => setSelectedRows(new Set())}
            className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded-lg hover:bg-gray-600 cursor-pointer"
          >
            Clear
          </button>
        </div>
      )}

      {/* ─── Detail modal ──────────────────────────────── */}
      {modalRow && tableData && (
        <ImageDetailModal
          row={modalRow}
          categories={tableData.categories}
          tableImages={tableData.images}
          onApprove={async (annId) => {
            await handleApprove(annId);
            // Optimistically update modalRow to show approved status immediately
            if (modalRow) {
              const updatedAnnotations = { ...modalRow.annotations };
              for (const catId of Object.keys(updatedAnnotations)) {
                if (updatedAnnotations[catId]?.annotation_id === annId) {
                  updatedAnnotations[catId] = { ...updatedAnnotations[catId], review_status: 'approved' };
                }
              }
              setModalRow({ ...modalRow, annotations: updatedAnnotations });
            }
            refreshData();
          }}
          onSaveEdits={async (annId, sels, dup) => { await handleSaveEdits(annId, sels, dup); refreshData(); }}
          onRework={(annId) => { setModalRow(null); openReworkModal(annId); }}
          onClose={() => setModalRow(null)}
          onNavigate={(newRow) => setModalRow(newRow)}
        />
      )}

      {/* Shortcuts help */}
      <ShortcutsHelp show={showShortcuts} onClose={() => setShowShortcuts(false)} />

      {/* Rework Modal */}
      {showReworkModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 animate-slide-up">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center">
                <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">Send Image for Rework</h3>
                <p className="text-sm text-gray-500">The annotator will be notified to redo all categories for this image</p>
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">Reason for rework</label>
              <textarea
                value={reworkReason}
                onChange={(e) => setReworkReason(e.target.value)}
                placeholder="Please describe what needs to be corrected..."
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowReworkModal(false);
                  setReworkAnnotationId(null);
                  setReworkReason('');
                }}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl transition cursor-pointer"
                disabled={sendingRework}
              >
                Cancel
              </button>
              <button
                onClick={handleSendRework}
                disabled={sendingRework || !reworkReason.trim()}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-xl transition cursor-pointer disabled:opacity-50"
              >
                {sendingRework ? 'Sending...' : 'Send Image for Rework'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Improper Images Tab ─────────────────────────────────────

function ImproperImagesTab() {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const imagesPerPage = 10;

  const load = async () => {
    setLoading(true);
    try {
      const [imagesRes, countRes] = await Promise.all([
        api.get(`/admin/images/improper?page=${page}&page_size=${imagesPerPage}`),
        api.get("/admin/images/improper/count"),
      ]);
      setImages(imagesRes.data.images);
      setTotal(imagesRes.data.total);
      setCount(countRes.data.count);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [page]);

  const revokeImproper = async (imageId) => {
    if (!confirm("Are you sure you want to mark this image as proper again?")) return;
    try {
      await api.put(`/admin/images/${imageId}/revoke-improper`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to revoke improper status");
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / imagesPerPage));

  if (loading && images.length === 0) {
    return <LoadingSkeleton rows={3} />;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Improper Images</h2>
          <p className="text-sm text-gray-500 mt-1">
            Images flagged by annotators as improper - review and revoke if needed
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${
            count > 0 ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
          }`}>
            {count} improper image{count !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {images.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <div className="text-gray-400 text-5xl mb-4">✓</div>
          <h3 className="text-lg font-medium text-gray-700">No improper images</h3>
          <p className="text-gray-500 mt-1">All images are marked as proper.</p>
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {images.map((img) => (
              <div key={img.id} className="bg-white rounded-xl border border-red-200 overflow-hidden">
                <div className="flex items-start gap-4 p-4">
                  <img
                    src={getImageUrl(img.id)}
                    alt={img.filename}
                    className="w-32 h-32 rounded-lg object-cover shrink-0 ring-2 ring-red-200"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-medium text-gray-900">{img.filename}</span>
                      <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-medium rounded-full">
                        Improper
                      </span>
                    </div>
                    <div className="bg-red-50 rounded-lg p-3 mb-3 border border-red-100">
                      <p className="text-sm text-gray-700 font-medium mb-1">Reason:</p>
                      <p className="text-sm text-gray-600">{img.improper_reason || "No reason provided"}</p>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>
                        Marked by: <span className="font-medium text-gray-700">{img.marked_improper_by || "Unknown"}</span>
                      </span>
                      {img.marked_improper_at && (
                        <span>
                          on {new Date(img.marked_improper_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0">
                    <button
                      onClick={() => revokeImproper(img.id)}
                      className="px-4 py-2 bg-green-500 text-white text-sm font-medium rounded-lg hover:bg-green-600 transition cursor-pointer flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Mark as Proper
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-gray-500">
              <span>Showing {((page - 1) * imagesPerPage) + 1}–{Math.min(page * imagesPerPage, total)} of {total}</span>
              <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}


// ─── Edit Requests Tab ───────────────────────────────────────

function EditRequestsTab() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [counts, setCounts] = useState({ pending: 0, approved: 0, rejected: 0 });
  const [filter, setFilter] = useState('pending');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const perPage = 10;

  const load = async () => {
    setLoading(true);
    try {
      const [reqRes, countRes] = await Promise.all([
        api.get(`/admin/edit-requests?status_filter=${filter}&page=${page}&page_size=${perPage}`),
        api.get('/admin/edit-requests/count'),
      ]);
      setRequests(reqRes.data.requests);
      setTotal(reqRes.data.total);
      setCounts(countRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter, page]);

  const handleApprove = async (requestId) => {
    try {
      await api.put(`/admin/edit-requests/${requestId}/approve`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to approve');
    }
  };

  const handleReject = async (requestId) => {
    if (!confirm('Are you sure you want to reject this edit request?')) return;
    try {
      await api.put(`/admin/edit-requests/${requestId}/reject`);
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to reject');
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  if (loading && requests.length === 0) {
    return <LoadingSkeleton rows={3} />;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Edit Requests</h2>
          <p className="text-sm text-gray-500 mt-1">
            Annotators requesting permission to edit completed annotations
          </p>
        </div>
        <div className="flex items-center gap-2">
          {counts.pending > 0 && (
            <span className="px-3 py-1.5 rounded-full text-sm font-medium bg-amber-100 text-amber-700">
              {counts.pending} pending
            </span>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 stagger-children">
        {[
          { label: 'Pending', value: counts.pending, key: 'pending', icon: '⏳', gradient: 'from-amber-500 to-orange-500', activeBorder: 'ring-2 ring-amber-400 ring-offset-2' },
          { label: 'Approved', value: counts.approved, key: 'approved', icon: '✓', gradient: 'from-emerald-500 to-teal-500', activeBorder: 'ring-2 ring-emerald-400 ring-offset-2' },
          { label: 'Rejected', value: counts.rejected, key: 'rejected', icon: '✗', gradient: 'from-red-500 to-rose-500', activeBorder: 'ring-2 ring-red-400 ring-offset-2' },
        ].map((s) => (
          <button
            key={s.key}
            onClick={() => { setFilter(s.key); setPage(1); }}
            className={`relative overflow-hidden p-5 rounded-xl border border-gray-200 bg-white text-left transition-all animate-slide-up shadow-sm hover:shadow-md cursor-pointer ${
              filter === s.key ? s.activeBorder : ''
            }`}
          >
            <div className={`absolute top-0 right-0 w-20 h-20 bg-gradient-to-br ${s.gradient} opacity-10 rounded-bl-[40px] -mr-2 -mt-2`} />
            <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${s.gradient} flex items-center justify-center text-white text-sm mb-3 shadow-sm`}>
              {s.icon}
            </div>
            <p className="text-2xl font-bold text-gray-900">{s.value}</p>
            <p className="text-xs text-gray-500 mt-1 font-medium">{s.label}</p>
          </button>
        ))}
      </div>

      {requests.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <div className="text-gray-400 text-5xl mb-4">📝</div>
          <h3 className="text-lg font-medium text-gray-700">No {filter} edit requests</h3>
          <p className="text-gray-500 mt-1">
            {filter === 'pending' ? 'All edit requests have been processed.' : `No ${filter} requests found.`}
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-4">
            {requests.map((req) => (
              <div key={req.id} className={`bg-white rounded-xl border overflow-hidden ${
                req.status === 'pending' ? 'border-amber-200' 
                  : req.status === 'approved' ? 'border-green-200' 
                    : 'border-red-200'
              }`}>
                <div className="flex items-start gap-4 p-4">
                  <img
                    src={getImageUrl(req.image_id)}
                    alt={req.image_filename}
                    className="w-24 h-24 rounded-lg object-cover shrink-0 ring-1 ring-gray-200"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-medium text-gray-900">{req.image_filename}</span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                        req.status === 'pending' ? 'bg-amber-100 text-amber-700'
                          : req.status === 'approved' ? 'bg-green-100 text-green-700'
                            : 'bg-red-100 text-red-700'
                      }`}>
                        {req.status}
                      </span>
                    </div>
                    
                    <p className="text-sm text-gray-600 mb-2">
                      <span className="font-medium">{req.username}</span> requested to edit
                    </p>
                    
                    <div className="bg-gray-50 rounded-lg p-3 mb-2 border border-gray-100">
                      <p className="text-sm text-gray-700 font-medium mb-1">Reason:</p>
                      <p className="text-sm text-gray-600">{req.reason || 'No reason provided'}</p>
                    </div>
                    
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>Requested: {new Date(req.created_at).toLocaleString()}</span>
                      {req.reviewed_by && (
                        <span>
                          Reviewed by: <span className="font-medium text-gray-700">{req.reviewed_by}</span>
                        </span>
                      )}
                    </div>
                    
                    {req.review_note && (
                      <div className="mt-2 text-xs text-gray-600 italic">
                        Admin note: {req.review_note}
                      </div>
                    )}
                  </div>
                  
                  {req.status === 'pending' && (
                    <div className="shrink-0 flex flex-col gap-2">
                      <button
                        onClick={() => handleApprove(req.id)}
                        className="px-4 py-2 bg-green-500 text-white text-sm font-medium rounded-lg hover:bg-green-600 transition cursor-pointer"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleReject(req.id)}
                        className="px-4 py-2 bg-red-500 text-white text-sm font-medium rounded-lg hover:bg-red-600 transition cursor-pointer"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-gray-500">
              <span>Showing {((page - 1) * perPage) + 1}–{Math.min(page * perPage, total)} of {total}</span>
              <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Annotation Log Tab (Time Tracking) ─────────────────────

function AnnotationLogTab() {
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [annotatorFilter, setAnnotatorFilter] = useState('');
  const [users, setUsers] = useState([]);
  const pageSize = 20;

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', page);
      params.set('page_size', pageSize);
      if (statusFilter !== 'all') params.set('status_filter', statusFilter);
      if (annotatorFilter) params.set('annotator_id', annotatorFilter);

      const [logRes, summaryRes, usersRes] = await Promise.all([
        api.get(`/admin/annotation-log?${params.toString()}`),
        api.get('/admin/annotation-log/summary'),
        api.get('/admin/users'),
      ]);
      setData(logRes.data);
      setSummary(summaryRes.data);
      setUsers(usersRes.data.filter(u => u.role === 'annotator'));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [page, statusFilter, annotatorFilter]);

  const formatTime = (seconds) => {
    if (!seconds || seconds <= 0) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Annotation Time Log</h2>
          <p className="text-sm text-gray-500 mt-1">Track time spent on each annotation by annotators</p>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-gray-900">{summary.total_annotations}</p>
            <p className="text-xs text-gray-500 font-medium">Total Annotations</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-emerald-600">{summary.total_approved}</p>
            <p className="text-xs text-gray-500 font-medium">Approved</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-amber-600">{summary.total_pending}</p>
            <p className="text-xs text-gray-500 font-medium">Pending Review</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-purple-600">{summary.total_reworks}</p>
            <p className="text-xs text-gray-500 font-medium">Reworks</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-indigo-600">{formatTime(summary.avg_annotation_time_seconds)}</p>
            <p className="text-xs text-gray-500 font-medium">Avg Annotation Time</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <p className="text-2xl font-bold text-orange-600">{formatTime(summary.avg_rework_time_seconds)}</p>
            <p className="text-xs text-gray-500 font-medium">Avg Rework Time</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Event Type:</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All Events</option>
            <option value="initial">Annotations</option>
            <option value="rework">Reworks</option>
            <option value="approved">Approvals</option>
            <option value="pending">Pending Review</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Annotator:</label>
          <select
            value={annotatorFilter}
            onChange={(e) => { setAnnotatorFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Annotators</option>
            {users.map(u => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
        </div>
        <button
          onClick={load}
          className="ml-auto px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition cursor-pointer"
        >
          Refresh
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
        </div>
      ) : !data || data.annotations.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-2xl flex items-center justify-center">
            <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-700">No annotations found</h3>
          <p className="text-gray-500 mt-1">Annotations will appear here once annotators submit their work.</p>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Image</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Annotator</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Categories</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Event</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Time</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Action By</th>
                    <th className="text-left px-4 py-3 font-semibold text-gray-700">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.annotations.map((a, idx) => (
                    <tr key={`${a.image_id}-${a.annotator_id}-${a.event_type}-${idx}`} className="hover:bg-gray-50 transition">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <img
                            src={getImageUrl(a.image_id)}
                            alt={a.image_name}
                            className="w-10 h-10 rounded-lg object-cover shrink-0"
                          />
                          <span className="font-medium text-gray-900 truncate max-w-[150px]">{a.image_name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white text-[10px] font-bold">
                            {a.annotator_name[0].toUpperCase()}
                          </div>
                          <span className="text-gray-700">{a.annotator_name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1 max-w-[200px]">
                          {a.categories && a.categories.length <= 2 ? (
                            a.categories.map((cat, i) => (
                              <span key={i} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-full">
                                {cat}
                              </span>
                            ))
                          ) : (
                            <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-full cursor-help" title={a.categories?.join(', ')}>
                              {a.category_count || a.categories?.length} categories
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                          a.event_type === 'Annotation'
                            ? 'bg-blue-100 text-blue-700'
                            : a.event_type === 'Rework'
                              ? 'bg-orange-100 text-orange-700'
                              : a.event_type === 'Review'
                                ? 'bg-amber-100 text-amber-700'
                                : a.event_type === 'Approval'
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-gray-100 text-gray-600'
                        }`}>
                          {a.event_type === 'Annotation' && '📝 '}
                          {a.event_type === 'Rework' && '🔄 '}
                          {a.event_type === 'Review' && '👁️ '}
                          {a.event_type === 'Approval' && '✅ '}
                          {a.event_type === 'Pending' && '⏳ '}
                          {a.event_type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {a.time_taken_seconds > 0 ? (
                          <div className="flex items-center gap-2">
                            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span className="font-medium text-gray-900">{formatTime(a.time_taken_seconds)}</span>
                          </div>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {a.actor_name && a.actor_name !== '-' ? (
                          <div className="flex items-center gap-2">
                            <div className={`w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold ${
                              a.actor_role === 'reviewer'
                                ? 'bg-gradient-to-br from-emerald-500 to-teal-500'
                                : 'bg-gradient-to-br from-indigo-500 to-purple-500'
                            }`}>
                              {a.actor_name[0].toUpperCase()}
                            </div>
                            <div>
                              <span className="text-gray-700 text-xs">{a.actor_name}</span>
                              <span className="text-[10px] text-gray-400 ml-1">({a.actor_role})</span>
                            </div>
                          </div>
                        ) : (
                          <span className="text-gray-400 text-xs">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                          a.status === 'Approved'
                            ? 'bg-emerald-100 text-emerald-700'
                            : a.status === 'Submitted'
                              ? 'bg-blue-100 text-blue-700'
                              : a.status === 'Sent for Rework'
                                ? 'bg-amber-100 text-amber-700'
                                : a.status === 'Sent for Rework Again'
                                  ? 'bg-red-100 text-red-700'
                                  : a.status === 'Pending Review'
                                    ? 'bg-gray-100 text-gray-600'
                                    : 'bg-gray-100 text-gray-600'
                        }`}>
                          {a.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-gray-500">
              <span>Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, data.total)} of {data.total}</span>
              <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Settings Tab ────────────────────────────────────────────

// ─── Compliance Tab (Biometric Compliance) ──────────────────────

function ComplianceTab() {
  const [flaggedImages, setFlaggedImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [selectedImages, setSelectedImages] = useState([]);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchFlaggedImages();
  }, []);

  const fetchFlaggedImages = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/compliance/flagged-images');
      setFlaggedImages(res.data.flagged_images || []);
    } catch (err) {
      console.error('Failed to fetch flagged images:', err);
    }
    setLoading(false);
  };

  const handleProcessImages = async () => {
    if (selectedImages.length === 0) {
      setMessage({ type: 'error', text: 'Please select at least one image to process' });
      return;
    }

    setProcessing(true);
    setMessage(null);
    try {
      const res = await api.post('/admin/compliance/process-images', {
        image_ids: selectedImages,
      });
      setMessage({ 
        type: 'success', 
        text: `Successfully processed ${res.data.processed_count} images!` 
      });
      setSelectedImages([]);
      fetchFlaggedImages();
    } catch (err) {
      setMessage({ 
        type: 'error', 
        text: err.response?.data?.detail || 'Failed to process images' 
      });
    }
    setProcessing(false);
  };

  const handleRevertImage = async (imageId) => {
    if (!confirm('Revert this image to the original unprocessed version? This will undo any blurring.')) {
      return;
    }

    try {
      const res = await api.post(`/admin/compliance/images/${imageId}/revert`, {
        reason: 'Animal wrongly blurred - flagged by annotator'
      });
      
      setMessage({ 
        type: 'success', 
        text: `Image reverted to original. Annotators will now see the unblurred version.` 
      });
      
      // Refresh the list
      fetchFlaggedImages();
    } catch (err) {
      setMessage({ 
        type: 'error', 
        text: err.response?.data?.detail || 'Failed to revert image' 
      });
    }
  };

  const handleReprocessImage = async (imageId) => {
    if (!confirm('Re-process this image with OpenAI for better face detection? This may take 10-20 seconds.')) {
      return;
    }

    setMessage({ type: 'info', text: 'Processing with OpenAI... This may take a moment.' });

    try {
      const res = await api.post(`/admin/compliance/images/${imageId}/reprocess`, {
        use_openai: true,
        reason: 'Human face missed - using OpenAI for better detection'
      });
      
      setMessage({ 
        type: 'success', 
        text: `Image reprocessed! Detected and blurred ${res.data.faces_detected} face(s) using OpenAI.` 
      });
      
      // Refresh the list
      setTimeout(() => fetchFlaggedImages(), 1000);
    } catch (err) {
      setMessage({ 
        type: 'error', 
        text: err.response?.data?.detail || 'Failed to reprocess image' 
      });
    }
  };

  const toggleImageSelection = (imageId) => {
    setSelectedImages(prev => 
      prev.includes(imageId) 
        ? prev.filter(id => id !== imageId)
        : [...prev, imageId]
    );
  };

  const selectAll = () => {
    if (selectedImages.length === flaggedImages.length) {
      setSelectedImages([]);
    } else {
      setSelectedImages(flaggedImages.map(img => img.image_id));
    }
  };

  if (loading) {
    return <LoadingSkeleton rows={6} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <svg className="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            Biometric Compliance
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Images flagged by annotators for human face visibility or animal face blur issues
          </p>
        </div>
        <div className="flex items-center gap-3">
          {selectedImages.length > 0 && (
            <button
              onClick={handleProcessImages}
              disabled={processing}
              className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-500 text-white text-sm font-medium rounded-xl hover:from-indigo-600 hover:to-purple-600 transition shadow-sm disabled:opacity-50 cursor-pointer flex items-center gap-2"
            >
              {processing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Process {selectedImages.length} Image{selectedImages.length > 1 ? 's' : ''}
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className={`p-4 rounded-xl border animate-slide-down ${
          message.type === 'success' 
            ? 'bg-emerald-50 border-emerald-200 text-emerald-700' 
            : 'bg-red-50 border-red-200 text-red-700'
        }`}>
          {message.text}
        </div>
      )}

      {/* Info Box */}
      <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl border border-indigo-100 p-5">
        <h4 className="text-sm font-semibold text-indigo-900 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          About Compliance Processing
        </h4>
        <ul className="mt-2 space-y-1 text-sm text-indigo-800">
          <li>• Annotators flag images with <strong>"Human face visible"</strong> or <strong>"Animal face blurred"</strong> issues</li>
          <li>• The pipeline uses AI to detect and blur human faces while preserving animal faces</li>
          <li>• After processing, images are automatically sent back to annotators for re-annotation</li>
          <li>• Processing typically takes 2-5 seconds per image</li>
        </ul>
      </div>

      {flaggedImages.length === 0 ? (
        <div className="text-center py-20 bg-gradient-to-b from-gray-50 to-white rounded-2xl border border-gray-200">
          <div className="w-16 h-16 bg-emerald-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-1">All Clear!</h3>
          <p className="text-sm text-gray-500">No images flagged for compliance issues</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={selectedImages.length === flaggedImages.length && flaggedImages.length > 0}
                onChange={selectAll}
                className="w-4 h-4 text-indigo-600 rounded cursor-pointer"
              />
              <h3 className="text-sm font-semibold text-gray-900">
                {flaggedImages.length} Flagged Image{flaggedImages.length > 1 ? 's' : ''}
              </h3>
            </div>
            {selectedImages.length > 0 && (
              <span className="text-xs text-indigo-600 font-medium">
                {selectedImages.length} selected
              </span>
            )}
          </div>

          {/* Image List */}
          <div className="divide-y divide-gray-100">
            {flaggedImages.map((img) => (
              <div
                key={img.image_id}
                className={`p-4 hover:bg-gray-50 transition ${
                  selectedImages.includes(img.image_id) ? 'bg-indigo-50' : ''
                }`}
              >
                <div className="flex items-start gap-4">
                  <input
                    type="checkbox"
                    checked={selectedImages.includes(img.image_id)}
                    onChange={() => toggleImageSelection(img.image_id)}
                    className="mt-1 w-4 h-4 text-indigo-600 rounded cursor-pointer"
                  />
                  <img
                    src={getImageUrl(img.image_id)}
                    alt={img.filename}
                    className="w-24 h-24 object-cover rounded-xl border border-gray-200"
                  />
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-gray-900 truncate">{img.filename}</h4>
                    <div className="mt-2 space-y-1">
                      {img.flagged_for_human && (
                        <div className="flex items-start gap-2 text-xs">
                          <Badge variant="danger">Human Issue</Badge>
                          <span className="text-gray-600">{img.human_flag_text}</span>
                        </div>
                      )}
                      {img.flagged_for_animal && (
                        <div className="flex items-start gap-2 text-xs">
                          <Badge variant="warning">Animal Issue</Badge>
                          <span className="text-gray-600">{img.animal_flag_text}</span>
                        </div>
                      )}
                    </div>
                    {img.compliance_status && (
                      <div className="mt-2">
                        <Badge variant="info">Status: {img.compliance_status}</Badge>
                      </div>
                    )}
                    
                    {/* Action buttons */}
                    <div className="mt-3 flex gap-2">
                      {img.flagged_for_animal && (
                        <button
                          onClick={() => handleRevertImage(img.image_id)}
                          className="px-3 py-1.5 text-xs bg-amber-100 hover:bg-amber-200 text-amber-700 rounded-lg transition font-medium"
                        >
                          🔄 Revert to Original
                        </button>
                      )}
                      {img.flagged_for_human && (
                        <button
                          onClick={() => handleReprocessImage(img.image_id)}
                          className="px-3 py-1.5 text-xs bg-indigo-100 hover:bg-indigo-200 text-indigo-700 rounded-lg transition font-medium"
                        >
                          🤖 Re-process with OpenAI
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Settings Tab ───────────────────────────────────────────────

function SettingsTab() {
  const [settings, setSettings] = useState({
    max_annotation_time_seconds: 120,
    max_rework_time_seconds: 120,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    api.get('/admin/settings')
      .then(res => {
        setSettings(res.data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await api.put('/admin/settings', settings);
      setSettings(res.data);
      setMessage({ type: 'success', text: 'Settings saved successfully!' });
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to save settings' });
    }
    setSaving(false);
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">Configure annotation time limits and other system settings.</p>
      </div>

      {message && (
        <div className={`p-4 rounded-xl border ${
          message.type === 'success' 
            ? 'bg-emerald-50 border-emerald-200 text-emerald-700' 
            : 'bg-red-50 border-red-200 text-red-700'
        }`}>
          {message.text}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
            <svg className="w-5 h-5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Time Limits
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            Set maximum time allowed for annotations. Time spent beyond this limit won't be recorded.
          </p>
        </div>

        <div className="p-5 space-y-6">
          {/* Max Annotation Time */}
          <div className="space-y-3">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Initial Annotation Time Limit</span>
              <p className="text-xs text-gray-500 mt-0.5">Maximum time for first-time annotation of an image</p>
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={30}
                max={600}
                step={10}
                value={settings.max_annotation_time_seconds}
                onChange={(e) => setSettings(s => ({ ...s, max_annotation_time_seconds: parseInt(e.target.value) }))}
                className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
              />
              <div className="w-24 text-center">
                <span className="text-lg font-bold text-gray-900">{formatTime(settings.max_annotation_time_seconds)}</span>
                <p className="text-[10px] text-gray-400">min:sec</p>
              </div>
            </div>
            <div className="flex justify-between text-[10px] text-gray-400 px-1">
              <span>30s</span>
              <span>2min</span>
              <span>5min</span>
              <span>10min</span>
            </div>
          </div>

          {/* Max Rework Time */}
          <div className="space-y-3">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Rework Annotation Time Limit</span>
              <p className="text-xs text-gray-500 mt-0.5">Maximum time for re-annotating images sent back for rework</p>
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={30}
                max={600}
                step={10}
                value={settings.max_rework_time_seconds}
                onChange={(e) => setSettings(s => ({ ...s, max_rework_time_seconds: parseInt(e.target.value) }))}
                className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-purple-600"
              />
              <div className="w-24 text-center">
                <span className="text-lg font-bold text-gray-900">{formatTime(settings.max_rework_time_seconds)}</span>
                <p className="text-[10px] text-gray-400">min:sec</p>
              </div>
            </div>
            <div className="flex justify-between text-[10px] text-gray-400 px-1">
              <span>30s</span>
              <span>2min</span>
              <span>5min</span>
              <span>10min</span>
            </div>
          </div>
        </div>

        <div className="px-5 py-4 bg-gray-50 border-t border-gray-100 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-500 text-white text-sm font-medium rounded-xl hover:from-indigo-600 hover:to-purple-600 transition shadow-sm disabled:opacity-50 cursor-pointer"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl border border-indigo-100 p-5">
        <h4 className="text-sm font-semibold text-indigo-900 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          How Time Limits Work
        </h4>
        <ul className="mt-2 space-y-1 text-sm text-indigo-800">
          <li>• Annotators see a <strong>countdown timer</strong> starting from the max time</li>
          <li>• If they take longer, a "Performance Warning" is shown</li>
          <li>• <strong>Logged time</strong> is capped at the max (never records more than the limit)</li>
          <li>• Rework annotations use the separate rework time limit</li>
        </ul>
      </div>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────

export default function AdminDashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Derive active tab from URL path: /admin/review -> 'review', /admin -> 'users'
  const VALID_TABS = ['users', 'progress', 'review', 'completion', 'images', 'improper', 'edit-requests', 'annotation-log', 'settings', 'pipeline'];
  const pathSegment = location.pathname.replace(/^\/admin\/?/, '').split('/')[0] || 'users';
  const activeTab = VALID_TABS.includes(pathSegment) ? pathSegment : 'users';

  const setActiveTab = (key) => {
    navigate(key === 'users' ? '/admin' : `/admin/${key}`, { replace: false });
  };

  const tabs = [
    { key: 'users', label: 'Users', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
    )},
    { key: 'progress', label: 'Progress', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
    )},
    { key: 'review', label: 'Review', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
    )},
    { key: 'completion', label: 'Image Status', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
    )},
    { key: 'images', label: 'Images', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
    )},
    { key: 'improper', label: 'Improper', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
    )},
    { key: 'edit-requests', label: 'Edit Requests', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
    )},
    { key: 'annotation-log', label: 'Time Log', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
    )},
    { key: 'settings', label: 'Settings', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
    )},
    { key: 'pipeline', label: 'Master Pipeline', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
    )},
    { key: 'compliance', label: 'Compliance', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
    )},
  ];

  return (
    <div className="min-h-screen mesh-bg flex">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0 sticky top-0 h-screen">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center shadow-sm">
              <span className="text-white text-sm">🐾</span>
            </div>
          <div>
              <h1 className="text-sm font-bold text-gray-900 leading-tight">Photo Pets</h1>
              <p className="text-[11px] text-gray-400 font-medium">Admin Dashboard</p>
          </div>
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          {tabs.map((tab) => (
          <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all cursor-pointer ${
                activeTab === tab.key
                  ? 'bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-700 sidebar-active shadow-sm'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <span className={activeTab === tab.key ? 'text-indigo-600' : 'text-gray-400'}>{tab.icon}</span>
              {tab.label}
          </button>
          ))}
        </nav>

        {/* User section */}
        <div className="border-t border-gray-100 p-4">
          <div className="flex items-center gap-3">
            <Avatar name={user?.username} size="md" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{user?.username}</p>
              <p className="text-[11px] text-gray-400">Administrator</p>
        </div>
            <button
              onClick={logout}
              className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition cursor-pointer"
              title="Sign out"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            </button>
      </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0">
        <div className={activeTab === 'review' ? 'p-5' : 'p-6'}>
            {activeTab === 'users' && <UsersTab />}
            {activeTab === 'progress' && <ProgressTab />}
            {activeTab === 'review' && <ReviewTab />}
            {activeTab === 'completion' && <ImageCompletionTab />}
            {activeTab === 'images' && <ImagesTab />}
          {activeTab === 'improper' && <ImproperImagesTab />}
          {activeTab === 'edit-requests' && <EditRequestsTab />}
          {activeTab === 'annotation-log' && <AnnotationLogTab />}
          {activeTab === 'settings' && <SettingsTab />}
          {activeTab === 'pipeline' && <MasterPipelineTab />}
          {activeTab === 'compliance' && <ComplianceTab />}
        </div>
      </main>
    </div>
  );
}
