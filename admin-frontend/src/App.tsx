import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import { useAuthStore } from './stores/authStore';
import ErrorBoundary from './components/ErrorBoundary';
import AdminLayout from './layouts/AdminLayout';
import LoginPage from './pages/login/LoginPage';
import DashboardPage from './pages/dashboard/DashboardPage';
import AigcPage from './pages/aigc/AigcPage';
import PersonaPage from './pages/persona/PersonaPage';
import MemoryPage from './pages/memory/MemoryPage';
import UsersPage from './pages/users/UsersPage';
import CommercePage from './pages/commerce/CommercePage';
import DevopsPage from './pages/devops/DevopsPage';
import ScenesPage from './pages/scenes/ScenesPage';
import OutfitsPage from './pages/outfits/OutfitsPage';
import LaunchesPage from './pages/launches/LaunchesPage';
import AssetsPage from './pages/assets/AssetsPage';
import SubscriptionsPage from './pages/subscriptions/SubscriptionsPage';
import WorldEventsPage from './pages/world-events/WorldEventsPage';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  if (!isLoggedIn) return <Navigate to="/admin/login" replace />;
  return <>{children}</>;
};

const App: React.FC = () => (
  <ErrorBoundary>
  <ConfigProvider theme={{ token: { colorPrimary: '#6c5ce7' } }}>
    <AntApp>
      <BrowserRouter>
        <Routes>
          <Route path="/admin/login" element={<LoginPage />} />
          <Route
            path="/admin"
            element={
              <ProtectedRoute>
                <AdminLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="aigc" element={<AigcPage />} />
            <Route path="persona" element={<PersonaPage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="commerce" element={<CommercePage />} />
            <Route path="devops" element={<DevopsPage />} />
            <Route path="scenes" element={<ScenesPage />} />
            <Route path="outfits" element={<OutfitsPage />} />
            <Route path="launches" element={<LaunchesPage />} />
            <Route path="assets" element={<AssetsPage />} />
            <Route path="subscriptions" element={<SubscriptionsPage />} />
            <Route path="world-events" element={<WorldEventsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </BrowserRouter>
    </AntApp>
  </ConfigProvider>
  </ErrorBoundary>
);

export default App;
