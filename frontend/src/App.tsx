import { useEffect, useState } from 'react'
import './App.css'
import PremiumScreen from './PremiumScreen'

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

export default function App() {
  const [currentUrl, setCurrentUrl] = useState('Loading...')
  const [backendStatus, setBackendStatus] = useState('Ready to scan')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [view, setView] = useState<'home' | 'premium'>('home')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasScanned, setHasScanned] = useState(false)

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
              <p>SMART PRODUCT ANALYZER</p>
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
                  <p className="keywords-label"><strong>Top Keywords (why this score):</strong></p>
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
                  <p className="keywords-label"><strong>Top Keywords (why this score):</strong></p>
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