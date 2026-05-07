/**
 * UI Zustand store — sidebar collapse, active route, global loading states.
 */
import { create } from 'zustand'

interface UIState {
  sidebarCollapsed: boolean
  mobileMenuOpen: boolean
  globalLoading: boolean
  alertPanelOpen: boolean

  toggleSidebar: () => void
  setSidebarCollapsed: (v: boolean) => void
  toggleMobileMenu: () => void
  setGlobalLoading: (v: boolean) => void
  toggleAlertPanel: () => void
}

export const useUIStore = create<UIState>()((set) => ({
  sidebarCollapsed: false,
  mobileMenuOpen: false,
  globalLoading: false,
  alertPanelOpen: false,

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  toggleMobileMenu: () => set((s) => ({ mobileMenuOpen: !s.mobileMenuOpen })),
  setGlobalLoading: (v) => set({ globalLoading: v }),
  toggleAlertPanel: () => set((s) => ({ alertPanelOpen: !s.alertPanelOpen })),
}))
