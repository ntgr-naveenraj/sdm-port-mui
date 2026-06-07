import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { AuthState } from "../utils/constants";

interface AuthStore extends AuthState {
  setAuth: (data: Partial<AuthState>) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      isAuthenticated: false,
      user_id: null,
      token: null,
      account_id: null,
      email: null,
      environment: "pri-qa",
      
      setAuth: (data) => set((state) => ({ ...state, ...data })),
      
      logout: () =>
        set({
          isAuthenticated: false,
          user_id: null,
          token: null,
          account_id: null,
          email: null,
        }),
    }),
    {
      name: "auth-storage",
      storage: createJSONStorage(() => localStorage),
    }
  )
);

export default useAuthStore;
