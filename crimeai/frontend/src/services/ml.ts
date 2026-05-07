import { api } from './api'
import type { ClusterResult, SimulationResult, PatrolRoute } from '@/types'

export const mlApi = {
  getClusters: () =>
    api.get<ClusterResult>('/ml/clusters').then((r) => r.data),

  triggerClustering: (params?: { eps_km?: number; auto_eps?: boolean }) =>
    api.post('/ml/cluster', null, { params }).then((r) => r.data),

  getRiskMap: () =>
    api.get<{ risk_map: Record<string, { score: number; level: string; components: Record<string, number> }> }>('/ml/risk-map').then((r) => r.data),

  getHotspotPredictions: () =>
    api.get('/ml/hotspot-predictions').then((r) => r.data),

  triggerHotspotPrediction: () =>
    api.post('/ml/hotspot-prediction').then((r) => r.data),

  getAreaProfile: (district: string, lookback_days = 60) =>
    api.get(`/ml/profile/${encodeURIComponent(district)}`, { params: { lookback_days } }).then((r) => r.data),

  getModelInfo: () =>
    api.get('/ml/model-info').then((r) => r.data),

  getTaskStatus: (taskId: string) =>
    api.get(`/ml/tasks/${taskId}`).then((r) => r.data),

  runSimulation: (payload: {
    scenario: string
    district: string
    parameters: Record<string, unknown>
    num_simulations?: number
  }) => api.post<SimulationResult>('/simulation/run', payload).then((r) => r.data),

  getScenarios: () =>
    api.get('/simulation/scenarios').then((r) => r.data),

  optimizePatrol: (payload: {
    start_lat: number
    start_lng: number
    district: string
    strategy?: string
    num_checkpoints?: number
    patrol_type?: string
  }) => api.post<PatrolRoute>('/patrol/optimize', payload).then((r) => r.data),
}
