import { useState } from 'react'
import { FileText, Send, RefreshCw, CheckCircle, AlertCircle, Clock } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { firApi } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import Badge from '@/components/ui/Badge'
import { formatDate, timeAgo, cn } from '@/utils'
import type { FIRReport, ExtractedEntities } from '@/types'

export default function FIRPage() {
  const [activeTab, setActiveTab] = useState<'submit' | 'list'>('submit')
  const [firNumber, setFirNumber] = useState('')
  const [rawText, setRawText] = useState('')
  const [analysisResult, setAnalysisResult] = useState<any>(null)
  const qc = useQueryClient()

  const { data: firList, isLoading } = useQuery({
    queryKey: ['fir', 'list'],
    queryFn: () => firApi.list({ limit: 50 }),
    enabled: activeTab === 'list',
  })

  const submitMutation = useMutation({
    mutationFn: () => firApi.submit({ fir_number: firNumber, raw_text: rawText }),
    onSuccess: (data) => {
      toast.success(`FIR ${firNumber} submitted — NLP processing queued`)
      qc.invalidateQueries({ queryKey: ['fir'] })
      setFirNumber('')
      setRawText('')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Submission failed'),
  })

  const analyzeMutation = useMutation({
    mutationFn: (text: string) => firApi.extract(text),
    onSuccess: (data) => setAnalysisResult(data),
    onError: () => toast.error('NLP analysis failed'),
  })

  const reprocessMutation = useMutation({
    mutationFn: (id: string) => firApi.reprocess(id),
    onSuccess: () => { toast.success('Reprocessing queued'); qc.invalidateQueries({ queryKey: ['fir'] }) },
  })

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      {/* Tabs */}
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
        {(['submit', 'list'] as const).map((tab) => (
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
            {tab === 'submit' ? 'Submit FIR' : 'FIR Records'}
          </button>
        ))}
      </div>

      {activeTab === 'submit' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Submit form */}
          <div className="card p-5 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                <FileText size={15} /> Submit FIR for NLP Analysis
              </h3>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                FIR Number *
              </label>
              <input
                className="input"
                placeholder="e.g. FIR-2024-DL-001"
                value={firNumber}
                onChange={(e) => setFirNumber(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                FIR Text *
              </label>
              <textarea
                className="input min-h-48 resize-y font-mono text-xs leading-relaxed"
                placeholder="Paste FIR content here… (minimum 20 characters)&#10;&#10;e.g. On 15/06/2024 at approximately 14:30 hours, the complainant Rajesh Kumar reported to Police Station Connaught Place that his motorcycle bearing registration number DL-01-AB-1234 was stolen…"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
              />
              <p className="text-2xs text-text-muted mt-1">{rawText.length} chars</p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => submitMutation.mutate()}
                disabled={!firNumber || rawText.length < 20 || submitMutation.isPending}
                className="btn-primary flex-1 justify-center"
              >
                {submitMutation.isPending
                  ? <><span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" /> Submitting…</>
                  : <><Send size={13} /> Submit & Queue NLP</>
                }
              </button>
              <button
                onClick={() => analyzeMutation.mutate(rawText)}
                disabled={rawText.length < 20 || analyzeMutation.isPending}
                className="btn-secondary justify-center"
                title="Analyse without saving"
              >
                {analyzeMutation.isPending
                  ? <span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                  : 'Preview NLP'
                }
              </button>
            </div>
          </div>

          {/* NLP Results panel */}
          <div className="card p-5">
            <h3 className="text-sm font-semibold text-text-primary mb-3">NLP Extraction Results</h3>
            {analyzeMutation.isPending ? (
              <PageLoader label="Analysing text…" />
            ) : analysisResult ? (
              <EntityResultPanel entities={analysisResult} />
            ) : (
              <EmptyState
                title="No analysis yet"
                description="Submit FIR text or click 'Preview NLP' to see extracted entities."
              />
            )}
          </div>
        </div>
      )}

      {activeTab === 'list' && (
        isLoading ? <PageLoader /> : (
          <div className="table-wrapper">
            <table className="table-base">
              <thead className="table-head">
                <tr>
                  <th className="table-th">FIR Number</th>
                  <th className="table-th">NLP Status</th>
                  <th className="table-th">Crime Type</th>
                  <th className="table-th">Confidence</th>
                  <th className="table-th">Submitted</th>
                  <th className="table-th">Actions</th>
                </tr>
              </thead>
              <tbody>
                {firList?.items.map((fir) => (
                  <tr key={fir.id} className="table-row">
                    <td className="table-td font-mono text-xs text-accent-blue">{fir.fir_number}</td>
                    <td className="table-td"><NLPStatusBadge status={fir.nlp_status} /></td>
                    <td className="table-td text-xs">
                      {fir.extracted_entities?.crime_type ?? <span className="text-text-muted">—</span>}
                    </td>
                    <td className="table-td text-xs tabular-nums">
                      {fir.extraction_confidence != null
                        ? `${(fir.extraction_confidence * 100).toFixed(0)}%`
                        : '—'}
                    </td>
                    <td className="table-td text-xs text-text-muted">{timeAgo(fir.created_at)}</td>
                    <td className="table-td">
                      {fir.nlp_status !== 'processing' && (
                        <button
                          onClick={() => reprocessMutation.mutate(fir.id)}
                          className="text-2xs text-accent-blue hover:underline flex items-center gap-1"
                        >
                          <RefreshCw size={10} /> Reprocess
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

function NLPStatusBadge({ status }: { status: string }) {
  const config = {
    completed:  { icon: <CheckCircle size={10} />, class: 'bg-severity-low-bg text-severity-low' },
    processing: { icon: <RefreshCw size={10} className="animate-spin" />, class: 'bg-accent-blue/10 text-accent-blue' },
    pending:    { icon: <Clock size={10} />, class: 'bg-severity-medium-bg text-severity-medium' },
    failed:     { icon: <AlertCircle size={10} />, class: 'bg-severity-high-bg text-severity-high' },
  }[status] ?? { icon: null, class: 'bg-bg-elevated text-text-muted' }

  return (
    <span className={cn('inline-flex items-center gap-1 text-2xs font-medium px-2 py-0.5 rounded', config.class)}>
      {config.icon}{status}
    </span>
  )
}

function EntityResultPanel({ entities }: { entities: any }) {
  const confidence = Math.round((entities.overall_confidence ?? 0) * 100)
  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-blue rounded-full transition-all"
            style={{ width: `${confidence}%` }}
          />
        </div>
        <span className="text-text-muted font-mono w-8 text-right">{confidence}%</span>
      </div>

      {[
        { label: 'Crime Type', value: entities.crime_type },
        { label: 'Primary Location', value: entities.primary_location },
        { label: 'Inferred Severity', value: entities.inferred_severity ? `${entities.inferred_severity}/5` : null },
        { label: 'Has Weapon', value: entities.has_weapon ? '⚠️ Yes' : 'No' },
        { label: 'Has Injury', value: entities.has_injury ? '🚑 Yes' : 'No' },
      ].map(({ label, value }) => (
        <div key={label} className="flex justify-between items-start gap-4">
          <span className="text-text-muted">{label}</span>
          <span className="text-text-primary font-medium text-right">{value ?? '—'}</span>
        </div>
      ))}

      {entities.locations?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">Locations ({entities.locations.length})</p>
          <div className="flex flex-wrap gap-1">
            {entities.locations.map((l: string, i: number) => (
              <span key={i} className="bg-bg-elevated text-text-secondary px-2 py-0.5 rounded text-2xs">{l}</span>
            ))}
          </div>
        </div>
      )}

      {entities.weapons?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">Weapons</p>
          <div className="flex flex-wrap gap-1">
            {entities.weapons.map((w: string, i: number) => (
              <span key={i} className="bg-severity-high-bg text-severity-high px-2 py-0.5 rounded text-2xs">{w}</span>
            ))}
          </div>
        </div>
      )}

      {entities.ipc_sections?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">IPC Sections</p>
          <div className="flex flex-wrap gap-1">
            {entities.ipc_sections.map((s: string, i: number) => (
              <span key={i} className="bg-accent-purple/10 text-accent-purple px-2 py-0.5 rounded text-2xs font-mono">§{s}</span>
            ))}
          </div>
        </div>
      )}

      {entities.suspects?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">Suspects ({entities.suspects.length})</p>
          {entities.suspects.slice(0, 2).map((s: any, i: number) => (
            <div key={i} className="bg-bg-tertiary rounded p-2 text-2xs text-text-secondary mb-1">
              {[s.gender, s.age ? `Age ${s.age}` : null, s.build, s.complexion].filter(Boolean).join(' · ')}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
