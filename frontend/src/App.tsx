import { useEffect, useRef, useState } from 'react'
import './App.css'
import PremiumScreen from './PremiumScreen'
import logoSrc from '/icons/logo.png'

// ─── Electron API ─────────────────────────────────────────────────────────────

declare global {
  interface Window {
    electronAPI?: {
      getActiveTabUrl: () => Promise<string | null>
      resizeWindow: (opts: { width?: number; height: number }) => Promise<void>
      minimizeWindow: () => void
      closeWindow: () => void
    }
  }
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEV_PREVIEW = import.meta.env.DEV && false
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const NECTAR_SECRET = import.meta.env.VITE_NECTAR_SECRET || ''

const EXIT_ANIMATION_MS = 720
const DELETE_ENTRY_DELAY_MS = 240
const CLEAR_ALL_ENTRY_DELAY_MS = 260
const SCAN_CANCEL_WINDOW_MS = 3000

const CURRENT_SCAN_KEY = 'nectar_current_scan'
const PREVIOUS_SCAN_KEY = 'nectar_previous_scan'
const SCAN_HISTORY_KEY = 'nectar_scan_history'
const MAX_SCAN_HISTORY = 10

// ─── Types ────────────────────────────────────────────────────────────────────

type Insight = { topic: string; status: string }
type Keyword = { word: string; count: number; sentiment: 'positive' | 'negative' | 'neutral' }

type SimilarProduct = {
  title?: string
  asin?: string
  listingId?: string
  marketplace?: string
  brand?: string
  rating?: string | number
  reviewCount?: number
  price?: string | number | null
  isPrime?: boolean
  image?: string
  listingUrl?: string
  productUrl?: string
  amazonUrl?: string
}

type Analysis = {
  asin?: string
  listingId?: string
  marketplace?: string
  listingUrl?: string
  productUrl?: string
  productKeyword?: string
  title?: string
  brand?: string | null
  price?: string | number | null
  rating?: string | number | null
  reviewCount?: number | null
  overallScore?: number
  image?: string
  imageUrl?: string
  mainImageUrl?: string
  mainImage?: string
  reviewIntegrity?: {
    score?: number
    label?: string
    verifiedPurchaseRatio?: number
    sentimentConsistencyRatio?: number
    flags?: Record<string, boolean>
    commonKeywords?: Keyword[]
  }
  sellerReviewIntegrity?: {
    score?: number
    label?: string
    verifiedPurchaseRatio?: number
    sentimentConsistencyRatio?: number
    flags?: Record<string, boolean>
    commonKeywords?: Keyword[]
  }
  brandReputation?: {
    score?: number
    label?: string
    insights?: Insight[]
    reviewsAnalyzed?: number
    commonKeywords?: Keyword[]
  }
  sellerReputation?: {
    score?: number
    label?: string
    insights?: Insight[]
    reviewsAnalyzed?: number
    commonKeywords?: Keyword[]
    sellerName?: string
    sellerPositivePct?: number
    sellerReviewCount?: number
    topRatedSeller?: boolean
  }
  similarProducts?: SimilarProduct[]
  aiAnalysis?: {
    pros?: string[]
    cons?: string[]
    verdict?: string
    recommendation?: 'BUY' | 'COMPARE' | 'SKIP'
  }
  raw?: { reviews?: { rating?: number; body?: string }[] }
}

type Recommendation = NonNullable<NonNullable<Analysis['aiAnalysis']>['recommendation']>

type ScanRecord = {
  id: string
  scannedAt: string
  url: string
  analysis: Analysis
}

// ─── Storage ──────────────────────────────────────────────────────────────────

function storageGet<T>(key: string): Promise<T | null> {
  try {
    const item = localStorage.getItem(key)
    return Promise.resolve(item ? (JSON.parse(item) as T) : null)
  } catch (e) {
    console.error(e)
    return Promise.resolve(null)
  }
}

function storageSet(values: Record<string, unknown>): Promise<void> {
  try {
    for (const [key, val] of Object.entries(values)) {
      localStorage.setItem(key, JSON.stringify(val))
    }
  } catch (e) {
    console.error(e)
  }
  return Promise.resolve()
}

function storageRemove(keys: string[]): Promise<void> {
  try {
    keys.forEach((key) => localStorage.removeItem(key))
  } catch (e) {
    console.error(e)
  }
  return Promise.resolve()
}

const loadCurrentSavedScan = () => storageGet<ScanRecord>(CURRENT_SCAN_KEY)
const loadPreviousSavedScan = () => storageGet<ScanRecord>(PREVIOUS_SCAN_KEY)
const loadScanHistory = () => storageGet<ScanRecord[]>(SCAN_HISTORY_KEY).then((r) => r ?? [])

// ─── Pure Utilities ───────────────────────────────────────────────────────────

function isSupportedUrl(url: string): boolean {
  return (
    /amazon\.(com|co\.|ca|com\.au|de|fr|es|it|nl|pl|se|sg|ae)/i.test(url) ||
    /ebay\.(com|co\.uk|com\.au|de|ca|fr|it|es|at|ch|com\.sg|com\.my|ph|ie|pl|nl)/i.test(url)
  )
}

function isEbayUrl(url: string): boolean {
  return /ebay\./i.test(url)
}

function getNumericValue(value?: string | number | null): number | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const parsed = Number(String(value).replace(/[^0-9.\-]/g, ''))
  return Number.isFinite(parsed) ? parsed : null
}

function getScoreColor(score?: number): string {
  if (score == null) return '#171717'
  if (score >= 75) return '#15803d'
  if (score >= 50) return '#b45309'
  return '#dc2626'
}

function formatPriceDifference(diff: number): string {
  const abs = Math.abs(diff).toFixed(2)
  if (diff === 0) return '$0.00'
  return diff > 0 ? `+$${abs}` : `-$${abs}`
}

function formatFlagLabel(flag: string): string {
  return flag
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function renderMetricValue(value?: string | number | null): string {
  return value !== null && value !== undefined ? String(value) : 'N/A'
}

function getAnalysisImage(item?: Analysis | null): string | undefined {
  return item?.image || item?.imageUrl || item?.mainImageUrl || item?.mainImage || undefined
}

function getCommerceUrl(item?: Pick<SimilarProduct, 'listingUrl' | 'productUrl' | 'amazonUrl'>): string {
  return item?.listingUrl || item?.productUrl || item?.amazonUrl || '#'
}

function compareProductAgainstCurrent(current: Analysis | null, product?: SimilarProduct) {
  const currentPrice = getNumericValue(current?.price)
  const otherPrice = getNumericValue(product?.price)
  const currentRating = getNumericValue(current?.rating)
  const otherRating = getNumericValue(product?.rating)
  const currentReviews = getNumericValue(current?.reviewCount)
  const otherReviews = getNumericValue(product?.reviewCount)
  const priceDiff = currentPrice !== null && otherPrice !== null ? otherPrice - currentPrice : null

  let score = 0

  if (priceDiff !== null) {
    if (priceDiff <= -12) score += 2
    else if (priceDiff < 0) score += 1
    else if (priceDiff >= 12) score -= 2
    else if (priceDiff > 0) score -= 1
  }

  if (currentRating !== null && otherRating !== null) {
    if (otherRating >= currentRating + 0.4) score += 2
    else if (otherRating > currentRating) score += 1
    else if (otherRating <= currentRating - 0.4) score -= 2
    else if (otherRating < currentRating) score -= 1
  }

  if (currentReviews !== null && otherReviews !== null) {
    if (otherReviews >= currentReviews * 1.2) score += 0.5
    if (otherReviews <= currentReviews * 0.6) score -= 0.5
  }

  const tag: 'BETTER' | 'SIMILAR' | 'WORSE' =
    score >= 1.5 ? 'BETTER' : score <= -1.5 ? 'WORSE' : 'SIMILAR'

  return { tag, priceDiff, score }
}

function getBestAlternativeIndex(current: Analysis | null, products?: SimilarProduct[]): number {
  if (!products?.length) return -1
  let bestIndex = -1
  let bestScore = Number.NEGATIVE_INFINITY
  products.forEach((product, i) => {
    const { score } = compareProductAgainstCurrent(current, product)
    if (score > bestScore) { bestScore = score; bestIndex = i }
  })
  return bestScore > 0 ? bestIndex : -1
}

function getMetricWinner(
  left: string | number | null | undefined,
  right: string | number | null | undefined,
  direction: 'higher' | 'lower' = 'higher'
): 'left' | 'right' | 'tie' {
  const l = getNumericValue(left)
  const r = getNumericValue(right)
  if (l === null || r === null || l === r) return 'tie'
  if (direction === 'higher') return l > r ? 'left' : 'right'
  return l < r ? 'left' : 'right'
}

function getTagClassName(tag: 'BETTER' | 'SIMILAR' | 'WORSE'): string {
  return `comparison-badge comparison-badge--${tag.toLowerCase()}`
}

function getRecommendationClass(rec?: Recommendation): string {
  return `recommendation-chip recommendation-chip--${(rec ?? 'COMPARE').toLowerCase()}`
}

function getCompareValueClass(winner: 'left' | 'right' | 'tie', side: 'left' | 'right'): string {
  if (winner === 'tie') return 'compare-value'
  return winner === side ? 'compare-value compare-value--winner' : 'compare-value compare-value--muted'
}

// ─── Mock Data (dev only) ─────────────────────────────────────────────────────

const mockAnalysis: Analysis = {
  title: 'Hydro Flask 32 oz Water Bottle',
  brand: 'Hydro Flask',
  price: '$44.95',
  rating: 4.7,
  reviewCount: 12000,
  overallScore: 84,
  image: '',
  reviewIntegrity: {
    score: 82,
    label: 'Mostly authentic',
    verifiedPurchaseRatio: 0.78,
    sentimentConsistencyRatio: 0.81,
    commonKeywords: [
      { word: 'durable', count: 120, sentiment: 'positive' },
      { word: 'expensive', count: 45, sentiment: 'negative' },
      { word: 'insulated', count: 90, sentiment: 'positive' },
    ],
  },
  brandReputation: {
    score: 76,
    label: 'Generally positive',
    reviewsAnalyzed: 500,
    insights: [
      { topic: 'Quality', status: 'Strong' },
      { topic: 'Price', status: 'Mixed' },
    ],
    commonKeywords: [
      { word: 'premium', count: 60, sentiment: 'positive' },
      { word: 'overpriced', count: 30, sentiment: 'negative' },
    ],
  },
  similarProducts: [
    { title: 'Stanley Quencher Tumbler', price: '$35.00', rating: 4.6, image: '', amazonUrl: 'https://amazon.com' },
    { title: 'Simple Modern Water Bottle', price: '$25.00', rating: 4.5, image: '', amazonUrl: 'https://amazon.com' },
  ],
  aiAnalysis: {
    pros: ['Great insulation', 'Durable build', 'Trusted brand'],
    cons: ['Higher price', 'Can dent if dropped'],
    verdict: 'Excellent bottle but slightly overpriced compared to competitors.',
    recommendation: 'COMPARE',
  },
}

// ─── Shared UI Components ─────────────────────────────────────────────────────

function SkeletonLine({ width = '100%', height = 14, mb = 8 }: { width?: string; height?: number; mb?: number }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 8, marginBottom: mb }} />
}

function SkeletonCard({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <section className="section-card skeleton-card-enter">
      <h3>{title}</h3>
      {children ?? (
        <>
          <SkeletonLine width="80%" />
          <SkeletonLine width="60%" />
          <SkeletonLine width="70%" />
        </>
      )}
    </section>
  )
}

function SkeletonResults() {
  return (
    <div className="results-animate">
      <SkeletonCard title="Overall Score">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
          <SkeletonLine width="80px" height={48} mb={0} />
          <SkeletonLine width="32px" height={16} mb={0} />
        </div>
        <SkeletonLine width="100%" height={8} />
      </SkeletonCard>
      <SkeletonCard title="Product">
        <SkeletonLine width="85%" />
        <SkeletonLine width="50%" />
        <SkeletonLine width="40%" />
        <SkeletonLine width="30%" />
        <SkeletonLine width="55%" />
      </SkeletonCard>
      <SkeletonCard title="AI Analysis">
        <SkeletonLine width="90%" height={52} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 4 }}>
          <div>
            <SkeletonLine width="100%" height={36} />
            <SkeletonLine width="100%" height={36} />
          </div>
          <div>
            <SkeletonLine width="100%" height={36} />
            <SkeletonLine width="100%" height={36} />
          </div>
        </div>
      </SkeletonCard>
      <SkeletonCard title="Review Integrity">
        <SkeletonLine width="100%" height={8} />
        <SkeletonLine width="65%" mb={4} />
        <SkeletonLine width="55%" mb={4} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {[72, 90, 64, 80].map((w, i) => (
            <SkeletonLine key={i} width={`${w}px`} height={24} mb={0} />
          ))}
        </div>
      </SkeletonCard>
      <SkeletonCard title="Brand Reputation">
        <SkeletonLine width="100%" height={8} />
        <SkeletonLine width="70%" mb={4} />
        <SkeletonLine width="45%" />
      </SkeletonCard>
      <SkeletonCard title="Similar Products">
        <div style={{ display: 'flex', gap: 12, overflow: 'hidden' }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ minWidth: 160, flexShrink: 0 }}>
              <SkeletonLine width="160px" height={110} />
              <SkeletonLine width="90%" height={12} mb={4} />
              <SkeletonLine width="60%" height={12} mb={4} />
              <SkeletonLine width="40%" height={12} />
            </div>
          ))}
        </div>
      </SkeletonCard>
    </div>
  )
}

function ProductImagePlaceholder({ className = 'similar-card-image' }: { className?: string }) {
  return (
    <svg viewBox="0 0 110 110" className={className} xmlns="http://www.w3.org/2000/svg" style={{ background: '#f8f7f5' }}>
      <rect width="110" height="110" fill="#f3ede8" rx="12" />
      <rect x="28" y="30" width="54" height="42" rx="5" fill="none" stroke="#d6cbc3" strokeWidth="2.5" />
      <polyline points="28,60 43,44 55,55 67,43 82,60" fill="none" stroke="#d6cbc3" strokeWidth="2.5" strokeLinejoin="round" />
      <circle cx="43" cy="42" r="4" fill="#d6cbc3" />
    </svg>
  )
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

function ScoreTrack({ value }: { value?: number }) {
  const safeValue = Math.max(0, Math.min(100, value ?? 0))
  return (
    <div className="score-track" aria-label={`Score ${safeValue} out of 100`}>
      <div className="metric-track">
        <div className="metric-fill" style={{ width: `${safeValue}%` }} />
      </div>
    </div>
  )
}

function SectionCard({
  title,
  children,
  collapsible = false,
  defaultOpen = true,
  className = '',
}: {
  title: string
  children: React.ReactNode
  collapsible?: boolean
  defaultOpen?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className={`section-card ${className} ${open || !collapsible ? 'section-card--open' : 'section-card--closed'}`}>
      <div className="section-card-header">
        <h3>{title}</h3>
        {collapsible && (
          <button
            type="button"
            className="collapse-icon-btn"
            onClick={() => setOpen((prev) => !prev)}
            aria-label={open ? `Collapse ${title}` : `Expand ${title}`}
            title={open ? 'Collapse' : 'Expand'}
          >
            <span className={`collapse-chevron ${open ? 'collapse-chevron--open' : ''}`} />
          </button>
        )}
      </div>
      <div className={`section-content ${!collapsible || open ? 'open' : ''}`}>
        <div className="section-content-inner">{children}</div>
      </div>
    </section>
  )
}

function KeywordPills({ keywords, emptyMessage }: { keywords?: Keyword[]; emptyMessage: string }) {
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

function ScoreExplainer({ metric, analysis }: { metric: string; analysis: Analysis | null }) {
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')

  const handleExplain = async () => {
    if (!analysis) return
    setLoading(true)
    setError('')
    try {
      const { raw: _raw, ...safeAnalysis } = analysis
      const response = await fetch(`${API_BASE}/explain-score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Nectar-Secret': NECTAR_SECRET },
        body: JSON.stringify({ metric, analysis: safeAnalysis }),
      })
      const data = await response.json()
      if (!response.ok) {
        setError(typeof data.detail === 'string' ? data.detail : 'Could not explain this score.')
      } else {
        setAnswer(data.answer ?? 'No explanation returned.')
      }
    } catch {
      setError('Could not explain this score right now.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="score-explainer">
      <button className="why-score-btn" onClick={handleExplain} disabled={loading || !analysis}>
        {loading ? 'Explaining…' : 'Why this score?'}
      </button>
      {error && <p className="body-text status-error explain-text">{error}</p>}
      {answer && <div className="explain-box"><p className="body-text explain-text">{answer}</p></div>}
    </div>
  )
}

function VerdictCard({ ai }: { ai: NonNullable<Analysis['aiAnalysis']> }) {
  const rec = ai.recommendation ?? 'COMPARE'
  return (
    <section className="section-card verdict-card results-animate">
      <div className="verdict-card-header">
        <h3 className="verdict-card-title">AI Analysis</h3>
      </div>
      <div className={`verdict-card-panel verdict-card-panel--${rec.toLowerCase()}`}>
        <p className="verdict-panel-label">Overall Take</p>
        <p className="verdict-summary">{ai.verdict}</p>
      </div>
      <div className="verdict-columns">
        <div className="verdict-column verdict-column--pros">
          <p className="verdict-list-label verdict-list-label--pros">PROS</p>
          {(ai.pros ?? []).map((pro, i) => (
            <p key={i} className="verdict-pill verdict-pill--pros">{pro}</p>
          ))}
        </div>
        <div className="verdict-column verdict-column--cons">
          <p className="verdict-list-label verdict-list-label--cons">CONS</p>
          {(ai.cons ?? []).map((con, i) => (
            <p key={i} className="verdict-pill verdict-pill--cons">{con}</p>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Similar Products Scroller ────────────────────────────────────────────────

export function SimilarProductsScroller({ analysis, products }: { analysis: Analysis; products: SimilarProduct[] }) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  const updateScrollState = () => {
    const el = scrollRef.current
    if (!el) return
    const maxScroll = el.scrollWidth - el.clientWidth
    setCanScrollLeft(el.scrollLeft > 2)
    setCanScrollRight(el.scrollLeft < maxScroll - 2)
  }

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateScrollState()
    el.addEventListener('scroll', updateScrollState, { passive: true })
    window.addEventListener('resize', updateScrollState)
    const ro = new ResizeObserver(updateScrollState)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', updateScrollState)
      window.removeEventListener('resize', updateScrollState)
      ro.disconnect()
    }
  }, [products.length])

  const scrollByCard = (direction: 'left' | 'right') => {
    const el = scrollRef.current
    if (!el) return
    const cards = Array.from(el.querySelectorAll<HTMLElement>('.similar-card'))
    const step = cards[1]
      ? cards[1].getBoundingClientRect().left - cards[0].getBoundingClientRect().left
      : cards[0]?.offsetWidth ?? 0
    el.scrollBy({ left: direction === 'right' ? step : -step, behavior: 'smooth' })
  }

  const bestIndex = getBestAlternativeIndex(analysis, products)

  return (
    <div className="similar-scroll-shell">
      <div className={`similar-fade-left ${canScrollLeft ? 'similar-fade-left--visible' : ''}`} />
      <div className={`similar-fade-right ${canScrollRight ? 'similar-fade-right--visible' : ''}`} />
      {canScrollLeft && (
        <button type="button" className="similar-scroll-arrow similar-scroll-arrow--left" aria-label="Scroll left" onClick={() => scrollByCard('left')}>
          <span />
        </button>
      )}
      <div className="similar-scroll" ref={scrollRef}>
        {products.map((product, i) => {
          const comparison = compareProductAgainstCurrent(analysis, product)
          const isBest = i === bestIndex
          return (
            <a
              key={product.listingId ?? product.asin ?? i}
              href={getCommerceUrl(product)}
              target="_blank"
              rel="noreferrer"
              className={`similar-card ${isBest ? 'similar-card--best' : ''}`}
            >
              <div className="similar-card-top">
                <div className="similar-card-badges">
                  {isBest && <span className="best-alt-badge">BEST ALT</span>}
                  <span className={getTagClassName(comparison.tag)}>{comparison.tag}</span>
                </div>
                {product.isPrime && <span className="prime-badge">Prime</span>}
              </div>
              {product.image
                ? <img src={product.image} alt={product.title ?? 'Product'} className="similar-card-image" />
                : <ProductImagePlaceholder />}
              <p className="similar-card-title">{product.title ?? 'Untitled Product'}</p>
              <p className="similar-card-brand">{product.brand ?? 'Unknown brand'}</p>
              <div className="similar-card-price-row">
                <p className="similar-card-price">{product.price ?? 'No price'}</p>
                {comparison.priceDiff !== null && (
                  <span className={`price-diff ${comparison.priceDiff <= 0 ? 'price-diff--down' : 'price-diff--up'}`}>
                    {formatPriceDifference(comparison.priceDiff)}
                  </span>
                )}
              </div>
              <p className="similar-card-rating">
                ⭐ {product.rating ?? 'N/A'}
                {product.reviewCount ? ` · ${product.reviewCount.toLocaleString()} reviews` : ''}
              </p>
            </a>
          )
        })}
      </div>
      {canScrollRight && (
        <button type="button" className="similar-scroll-arrow similar-scroll-arrow--right" aria-label="Scroll right" onClick={() => scrollByCard('right')}>
          <span />
        </button>
      )}
    </div>
  )
}

// ─── Scan History Section ─────────────────────────────────────────────────────

function ScanHistorySection({
  scanHistory,
  selectedCompareIds,
  deletingScanIds,
  isClearingHistory,
  onLoad,
  onToggleCompare,
  onDelete,
  onClearAll,
  onCompare,
}: {
  scanHistory: ScanRecord[]
  selectedCompareIds: string[]
  deletingScanIds: string[]
  isClearingHistory: boolean
  onLoad: (record: ScanRecord) => void
  onToggleCompare: (id: string) => void
  onDelete: (id: string) => void
  onClearAll: () => void
  onCompare: () => void
}) {
  return (
    <SectionCard title="Scan History" collapsible defaultOpen={false} className="section-card--history">
      {scanHistory.length > 0 ? (
        <>
          <div className="scan-history-toolbar">
            <p className="scan-history-count">
              {scanHistory.length} saved {scanHistory.length === 1 ? 'scan' : 'scans'}
            </p>
            <button type="button" className="history-clear-btn" onClick={onClearAll} disabled={isClearingHistory}>
              {isClearingHistory ? 'Clearing…' : 'Clear All'}
            </button>
          </div>

          <div className="scan-history-list">
            {scanHistory.map((item) => {
              const isSelected = selectedCompareIds.includes(item.id)
              const isDeleting = deletingScanIds.includes(item.id)
              return (
                <div
                  key={item.id}
                  className={`history-item history-item--selectable ${isSelected ? 'history-item--selected' : ''} ${isDeleting ? 'history-item--deleting' : ''}`}
                >
                  <button type="button" className="history-load-btn" onClick={() => onLoad(item)}>
                    <div className="history-item-top">
                      <p className="history-item-title">{item.analysis.title ?? 'Untitled Product'}</p>
                      <span className="history-score">{item.analysis.overallScore ?? '--'}</span>
                    </div>
                    <div className="history-item-meta-row">
                      <span className="history-item-meta history-item-meta--brand">{item.analysis.brand ?? 'Unknown brand'}</span>
                      <span className="history-item-meta-separator" aria-hidden="true" />
                      <span className="history-item-meta history-item-meta--time">{new Date(item.scannedAt).toLocaleString()}</span>
                    </div>
                  </button>

                  <div className="history-item-actions">
                    <button
                      type="button"
                      className={`why-score-btn history-compare-btn ${isSelected ? 'secondary-btn--active history-compare-btn--selected' : ''}`}
                      onClick={() => onToggleCompare(item.id)}
                      aria-pressed={isSelected}
                      aria-label={isSelected ? 'Selected for Compare' : 'Select to Compare'}
                    >
                      <span className={`history-compare-btn-indicator ${isSelected ? 'history-compare-btn-indicator--selected' : ''}`} aria-hidden="true" />
                      <span className="history-compare-btn-copy" aria-hidden="true">
                        <span className={`history-compare-btn-text ${isSelected ? 'history-compare-btn-text--hidden' : 'history-compare-btn-text--visible'}`}>
                          Select to Compare
                        </span>
                        <span className={`history-compare-btn-text history-compare-btn-text--selected ${isSelected ? 'history-compare-btn-text--visible' : 'history-compare-btn-text--hidden'}`}>
                          Selected for Compare
                        </span>
                      </span>
                    </button>
                    <button
                      type="button"
                      className="history-delete-btn"
                      aria-label={`Delete scan for ${item.analysis.title ?? 'product'}`}
                      title="Delete this scan"
                      onClick={() => onDelete(item.id)}
                    >
                      ×
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          {scanHistory.length >= 2 && (
            <div className="compare-history-actions">
              <button className="scan-btn" disabled={selectedCompareIds.length !== 2} onClick={onCompare}>
                {selectedCompareIds.length === 2 ? 'Compare Selected Products' : 'Select 2 Products to Compare'}
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="empty-state empty-state--compact">No saved scans yet.</div>
      )}
    </SectionCard>
  )
}

// ─── Results View ─────────────────────────────────────────────────────────────

function ResultsView({ analysis, isExiting }: { analysis: Analysis; isExiting: boolean }) {
  const ri = analysis.sellerReviewIntegrity || analysis.reviewIntegrity
  const br = analysis.sellerReputation || analysis.brandReputation
  const isEbay = analysis.marketplace === 'ebay'

  return (
    <div className={`results-animate${isExiting ? ' results-exit-waterfall' : ''}`}>
      <div className="cascade-item cascade-delay-1">
        <SectionCard title="Overall Score" collapsible className="section-card--score">
          <div className="overall-score-stack">
            <div className="score-row score-row--hero">
              <span className="score-number score-number--hero" style={{ color: getScoreColor(analysis.overallScore) }}>
                {analysis.overallScore ?? '--'}
              </span>
              <span className="score-max">/100</span>
            </div>
            {analysis.aiAnalysis?.recommendation && (
              <div className="overall-score-chip-row">
                <span className={getRecommendationClass(analysis.aiAnalysis.recommendation)}>
                  {analysis.aiAnalysis.recommendation}
                </span>
              </div>
            )}
          </div>
          <MetricBar label="Trust Score" value={analysis.overallScore} />
        </SectionCard>
      </div>

      <div className="cascade-item cascade-delay-2">
        <SectionCard title="Product" collapsible>
          <div className="info-list">
            <p><strong>Title:</strong> {analysis.title ?? 'N/A'}</p>
            <p><strong>Brand:</strong> {analysis.brand ?? 'N/A'}</p>
            <p><strong>Price:</strong> {analysis.price ?? 'N/A'}</p>
            <p><strong>Rating:</strong> {analysis.rating ?? 'N/A'}</p>
            <p><strong>Review Count:</strong> {analysis.reviewCount ?? 'N/A'}</p>
          </div>
        </SectionCard>
      </div>

      {analysis.aiAnalysis && (
        <div className="cascade-item cascade-delay-3">
          <VerdictCard ai={analysis.aiAnalysis} />
        </div>
      )}

      <div className="cascade-item cascade-delay-4">
        <SectionCard title={isEbay ? "Seller Review Integrity" : "Review Integrity"} collapsible className="section-card--integrity">
          <div className="integrity-lead">
            <div className="mini-score mini-score--featured">
              <span>Score</span>
              <strong>{ri?.score ?? 'N/A'}</strong>
            </div>
            <ScoreTrack value={ri?.score} />
          </div>
          {Object.entries(ri?.flags ?? {}).some(([, active]) => active) && (
            <div className="integrity-flags">
              {Object.entries(ri!.flags!)
                .filter(([, active]) => active)
                .map(([flag]) => (
                  <span key={flag} className="integrity-flag">{formatFlagLabel(flag)}</span>
                ))}
            </div>
          )}
          <div className="info-list">
            <p><strong>Label:</strong> {ri?.label ?? 'N/A'}</p>
            <p><strong>Verified Purchase Ratio:</strong> {ri?.verifiedPurchaseRatio ?? 'N/A'}</p>
            <p><strong>Sentiment Consistency:</strong> {ri?.sentimentConsistencyRatio ?? 'N/A'}</p>
            <p className="keywords-label"><strong>Top Keywords:</strong></p>
            <KeywordPills keywords={ri?.commonKeywords} emptyMessage="No keywords found" />
          </div>
          <ScoreExplainer metric={isEbay ? "seller_review_integrity" : "review_integrity"} analysis={analysis} />
        </SectionCard>
      </div>

      <div className="cascade-item cascade-delay-5">
        <SectionCard title={isEbay ? "Seller Reputation" : "Brand Reputation"} collapsible className="section-card--brand">
          <div className="brand-lead">
            <div className="mini-score mini-score--featured">
              <span>Score</span>
              <strong>{br?.score ?? 'N/A'}</strong>
            </div>
            <ScoreTrack value={br?.score} />
          </div>
          <div className="info-list">
            {isEbay ? (
              <>
                <p><strong>Seller Name:</strong> {br?.sellerName ?? 'N/A'}</p>
                <p><strong>Feedback Label:</strong> {br?.label ?? 'N/A'}</p>
                <p><strong>Positive Feedback:</strong> {br?.sellerPositivePct != null ? `${br.sellerPositivePct}%` : 'N/A'}</p>
                <p><strong>Seller Review Count:</strong> {br?.sellerReviewCount != null ? br.sellerReviewCount.toLocaleString() : 'N/A'}</p>
                {br?.topRatedSeller && (
                  <p><strong>Status:</strong> <span style={{ color: '#15803d', fontWeight: 'bold' }}>Top Rated Seller</span></p>
                )}
              </>
            ) : (
              <>
                <p><strong>Label:</strong> {br?.label ?? 'N/A'}</p>
                <p><strong>Reviews Analyzed:</strong> {br?.reviewsAnalyzed ?? 'N/A'}</p>
              </>
            )}
          </div>
          {br?.insights?.length ? (
            <div className="insight-list">
              {br.insights.map((insight) => (
                <div key={insight.topic} className="insight-pill">
                  <span>{insight.topic}</span>
                  <strong>{insight.status}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="body-text muted">{isEbay ? "No seller insights yet." : "No brand insights yet."}</p>
          )}
          <p className="keywords-label"><strong>Top Keywords:</strong></p>
          <KeywordPills keywords={br?.commonKeywords} emptyMessage="No keywords found" />
          <ScoreExplainer metric={isEbay ? "seller_reputation" : "brand_reputation"} analysis={analysis} />
        </SectionCard>
      </div>

      <div className="cascade-item cascade-delay-6">
        <SectionCard title="Similar Products" collapsible className="section-card--similar">
          {(analysis.similarProducts?.length ?? 0) > 0 ? (
            <SimilarProductsScroller analysis={analysis} products={analysis.similarProducts ?? []} />
          ) : (
            <p className="body-text muted empty-state empty-state--compact">
              No alternatives found{analysis.productKeyword && analysis.productKeyword !== 'unknown' ? ` for ${analysis.productKeyword}` : ''}.
            </p>
          )}
        </SectionCard>
      </div>
    </div>
  )
}

// ─── Compare View ─────────────────────────────────────────────────────────────

function CompareView({ records, onBack }: { records: [ScanRecord, ScanRecord]; onBack: () => void }) {
  const [left, right] = records
  const la = left.analysis
  const ra = right.analysis

  const lri = la.sellerReviewIntegrity || la.reviewIntegrity
  const rri = ra.sellerReviewIntegrity || ra.reviewIntegrity
  const lbr = la.sellerReputation || la.brandReputation
  const rbr = ra.sellerReputation || ra.brandReputation

  const scoreW = getMetricWinner(la.overallScore, ra.overallScore, 'higher')
  const priceW = getMetricWinner(la.price, ra.price, 'lower')
  const ratingW = getMetricWinner(la.rating, ra.rating, 'higher')
  const reviewCountW = getMetricWinner(la.reviewCount, ra.reviewCount, 'higher')
  const integrityW = getMetricWinner(lri?.score, rri?.score, 'higher')
  const brandW = getMetricWinner(lbr?.score, rbr?.score, 'higher')

  const allWinners = [scoreW, priceW, ratingW, reviewCountW, integrityW, brandW]
  const leftWins = allWinners.filter((w) => w === 'left').length
  const rightWins = allWinners.filter((w) => w === 'right').length
  const summaryLabel = leftWins === rightWins ? 'CLOSE MATCH' : leftWins > rightWins ? 'LEFT PRODUCT LEADS' : 'RIGHT PRODUCT LEADS'

  const coreMetrics = [
    { label: 'Overall Score', lv: la.overallScore, rv: ra.overallScore, winner: scoreW },
    { label: 'Price', lv: la.price, rv: ra.price, winner: priceW },
    { label: 'Rating', lv: la.rating, rv: ra.rating, winner: ratingW },
    { label: 'Review Count', lv: la.reviewCount, rv: ra.reviewCount, winner: reviewCountW },
  ]

  const isLeftEbay = la.marketplace === 'ebay'
  const isRightEbay = ra.marketplace === 'ebay'

  const integrityLabel = isLeftEbay && isRightEbay
    ? 'Seller Review Integrity'
    : isLeftEbay || isRightEbay
    ? 'Review / Seller Review Integrity'
    : 'Review Integrity'

  const integrityLabelRow = isLeftEbay && isRightEbay
    ? 'Seller Integrity Label'
    : isLeftEbay || isRightEbay
    ? 'Integrity Label / Seller Integrity Label'
    : 'Integrity Label'

  const verifiedLabel = isLeftEbay && isRightEbay
    ? 'Seller Verified Ratio'
    : isLeftEbay || isRightEbay
    ? 'Verified Ratio / Seller Verified Ratio'
    : 'Verified Ratio'

  const reputationLabel = isLeftEbay && isRightEbay
    ? 'Seller Reputation'
    : isLeftEbay || isRightEbay
    ? 'Brand / Seller Reputation'
    : 'Brand Reputation'

  const brandLabelRow = isLeftEbay && isRightEbay
    ? 'Seller Label'
    : isLeftEbay || isRightEbay
    ? 'Brand Label / Seller Label'
    : 'Brand Label'

  const trustMetrics = [
    { label: integrityLabel, lv: lri?.score, rv: rri?.score, winner: integrityW },
    { label: integrityLabelRow, lv: lri?.label, rv: rri?.label, winner: 'tie' as const },
    { label: verifiedLabel, lv: lri?.verifiedPurchaseRatio, rv: rri?.verifiedPurchaseRatio, winner: 'tie' as const },
    { label: reputationLabel, lv: lbr?.score, rv: rbr?.score, winner: brandW },
    { label: brandLabelRow, lv: lbr?.label, rv: rbr?.label, winner: 'tie' as const },
  ]

  return (
    <main className="app-shell">
      <div className="popup-shell">
        <header className="top-header">
          <div className="brand-row">
            <img src={logoSrc} alt="Nectar logo" className="brand-logo" />
            <div className="brand-block">
              <h1>Nectar</h1>
              <p>PRODUCT COMPARISON</p>
            </div>
          </div>
          <button className="premium-btn" onClick={onBack}>← Back</button>
        </header>

        <div className="content" key="compare-view">
          <div className="cascade-item cascade-delay-1">
            <section className="section-card compare-hero">
              <div className="compare-hero-top">
                <div>
                  <h3 className="compare-hero-title">Compare Products</h3>
                  <p className="compare-hero-text">Side-by-side view of pricing, trust, ratings, and AI verdicts.</p>
                </div>
                <span className="compare-summary-badge">{summaryLabel}</span>
              </div>
              <div className="compare-summary-pills">
                <span className={`compare-chip ${priceW}`}>Best Value · {priceW === 'tie' ? 'Tie' : priceW === 'left' ? 'Left' : 'Right'}</span>
                <span className={`compare-chip ${ratingW}`}>Higher Rated · {ratingW === 'tie' ? 'Tie' : ratingW === 'left' ? 'Left' : 'Right'}</span>
                <span className={`compare-chip ${integrityW}`}>More Trusted · {integrityW === 'tie' ? 'Tie' : integrityW === 'left' ? 'Left' : 'Right'}</span>
                <span className={`compare-chip ${brandW}`}>Better Brand/Seller · {brandW === 'tie' ? 'Tie' : brandW === 'left' ? 'Left' : 'Right'}</span>
              </div>
            </section>
          </div>

          <div className="cascade-item cascade-delay-2">
            <section className="compare-products-grid">
              {([
                { side: 'LEFT', a: la, record: left, image: getAnalysisImage(la), isLeader: leftWins > rightWins },
                { side: 'RIGHT', a: ra, record: right, image: getAnalysisImage(ra), isLeader: rightWins > leftWins },
              ] as const).map(({ side, a, record, image, isLeader }) => (
                <article key={side} className={`compare-product-card ${isLeader ? 'compare-product-card--leader' : ''}`}>
                  <div className="compare-product-image-wrap">
                    {image
                      ? <img src={image} alt={a.title ?? 'Product'} className="compare-product-image" />
                      : <ProductImagePlaceholder className="compare-product-image" />}
                  </div>
                  <div className="compare-product-card-body">
                    <div className="compare-product-card-top">
                      <span className="compare-side-badge">{side}</span>
                      {isLeader && <span className="compare-winner-badge">BEST PICK</span>}
                    </div>
                    <p className="compare-product-title">{a.title ?? 'Untitled Product'}</p>
                    <p className="compare-product-meta">{a.brand ?? 'Unknown brand'} · {new Date(record.scannedAt).toLocaleString()}</p>
                    <div className="compare-quick-stats">
                      <div className="compare-quick-stat"><span>Score</span><strong>{renderMetricValue(a.overallScore)}</strong></div>
                      <div className="compare-quick-stat"><span>Price</span><strong>{renderMetricValue(a.price)}</strong></div>
                      <div className="compare-quick-stat"><span>Rating</span><strong>{renderMetricValue(a.rating)}</strong></div>
                    </div>
                  </div>
                </article>
              ))}
            </section>
          </div>

          <div className="cascade-item cascade-delay-3">
            <section className="section-card compare-section-card">
              <h3 className="compare-section-title">Core Metrics</h3>
              <div className="compare-rows">
                {coreMetrics.map(({ label, lv, rv, winner }) => (
                  <div key={label} className="compare-row">
                    <div className="compare-row-label">{label}</div>
                    <div className={getCompareValueClass(winner, 'left')}>{renderMetricValue(lv)}</div>
                    <div className={getCompareValueClass(winner, 'right')}>{renderMetricValue(rv)}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="cascade-item cascade-delay-4">
            <section className="section-card compare-section-card">
              <h3 className="compare-section-title">Trust & Reputation</h3>
              <div className="compare-rows">
                {trustMetrics.map(({ label, lv, rv, winner }) => (
                  <div key={label} className="compare-row">
                    <div className="compare-row-label">{label}</div>
                    <div className={getCompareValueClass(winner, 'left')}>{renderMetricValue(lv)}</div>
                    <div className={getCompareValueClass(winner, 'right')}>{renderMetricValue(rv)}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="cascade-item cascade-delay-5">
            <section className="section-card compare-section-card">
              <h3 className="compare-section-title">AI Verdict</h3>
              <div className="compare-ai-grid">
                {[la, ra].map((a, i) => (
                  <div key={i} className="compare-ai-card">
                    <p className="compare-ai-label">Recommendation</p>
                    <p className="compare-ai-recommendation">{renderMetricValue(a.aiAnalysis?.recommendation)}</p>
                    <p className="compare-ai-verdict">{renderMetricValue(a.aiAnalysis?.verdict)}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="cascade-item cascade-delay-6">
            <SectionCard title={isLeftEbay || isRightEbay ? "Review / Seller Review Integrity Keywords" : "Review Integrity Keywords"}>
              <p className="compare-subtitle">{la.title ?? 'Left Product'}</p>
              <KeywordPills keywords={lri?.commonKeywords} emptyMessage="No keywords found" />
              <div style={{ height: 14 }} />
              <p className="compare-subtitle">{ra.title ?? 'Right Product'}</p>
              <KeywordPills keywords={rri?.commonKeywords} emptyMessage="No keywords found" />
            </SectionCard>
          </div>

          <div className="cascade-item cascade-delay-7">
            <SectionCard title={isLeftEbay || isRightEbay ? "Brand / Seller Reputation Keywords" : "Brand Reputation Keywords"}>
              <p className="compare-subtitle">{la.title ?? 'Left Product'}</p>
              <KeywordPills keywords={lbr?.commonKeywords} emptyMessage="No keywords found" />
              <div style={{ height: 14 }} />
              <p className="compare-subtitle">{ra.title ?? 'Right Product'}</p>
              <KeywordPills keywords={rbr?.commonKeywords} emptyMessage="No keywords found" />
            </SectionCard>
          </div>
        </div>
      </div>
    </main>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [scanUrl, setScanUrl] = useState('')
  const detectedMarketplace = /amazon\./i.test(scanUrl) ? 'amazon' : /ebay\./i.test(scanUrl) ? 'ebay' : null
  const [isAutoDetected, setIsAutoDetected] = useState(false)
  const [backendStatus, setBackendStatus] = useState('Ready to scan')
  const [analysis, setAnalysis] = useState<Analysis | null>(DEV_PREVIEW ? mockAnalysis : null)
  const [view, setView] = useState<'home' | 'premium' | 'compare'>('home')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasScanned, setHasScanned] = useState<boolean>(DEV_PREVIEW)
  const [isExitingResults, setIsExitingResults] = useState(false)
  const [cancelAvailable, setCancelAvailable] = useState(false)
  const [windowControlsVisible, setWindowControlsVisible] = useState(false)

  const [currentSavedScan, setCurrentSavedScan] = useState<ScanRecord | null>(null)
  const [previousSavedScan, setPreviousSavedScan] = useState<ScanRecord | null>(null)
  const [scanHistory, setScanHistory] = useState<ScanRecord[]>([])
  const [deletingScanIds, setDeletingScanIds] = useState<string[]>([])
  const [isClearingHistory, setIsClearingHistory] = useState(false)
  const [selectedCompareIds, setSelectedCompareIds] = useState<string[]>([])
  const [compareRecords, setCompareRecords] = useState<[ScanRecord, ScanRecord] | null>(null)

  const scanAbortRef = useRef<AbortController | null>(null)
  const scanIdRef = useRef<string | null>(null)
  const cancelTimerRef = useRef<number | null>(null)
  const scanDelayResolveRef = useRef<(() => void) | null>(null)
  const scanWasCancelledRef = useRef(false)

  useEffect(() => {
    detectActiveUrl()
    loadCurrentSavedScan().then(setCurrentSavedScan)
    loadPreviousSavedScan().then(setPreviousSavedScan)
    loadScanHistory().then(setScanHistory)
    return () => {
      if (cancelTimerRef.current !== null) window.clearTimeout(cancelTimerRef.current)
      scanDelayResolveRef.current?.()
      scanAbortRef.current?.abort()
    }
  }, [])

  // ── URL Detection ──

  const detectActiveUrl = async () => {
    try {
      if (typeof window.electronAPI?.getActiveTabUrl === 'function') {
        const url = await window.electronAPI.getActiveTabUrl()
        if (url) {
          setScanUrl(url)
          setIsAutoDetected(true)
          setBackendStatus(
            isSupportedUrl(url)
              ? `${isEbayUrl(url) ? 'eBay' : 'Amazon'} product page auto-detected`
              : 'Active tab detected. Edit or enter a product URL.'
          )
          setError('')
        } else {
          setIsAutoDetected(false)
          setBackendStatus('No active browser tab found. Enter URL manually.')
        }
      } else {
        setIsAutoDetected(false)
        setBackendStatus('Running outside Electron. Enter URL manually.')
      }
    } catch {
      setIsAutoDetected(false)
    }
  }

  // ── Scan Lifecycle ──

  const closeCancelWindow = () => {
    if (cancelTimerRef.current !== null) {
      window.clearTimeout(cancelTimerRef.current)
      cancelTimerRef.current = null
    }
    scanDelayResolveRef.current?.()
    scanDelayResolveRef.current = null
    setCancelAvailable(false)
  }

  const notifyBackendScanCancelled = (scanId: string | null) => {
    if (!scanId) return
    fetch(`${API_BASE}/cancel-scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scanId }),
    }).catch(() => { })
  }

  const handleCancelScan = () => {
    if (!loading || !cancelAvailable) return
    scanWasCancelledRef.current = true
    const scanId = scanIdRef.current
    const controller = scanAbortRef.current
    closeCancelWindow()
    controller?.abort()
    notifyBackendScanCancelled(scanId)
    setLoading(false)
    setAnalysis(null)
    setError('')
    setBackendStatus('Scan has been cancelled successfully')
  }

  const handleScan = async () => {
    const url = scanUrl.trim()

    if (!url) {
      const msg = 'Enter a product page URL first.'
      setError(msg); setBackendStatus(msg); return
    }
    if (!isSupportedUrl(url)) {
      const msg = 'Navigate to an Amazon or eBay product page, or enter a valid product URL.'
      setError(msg); setBackendStatus(msg); return
    }

    try {
      scanWasCancelledRef.current = false
      setLoading(true)
      setCancelAvailable(true)
      setError('')
      setAnalysis(null)
      setBackendStatus('Scan will begin in 3 seconds…')

      await new Promise<void>((resolve) => {
        scanDelayResolveRef.current = resolve
        cancelTimerRef.current = window.setTimeout(closeCancelWindow, SCAN_CANCEL_WINDOW_MS)
      })

      if (scanWasCancelledRef.current) return

      const scanId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const controller = new AbortController()
      scanIdRef.current = scanId
      scanAbortRef.current = controller
      setBackendStatus('Running product analyses…')

      const response = await fetch(`${API_BASE}/current-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Nectar-Secret': NECTAR_SECRET },
        body: JSON.stringify({ url, scanId }),
        signal: controller.signal,
      })

      const data = await response.json()

      if (response.status === 499 || data?.cancelled) {
        setBackendStatus('Scan has been cancelled successfully')
        setError('')
        return
      }

      if (!response.ok) {
        const msg = typeof data.detail === 'string' ? data.detail : 'Request failed.'
        setBackendStatus(msg); setError(msg); return
      }

      const nextAnalysis: Analysis | null = data.analysis ?? null

      if (!nextAnalysis) {
        const msg = 'Scan completed, but no analysis was returned.'
        setBackendStatus(msg); setError(msg); return
      }

      setAnalysis(nextAnalysis)
      setBackendStatus('Analysis complete')
      setHasScanned(true)
      setError('')
      setView('home')

      const record: ScanRecord = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        scannedAt: new Date().toISOString(),
        url,
        analysis: nextAnalysis,
      }

      const oldCurrent = await loadCurrentSavedScan()
      await storageSet({ [CURRENT_SCAN_KEY]: record, [PREVIOUS_SCAN_KEY]: oldCurrent })
      setCurrentSavedScan(record)
      setPreviousSavedScan(oldCurrent)

      const existingHistory = await loadScanHistory()
      const nextHistory = [record, ...existingHistory].slice(0, MAX_SCAN_HISTORY)
      await storageSet({ [SCAN_HISTORY_KEY]: nextHistory })
      setScanHistory(nextHistory)
    } catch (err) {
      if (scanWasCancelledRef.current || (err instanceof DOMException && err.name === 'AbortError')) {
        setBackendStatus('Scan has been cancelled successfully')
        setError('')
        return
      }
      const msg = 'Scan failed. Please open a supported product page or start the server.'
      setBackendStatus(msg); setError(msg)
    } finally {
      closeCancelWindow()
      scanAbortRef.current = null
      scanIdRef.current = null
      scanWasCancelledRef.current = false
      setLoading(false)
    }
  }

  // ── Results Exit Animation ──

  const triggerResultsExit = (onComplete: () => void) => {
    setIsExitingResults(true)
    setTimeout(() => {
      onComplete()
      setIsExitingResults(false)
    }, EXIT_ANIMATION_MS)
  }

  // ── History Management ──

  const toggleCompareSelection = (id: string) => {
    setSelectedCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((i) => i !== id)
      if (prev.length >= 2) return [prev[1], id]
      return [...prev, id]
    })
  }

  const handleLoadScan = (record: ScanRecord) => {
    setAnalysis(record.analysis)
    setHasScanned(true)
    setBackendStatus('Loaded scan from history')
    setError('')
  }

  const handleDeleteScan = (id: string) => {
    setDeletingScanIds((prev) => [...prev, id])
    setTimeout(async () => {
      const deletedRecord = scanHistory.find((item) => item.id === id)
      const nextHistory = scanHistory.filter((item) => item.id !== id)

      await storageSet({ [SCAN_HISTORY_KEY]: nextHistory })

      const [savedCurrent, savedPrevious] = await Promise.all([loadCurrentSavedScan(), loadPreviousSavedScan()])
      const keysToRemove: string[] = []
      if (savedCurrent?.id === id) keysToRemove.push(CURRENT_SCAN_KEY)
      if (savedPrevious?.id === id) keysToRemove.push(PREVIOUS_SCAN_KEY)
      if (keysToRemove.length) await storageRemove(keysToRemove)

      setScanHistory(nextHistory)
      setSelectedCompareIds((prev) => prev.filter((i) => i !== id))
      if (currentSavedScan?.id === id) setCurrentSavedScan(null)
      if (previousSavedScan?.id === id) setPreviousSavedScan(null)

      if (deletedRecord?.analysis === analysis) {
        triggerResultsExit(() => { setAnalysis(null); setHasScanned(false) })
      }

      setDeletingScanIds((prev) => prev.filter((i) => i !== id))
      setBackendStatus('Removed scan from history')
      setError('')
    }, DELETE_ENTRY_DELAY_MS)
  }

  const handleClearScanHistory = () => {
    setIsClearingHistory(true)
    setDeletingScanIds(scanHistory.map((item) => item.id))
    setTimeout(async () => {
      await storageSet({ [SCAN_HISTORY_KEY]: [] })
      await storageRemove([CURRENT_SCAN_KEY, PREVIOUS_SCAN_KEY])

      setScanHistory([])
      setSelectedCompareIds([])
      setCompareRecords(null)
      setCurrentSavedScan(null)
      setPreviousSavedScan(null)
      setView('home')
      setBackendStatus('Scan history cleared')
      setError('')

      if (analysis) {
        triggerResultsExit(() => { setAnalysis(null); setHasScanned(false) })
      } else {
        setAnalysis(null)
        setHasScanned(false)
      }

      setDeletingScanIds([])
      setIsClearingHistory(false)
    }, CLEAR_ALL_ENTRY_DELAY_MS)
  }

  const handleStartCompare = () => {
    const selected = scanHistory.filter((item) => selectedCompareIds.includes(item.id))
    if (selected.length === 2) {
      setCompareRecords([selected[0], selected[1]])
      setView('compare')
      setSelectedCompareIds([])
    }
  }

  // ── Routing ──

  if (view === 'compare' && compareRecords) {
    return <CompareView records={compareRecords} onBack={() => setView('home')} />
  }

  if (view === 'premium') {
    return (
      <main className="app-shell">
        <div className="popup-shell">
          <PremiumScreen key="premium-screen" onBack={() => setView('home')} />
        </div>
      </main>
    )
  }

  const historySection = (
    <ScanHistorySection
      scanHistory={scanHistory}
      selectedCompareIds={selectedCompareIds}
      deletingScanIds={deletingScanIds}
      isClearingHistory={isClearingHistory}
      onLoad={handleLoadScan}
      onToggleCompare={toggleCompareSelection}
      onDelete={handleDeleteScan}
      onClearAll={handleClearScanHistory}
      onCompare={handleStartCompare}
    />
  )

  return (
    <main className="app-shell">
      <div className="popup-shell">
        <header
          className="top-header"
          onMouseEnter={() => setWindowControlsVisible(true)}
          onMouseLeave={() => setWindowControlsVisible(false)}
        >
          <div className="brand-row">
            <img src={logoSrc} alt="Nectar logo" className="brand-logo" />
            <div className="brand-block">
              <h1>Nectar</h1>
              <p>SMART PRODUCT ANALYZER</p>
            </div>
          </div>
          <button className="premium-btn" onClick={() => setView('premium')}>Go Premium</button>
          <div className={`window-controls ${windowControlsVisible ? 'visible' : ''}`}>
            <button className="window-control window-control-minimize" onClick={() => window.electronAPI?.minimizeWindow?.()} title="Minimize" />
            <button className="window-control window-control-close" onClick={() => window.electronAPI?.closeWindow?.()} title="Close" />
          </div>
        </header>

        <div className="content" key="home-view">
          <div className="cascade-item cascade-delay-1">
            <SectionCard title="Product Analysis" className="section-card--hero">
              <div className="url-input-container">
                <div className="url-status-bar">
                  <span className={`status-dot ${isAutoDetected ? 'status-dot--active' : ''}`} />
                  <span className="status-label">{isAutoDetected ? 'Active Browser Tab' : 'Manual Entry'}</span>
                  {detectedMarketplace && (
                    <span className={`marketplace-badge marketplace-badge--${detectedMarketplace}`}>
                      {detectedMarketplace === 'amazon' ? 'Amazon' : 'eBay'}
                    </span>
                  )}
                  <button type="button" className="url-refresh-btn" onClick={detectActiveUrl} title="Detect active URL from browser">
                    ↻ Sync Browser
                  </button>
                </div>
                <input
                  type="text"
                  className="premium-url-input"
                  placeholder="Paste Amazon or eBay product URL here..."
                  value={scanUrl}
                  onChange={(e) => { setScanUrl(e.target.value); setIsAutoDetected(false) }}
                />
              </div>
              <p className={`body-text hero-status ${error ? 'status-error' : 'status-ok'}`}>
                {error || backendStatus}
              </p>
              <button className="scan-btn scan-btn--hero" onClick={handleScan} disabled={loading}>
                {loading ? 'Scanning…' : 'Scan Product'}
              </button>
              {loading && cancelAvailable && (
                <button type="button" className="scan-cancel-btn" onClick={handleCancelScan}>
                  <span>Cancel Scan</span>
                </button>
              )}
            </SectionCard>
          </div>

          {!hasScanned && <div className="cascade-item cascade-delay-2">{historySection}</div>}
          {loading && <SkeletonResults />}

          {!loading && hasScanned && analysis && (
            <>
              <ResultsView analysis={analysis} isExiting={isExitingResults} />
              <div className="cascade-item cascade-delay-7">{historySection}</div>
            </>
          )}
        </div>
      </div>
    </main>
  )
}