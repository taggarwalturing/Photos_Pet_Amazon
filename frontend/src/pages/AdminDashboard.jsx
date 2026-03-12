import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import MasterPipelineTab from '../components/MasterPipelineTab';
import PhotoRegistryTab from '../components/PhotoRegistryTab';
import ArbiterClassifierTab from '../components/ArbiterClassifierTab';
import AnnotatorStatsTab from '../components/AnnotatorStatsTab';
import BoundingBoxCanvas from '../components/BoundingBoxCanvas';
import SignedImage from '../components/SignedImage';
import { getProxyUrl, getThumbUrl } from '../hooks/useSignedUrl';

const PAGE_SIZE = 10;

const getImageUrl = (imageId) => {
  if (!imageId) return '';
  return getThumbUrl(imageId);
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
  const [showCreate, setShowCreate] = useState(false);
  const [editingAssignment, setEditingAssignment] = useState(null); // user id for category assignment
  const [form, setForm] = useState({ username: '', password: '', full_name: '', role: 'annotator' });
  const [showPassword, setShowPassword] = useState(false);
  const [assignedCats, setAssignedCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dailyStats, setDailyStats] = useState(null);
  const [dailyDays, setDailyDays] = useState(7);
  const [editingImageCount, setEditingImageCount] = useState({}); // { userId: count }
  const [assigningUserId, setAssigningUserId] = useState(null);
  const [reassignModal, setReassignModal] = useState(null); // { fromId, fromUsername }
  const [reassignTarget, setReassignTarget] = useState('');
  const [reassignCount, setReassignCount] = useState('');
  const [reassigning, setReassigning] = useState(false);

  const generatePassword = () => {
    const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*';
    let pw = '';
    for (let i = 0; i < 14; i++) pw += chars[Math.floor(Math.random() * chars.length)];
    setForm((f) => ({ ...f, password: pw }));
    setShowPassword(true);
  };

  const load = async () => {
    try {
      const [usersRes, catsRes, dailyRes] = await Promise.all([
        api.get('/admin/users'),
        api.get('/admin/categories'),
        api.get(`/admin/users/daily-stats?days=${dailyDays}`),
      ]);
      setUsers(usersRes.data);
      setCategories(catsRes.data);
      setDailyStats(dailyRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [dailyDays]);

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

  const handleAssignForUser = async (userId) => {
    const rawVal = editingImageCount[userId];
    const count = rawVal !== undefined ? (parseInt(rawVal) || 0) : null;

    setAssigningUserId(userId);
    try {
      // Call per-annotator assignment endpoint (only affects this annotator)
      const queryCount = count !== null ? `?count=${count}` : '';
      await api.post(`/admin/assign-images/${userId}${queryCount}`);
      setEditingImageCount(prev => { const copy = { ...prev }; delete copy[userId]; return copy; });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Assignment failed');
    } finally {
      setAssigningUserId(null);
    }
  };

  const handleReassign = async () => {
    if (!reassignModal || !reassignTarget) return;
    setReassigning(true);
    try {
      const body = {
        from_annotator_id: reassignModal.fromId,
        to_annotator_id: parseInt(reassignTarget),
      };
      if (reassignCount) body.count = parseInt(reassignCount);
      await api.post('/admin/reassign-images', body);
      setReassignModal(null);
      setReassignTarget('');
      setReassignCount('');
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Reassignment failed');
    } finally {
      setReassigning(false);
    }
  };

  const annotators = users.filter(u => u.role === 'annotator' && u.is_active);

  if (loading) return <LoadingSkeleton rows={6} />;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Users & Assignments</h2>
          <p className="text-sm text-gray-500 mt-0.5">{users.filter(u => u.role === 'annotator').length} annotators, {users.filter(u => u.role === 'admin').length} admins</p>
          {(() => {
            const totalAssigned = users.filter(u => u.role === 'annotator').reduce((s, u) => s + (u.actual_assigned || 0), 0);
            const totalImages = users.find(u => u.role === 'annotator')?.total_images || 0;
            const unassigned = totalImages - totalAssigned;
            return totalImages > 0 ? (
              <p className="text-xs text-gray-400 mt-0.5">
                {totalImages} total &middot; {totalAssigned} assigned &middot; <span className={unassigned > 0 ? 'text-amber-600 font-semibold' : 'text-emerald-600 font-semibold'}>{unassigned} unassigned</span>
              </p>
            ) : null;
          })()}
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
              <label className="block text-sm font-medium text-gray-700 mb-1">Turing ID <span className="text-red-500">*</span></label>
              <input
                type="email"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="xyz@turing.com"
                pattern=".+@turing\.com$"
                title="Must be a valid Turing ID (e.g. xyz@turing.com)"
                required
              />
              <p className="text-[10px] text-gray-400 mt-0.5">Format: name@turing.com</p>
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

      

      {/* Users table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gradient-to-r from-gray-50 to-gray-50/80 text-gray-600 text-left">
              <th className="px-5 py-3.5 font-semibold">Turing ID</th>
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Role</th>
              <th className="px-5 py-3 font-medium">Assign Count</th>
              <th className="px-5 py-3 font-medium">Assigned</th>
              <th className="px-5 py-3 font-medium">Today</th>
              <th className="px-5 py-3 font-medium">Progress</th>
              <th className="px-5 py-3 font-medium">Improper</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => {
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
                <td className="px-5 py-3">
                  {u.role === 'annotator' ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        value={editingImageCount[u.id] !== undefined ? editingImageCount[u.id] : String(u.assigned_image_count || 0)}
                        onChange={(e) => {
                          const val = e.target.value.replace(/[^0-9]/g, '');
                          setEditingImageCount(prev => ({ ...prev, [u.id]: val }));
                        }}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAssignForUser(u.id); } }}
                        className="w-20 px-2 py-1 text-sm border border-gray-300 rounded-lg text-center focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                      />
                      <button
                        onClick={() => handleAssignForUser(u.id)}
                        disabled={assigningUserId !== null}
                        className="px-2.5 py-1 text-xs font-semibold bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition cursor-pointer disabled:opacity-50 whitespace-nowrap"
                      >
                        {assigningUserId === u.id ? '…' : 'Assign'}
                      </button>
                      {(u.actual_assigned || 0) > 0 && (
                        <button
                          onClick={() => { setReassignModal({ fromId: u.id, fromUsername: u.username }); setReassignTarget(''); setReassignCount(''); }}
                          className="px-2.5 py-1 text-xs font-semibold bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition cursor-pointer whitespace-nowrap"
                        >
                          Reassign
                        </button>
                      )}
                    </div>
                  ) : '—'}
                </td>
                  <td className="px-5 py-3">
                    {u.role === 'annotator' ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        (u.actual_assigned || 0) > 0 ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {u.actual_assigned || 0} images
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-5 py-3">
                    {u.role === 'annotator' ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        (u.today_image_count || 0) > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-400'
                      }`}>
                        {u.today_image_count || 0} images
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
                              style={{ width: `${(u.actual_assigned || 0) > 0 ? Math.min(100, (u.completed_annotations / (u.actual_assigned || 1)) * 100) : 0}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">
                            {(u.actual_assigned || 0) > 0 ? Math.round((u.completed_annotations / (u.actual_assigned || 1)) * 100) : 0}%
                          </span>
                        </div>
                        <span className="text-[10px] text-gray-400">
                          {u.completed_annotations}/{u.actual_assigned || 0} annotated
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

      {/* Reassign Modal */}
      {reassignModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setReassignModal(null)}>
          <div className="bg-white rounded-xl shadow-xl p-6 w-96 space-y-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-gray-900">Reassign Images</h3>
            <p className="text-sm text-gray-500">
              Move non-completed images from <span className="font-semibold text-gray-800">{reassignModal.fromUsername}</span> to another annotator.
            </p>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Target Annotator</label>
              <select
                value={reassignTarget}
                onChange={e => setReassignTarget(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select annotator...</option>
                {annotators.filter(a => a.id !== reassignModal.fromId).map(a => (
                  <option key={a.id} value={a.id}>{a.username} ({a.actual_assigned || 0} assigned)</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Number of images <span className="text-gray-400 font-normal">(leave empty = all non-completed)</span>
              </label>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={reassignCount}
                onChange={e => setReassignCount(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="All"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div className="flex gap-3 justify-end pt-2">
              <button
                onClick={() => setReassignModal(null)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleReassign}
                disabled={!reassignTarget || reassigning}
                className="px-4 py-2 text-sm font-semibold bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition cursor-pointer disabled:opacity-50"
              >
                {reassigning ? 'Reassigning...' : 'Reassign'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Daily Annotation Stats */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-gray-900">📊 Daily Annotations (Images per Day)</h3>
            <p className="text-xs text-gray-500 mt-0.5">Distinct images annotated by each annotator per day</p>
              </div>
          <div className="flex items-center gap-2">
            {[7, 14, 30].map((d) => (
                <button
                key={d}
                onClick={() => setDailyDays(d)}
                className={`px-3 py-1 text-xs font-medium rounded-full transition cursor-pointer ${
                  dailyDays === d
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {d}d
                </button>
              ))}
            </div>
            </div>
        {dailyStats && dailyStats.date_range?.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 text-gray-500">
                  <th className="px-4 py-2.5 text-left font-semibold sticky left-0 bg-gray-50 z-10">Turing ID</th>
                  {dailyStats.date_range.map((d) => {
                    const dateObj = new Date(d + 'T00:00:00');
                    const isToday = d === new Date().toISOString().split('T')[0];
                    return (
                      <th key={d} className={`px-3 py-2.5 text-center font-medium whitespace-nowrap ${isToday ? 'bg-indigo-50 text-indigo-700' : ''}`}>
                        {dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        {isToday && <span className="block text-[9px] font-bold text-indigo-500">TODAY</span>}
                      </th>
                    );
                  })}
                  <th className="px-3 py-2.5 text-center font-semibold bg-gray-100">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {Object.entries(dailyStats.annotators).map(([username, data]) => {
                  const total = dailyStats.date_range.reduce((sum, d) => sum + (data.daily[d] || 0), 0);
                  return (
                    <tr key={username} className="hover:bg-gray-50/50">
                      <td className="px-4 py-2 font-medium text-gray-900 sticky left-0 bg-white z-10">
                        <div className="flex items-center gap-2">
                          <Avatar name={username} size="sm" />
                          {username}
          </div>
                      </td>
                      {dailyStats.date_range.map((d) => {
                        const count = data.daily[d] || 0;
                        const isToday = d === new Date().toISOString().split('T')[0];
                        return (
                          <td key={d} className={`px-3 py-2 text-center ${isToday ? 'bg-indigo-50/50' : ''}`}>
                            {count > 0 ? (
                              <span className={`inline-block min-w-[24px] px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                                count >= 50 ? 'bg-emerald-100 text-emerald-700' :
                                count >= 20 ? 'bg-blue-100 text-blue-700' :
                                count >= 5 ? 'bg-amber-100 text-amber-700' :
                                'bg-gray-100 text-gray-600'
                              }`}>
                                {count}
                              </span>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                        );
                      })}
                      <td className="px-3 py-2 text-center bg-gray-50">
                        <span className="font-bold text-gray-900">{total}</span>
                      </td>
                    </tr>
                  );
                })}
                {Object.keys(dailyStats.annotators).length === 0 && (
                  <tr>
                    <td colSpan={dailyStats.date_range.length + 2} className="px-4 py-8 text-center text-gray-400">
                      No annotation activity in this period
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
        </div>
        ) : (
          <div className="px-5 py-8 text-center text-gray-400 text-sm">No daily stats available</div>
      )}
      </div>
    </div>
  );
}

// ─── Images Tab ───────────────────────────────────────────────

function ImagesTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [lightboxImg, setLightboxImg] = useState(null); // image object for lightbox
  const imagesPerPage = 20;

  const fetchImages = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filter !== 'all') params.filter = filter;
      if (search) params.search = search;
      const res = await api.get('/admin/images', { params });
      setData(res.data);
    } catch (err) {
      console.error('Failed to load images:', err);
    }
      setLoading(false);
  }, [filter, search]);

  useEffect(() => { fetchImages(); }, [fetchImages]);

  const handleFilterChange = (f) => {
    setFilter(f);
    setPage(1);
  };

  const handleSearch = (e) => {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
  };

  const images = data?.images || [];
  const summary = data?.summary || {};
  const categories = data?.categories || [];
  const totalPages = Math.max(1, Math.ceil(images.length / imagesPerPage));
  const safePage = Math.min(page, totalPages);
  const paginatedImages = images.slice((safePage - 1) * imagesPerPage, safePage * imagesPerPage);

  const filterTags = [
    { key: 'all', label: 'All', value: summary.total, icon: '📋', color: 'indigo' },
    { key: 'blurred', label: 'Blurred', value: summary.blurred, icon: '🔒', color: 'red' },
    { key: 'clean', label: 'Clean', value: summary.clean, icon: '🟢', color: 'green' },
    { key: 'manually_blurred', label: 'Manual Blur', value: summary.manually_blurred, icon: '✋', color: 'violet' },
    { key: 'ai_generated', label: 'AI Generated', value: summary.ai_generated, icon: '🤖', color: 'amber' },
    { key: 'human_visible', label: 'Human Visible', value: summary.human_visible, icon: '👤', color: 'blue' },
    { key: 'improper', label: 'Improper', value: summary.improper, icon: '⚠️', color: 'orange' },
    { key: 'delivered', label: 'Delivered', value: summary.delivered, icon: '📦', color: 'teal' },
    { key: 'not_delivered', label: 'Not Delivered', value: (summary.total || 0) - (summary.delivered || 0), icon: '⏳', color: 'gray' },
  ];

  const colorMap = {
    indigo: { active: 'bg-indigo-100 text-indigo-700 border-indigo-300 ring-indigo-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    red: { active: 'bg-red-100 text-red-700 border-red-300 ring-red-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    green: { active: 'bg-green-100 text-green-700 border-green-300 ring-green-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    violet: { active: 'bg-violet-100 text-violet-700 border-violet-300 ring-violet-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    amber: { active: 'bg-amber-100 text-amber-700 border-amber-300 ring-amber-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    blue: { active: 'bg-blue-100 text-blue-700 border-blue-300 ring-blue-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    orange: { active: 'bg-orange-100 text-orange-700 border-orange-300 ring-orange-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    teal: { active: 'bg-teal-100 text-teal-700 border-teal-300 ring-teal-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
    gray: { active: 'bg-gray-100 text-gray-700 border-gray-300 ring-gray-400', inactive: 'bg-white text-gray-600 border-gray-200 hover:border-gray-300' },
  };

  const getStatusBadges = (img) => {
    const badges = [];
    if (img.manually_blurred) {
      badges.push({ label: 'Manual Blur', className: 'bg-violet-500' });
    } else if (img.compliance_status && ['blurred', 'processed', 'obfuscated'].includes(img.compliance_status)) {
      badges.push({ label: 'Blurred', className: 'bg-red-500' });
    } else if (img.compliance_status === 'clean') {
      badges.push({ label: 'Clean', className: 'bg-green-500' });
    }
    if (img.is_ai_generated) {
      badges.push({ label: 'AI', className: 'bg-amber-500' });
    }
    if (img.is_improper) {
      badges.push({ label: 'Improper', className: 'bg-orange-500' });
    }
    if (img.human_faces_detected > 0) {
      badges.push({ label: `${img.human_faces_detected} face${img.human_faces_detected > 1 ? 's' : ''}`, className: 'bg-sky-500' });
    }
    if (img.deliverable_image_path) {
      const isBlurredDelivery = img.deliverable_image_path.includes('/blurred/');
      const delivLabel = isBlurredDelivery ? '🔒 Blurred' : '✅ Clean';
      badges.push({ label: img.is_manually_modified ? `${delivLabel} (Edited)` : delivLabel, className: isBlurredDelivery ? 'bg-amber-600' : 'bg-teal-500' });
    }
    if (img.is_blurred_annotator) {
      badges.push({ label: '🖌 Annotator Blurred', className: 'bg-purple-500' });
    }
    if (img.is_restore_annotator) {
      badges.push({ label: '↩ Annotator Restored', className: 'bg-cyan-500' });
    }
    return badges;
  };

  // Lightbox navigation
  const lightboxIdx = lightboxImg ? images.findIndex(i => i.id === lightboxImg.id) : -1;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Images ({data?.total ?? '…'})</h2>
        <form onSubmit={handleSearch} className="relative max-w-xs">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search filename…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-indigo-500 focus:border-indigo-500"
          />
          <svg className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </form>
      </div>

      {/* Filter Tags */}
      <div className="flex flex-wrap gap-2">
        {filterTags.map((tag) => {
          const isActive = filter === tag.key;
          const colors = colorMap[tag.color];
          return (
            <button
              key={tag.key}
              onClick={() => handleFilterChange(tag.key)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full border transition cursor-pointer ${
                isActive ? colors.active + ' ring-2 ring-offset-1 ' + colors.active.split(' ').find(c => c.startsWith('ring-')) : colors.inactive
              }`}
            >
              <span>{tag.icon}</span>
              <span>{tag.label}</span>
              <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${isActive ? 'bg-white/60' : 'bg-gray-100'}`}>
                {tag.value ?? '—'}
              </span>
            </button>
          );
        })}
      </div>

      {/* Image Grid */}
      {loading ? (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="bg-gray-100 rounded-xl aspect-[4/3] animate-pulse" />
          ))}
            </div>
      ) : images.length === 0 ? (
        <div className="py-16 text-center text-gray-400">
          <p className="text-lg">No images found</p>
          <p className="text-sm mt-1">Try adjusting your filter or search.</p>
          </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {images.map((img) => {
            const badges = getStatusBadges(img);
            const catLabels = img.category_labels || {};
            const catSources = img.category_label_source || {};
            return (
              <div
                key={img.id}
                onClick={() => setLightboxImg(img)}
                className="group relative bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm hover:shadow-lg hover:ring-2 hover:ring-indigo-400 transition-all cursor-pointer"
              >
                <div className="relative aspect-[4/3]">
                  <img
                    src={getImageUrl(img.id)}
                    alt={img.filename}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                  {/* Status badges overlay */}
                  {badges.length > 0 && (
                    <div className="absolute top-2 left-2 flex flex-wrap gap-1">
                      {badges.map((b, i) => (
                        <span key={i} className={`px-1.5 py-0.5 text-[9px] font-bold text-white rounded-md shadow-sm ${b.className}`}>
                          {b.label}
                        </span>
        ))}
      </div>
                  )}
                  {/* Dark gradient for label readability */}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent pointer-events-none" />
                  {/* Labels overlay – bottom */}
                  {categories.length > 0 && (
                    <div className="absolute bottom-0 left-0 right-0 p-2">
                      <div className="flex flex-wrap gap-1">
                        {categories.map((cat) => {
                          const labels = catLabels[String(cat.id)] || [];
                          const source = catSources[String(cat.id)];
                          if (labels.length === 0) {
                            return (
                              <span
                                key={cat.id}
                                className="px-1.5 py-0.5 bg-gray-900/60 text-gray-400 text-[9px] rounded-md backdrop-blur-sm border border-gray-600/50"
                                title={`${cat.name}: Not set`}
                              >
                                {cat.name.split(' ')[0]}: <span className="italic">?</span>
                              </span>
                            );
                          }
                          return labels.map((label, i) => (
                            <span
                              key={`${cat.id}-${i}`}
                              className={`px-1.5 py-0.5 text-[9px] font-medium rounded-md backdrop-blur-sm border ${
                                source === 'approved'
                                  ? 'bg-emerald-500/80 text-white border-emerald-400'
                                  : source === 'rework'
                                    ? 'bg-orange-500/80 text-white border-orange-400'
                                    : source === 'ai'
                                      ? 'bg-purple-500/80 text-white border-purple-400'
                                      : label === 'None of the Above'
                                        ? 'bg-gray-700/80 text-gray-300 border-gray-600'
                                        : 'bg-indigo-500/80 text-white border-indigo-400'
                              }`}
                              title={`${cat.name}${source === 'ai' ? ' (AI)' : source === 'approved' ? ' (Approved)' : source === 'rework' ? ' (Rework)' : ''}`}
                            >
                              {label}
                            </span>
                          ));
                        })}
                      </div>
                    </div>
                  )}
                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-all flex items-center justify-center">
                    <svg className="w-8 h-8 text-white opacity-0 group-hover:opacity-80 transition-all scale-75 group-hover:scale-100" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                </div>
                <div className="px-3 py-2">
                  {img.image_drive_id && (
                    <p className="text-[9px] text-blue-500 font-mono truncate" title={img.image_drive_id}>{img.image_drive_id}</p>
                  )}
                  <p className="text-xs text-gray-600 truncate font-medium" title={img.filename}>{img.filename}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Image count */}
      {images.length > 0 && (
      <div className="text-sm text-gray-500">
        <span>Showing all {images.length} images</span>
        </div>
      )}

      {/* Lightbox Modal with Blur Tool */}
      {lightboxImg && (
        <ImageLightbox
          img={lightboxImg}
          images={images}
          idx={lightboxIdx}
          getStatusBadges={getStatusBadges}
          onClose={() => setLightboxImg(null)}
          onNavigate={(newImg) => setLightboxImg(newImg)}
          onImageUpdated={fetchImages}
        />
      )}
    </div>
  );
}

// ─── Image Lightbox with Blur Tool ──────────────────────────

function ImageLightbox({ img, images, idx, getStatusBadges, onClose, onNavigate, onImageUpdated }) {
  const [blurActive, setBlurActive] = useState(false);
  const [blurBoxes, setBlurBoxes] = useState([]);
  const [applyingBlur, setApplyingBlur] = useState(false);
  const [imageVersion, setImageVersion] = useState(Date.now());
  const [blurError, setBlurError] = useState('');
  const imageContainerRef = useRef(null);

  // Blur state flags — initialised from img prop, refreshed from admin endpoint
  const [blurFlags, setBlurFlags] = useState({
    is_blurred: img.is_blurred || false,
    compliance_status: img.compliance_status || null,
    is_using_processed: img.is_using_processed !== undefined ? img.is_using_processed : true,
    manually_blurred: img.manually_blurred || false,
  });

  // Fetch blur flags from the admin-accessible status endpoint
  const refreshBlurFlags = useCallback(async () => {
    try {
      const res = await api.get(`/admin/images/${img.id}/status`);
      setBlurFlags({
        is_blurred: res.data.is_blurred || false,
        compliance_status: res.data.compliance_status || null,
        is_using_processed: res.data.is_using_processed,
        manually_blurred: res.data.manually_blurred || false,
      });
    } catch (err) {
      console.error('Failed to refresh blur flags:', err);
    }
  }, [img.id]);

  useEffect(() => {
    refreshBlurFlags();
    setBlurActive(false);
    setBlurBoxes([]);
    setBlurError('');
    setImageVersion(Date.now());
  }, [img.id, refreshBlurFlags]);

  // Keyboard nav
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft' && idx > 0) onNavigate(images[idx - 1]);
      if (e.key === 'ArrowRight' && idx < images.length - 1) onNavigate(images[idx + 1]);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  });

  const handleApplyBlur = async () => {
    if (!blurBoxes.length) return;
    setApplyingBlur(true);
    setBlurError('');
    try {
      await api.post(`/annotator/blur/apply/${img.id}`, { regions: blurBoxes });
      setBlurBoxes([]);
      setBlurActive(false);
      setImageVersion(Date.now());
      await refreshBlurFlags();
      if (onImageUpdated) onImageUpdated();
    } catch (err) {
      setBlurError(err.response?.data?.detail || 'Failed to apply blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const handleUndoBlur = async () => {
    setApplyingBlur(true);
    setBlurError('');
    try {
      const res = await api.delete(`/annotator/blur/${img.id}/blur`);
      if (res.data?.had_original) {
        setImageVersion(Date.now());
        await refreshBlurFlags();
        if (onImageUpdated) onImageUpdated();
      } else {
        setBlurError('Original unblurred image not found.');
      }
    } catch (err) {
      setBlurError(err.response?.data?.detail || 'Failed to undo blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const handleRestoreBlur = async () => {
    setApplyingBlur(true);
    setBlurError('');
    try {
      await api.post(`/annotator/blur/${img.id}/restore-blur`);
      setImageVersion(Date.now());
      await refreshBlurFlags();
      if (onImageUpdated) onImageUpdated();
    } catch (err) {
      setBlurError(err.response?.data?.detail || 'Failed to restore blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 flex flex-col" onClick={onClose}>
      <div className="flex-1 flex items-center justify-center relative" onClick={(e) => e.stopPropagation()}>
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-30 w-9 h-9 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
        </button>

        {/* Nav arrows */}
        {idx > 0 && (
          <button
            onClick={() => onNavigate(images[idx - 1])}
            className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer z-20"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
          </button>
        )}
        {idx < images.length - 1 && (
          <button
            onClick={() => onNavigate(images[idx + 1])}
            className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer z-20"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
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
              <button
                onClick={() => setBlurActive(!blurActive)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-sm border transition cursor-pointer ${
                  blurActive ? 'bg-red-500/90 text-white border-red-400' : 'bg-black/50 text-white border-white/20 hover:bg-black/70'
                }`}
              >
                {blurActive ? '✕ Cancel Blur' : '🔒 Blur Tool'}
              </button>

              {blurActive && blurBoxes.length > 0 && (
                <>
                  <button
                    onClick={handleApplyBlur}
                    className="px-3 py-1.5 rounded-full bg-green-500/90 text-white text-xs font-semibold hover:bg-green-600 transition cursor-pointer backdrop-blur-sm border border-green-400 shadow-lg"
                  >
                    ✓ Apply ({blurBoxes.length})
                  </button>
                  <button
                    onClick={() => setBlurBoxes([])}
                    className="px-3 py-1.5 rounded-full bg-gray-500/80 text-white text-xs font-semibold hover:bg-gray-600 transition cursor-pointer backdrop-blur-sm border border-gray-400"
                  >
                    Clear
                  </button>
                </>
              )}

              {/* Undo Blur */}
              {blurFlags.is_blurred && blurBoxes.length === 0 && (
                <button
                  onClick={handleUndoBlur}
                  className="px-3 py-1.5 rounded-full bg-amber-500/90 text-white text-xs font-semibold hover:bg-amber-600 transition cursor-pointer backdrop-blur-sm border border-amber-400 shadow-lg"
                >
                  ↶ Undo Blur
                </button>
              )}

              {/* Restore Blur — visible after undoing a blurred image */}
              {!blurFlags.is_blurred && blurFlags.compliance_status === 'blurred' && blurBoxes.length === 0 && (
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

        {/* Blur error toast */}
        {blurError && (
          <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-full bg-red-600 text-white text-xs font-medium shadow-lg">
            {blurError}
          </div>
        )}

        {/* Image with BoundingBoxCanvas overlay */}
        <div ref={imageContainerRef} className="relative max-w-5xl w-full mx-16 flex items-center justify-center">
          <SignedImage
            imageId={img.id}
            view={true}
            refreshKey={imageVersion}
            alt={img.filename}
            className="max-w-full max-h-[80vh] object-contain rounded-lg block"
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
      </div>

      {/* Info bar at bottom */}
      <div className="shrink-0 px-6 py-3" onClick={(e) => e.stopPropagation()}>
        <div className="max-w-5xl mx-auto bg-gray-900/80 rounded-lg p-3 flex items-center justify-between backdrop-blur-sm">
          <div className="flex items-center gap-3 min-w-0">
            {img.image_drive_id && (
              <span className="text-blue-300 text-[10px] font-mono shrink-0" title={img.image_drive_id}>{img.image_drive_id.slice(0, 20)}…</span>
            )}
            <span className="text-white text-sm font-medium truncate">{img.filename}</span>
            <div className="flex gap-1.5">
              {getStatusBadges(img).map((b, i) => (
                <span key={i} className={`px-2 py-0.5 text-[10px] font-bold text-white rounded-md ${b.className}`}>
                  {b.label}
                </span>
              ))}
              {blurFlags.is_blurred && !img.manually_blurred && !['blurred', 'processed', 'obfuscated'].includes(img.compliance_status) && (
                <span className="px-2 py-0.5 text-[10px] font-bold text-white rounded-md bg-violet-500">Manual Blur</span>
              )}
            </div>
          </div>
          <span className="text-white/50 text-xs shrink-0 ml-3">
            {idx + 1} / {images.length}
          </span>
        </div>
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
          <button onClick={() => onSave(cell.image_id, selections, isDuplicate)} className="flex-1 px-3 py-1.5 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 cursor-pointer">Save & Approve</button>
        ) : (
          <button onClick={() => onApprove(cell.image_id)} className="flex-1 px-3 py-1.5 bg-green-500 text-white text-xs font-medium rounded-lg hover:bg-green-600 cursor-pointer">Approve</button>
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

  // Blur tool state
  const [blurActive, setBlurActive] = useState(false);
  const [blurBoxes, setBlurBoxes] = useState([]);
  const [applyingBlur, setApplyingBlur] = useState(false);
  const [imageVersion, setImageVersion] = useState(Date.now());
  const [blurError, setBlurError] = useState('');
  // Blur state flags — initialized from row, refreshed after undo/restore
  const [blurFlags, setBlurFlags] = useState({
    is_blurred: row.is_blurred || false,
    compliance_status: row.compliance_status || null,
    is_using_processed: row.is_using_processed,
    manually_blurred: row.manually_blurred || false,
  });
  const imageContainerRef = useRef(null);

  // Reset edits and blur state when image changes
  useEffect(() => {
    setEdits({});
    setBlurActive(false);
    setBlurBoxes([]);
    setBlurError('');
    setImageVersion(Date.now());
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

  // Radio button behavior: select exactly one option per category
  const selectOption = (catId, optId) => {
    const current = getEditsForCat(catId);
    if (!current) return;
    // If already selected, deselect; otherwise select only this one
    const newSels = current.selections.includes(optId) ? [] : [optId];
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

  // In the new schema, review is image-level, not per-category
  const isPending = !row.review_status || row.review_status === 'pending' || row.review_status === 'rework_completed';

  const handleApproveAll = async () => {
    setSaving(true);
    try {
      await onApprove(row.image_id);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      // Build updated annotations if any edits were made
      if (hasAnyChanges) {
        const updatedAnnotations = {};
      for (const cat of categories) {
          const editData = getEditsForCat(cat.id);
          if (editData) {
            updatedAnnotations[cat.key || String(cat.id)] = {
              selected_option_ids: editData.selections,
            };
          }
        }
        await onSaveEdits(row.image_id, updatedAnnotations, null);
      } else {
        await onApprove(row.image_id);
      }
    } finally {
      setSaving(false);
      setEdits({});
    }
  };

  // ── Blur handlers ──
  // Helper to refresh blur flags from admin-accessible endpoint
  const refreshBlurFlags = async () => {
    try {
      const res = await api.get(`/admin/images/${row.image_id}/status`);
      setBlurFlags({
        is_blurred: res.data.is_blurred || false,
        compliance_status: res.data.compliance_status || null,
        is_using_processed: res.data.is_using_processed,
        manually_blurred: res.data.manually_blurred || false,
      });
    } catch (err) {
      console.error('Failed to refresh blur flags:', err);
    }
  };

  const handleApplyBlur = async () => {
    if (!blurBoxes.length) return;
    setApplyingBlur(true);
    setBlurError('');
    try {
      await api.post(`/annotator/blur/apply/${row.image_id}`, { regions: blurBoxes });
      setBlurBoxes([]);
      setBlurActive(false);
      setImageVersion(Date.now());
      await refreshBlurFlags();
    } catch (err) {
      setBlurError(err.response?.data?.detail || 'Failed to apply blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const handleUndoBlur = async () => {
    setApplyingBlur(true);
    setBlurError('');
    try {
      const res = await api.delete(`/annotator/blur/${row.image_id}/blur`);
      if (res.data?.had_original) {
        setImageVersion(Date.now());
        await refreshBlurFlags();
      } else {
        setBlurError('Original unblurred image not found.');
        setApplyingBlur(false);
        return;
      }
    } catch (err) {
      setBlurError(err.response?.data?.detail || 'Failed to undo blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const handleRestoreBlur = async () => {
    setApplyingBlur(true);
    setBlurError('');
    try {
      await api.post(`/annotator/blur/${row.image_id}/restore-blur`);
      setImageVersion(Date.now());
      await refreshBlurFlags();
    } catch (err) {
      setBlurError(err.response?.data?.detail || 'Failed to restore blur');
    } finally {
      setApplyingBlur(false);
    }
  };

  const currentIdx = tableImages.findIndex((img) => img.image_id === row.image_id);

  return (
    <div className="fixed inset-0 z-50 flex bg-black/60" onClick={onClose}>
      <div className="flex w-full h-full" onClick={(e) => e.stopPropagation()}>
        {/* Left panel: Large image + blur tool */}
        <div className="w-[65%] bg-gray-900 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-6 py-3 shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              {row.gcs_folder && (
                <span className="text-blue-300 text-[10px] font-mono shrink-0" title={`Folder: ${row.gcs_folder}`}>{row.gcs_folder.slice(0, 20)}</span>
              )}
              <span className="text-white/80 text-sm font-medium truncate">{row.image_filename}</span>
              {row.reviewed_by_username && (
                <span className="flex items-center gap-1.5 px-2.5 py-1 bg-green-500/20 text-green-300 text-[11px] font-medium rounded-full border border-green-500/30 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                  Reviewed by {row.reviewed_by_username}
                  {row.reviewed_at && (
                    <span className="text-green-400/70 ml-1">
                      · {new Date(row.reviewed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </span>
                  )}
                </span>
              )}
          </div>
            <span className="text-white/50 text-xs shrink-0">{currentIdx + 1} / {tableImages.length}</span>
          </div>
          <div className="flex-1 min-h-0 flex items-center justify-center p-4 relative">
            {/* Nav arrows */}
            {currentIdx > 0 && (
              <button
                onClick={() => onNavigate(tableImages[currentIdx - 1])}
                className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer z-20"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              </button>
            )}
            {currentIdx < tableImages.length - 1 && (
              <button
                onClick={() => onNavigate(tableImages[currentIdx + 1])}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white transition cursor-pointer z-20"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
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
                  <button
                    onClick={() => setBlurActive(!blurActive)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-sm border transition cursor-pointer ${
                      blurActive ? 'bg-red-500/90 text-white border-red-400' : 'bg-black/50 text-white border-white/20 hover:bg-black/70'
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4h16v16H4z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9h6v6H9z" /></svg>
                    {blurActive ? 'Drawing…' : 'Blur Tool'}
                  </button>
                  {blurBoxes.length > 0 && (
                    <>
                      <span className="px-2 py-1 rounded-full bg-black/50 text-white text-xs backdrop-blur-sm border border-white/20">
                        {blurBoxes.length} region{blurBoxes.length > 1 ? 's' : ''}
                      </span>
                      <button onClick={handleApplyBlur} className="px-3 py-1.5 rounded-full bg-green-600 text-white text-xs font-semibold hover:bg-green-700 transition cursor-pointer shadow-lg">
                        ✓ Apply Blur
                      </button>
                      <button onClick={() => setBlurBoxes(prev => prev.slice(0, -1))} className="px-2 py-1.5 rounded-full bg-black/50 text-white text-xs hover:bg-black/70 transition cursor-pointer backdrop-blur-sm border border-white/20">
                        ↶ Undo
                      </button>
                      <button onClick={() => setBlurBoxes([])} className="px-2 py-1.5 rounded-full bg-black/50 text-white text-xs hover:bg-black/70 transition cursor-pointer backdrop-blur-sm border border-white/20">
                        Clear
                      </button>
                    </>
                  )}

                  {/* Undo applied blur — visible when image is blurred (manual or pipeline) & no new boxes drawn */}
                  {blurFlags.is_blurred && blurBoxes.length === 0 && (
                    <button
                      onClick={handleUndoBlur}
                      className="px-3 py-1.5 rounded-full bg-amber-500/90 text-white text-xs font-semibold hover:bg-amber-600 transition cursor-pointer backdrop-blur-sm border border-amber-400 shadow-lg"
                    >
                      ↶ Undo Blur
                    </button>
                  )}

                  {/* Restore blur — visible after undoing a pipeline-blurred image */}
                  {!blurFlags.is_blurred && blurFlags.compliance_status === 'blurred' && blurBoxes.length === 0 && (
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

            {/* Blur error */}
            {blurError && (
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-full bg-red-600 text-white text-xs font-medium shadow-lg">
                {blurError}
              </div>
            )}

            <div ref={imageContainerRef} className="relative w-full h-full overflow-hidden flex items-center justify-center">
              <SignedImage
                imageId={row.image_id}
                view={true}
                refreshKey={imageVersion}
                alt={row.image_filename}
                className="max-w-full max-h-full object-contain rounded-lg block"
                style={{ maxHeight: 'calc(100vh - 120px)' }}
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
          </div>
        </div>

        {/* Right panel: Categories + options (narrower) */}
        <div className="w-[35%] bg-white flex flex-col min-h-0">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
            <h3 className="text-sm font-semibold text-gray-900">Annotations</h3>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-400 bg-gray-100 px-2 py-1 rounded">Esc</span>
              <button onClick={onClose} className="w-7 h-7 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg cursor-pointer">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
          </div>

          {/* Scrollable category list */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-3">
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
                <div key={cat.id} className={`rounded-lg border p-2.5 ${changed ? 'border-indigo-300 bg-indigo-50/30' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <h4 className="text-[11px] font-semibold text-gray-800 truncate">{cat.name}</h4>
                    {row.review_status === 'approved' ? (
                      <span className="px-1.5 py-0.5 bg-green-100 text-green-700 text-[9px] font-medium rounded-full shrink-0">✓</span>
                    ) : row.review_status === 'rework_requested' ? (
                      <span className="px-1.5 py-0.5 bg-orange-100 text-orange-700 text-[9px] font-medium rounded-full shrink-0">🔄</span>
                    ) : row.review_status === 'rework_completed' ? (
                      <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-[9px] font-medium rounded-full shrink-0">✅</span>
                    ) : (
                      <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-medium rounded-full shrink-0">⏳</span>
                    )}
                    <span className="text-[9px] text-gray-400 ml-auto shrink-0">{row.annotated_by_username}</span>
                  </div>
                  {row.reviewed_by_username && (
                    <div className="flex items-center gap-1 mb-1 px-1">
                      <span className="w-1 h-1 rounded-full bg-green-400 shrink-0" />
                      <span className="text-[9px] text-green-600">
                        Reviewed by <span className="font-semibold">{row.reviewed_by_username}</span>
                        {row.reviewed_at && (
                          <span className="text-green-400 ml-1">
                            · {new Date(row.reviewed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                          </span>
                        )}
                    </span>
                  </div>
                  )}
                  <div className="space-y-0.5">
                    {cell.all_options.map((opt) => {
                      const selected = currentEdits?.selections.includes(opt.id);
                      return (
                        <label key={opt.id} className={`flex items-center gap-2 px-2 py-1 rounded-md border cursor-pointer transition text-[11px] ${selected ? 'border-indigo-400 bg-indigo-50 text-indigo-900' : 'border-gray-100 bg-white text-gray-600 hover:border-gray-300'}`}>
                          <input type="radio" name={`cat-${cat.id}`} checked={selected || false} onChange={() => selectOption(cat.id, opt.id)} className="sr-only" />
                          <div className={`w-3 h-3 rounded-full flex items-center justify-center border shrink-0 ${selected ? 'border-indigo-500' : 'border-gray-300'}`}>
                            {selected && <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />}
                          </div>
                          <span className="truncate">{opt.label}</span>
                          {opt.is_typical && <span className="ml-auto text-[9px] bg-gray-100 text-gray-400 px-1 rounded shrink-0">typ</span>}
                        </label>
                      );
                    })}
                  </div>
                  <label className="flex items-center gap-2 mt-1.5 px-2 py-1 rounded-md border border-gray-200 cursor-pointer text-[11px]">
                    <input type="checkbox" checked={currentEdits?.isDuplicate || false} onChange={() => setEditForCat(cat.id, 'isDuplicate', !currentEdits?.isDuplicate)} className="accent-red-500 w-3 h-3" />
                    <span className="text-gray-700">Duplicate?</span>
                  </label>
                </div>
              );
            })}
          </div>

          {/* Bottom action bar */}
          <div className="border-t border-gray-200 px-4 py-2.5 flex items-center gap-2 bg-gray-50">
            {hasAnyChanges ? (
              <button
                onClick={handleSaveAll}
                disabled={saving}
                className="flex-1 px-3 py-2 bg-green-600 text-white text-xs font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 cursor-pointer"
              >
                {saving ? 'Saving...' : 'Save & Approve All'}
              </button>
            ) : isPending ? (
              <>
              <button
                onClick={handleApproveAll}
                disabled={saving}
                  className="flex-1 px-3 py-2 bg-green-500 text-white text-xs font-medium rounded-lg hover:bg-green-600 disabled:opacity-50 cursor-pointer"
              >
                  {saving ? 'Approving...' : 'Approve'}
              </button>
                <button
                  onClick={() => onRework(row.image_id)}
                  disabled={saving}
                  className="px-3 py-2 border border-amber-300 text-amber-600 text-xs font-medium rounded-lg hover:bg-amber-50 disabled:opacity-50 cursor-pointer"
                >
                  Rework
                </button>
              </>
            ) : (
              <>
                <span className="flex-1 text-center text-xs text-green-600 font-medium">✓ Approved</span>
                  <button
                  onClick={() => onRework(row.image_id)}
                    disabled={saving}
                  className="px-3 py-2 border border-amber-300 text-amber-600 text-xs font-medium rounded-lg hover:bg-amber-50 disabled:opacity-50 cursor-pointer"
                  >
                  Rework
                  </button>
              </>
            )}
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
  const [viewMode] = useState('gallery'); // gallery only
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
      params.set('page', '1');
      params.set('page_size', '10000');
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
  }, [filter, annotatorFilter]);

  useEffect(() => {
    loadTable();
  }, [loadTable]);

  const refreshData = useCallback(() => {
    loadTable();
  }, [loadTable]);

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
  // In the new schema, review is image-level. The "annotationId" param is
  // actually the image_id for all callers from the review table view.
  const handleApprove = async (imageId) => {
    try {
      await api.put(`/admin/review/image/${imageId}/approve`, {});
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed');
    }
  };

  const handleApproveAndRefresh = async (imageId) => {
    await handleApprove(imageId);
    refreshData();
  };

  const handleSaveEdits = async (imageId, selectedIds, isDuplicate) => {
    try {
      await api.put(`/admin/review/image/${imageId}/update`, {
        annotations: selectedIds,  // image-level annotations dict
        is_duplicate: isDuplicate,
      });
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to save');
    }
  };

  const handleSaveEditsAndRefresh = async (imageId, selectedIds, isDuplicate) => {
    await handleSaveEdits(imageId, selectedIds, isDuplicate);
    setEditingCell(null);
    cancelEditing();
    refreshData();
  };

  // ── Send for Rework ──
  const [showReworkModal, setShowReworkModal] = useState(false);
  const [reworkAnnotationId, setReworkAnnotationId] = useState(null);
  const [reworkReason, setReworkReason] = useState('');
  const [sendingRework, setSendingRework] = useState(false);

  const openReworkModal = (imageId) => {
    setReworkAnnotationId(imageId);
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
      await api.post(`/admin/images/${reworkAnnotationId}/rework`, { reason: reworkReason });
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
        // Image-level approve — only if not already approved
        if (!row.review_status || row.review_status === 'pending' || row.review_status === 'rework_completed') {
          promises.push(api.put(`/admin/review/image/${imgId}/approve`, {}));
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
          // Approve this image (image-level review)
          if (!modalRow.review_status || modalRow.review_status === 'pending' || modalRow.review_status === 'rework_completed') {
            handleApprove(modalRow.image_id).then(() => refreshData());
          }
          return;
        }
        return;
      }

      // Gallery/Table shortcuts (no modal)
      if (tableData && tableData.images.length > 0) {
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

  if (tableLoading && !stats) {
    return <div className="py-8 text-center text-gray-500">Loading...</div>;
  }

  const tableTotalPages = tableData ? Math.max(1, Math.ceil(tableData.total_images / tableData.page_size)) : 1;

  return (
    <div className="space-y-4">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 stagger-children">
          {[
            { label: 'Images Pending Review', value: stats.pending_review, key: 'pending', icon: '⏳', gradient: 'from-amber-500 to-orange-500', activeBorder: 'ring-2 ring-amber-400 ring-offset-2' },
            { label: 'Images Approved', value: stats.approved, key: 'approved', icon: '✓', gradient: 'from-emerald-500 to-teal-500', activeBorder: 'ring-2 ring-emerald-400 ring-offset-2' },
            { label: 'Total Images', value: stats.total_completed, key: null, icon: '📊', gradient: 'from-indigo-500 to-purple-500', activeBorder: '' },
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

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
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

      {/* ─── GALLERY VIEW ────────────────────────────────── */}
      {viewMode === 'gallery' && (
        <>
          {tableLoading ? (
            <div className="py-8 text-center text-gray-500">Loading...</div>
          ) : !tableData || tableData.images.length === 0 ? (
            <div className="py-12 text-center text-gray-500">No annotations found for this filter.</div>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {tableData.images.map((row) => {
                  // Count annotated categories for this image
                  const totalAnnotated = tableData.categories.filter((cat) => row.annotations[String(cat.id)]).length;
                  // Review is image-level, not per-cell
                  const allApproved = row.review_status === 'approved' && totalAnnotated > 0;
                  const hasRework = row.review_status === 'rework_requested' || row.review_status === 'rework_completed';
                  const isPending = (!row.review_status || row.review_status === 'pending' || row.review_status === 'rework_completed') && totalAnnotated > 0;

                        return (
                    <div
                            key={row.image_id}
                      className={`group relative rounded-xl overflow-hidden shadow-md hover:shadow-xl transition-all duration-300 ${
                        hasRework ? 'ring-3 ring-orange-400' : allApproved ? 'ring-2 ring-green-400' : 'ring-1 ring-gray-200 hover:ring-indigo-400'
                      }`}
                          >
                      {/* Image */}
                      <div className="relative aspect-[4/3]">
                        <img
                          src={getImageUrl(row.image_id)}
                          alt={row.image_filename}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />

                        {/* Gradient overlay for text readability */}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

                        {/* Status badge - top left */}
                        <div className="absolute top-3 left-3 flex gap-1">
                          {allApproved ? (
                            <span className="px-2.5 py-1 bg-green-500 text-white text-xs font-bold rounded-lg shadow-lg">
                              ✓ Approved
                            </span>
                          ) : hasRework ? (
                            <span className="px-2.5 py-1 bg-orange-500 text-white text-xs font-bold rounded-lg shadow-lg">
                              🔄 Rework
                            </span>
                          ) : isPending ? (
                            <span className="px-2.5 py-1 bg-amber-500 text-white text-xs font-bold rounded-lg shadow-lg">
                              ⏳ Pending
                            </span>
                          ) : null}
                          {row.deliverable_image_path && (
                            <span className={`px-2 py-1 text-white text-xs font-bold rounded-lg shadow-lg ${row.deliverable_image_path.includes('/blurred/') ? 'bg-amber-600' : 'bg-teal-500'}`} title={`Delivered: ${row.deliverable_image_path}`}>
                              {row.deliverable_image_path.includes('/blurred/') ? '🔒' : '✅'}
                            </span>
                          )}
                              </div>

                        {/* Image ID + Filename - top right */}
                        <div className="absolute top-3 right-3 max-w-[60%] flex flex-col items-end gap-0.5">
                          {row.image_drive_id && (
                            <span className="px-2 py-0.5 bg-blue-600/70 text-white text-[9px] font-mono rounded-md backdrop-blur-sm truncate block max-w-full" title={row.image_drive_id}>
                              {row.image_drive_id.slice(0, 16)}…
                            </span>
                          )}
                          <span className="px-2 py-1 bg-black/50 text-white text-[10px] font-medium rounded-lg backdrop-blur-sm truncate block">
                            {row.image_filename}
                          </span>
                        </div>

                        {/* Annotation labels overlay - bottom */}
                        <div className="absolute bottom-0 left-0 right-0 p-3">
                          <div className="flex flex-wrap gap-1.5">
                            {tableData.categories.map((cat) => {
                              const cell = row.annotations[String(cat.id)];
                              if (!cell) {
                                return (
                                  <span
                                    key={cat.id}
                                    className="px-2 py-1 bg-gray-900/60 text-gray-400 text-[10px] rounded-md backdrop-blur-sm border border-gray-600/50"
                                    title={`${cat.name}: Not annotated`}
                                  >
                                    {cat.name.split(' ')[0]}: <span className="italic">?</span>
                                  </span>
                                );
                              }
                              const isReworkCell = cell.review_status === 'rework_requested' || cell.review_status === 'rework_completed';
                              const isApprovedCell = cell.review_status === 'approved';
                              return cell.selected_options.length === 0 ? (
                                <span
                                  key={cat.id}
                                  className="px-2 py-1 bg-gray-700/80 text-gray-300 text-[10px] rounded-md backdrop-blur-sm border border-gray-600"
                                  title={cat.name}
                                >
                                  {cat.name.split(' ')[0]}: <span className="italic">none</span>
                                </span>
                                      ) : (
                                cell.selected_options.map((opt, i) => (
                                  <span
                                    key={`${cat.id}-${i}`}
                                    className={`px-2 py-1 text-[11px] font-medium rounded-md backdrop-blur-sm border ${
                                      isReworkCell
                                        ? 'bg-orange-500/80 text-white border-orange-400'
                                        : isApprovedCell
                                          ? 'bg-green-500/80 text-white border-green-400'
                                          : 'bg-indigo-500/80 text-white border-indigo-400'
                                    }`}
                                    title={`${cat.name} — by ${cell.annotator_username}`}
                                  >
                                            {opt.label}
                                          </span>
                                        ))
                              );
                            })}
                          </div>
                        </div>

                        {/* Hover overlay with action buttons */}
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-center justify-center gap-3">
                          {/* Approve All button */}
                          {isPending && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleApprove(row.image_id).then(() => refreshData());
                              }}
                              className="flex flex-col items-center gap-1.5 px-4 py-3 bg-green-500 hover:bg-green-600 text-white rounded-xl shadow-lg transform scale-90 group-hover:scale-100 transition-all duration-200 cursor-pointer"
                              title="Approve all pending annotations"
                            >
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                              </svg>
                              <span className="text-[10px] font-semibold">Approve</span>
                            </button>
                          )}
                          {/* Rework button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              openReworkModal(row.image_id);
                            }}
                            className="flex flex-col items-center gap-1.5 px-4 py-3 bg-amber-500 hover:bg-amber-600 text-white rounded-xl shadow-lg transform scale-90 group-hover:scale-100 transition-all duration-200 cursor-pointer"
                            title="Send for rework"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            <span className="text-[10px] font-semibold">Rework</span>
                          </button>
                          {/* View button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setModalRow(row);
                            }}
                            className="flex flex-col items-center gap-1.5 px-4 py-3 bg-white hover:bg-gray-100 text-gray-800 rounded-xl shadow-lg transform scale-90 group-hover:scale-100 transition-all duration-200 cursor-pointer"
                            title="View details"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                            <span className="text-[10px] font-semibold">View</span>
                          </button>
                                    </div>
                                  </div>

                      {/* Annotator + Reviewer info bar */}
                      <div className="bg-white px-3 py-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 min-w-0">
                            {row.annotated_by_username && (
                              <span className="flex items-center gap-1 text-xs text-gray-600">
                                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                                {row.annotated_by_username}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-gray-400">
                            {allApproved ? '✓ Approved' : hasRework ? '🔄 Rework' : isPending ? 'Pending review' : ''}
                          </span>
                        </div>
                        {row.reviewed_by_username && (
                          <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                            <span>Reviewed by <span className="font-semibold text-gray-700">{row.reviewed_by_username}</span></span>
                            {row.reviewed_at && (
                              <span className="text-gray-400 ml-auto">
                                {new Date(row.reviewed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}{' '}
                                {new Date(row.reviewed_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                              </span>
                                  )}
                          </div>
                        )}
                      </div>
                    </div>
                              );
                            })}
              </div>
              {/* Image count */}
              <div className="text-sm text-gray-500 mt-4">
                <span>Showing all {tableData.total_images} images</span>
              </div>
            </>
          )}
        </>
      )}

      {/* ─── CARDS VIEW (hidden — gallery only) ──────────── */}
      {false && (
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

      {/* ─── Floating bulk approve bar (table only — hidden) ── */}
      {selectedRows.size > 0 && false && (
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
          onApprove={async (imageId) => {
            await handleApprove(imageId);
            // Optimistically update modalRow to show approved status immediately
            if (modalRow) {
              setModalRow({ ...modalRow, review_status: 'approved' });
            }
            refreshData();
          }}
          onSaveEdits={async (imageId, sels, dup) => { await handleSaveEdits(imageId, sels, dup); refreshData(); }}
          onRework={(imageId) => { setModalRow(null); openReworkModal(imageId); }}
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
  const VALID_TABS = ['users', 'review', 'images', 'improper', 'edit-requests', 'annotator-stats', 'settings', 'pipeline', 'arbiter', 'compliance', 'photo-registry'];
  const pathSegment = location.pathname.replace(/^\/admin\/?/, '').split('/')[0] || 'users';
  const activeTab = VALID_TABS.includes(pathSegment) ? pathSegment : 'users';

  const setActiveTab = (key) => {
    navigate(key === 'users' ? '/admin' : `/admin/${key}`, { replace: false });
  };

  const tabs = [
    { key: 'users', label: 'Users', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
    )},
    { key: 'review', label: 'Review', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
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
    { key: 'annotator-stats', label: 'Annotator Stats', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
    )},
    { key: 'settings', label: 'Settings', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
    )},
    { key: 'pipeline', label: 'Master Pipeline', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
    )},
    { key: 'arbiter', label: 'Arbiter Classifier', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" /></svg>
    )},
    { key: 'compliance', label: 'Compliance', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
    )},
    { key: 'photo-registry', label: 'Photo Registry', icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
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
            {activeTab === 'review' && <ReviewTab />}
            {activeTab === 'images' && <ImagesTab />}
          {activeTab === 'improper' && <ImproperImagesTab />}
          {activeTab === 'edit-requests' && <EditRequestsTab />}
          {activeTab === 'annotator-stats' && <AnnotatorStatsTab />}
          {activeTab === 'settings' && <SettingsTab />}
          {activeTab === 'pipeline' && <MasterPipelineTab />}
          {activeTab === 'arbiter' && <ArbiterClassifierTab />}
          {activeTab === 'compliance' && <ComplianceTab />}
          {activeTab === 'photo-registry' && <PhotoRegistryTab />}
        </div>
      </main>
    </div>
  );
}
