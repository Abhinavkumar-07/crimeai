import { api } from './api'
import type { FIRReport } from '@/types'

export const firApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<{ items: FIRReport[]; total: number }>('/fir/', { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<FIRReport>(`/fir/${id}`).then((r) => r.data),

  submit: (payload: { fir_number: string; raw_text: string; crime_id?: string }) =>
    api.post<FIRReport>('/fir/', payload).then((r) => r.data),

  reprocess: (id: string) =>
    api.post(`/fir/${id}/reprocess`).then((r) => r.data),

  extract: (text: string) =>
    api.post('/nlp/extract', { text }).then((r) => r.data),

  classify: (text: string) =>
    api.post('/nlp/classify', { text }).then((r) => r.data),
}
