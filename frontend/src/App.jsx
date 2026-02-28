import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import AdminDashboard from './pages/AdminDashboard';
import AnnotatorHome from './pages/AnnotatorHome';
import AnnotationPage from './pages/AnnotationPage';
import ImageAnnotationPage from './pages/ImageAnnotationPage';

function ProtectedRoute({ children, role }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="flex items-center justify-center h-screen">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-3 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
        <p className="text-sm text-gray-500 font-medium">Loading...</p>
      </div>
    </div>
  );
  if (!user) return <Navigate to="/login" />;
  if (role && user.role !== role) return <Navigate to="/" />;
  return children;
}

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" />;
  if (user.role === 'admin') return <Navigate to="/admin" />;
  return <Navigate to="/annotator" />;
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/admin/*"
          element={
            <ProtectedRoute role="admin">
              <AdminDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/annotator"
          element={
            <ProtectedRoute role="annotator">
              <AnnotatorHome />
            </ProtectedRoute>
          }
        />
        <Route
          path="/annotator/category/:categoryId"
          element={
            <ProtectedRoute role="annotator">
              <AnnotationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/annotator/image/:imageId"
          element={
            <ProtectedRoute role="annotator">
              <ImageAnnotationPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </div>
  );
}
