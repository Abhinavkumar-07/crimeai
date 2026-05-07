import { useState } from 'react'
import { FlaskConical, Play, TrendingDown, AlertTriangle } from 'lucide-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
import toast from 'react-hot-toast'
import { mlApi } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import { cn } from '@/utils'
import type { SimulationResult } from '@/types'

const DISTRICTS = [
  'Connaught Place', 'Karol Bagh', 'Rohini', 'Dwarka',
  'Saket', 'Lajpat Nagar', 'Janakpuri', 'Shahdara',
]

export default function SimulationPage() {
  const [scenario, setScenario] = useState('patrol_increase')
  const [district, setDistrict] = useState(DISTRICTS[0])
  const [numSims, setNumSims] = useState(200)
  const [params, setParams] = useState<Record<string, unknown>>({ increase_pct: 30 })
  const [result, setResult] = useState<SimulationResult | null>(null)

  const { data: scenarios } = useQuery({
    queryKey: ['simulation', 'scenarios'],
    queryFn: mlApi.getScenarios,
  })

  const runMutation = useMutation({
    mutationFn: () => mlApi.runSimulation({ scenario, district, parameters: params, num_simulations: numSims }),
    onSuccess: (data) => {
      setResult(data)
      toast.success('Simulation complete')
    },
    onError: () => toast.error('Simulation failed'),
  })

  const selectedScenario = scenarios?.find((s: any) => s.id === scenario)

  return (
    <div className="p-5 space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Config panel */}
        <div className="card p-5 space-y-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <FlaskConical size={15} /> Scenario Configuration
          </h3>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Scenario</label>
            <select className="input" value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {scenarios?.map((s: any) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            {selectedScenario && (
              <p className="text-2xs text-text-muted mt-1.5 leading-relaxed">{selectedScenario.description}</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">District</label>
            <select className="input" value={district} onChange={(e) => setDistrict(e.target.value)}>
              {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>

          {/* Dynamic params */}
          {scenario === 'patrol_increase' && (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Patrol Increase: {params.increase_pct as number}%
              </label>
              <input
                type="range" min={5} max={100} step={5}
                value={params.increase_pct as number}
                onChange={(e) => setParams({ increase_pct: Number(e.target.value) })}
                className="w-full accent-accent-blue"
              />
            </div>
          )}

          {scenario === 'curfew' && (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">Curfew Duration (days)</label>
              <input
                type="number" min={1} max={30}
                value={(params.duration_days as number) ?? 7}
                onChange={(e) => setParams({ ...params, duration_days: Number(e.target.value) })}
                className="input"
              />
            </div>
          )}

          {scenario === 'tech_deployment' && (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Coverage: {params.coverage_pct as number}%
              </label>
              <input
                type="range" min={10} max={100} step={10}
                value={params.coverage_pct as number ?? 60}
                onChange={(e) => setParams({ coverage_pct: Number(e.target.value) })}
                className="w-full accent-accent-blue"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              Monte Carlo Trials: {numSims}
            </label>
            <input
              type="range" min={50} max={500} step={50}
              value={numSims}
              onChange={(e) => setNumSims(Number(e.target.value))}
              className="w-full accent-accent-blue"
            />
            <p className="text-2xs text-text-muted mt-0.5">More trials = more accurate, slower</p>
          </div>

          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="btn-primary w-full justify-center"
          >
            {runMutation.isPending
              ? <><span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" /> Running…</>
              : <><Play size={13} /> Run Simulation</>
            }
          </button>
        </div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-4">
          {runMutation.isPending ? (
            <div className="card p-8 flex items-center justify-center">
              <PageLoader label={`Running ${numSims} Monte Carlo trials…`} />
            </div>
          ) : result ? (
            <SimulationResults result={result} />
          ) : (
            <div className="card">
              <EmptyState
                icon={<FlaskConical size={24} />}
                title="Configure and run a simulation"
                description="Select a scenario, district, and parameters, then click Run Simulation."
                className="py-20"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SimulationResults({ result }: { result: SimulationResult }) {
  const reduction = result.reduction
  const isPositive = reduction.p50_pct > 0

  // Distribution chart data
  const distributionData = [
    { label: 'Pessimistic (P5)', pct: reduction.p5_pct },
    { label: 'Median (P50)', pct: reduction.p50_pct },
    { label: 'Optimistic (P95)', pct: reduction.p95_pct },
  ]

  // Crime type comparison
  const typeData = Object.keys(result.baseline.by_type).slice(0, 8).map((type) => ({
    type: type.replace(/_/g, ' '),
    before: result.baseline.by_type[type] ?? 0,
    after: result.projected.by_type[type] ?? 0,
  }))

  return (
    <div className="space-y-4">
      {/* KPI row */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Median Reduction', value: `${reduction.p50_pct.toFixed(1)}%`, positive: isPositive },
          { label: 'Baseline Crimes/day', value: result.baseline.crimes_per_day.toFixed(1), positive: null },
          { label: 'Projected Crimes/day', value: result.projected.crimes_per_day.toFixed(1), positive: isPositive },
        ].map(({ label, value, positive }) => (
          <div key={label} className="card p-3 text-center">
            <p className="text-2xs text-text-muted mb-1">{label}</p>
            <p className={cn('text-xl font-bold tabular-nums',
              positive === true ? 'text-severity-low' : positive === false ? 'text-severity-high' : 'text-text-primary'
            )}>{value}</p>
          </div>
        ))}
      </div>

      {/* Reduction distribution */}
      <div className="card p-4">
        <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
          Expected Crime Reduction Distribution
        </p>
        <div className="flex items-end gap-4 h-28">
          {distributionData.map(({ label, pct }) => (
            <div key={label} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-xs font-bold text-severity-low">{pct.toFixed(1)}%</span>
              <div
                className="w-full bg-severity-low/30 rounded-t"
                style={{ height: `${Math.max(8, (pct / 100) * 88)}px` }}
              />
              <span className="text-2xs text-text-muted text-center leading-tight">{label}</span>
            </div>
          ))}
        </div>
        <p className="text-2xs text-text-muted mt-3">
          95% CI: [{result.reduction.confidence_interval_95[0].toFixed(1)}, {result.reduction.confidence_interval_95[1].toFixed(1)}] crimes/day
        </p>
      </div>

      {/* Before/after by crime type */}
      {typeData.length > 0 && (
        <div className="card p-4">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
            Before vs After — By Crime Type (crimes/day)
          </p>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={typeData} margin={{ left: -10, right: 4, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
              <XAxis dataKey="type" tick={{ fill: '#8b949e', fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: '8px', fontSize: '12px', color: '#e6edf3' }} />
              <Bar dataKey="before" fill="#f85149" name="Before" radius={[2, 2, 0, 0]} />
              <Bar dataKey="after" fill="#3fb950" name="After" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="text-2xs text-text-muted px-1">
        Scenario: <strong>{result.scenario.replace(/_/g, ' ')}</strong> · District: <strong>{result.district}</strong> · {result.num_simulations} trials · Risk: {result.baseline.risk_level} → {result.projected.risk_level}
      </div>
    </div>
  )
}
