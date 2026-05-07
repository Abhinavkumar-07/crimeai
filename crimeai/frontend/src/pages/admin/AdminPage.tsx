import { useState } from 'react'
import { Users, Database, Activity, RefreshCw, Cpu, Shield } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api } from '@/services'
import { mlApi } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import Badge from '@/components/ui/Badge'
import { formatDate, roleLabel, timeAgo, cn } from '@/utils'
import type { User } from '@/types'

type AdminTab = 'users' | 'ml' | 'system'

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>('users')

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      {/* Tab bar */}
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
        {(['users', 'ml', 'system'] as AdminTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize',
              activeTab === tab
                ? 'bg-bg-elevated text-text-primary shadow-inner-sm'
                : 'text-text-muted hover:text-text-secondary'
            )}
          >
            {tab === 'ml' ? 'ML Models' : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === 'users' && <UsersTab />}
      {activeTab === 'ml' && <MLTab />}
      {activeTab === 'system' && <SystemTab />}
    </div>
  )
}

/* ── Users Tab ────────────────────────────────────────────────────────────── */
function UsersTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => api.get<User[]>('/users/').then((r) => r.data),
  })

  const qc = useQueryClient()
  const deactivate = useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin', 'users'] }); toast.success('User deactivated') },
    onError: () => toast.error('Failed to deactivate user'),
  })

  if (isLoading) return <PageLoader />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Users size={15} /> User Management
        </h3>
        <span className="text-xs text-text-muted">{data?.length ?? 0} total users</span>
      </div>

      <div className="table-wrapper">
        <table className="table-base">
          <thead className="table-head">
            <tr>
              <th className="table-th">Name</th>
              <th className="table-th">Email</th>
              <th className="table-th">Role</th>
              <th className="table-th">Badge</th>
              <th className="table-th">Department</th>
              <th className="table-th">Status</th>
              <th className="table-th">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((user) => (
              <tr key={user.id} className="table-row">
                <td className="table-td font-medium">{user.full_name}</td>
                <td className="table-td text-text-secondary text-xs">{user.email}</td>
                <td className="table-td">
                  <Badge variant={user.role === 'admin' ? 'red' : user.role === 'police' ? 'blue' : 'gray'}>
                    {roleLabel(user.role)}
                  </Badge>
                </td>
                <td className="table-td font-mono text-xs text-text-muted">{user.badge_number ?? '—'}</td>
                <td className="table-td text-xs text-text-secondary">{user.department ?? '—'}</td>
                <td className="table-td">
                  <span className="inline-flex items-center gap-1 text-2xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-status-online" />
                    Active
                  </span>
                </td>
                <td className="table-td">
                  <button
                    onClick={() => {
                      if (confirm(`Deactivate ${user.full_name}?`)) deactivate.mutate(user.id)
                    }}
                    className="text-2xs text-severity-high hover:underline"
                  >
                    Deactivate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ── ML Models Tab ────────────────────────────────────────────────────────── */
function MLTab() {
  const { data: modelInfo, isLoading, refetch } = useQuery({
    queryKey: ['admin', 'ml', 'model-info'],
    queryFn: mlApi.getModelInfo,
  })

  const qc = useQueryClient()

  const trainMutation = useMutation({
    mutationFn: mlApi.triggerHotspotPrediction,
    onSuccess: () => {
      toast.success('Training job queued')
      setTimeout(() => qc.invalidateQueries({ queryKey: ['admin', 'ml'] }), 3000)
    },
    onError: () => toast.error('Failed to trigger training'),
  })

  const clusterMutation = useMutation({
    mutationFn: () => mlApi.triggerClustering({ auto_eps: true }),
    onSuccess: () => toast.success('Clustering job queued'),
    onError: () => toast.error('Failed to trigger clustering'),
  })

  const embedMutation = useMutation({
    mutationFn: () => api.post('/ml/embed-crimes', null, { params: { limit: 1000 } }).then((r) => r.data),
    onSuccess: (data: any) => toast.success(`Embeddings: ${data.processed ?? 0} processed`),
    onError: () => toast.error('Embedding failed'),
  })

  if (isLoading) return <PageLoader />

  const hotspotMeta = modelInfo?.hotspot_model
  const isTrained = hotspotMeta?.status !== 'not_trained' && hotspotMeta?.trained_at

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        <Cpu size={15} /> ML Model Management
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Hotspot model */}
        <div className="card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-text-primary">Hotspot Predictor</p>
            <Badge variant={isTrained ? 'green' : 'amber'}>{isTrained ? 'Trained' : 'Not trained'}</Badge>
          </div>
          {isTrained && (
            <div className="space-y-1 text-xs text-text-secondary">
              <div className="flex justify-between"><span>Accuracy</span><span className="font-mono">{((hotspotMeta.accuracy ?? 0) * 100).toFixed(1)}%</span></div>
              <div className="flex justify-between"><span>AUC-ROC</span><span className="font-mono">{((hotspotMeta.auc_roc ?? 0) * 100).toFixed(1)}%</span></div>
              <div className="flex justify-between"><span>Trained</span><span>{timeAgo(hotspotMeta.trained_at)}</span></div>
              <div className="flex justify-between"><span>Samples</span><span className="font-mono">{hotspotMeta.n_training_samples?.toLocaleString()}</span></div>
            </div>
          )}
          <button
            onClick={() => trainMutation.mutate()}
            disabled={trainMutation.isPending}
            className="btn-primary text-xs w-full justify-center"
          >
            {trainMutation.isPending ? 'Queuing…' : isTrained ? 'Retrain' : 'Train Now'}
          </button>
        </div>

        {/* Clustering */}
        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-primary">DBSCAN Clustering</p>
          <p className="text-xs text-text-muted">Groups crime locations into spatial clusters using adaptive eps detection.</p>
          <button
            onClick={() => clusterMutation.mutate()}
            disabled={clusterMutation.isPending}
            className="btn-secondary text-xs w-full justify-center"
          >
            {clusterMutation.isPending ? 'Queuing…' : 'Run Clustering'}
          </button>
        </div>

        {/* Embeddings */}
        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-primary">Crime Embeddings</p>
          <p className="text-xs text-text-muted">Generate sentence-transformer embeddings for similarity search (pgvector).</p>
          <p className="text-2xs text-text-muted font-mono">{modelInfo?.embedding_model}</p>
          <button
            onClick={() => embedMutation.mutate()}
            disabled={embedMutation.isPending}
            className="btn-secondary text-xs w-full justify-center"
          >
            {embedMutation.isPending ? 'Processing…' : 'Batch Embed (1000)'}
          </button>
        </div>
      </div>

      {/* Feature importances */}
      {isTrained && hotspotMeta?.feature_importances && (
        <div className="card p-4">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">Feature Importances</p>
          <div className="space-y-2">
            {Object.entries(hotspotMeta.feature_importances as Record<string, number>)
              .sort(([, a], [, b]) => b - a)
              .map(([feature, importance]) => (
                <div key={feature} className="flex items-center gap-3">
                  <span className="text-xs text-text-secondary w-28 font-mono">{feature}</span>
                  <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent-blue rounded-full"
                      style={{ width: `${(importance * 100).toFixed(1)}%` }}
                    />
                  </div>
                  <span className="text-2xs text-text-muted font-mono w-10 text-right">
                    {(importance * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── System Tab ───────────────────────────────────────────────────────────── */
function SystemTab() {
  const { data: health } = useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => fetch('/health').then((r) => r.json()),
    refetchInterval: 30_000,
  })

  const { data: ready } = useQuery({
    queryKey: ['system', 'ready'],
    queryFn: () => fetch('/ready').then((r) => r.json()),
    refetchInterval: 30_000,
  })

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        <Activity size={15} /> System Health
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Application</p>
          {health ? (
            <div className="space-y-2 text-xs">
              <StatusRow label="Status" value={health.status} ok={health.status === 'ok'} />
              <StatusRow label="Version" value={health.version} />
              <StatusRow label="Environment" value={health.env} />
            </div>
          ) : <div className="h-16 flex items-center justify-center text-text-muted text-xs">Loading…</div>}
        </div>

        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Infrastructure</p>
          {ready ? (
            <div className="space-y-2 text-xs">
              <StatusRow label="Database" value={ready.checks?.database} ok={ready.checks?.database === 'ok'} />
              <StatusRow label="Redis Cache" value={ready.checks?.redis} ok={ready.checks?.redis === 'ok'} />
              <StatusRow label="Overall" value={ready.status} ok={ready.status === 'ready'} />
            </div>
          ) : <div className="h-16 flex items-center justify-center text-text-muted text-xs">Loading…</div>}
        </div>
      </div>
    </div>
  )
}

function StatusRow({ label, value, ok }: { label: string; value?: string; ok?: boolean }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-text-muted">{label}</span>
      <span className={cn('flex items-center gap-1.5 font-medium capitalize',
        ok === true ? 'text-severity-low' : ok === false ? 'text-severity-high' : 'text-text-primary'
      )}>
        {ok !== undefined && (
          <span className={cn('w-1.5 h-1.5 rounded-full', ok ? 'bg-status-online' : 'bg-status-offline')} />
        )}
        {value ?? '—'}
      </span>
    </div>
  )
}
