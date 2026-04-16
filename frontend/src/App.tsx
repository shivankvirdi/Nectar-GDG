import { useEffect, useState } from 'react'
import './App.css'

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
  }
  brandReputation?: {
    score?: number
    label?: string
    insights?: Insight[]
    reviewsAnalyzed?: number
  }
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

export default function App() {
  const [currentUrl, setCurrentUrl] = useState('Loading...')
  const [backendStatus, setBackendStatus] = useState('Waiting for backend...')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const fetchData = async (url: string) => {
      try {
        setLoading(true)
        setError('')
        setBackendStatus('Sending URL to backend...')

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
              : 'Backend request failed.'
          setBackendStatus(errorMessage)
          setError(errorMessage)
          return
        }

        setAnalysis(data.analysis ?? null)
        setBackendStatus('Analysis complete')
      } catch (err) {
        console.error('Failed to send URL:', err)
        const message = 'Backend request failed. Is FastAPI running on port 8000?'
        setBackendStatus(message)
        setError(message)
      } finally {
        setLoading(false)
      }
    }

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const url = tabs[0]?.url ?? ''
      setCurrentUrl(url || 'No active tab URL found')

      if (!url) {
        setError('No URL available to send.')
        setBackendStatus('No URL available to send.')
        setLoading(false)
        return
      }

      fetchData(url)
    })
  }, [])

  return (
    <main className="app-shell">
      <div className="phone-frame">
        <header className="top-header">
          <div>
            <div className="brand-row">
              <span className="brand-icon"></span>
              <div className="brand-block">
                <h1>Nectar</h1>
                <p>PRODUCT ANALYZER</p>
              </div>
            </div>
          </div>

          <button className="premium-btn">Go Premium</button>
        </header>

        <div className="content">
          <SectionCard title="Overall Score">
            <div className="score-row">
              <span className="score-number">
                {loading ? '--' : analysis?.overallScore ?? '--'}
              </span>
              <span className="score-max">/100</span>
            </div>
            <MetricBar label="Trust Score" value={analysis?.overallScore} />
          </SectionCard>

          <SectionCard title="Current Page">
            <p className="body-text url-text">{currentUrl}</p>
          </SectionCard>

          <SectionCard title="Backend Status">
            <p className={`body-text ${error ? 'status-error' : 'status-ok'}`}>
              {error || backendStatus}
            </p>
          </SectionCard>

          <SectionCard title="Product">
            <div className="info-list">
              <p><strong>Keyword:</strong> {analysis?.productKeyword ?? 'Not detected yet'}</p>
              <p><strong>ASIN:</strong> {analysis?.asin ?? 'Not found yet'}</p>
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

            <MetricBar label="Review Integrity" value={analysis?.reviewIntegrity?.score} />

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
            </div>
          </SectionCard>

          <SectionCard title="Brand Reputation">
            <div className="mini-score">
              <span>Score</span>
              <strong>{analysis?.brandReputation?.score ?? 'Waiting...'}</strong>
            </div>

            <MetricBar label="Brand Reputation" value={analysis?.brandReputation?.score} />

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
          </SectionCard>
        </div>
      </div>
    </main>
  )
}