import { useState, useCallback } from 'react'
import { Navigation, Target, Zap, Route } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, Marker, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import toast from 'react-hot-toast'
import { mlApi } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { cn, riskColor } from '@/utils'
import type { PatrolRoute, PatrolStop } from '@/types'

const DISTRICTS = [
  'Connaught Place', 'Karol Bagh', 'Rohini', 'Dwarka',
  'Saket', 'Lajpat Nagar', 'Janakpuri', 'Shahdara',
]

const STRATEGIES = [
  { value: 'risk_weighted', label: 'Risk Weighted', desc: 'Prioritise high-crime areas' },
  { value: 'coverage',      label: 'Coverage',      desc: 'Maximise geographic spread' },
  { value: 'shortest',      label: 'Shortest',      desc: 'Minimum travel distance' },
]

export default function PatrolPage() {
  const [district, setDistrict] = useState(DISTRICTS[0])
  const [strategy, setStrategy] = useState('risk_weighted')
  const [numCheckpoints, setNumCheckpoints] = useState(5)
  const [patrolType, setPatrolType] = useState('vehicle')
  const [startPos, setStartPos] = useState<[number, number]>([28.6315, 77.2167])
  const [route, setRoute] = useState<PatrolRoute | null>(null)
  const [pickingStart, setPickingStart] = useState(false)

  const optimizeMutation = useMutation({
    mutationFn: () => mlApi.optimizePatrol({
      start_lat: startPos[0],
      start_lng: startPos[1],
      district,
      strategy,
      num_checkpoints: numCheckpoints,
      patrol_type: patrolType,
    }),
    onSuccess: (data) => { setRoute(data); toast.success('Patrol route optimised') },
    onError: () => toast.error('Route optimization failed'),
  })

  const routePath: [number, number][] = route?.checkpoints.map((c) => [c.lat, c.lng]) ?? []

  return (
    <div className="flex h-full">
      {/* Config panel */}
      <div className="w-72 border-r border-border-default bg-bg-secondary flex flex-col flex-shrink-0">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Navigation size={15} /> Route Configuration
          </h3>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">District</label>
            <select className="input" value={district} onChange={(e) => setDistrict(e.target.value)}>
              {DISTRICTS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-2">Strategy</label>
            <div className="space-y-1.5">
              {STRATEGIES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setStrategy(s.value)}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded-md border transition-colors text-xs',
                    strategy === s.value
                      ? 'border-accent-blue bg-accent-blue/10 text-text-primary'
                      : 'border-border-subtle bg-bg-tertiary text-text-muted hover:bg-bg-hover'
                  )}
                >
                  <p className="font-medium">{s.label}</p>
                  <p className="text-2xs mt-0.5 opacity-70">{s.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              Checkpoints: {numCheckpoints}
            </label>
            <input
              type="range" min={2} max={15} value={numCheckpoints}
              onChange={(e) => setNumCheckpoints(Number(e.target.value))}
              className="w-full accent-accent-blue"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Patrol Type</label>
            <div className="flex gap-2">
              {['vehicle', 'foot'].map((t) => (
                <button
                  key={t}
                  onClick={() => setPatrolType(t)}
                  className={cn(
                    'flex-1 py-1.5 rounded-md text-xs font-medium border transition-colors capitalize',
                    patrolType === t
                      ? 'border-accent-blue bg-accent-blue/10 text-accent-blue'
                      : 'border-border-subtle text-text-muted hover:bg-bg-hover'
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Start Position</label>
            <p className="text-2xs text-text-muted mb-2">
              {startPos[0].toFixed(4)}, {startPos[1].toFixed(4)}
            </p>
            <button
              onClick={() => setPickingStart((v) => !v)}
              className={cn('btn-secondary text-xs w-full justify-center gap-1.5',
                pickingStart && 'border-accent-blue text-accent-blue')}
            >
              <Target size={12} />
              {pickingStart ? 'Click map to set start' : 'Pick on map'}
            </button>
          </div>
        </div>

        <div className="p-4 border-t border-border-subtle space-y-3">
          <button
            onClick={() => optimizeMutation.mutate()}
            disabled={optimizeMutation.isPending}
            className="btn-primary w-full justify-center"
          >
            {optimizeMutation.isPending
              ? <><span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" /> Optimising…</>
              : <><Zap size={13} /> Optimise Route</>
            }
          </button>

          {route && (
            <div className="card p-3 space-y-1 text-xs">
              <div className="flex justify-between"><span className="text-text-muted">Distance</span><span className="tabular-nums">{route.total_distance_km.toFixed(1)} km</span></div>
              <div className="flex justify-between"><span className="text-text-muted">Est. Duration</span><span className="tabular-nums">{Math.round(route.estimated_duration_minutes)} min</span></div>
              <div className="flex justify-between"><span className="text-text-muted">Stops</span><span className="tabular-nums">{route.checkpoints.length}</span></div>
              <div className="flex justify-between"><span className="text-text-muted">Coverage Radius</span><span className="tabular-nums">{route.coverage_radius_km.toFixed(1)} km</span></div>
            </div>
          )}
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <MapContainer center={startPos} zoom={12} style={{ height: '100%', width: '100%' }}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <MapClickHandler pickingStart={pickingStart} onPick={(pos) => { setStartPos(pos); setPickingStart(false) }} />

          {/* Start marker */}
          <CircleMarker center={startPos} radius={8} pathOptions={{ color: '#1f6feb', fillColor: '#1f6feb', fillOpacity: 0.9 }}>
            <Popup>Start position</Popup>
          </CircleMarker>

          {/* Route line */}
          {routePath.length > 1 && (
            <Polyline positions={routePath} pathOptions={{ color: '#1f6feb', weight: 3, dashArray: '8 6', opacity: 0.85 }} />
          )}

          {/* Checkpoint markers */}
          {route?.checkpoints.map((stop, i) => (
            <CircleMarker
              key={stop.node_id}
              center={[stop.lat, stop.lng]}
              radius={6}
              pathOptions={{ color: riskColor(stop.risk_score), fillColor: riskColor(stop.risk_score), fillOpacity: 0.85 }}
            >
              <Popup>
                <div>
                  <p className="font-semibold">Stop {stop.stop_number}</p>
                  <p className="text-xs text-gray-400">{stop.label}</p>
                  <p className="text-xs">Risk: {stop.risk_score.toFixed(0)}/100</p>
                  <p className="text-xs">Crimes: {stop.crime_count}</p>
                  <p className="text-xs">+{stop.distance_from_prev_km.toFixed(2)} km</p>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>

        {optimizeMutation.isPending && (
          <div className="absolute inset-0 bg-bg-primary/60 flex items-center justify-center z-10">
            <PageLoader label="Optimising patrol route…" />
          </div>
        )}

        {pickingStart && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 card-elevated px-4 py-2 text-xs text-accent-blue font-medium">
            Click map to set patrol start position
          </div>
        )}
      </div>
    </div>
  )
}

function MapClickHandler({ pickingStart, onPick }: { pickingStart: boolean; onPick: (pos: [number, number]) => void }) {
  useMapEvents({
    click(e) {
      if (pickingStart) onPick([e.latlng.lat, e.latlng.lng])
    },
  })
  return null
}
