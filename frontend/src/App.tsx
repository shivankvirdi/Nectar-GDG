import { useEffect, useState } from 'react'
import './App.css'
import PremiumScreen from './PremiumScreen'

const DEV_PREVIEW = false
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

type Insight = {
  topic: string
  status: string
}

type Analysis = {
  asin?: string
  productKeyword?: string
  title?: string
  brand?: string | null
  price?: string | number | null
  rating?: string | number | null
  reviewCount?: number | null
  overallScore?: number
  reviewIntegrity?: {
    score?: number
    label?: string
    verifiedPurchaseRatio?: number
    sentimentConsistencyRatio?: number
    commonKeywords?: {
      word: string
      count: number
      sentiment: "positive" | "negative" | "neutral"
    }[]
  }
  brandReputation?: {
    score?: number
    label?: string
    insights?: Insight[]
    reviewsAnalyzed?: number
    commonKeywords?: {
      word: string
      count: number
      sentiment: "positive" | "negative" | "neutral"
    }[]
  }
  similarProducts?: {
    title?: string
    asin?: string
    brand?: string
    rating?: string | number
    reviewCount?: number
    price?: string
    isPrime?: boolean
    image?: string
    amazonUrl?: string
  }[]
  aiAnalysis?: {
    pros?: string[]
    cons?: string[]
    verdict?: string
    recommendation?: 'BUY' | 'COMPARE' | 'SKIP'
  }
}

const mockAnalysis: Analysis = {
  title: "Hydro Flask 32 oz Water Bottle",
  brand: "Hydro Flask",
  price: "$44.95",
  rating: 4.7,
  reviewCount: 12000,
  overallScore: 84,

  reviewIntegrity: {
    score: 82,
    label: "Mostly authentic",
    verifiedPurchaseRatio: 0.78,
    sentimentConsistencyRatio: 0.81,
    commonKeywords: [
      { word: "durable", count: 120, sentiment: "positive" },
      { word: "expensive", count: 45, sentiment: "negative" },
      { word: "insulated", count: 90, sentiment: "positive" },
    ],
  },

  brandReputation: {
    score: 76,
    label: "Generally positive",
    reviewsAnalyzed: 500,
    insights: [
      { topic: "Quality", status: "Strong" },
      { topic: "Price", status: "Mixed" },
    ],
    commonKeywords: [
      { word: "premium", count: 60, sentiment: "positive" },
      { word: "overpriced", count: 30, sentiment: "negative" },
    ],
  },

  similarProducts: [
    {
      title: "Stanley Quencher Tumbler",
      price: "$35.00",
      rating: 4.6,
      image: "https://via.placeholder.com/150",
      amazonUrl: "https://amazon.com",
    },
    {
      title: "Simple Modern Water Bottle",
      price: "$25.00",
      rating: 4.5,
      image: "https://via.placeholder.com/150",
      amazonUrl: "https://amazon.com",
    },
  ],

  aiAnalysis: {
    pros: ["Great insulation", "Durable build", "Trusted brand"],
    cons: ["Higher price", "Can dent if dropped"],
    verdict: "Excellent bottle but slightly overpriced compared to competitors.",
    recommendation: "COMPARE",
  },
}

function MetricBar({ label, value }: { label: string; value?: number }) {
  const safeValue = Math.max(0, Math.min(100, value ?? 0))

  return (
    <div className="metric">
      <div className="metric-top">
        <span>{label}</span>
        <span>{safeValue}/100</span>
      </div>
      <div className="metric-track">
        <div className="metric-fill" style={{ width: `${safeValue}%` }} />
      </div>
    </div>
  )
}

function SectionCard({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="section-card">
      <h3>{title}</h3>
      {children}
    </section>
  )
}

function KeywordPills({
  keywords,
  emptyMessage,
}: {
  keywords?: { word: string; count: number; sentiment: 'positive' | 'negative' | 'neutral' }[]
  emptyMessage: string
}) {
  if (!keywords?.length) return <p className="body-text muted">{emptyMessage}</p>

  return (
    <div className="keyword-pills">
      {keywords.map((kw) => (
        <span key={kw.word} className={`keyword-pill keyword-pill--${kw.sentiment}`}>
          {kw.word} <em>×{kw.count}</em>
        </span>
      ))}
    </div>
  )
}

function VerdictCard({ ai }: { ai: NonNullable<Analysis['aiAnalysis']> }) {
  const rec = ai.recommendation ?? 'COMPARE'

  const colorMap = {
    BUY: { bg: '#dcfce7', border: '#86efac', text: '#15803d', badge: '#16a34a' },
    COMPARE: { bg: '#fef9c3', border: '#fde047', text: '#854d0e', badge: '#ca8a04' },
    SKIP: { bg: '#fee2e2', border: '#fca5a5', text: '#991b1b', badge: '#dc2626' },
  }
  const c = colorMap[rec]

  return (
    <section className="section-card">
      {/* Recommendation badge */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>AI Analysis</h3>
        <span style={{
          background: c.badge,
          color: '#fff',
          fontWeight: 800,
          fontSize: 12,
          letterSpacing: '0.1em',
          padding: '4px 12px',
          borderRadius: 999,
        }}>
          {rec}
        </span>
      </div>

      {/* Verdict sentence */}
      <p style={{
        margin: '0 0 14px',
        fontSize: 13,
        color: '#444',
        lineHeight: 1.5,
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: 10,
        padding: '8px 12px',
      }}>
        {ai.verdict}
      </p>

      {/* Pros + Cons side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <p style={{ margin: '0 0 6px', fontSize: 11, fontWeight: 700, color: '#15803d', letterSpacing: '0.08em' }}>
            ✦ PROS
          </p>
          {(ai.pros ?? []).map((pro, i) => (
            <p key={i} style={{
              margin: '0 0 5px',
              fontSize: 12,
              color: '#1e1e1e',
              lineHeight: 1.4,
              padding: '6px 8px',
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              borderRadius: 8,
            }}>
              {pro}
            </p>
          ))}
        </div>
        <div>
          <p style={{ margin: '0 0 6px', fontSize: 11, fontWeight: 700, color: '#dc2626', letterSpacing: '0.08em' }}>
            ✦ CONS
          </p>
          {(ai.cons ?? []).map((con, i) => (
            <p key={i} style={{
              margin: '0 0 5px',
              fontSize: 12,
              color: '#1e1e1e',
              lineHeight: 1.4,
              padding: '6px 8px',
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: 8,
            }}>
              {con}
            </p>
          ))}
        </div>
      </div>
    </section>
  )
}

export default function App() {
  const [currentUrl, setCurrentUrl] = useState('Loading...')
  const [backendStatus, setBackendStatus] = useState('Ready to scan')
  const [analysis, setAnalysis] = useState<Analysis | null>(
    DEV_PREVIEW ? mockAnalysis : null
  )
  const [view, setView] = useState<'home' | 'premium'>('home')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasScanned, setHasScanned] = useState(DEV_PREVIEW)

  useEffect(() => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const url = tabs[0]?.url ?? ''
      setCurrentUrl(url || 'No active tab ASIN found')
    })
  }, [])

  const handleScan = async () => {
    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      const url = tabs[0]?.url ?? ''
      setCurrentUrl(url || 'No active tab ASIN found')

      if (!url) {
        setError('No URL available to send.')
        setBackendStatus('No ASIN available to send.')
        return
      }

      try {
        setLoading(true)
        setError('')
        setAnalysis(null)
        setBackendStatus('Sending ASIN to backend...')

        const response = await fetch(`${API_BASE}/current-url`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ url }),
        })

        const data = await response.json()
        console.log('Backend response:', data)

        if (!response.ok) {
          const errorMessage =
            typeof data.detail === 'string'
              ? data.detail
              : 'Request failed.'
          setBackendStatus(errorMessage)
          setError(errorMessage)
          return
        }

        setAnalysis(data.analysis ?? null)
        setBackendStatus('Analysis complete')
        setHasScanned(true)
      } catch (err) {
        console.error('Failed to send URL:', err)
        const message = 'Scan failed. Is server running?'
        setBackendStatus(message)
        setError(message)
      } finally {
        setLoading(false)
      }
    })
  }

  if (view === 'premium') return (
    <main className="app-shell">
      <div className="popup-shell">
        <PremiumScreen onBack={() => setView('home')} />
      </div>
    </main>
  )

  return (
    <main className="app-shell">
      <div className="popup-shell">
        <header className="top-header">
          <div className="brand-row">
            <img src="/icons/logo.png" alt="Nectar logo" className="brand-logo" />
            <div className="brand-block">
              <h1>Nectar</h1>
              <p>AMAZON PRODUCT ANALYZER</p>
            </div>
          </div>

          <button className="premium-btn" onClick={() => setView('premium')}>Go Premium</button>
        </header>

        <div className="content">
          <SectionCard title="Product Analysis">
            <p className={`body-text ${error ? 'status-error' : 'status-ok'}`}>
              {error || backendStatus}
            </p>
            <button
              className="scan-btn"
              onClick={handleScan}
              disabled={loading}
            >
              {loading ? 'Scanning...' : 'Scan Product'}
            </button>
          </SectionCard>

          {hasScanned && (
            <>
              <SectionCard title="Overall Score">
                <div className="score-row">
                  <span className="score-number">
                    {loading ? '--' : analysis?.overallScore ?? '--'}
                  </span>
                  <span className="score-max">/100</span>
                </div>
                <MetricBar label="Trust Score" value={analysis?.overallScore} />
              </SectionCard>

              <SectionCard title="Product">
                <div className="info-list">
                  <p><strong>Title:</strong> {analysis?.title ?? 'Waiting...'}</p>
                  <p><strong>Brand:</strong> {analysis?.brand ?? 'Waiting...'}</p>
                  <p><strong>Price:</strong> {analysis?.price ?? 'Waiting...'}</p>
                  <p><strong>Rating:</strong> {analysis?.rating ?? 'Waiting...'}</p>
                  <p><strong>Review Count:</strong> {analysis?.reviewCount ?? 'Waiting...'}</p>
                </div>
              </SectionCard>

              {analysis?.aiAnalysis && (
                <VerdictCard ai={analysis.aiAnalysis} />
              )}

              <SectionCard title="Review Integrity">
                <div className="mini-score">
                  <span>Score</span>
                  <strong>{analysis?.reviewIntegrity?.score ?? 'Waiting...'}</strong>
                </div>

                <MetricBar
                  label="Review Integrity"
                  value={analysis?.reviewIntegrity?.score}
                />

                <div className="info-list">
                  <p><strong>Label:</strong> {analysis?.reviewIntegrity?.label ?? 'Waiting...'}</p>
                  <p>
                    <strong>Verified Purchase Ratio:</strong>{' '}
                    {analysis?.reviewIntegrity?.verifiedPurchaseRatio ?? 'Waiting...'}
                  </p>
                  <p>
                    <strong>Sentiment Consistency:</strong>{' '}
                    {analysis?.reviewIntegrity?.sentimentConsistencyRatio ?? 'Waiting...'}
                  </p>
                  <p className="keywords-label"><strong>Top Keywords:</strong></p>
                  <KeywordPills
                    keywords={analysis?.reviewIntegrity?.commonKeywords}
                    emptyMessage="No keywords found"
                  />
                </div>
              </SectionCard>

              <SectionCard title="Brand Reputation">
                <div className="mini-score">
                  <span>Score</span>
                  <strong>{analysis?.brandReputation?.score ?? 'Waiting...'}</strong>
                </div>

                <MetricBar
                  label="Brand Reputation"
                  value={analysis?.brandReputation?.score}
                />

                <div className="info-list">
                  <p><strong>Label:</strong> {analysis?.brandReputation?.label ?? 'Waiting...'}</p>
                  <p>
                    <strong>Reviews Analyzed:</strong>{' '}
                    {analysis?.brandReputation?.reviewsAnalyzed ?? 'Waiting...'}
                  </p>
                </div>

                {analysis?.brandReputation?.insights?.length ? (
                  <div className="insight-list">
                    {analysis.brandReputation.insights.map((insight) => (
                      <div key={insight.topic} className="insight-pill">
                        <span>{insight.topic}</span>
                        <strong>{insight.status}</strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="body-text muted">No brand insights yet.</p>
                )}
                <p className="keywords-label"><strong>Top Keywords:</strong></p>
                <KeywordPills
                  keywords={analysis?.brandReputation?.commonKeywords}
                  emptyMessage="No keywords found"
                />
              </SectionCard>

              <SectionCard title="Similar Products">
                {(analysis?.similarProducts?.length ?? 0) > 0 ? (
                  <div className="similar-scroll">
                    {analysis?.similarProducts?.map((product, i) => (
                      <a
                        key={product.asin ?? i}
                        href={product.amazonUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="similar-card"
                      >
                        {product.image ? (
                          <img
                            src={product.image}
                            alt={product.title ?? 'Similar product'}
                            className="similar-card-image"
                          />
                        ) : (
                          <div className="similar-card-image placeholder">No Image</div>
                        )}

                        <p className="similar-card-title">
                          {product.title ?? 'Untitled Product'}
                        </p>

                        <p className="similar-card-brand">
                          {product.brand ?? 'Unknown brand'}
                        </p>

                        <p className="similar-card-price">
                          {product.price ?? 'No price'}
                        </p>

                        <p className="similar-card-rating">
                          ⭐ {product.rating ?? 'N/A'}
                        </p>

                        {product.isPrime && (
                          <p className="similar-card-prime">Prime</p>
                        )}
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="body-text muted">No similar products found.</p>
                )}
              </SectionCard>
            </>
          )}
        </div>
      </div>
    </main>
  )
}