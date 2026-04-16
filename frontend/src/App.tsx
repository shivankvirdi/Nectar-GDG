import { useEffect, useState } from 'react'
import './App.css'

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

export default function App() {
  const [currentUrl, setCurrentUrl] = useState('Loading...')
  const [backendStatus, setBackendStatus] = useState('Waiting for backend...')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)

  useEffect(() => {
    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      const url = tabs[0]?.url ?? ''
      setCurrentUrl(url || 'No active tab URL found')

      if (!url) {
        setBackendStatus('No URL available to send.')
        return
      }

      try {
        const response = await fetch('http://127.0.0.1:8000/current-url', {
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
            typeof data.detail === 'string' ? data.detail : 'Backend request failed.'
          setBackendStatus(errorMessage)
          return
        }

        setAnalysis(data.analysis ?? null)
        setBackendStatus('Analysis complete')
      } catch (error) {
        console.error('Failed to send URL:', error)
        setBackendStatus('Backend request failed. Is FastAPI running on port 8000?')
      }
    })
  }, [])

  return (
    <div className="container">
      <div className="header">
        <div>
          <h2>Nectar</h2>
          <p className="subtitle">PRODUCT ANALYZER</p>
        </div>
      </div>

      <div className="card">
        <h3>Overall Score</h3>
        <h1>{analysis?.overallScore ?? 'Waiting...'}</h1>
      </div>

      <div className="card">
        <h3>Current Page</h3>
        <p className="desc">{currentUrl}</p>
      </div>

      <div className="card">
        <h3>Backend Status</h3>
        <p className="desc">{backendStatus}</p>
      </div>

      <div className="card">
        <h3>Product</h3>
        <p className="desc">Keyword: {analysis?.productKeyword ?? 'Not detected yet'}</p>
        <p className="desc">ASIN: {analysis?.asin ?? 'Not found yet'}</p>
        <p className="desc">Title: {analysis?.title ?? 'Waiting...'}</p>
        <p className="desc">Brand: {analysis?.brand ?? 'Waiting...'}</p>
        <p className="desc">Price: {analysis?.price ?? 'Waiting...'}</p>
        <p className="desc">Rating: {analysis?.rating ?? 'Waiting...'}</p>
        <p className="desc">Review Count: {analysis?.reviewCount ?? 'Waiting...'}</p>
      </div>

      <div className="card">
        <h3>Review Integrity</h3>
        <p className="desc">Score: {analysis?.reviewIntegrity?.score ?? 'Waiting...'}</p>
        <p className="desc">{analysis?.reviewIntegrity?.label ?? 'Waiting...'}</p>
        <p className="desc">
          Verified Purchase Ratio: {analysis?.reviewIntegrity?.verifiedPurchaseRatio ?? 'Waiting...'}
        </p>
        <p className="desc">
          Sentiment Consistency: {analysis?.reviewIntegrity?.sentimentConsistencyRatio ?? 'Waiting...'}
        </p>
      </div>

      <div className="card">
        <h3>Brand Reputation</h3>
        <p className="desc">Score: {analysis?.brandReputation?.score ?? 'Waiting...'}</p>
        <p className="desc">{analysis?.brandReputation?.label ?? 'Waiting...'}</p>
        <p className="desc">
          Reviews Analyzed: {analysis?.brandReputation?.reviewsAnalyzed ?? 'Waiting...'}
        </p>
        {analysis?.brandReputation?.insights?.map((insight) => (
          <p key={insight.topic} className="desc">
            {insight.topic}: {insight.status}
          </p>
        ))}
      </div>
    </div>
  )
}