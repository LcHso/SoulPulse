import { create } from 'zustand';

interface AuthState {
  token: string | null;
  isLoggedIn: boolean;
  login: (token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: sessionStorage.getItem('admin_token'),
  isLoggedIn: !!sessionStorage.getItem('admin_token'),
  login: (token: string) => {
    sessionStorage.setItem('admin_token', token);
    set({ token, isLoggedIn: true });
  },
  logout: () => {
    sessionStorage.removeItem('admin_token');
    set({ token: null, isLoggedIn: false });
  },
}));
