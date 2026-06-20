import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import './App.css'
import logoSrc from '/Icons/logo.png'

// ─── Electron API ─────────────────────────────────────────────────────────────

declare global {
  interface Window {
    electronAPI?: {
      getActiveTabUrl: () => Promise<string | null>
      fitToContent: (opts: { contentHeight: number }) => Promise<void>
      resizeWindow: (opts: { width?: number; height: number }) => Promise<void>
      minimizeWindow: () => void
      closeWindow: () => void
      openExternal?: (url: string) => void
      toggleExpand?: () => Promise<boolean>
    }
  }
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEV_PREVIEW = import.meta.env.DEV && true
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const NECTAR_SECRET = import.meta.env.NECTAR_API_SECRET || ''

const EXIT_ANIMATION_MS = 720
const DELETE_ENTRY_DELAY_MS = 240
const CLEAR_ALL_ENTRY_DELAY_MS = 260
const SCAN_CANCEL_WINDOW_MS = 3000
const AUTO_FIT_DELTA_THRESHOLD = 2
const RECOMMENDATION_TIMEOUT_MS = 24000
const RECOMMENDATION_REFINEMENT_TIMEOUT_MS = 26000
const RECOMMENDATION_FADE_MS = 180

const CURRENT_SCAN_KEY = 'nectar_current_scan'
const PREVIOUS_SCAN_KEY = 'nectar_previous_scan'
const SCAN_HISTORY_KEY = 'nectar_scan_history'
const MAX_SCAN_HISTORY = 10

const RECOMMENDER_FILTERS = ['overall', 'durability', 'price', 'quality'] as const
const RECOMMENDER_MARKETPLACES = ['all', 'amazon', 'ebay'] as const
const DASHBOARD_TABS = ['home', 'trends'] as const

// ─── Types ────────────────────────────────────────────────────────────────────

type Insight = { topic: string; status: unknown; detail?: unknown }
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
  condition?: string | null
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
type RecommenderFilter = typeof RECOMMENDER_FILTERS[number]
type RecommenderMarketplace = typeof RECOMMENDER_MARKETPLACES[number]
type DashboardTab = typeof DASHBOARD_TABS[number]

type PricePoint = {
  date: string
  price: number
}

type PriceInsight = {
  type: string
  label: string
  date?: string
  price?: number
}

type PriceIntelligence = {
  points: PricePoint[]
  insights: PriceInsight[]
  narrative: string
  likelyToDrop: boolean
  confidence: number
  callouts: string[]
  generatedAt: string
}

function AutoSizingWindow({ children }: { children: ReactNode }) {
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const panel = panelRef.current
    const fitToContent = window.electronAPI?.fitToContent
    if (!panel || !fitToContent) return

    let frame = 0
    let lastMeasuredHeight = 0

    const measureAndFit = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => {
        const header = panel.querySelector<HTMLElement>('.top-header')
        const content = panel.querySelector<HTMLElement>('.content')
        const panelStyles = window.getComputedStyle(panel)
        const borderHeight =
          parseFloat(panelStyles.borderTopWidth || '0') +
          parseFloat(panelStyles.borderBottomWidth || '0')
        const headerHeight = header?.getBoundingClientRect().height ?? 0
        const fitStop = panel.querySelector<HTMLElement>('.popup-fit-stop')
        const historyIsOpen = Boolean(panel.querySelector('.section-card--history.section-card--open'))
        const shouldUseFitStop = Boolean(fitStop && !historyIsOpen)
        const contentStyles = content ? window.getComputedStyle(content) : null
        const contentBottomPadding = contentStyles ? parseFloat(contentStyles.paddingBottom || '0') : 0
        const stopHeight = content && fitStop && shouldUseFitStop
          ? headerHeight + fitStop.offsetTop + fitStop.offsetHeight + contentBottomPadding + borderHeight
          : null
        const contentHeight = shouldUseFitStop
          ? stopHeight ?? panel.scrollHeight
          : headerHeight + (content?.scrollHeight ?? panel.scrollHeight) + borderHeight
        const nextHeight = Math.ceil(contentHeight)

        if (Math.abs(nextHeight - lastMeasuredHeight) < AUTO_FIT_DELTA_THRESHOLD) return
        lastMeasuredHeight = nextHeight
        fitToContent({ contentHeight: nextHeight })
      })
    }

    const measureAfterLayoutTransition = (event: TransitionEvent) => {
      if (event.propertyName !== 'grid-template-rows') return
      measureAndFit()
    }

    measureAndFit()

    const observer = new MutationObserver(measureAndFit)
    observer.observe(panel, {
      attributes: true,
      childList: true,
      characterData: true,
      subtree: true,
    })

    panel.addEventListener('load', measureAndFit, true)
    panel.addEventListener('transitionend', measureAfterLayoutTransition)
    panel.addEventListener('animationend', measureAndFit)

    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      panel.removeEventListener('load', measureAndFit, true)
      panel.removeEventListener('transitionend', measureAfterLayoutTransition)
      panel.removeEventListener('animationend', measureAndFit)
    }
  }, [])

  return (
    <main className="app-shell">
      <div className="popup-shell" ref={panelRef}>
        {children}
      </div>
    </main>
  )
}

type ScanRecord = {
  id: string
  scannedAt: string
  url: string
  analysis: Analysis
  priceIntelligence?: PriceIntelligence
}

type RecommendationResponse = {
  ok?: boolean
  rejected?: boolean
  message?: string
  query?: string
  reason?: string
  marketplace?: RecommenderMarketplace
  products?: SimilarProduct[]
}

type PriceTrendResponse = {
  ok?: boolean
  points?: PricePoint[]
  insights?: PriceInsight[]
  narrative?: string
  likelyToDrop?: boolean
  confidence?: number
  callouts?: string[]
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

function getRecommendationHistoryKey(history: ScanRecord[]): string {
  return history
    .slice(0, 8)
    .map((item) => {
      const analysis = item.analysis ?? {}
      return [
        item.id,
        item.scannedAt,
        analysis.title,
        analysis.brand,
        analysis.productKeyword,
        analysis.marketplace,
        analysis.price,
      ].filter(Boolean).join('~')
    })
    .join('|')
}

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
  if (diff === 0) return 'Same price'
  return diff > 0 ? `+$${abs}` : `Save $${abs}`
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

function formatProductRating(analysis: Analysis, isEbay: boolean): string {
  if (analysis.rating !== null && analysis.rating !== undefined && analysis.rating !== '') {
    return `${analysis.rating} / 5`
  }
  if (isEbay) {
    const sellerPct = analysis.sellerReputation?.sellerPositivePct
    return sellerPct != null ? `Seller feedback ${sellerPct}% positive` : 'Product rating unavailable'
  }
  return 'N/A'
}

function formatProductReviewCount(analysis: Analysis, isEbay: boolean): string {
  if (analysis.reviewCount !== null && analysis.reviewCount !== undefined) {
    return analysis.reviewCount.toLocaleString()
  }
  if (isEbay) {
    const sellerCount = analysis.sellerReputation?.sellerReviewCount
    return sellerCount != null ? `${sellerCount.toLocaleString()} seller feedback ratings` : 'Product reviews unavailable'
  }
  return 'N/A'
}

function formatInsightStatus(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Unavailable'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const display = record.display ?? record.text ?? record.formatted ?? record.raw ?? record.description
    if (display) return formatInsightStatus(display)
    const amount = record.value ?? record.amount ?? record.extracted
    const currency = record.currency
    if (typeof amount === 'number') {
      if (currency && /delivery|day/i.test(String(currency))) return `Delivery in ${amount} days`
      if (amount === 0) return 'Free'
      return currency && String(currency).toUpperCase() !== 'USD'
        ? `${amount} ${currency}`
        : `$${amount.toFixed(2)}`
    }
    if (amount) return String(amount)
  }
  return 'Details unavailable'
}

function getInsightTone(status: string): 'positive' | 'caution' | 'neutral' {
  const text = status.toLowerCase()
  if (/(excellent|good|positive|free|matched|top rated|strong)/.test(text)) return 'positive'
  if (/(caution|poor|disputed|unavailable|not specified|low|missing|unclear)/.test(text)) return 'caution'
  return 'neutral'
}

function InsightPill({ insight }: { insight: Insight }) {
  const status = formatInsightStatus(insight.status)
  const detail = formatInsightStatus(insight.detail ?? insight.status)
  const tone = getInsightTone(status)
  return (
    <div className={`insight-pill insight-pill--${tone}`} tabIndex={0}>
      <span>{insight.topic}</span>
      <strong>{status}</strong>
      {detail.length > 42 && (
        <div className="insight-popover" role="tooltip">
          <span className="insight-popover-title">{insight.topic}</span>
          <p>{detail}</p>
        </div>
      )}
    </div>
  )
}

function getAnalysisImage(item?: Analysis | null): string | undefined {
  return item?.image || item?.imageUrl || item?.mainImageUrl || item?.mainImage || undefined
}

function getCommerceUrl(item?: Pick<SimilarProduct, 'listingUrl' | 'productUrl' | 'amazonUrl'>): string {
  return item?.listingUrl || item?.productUrl || item?.amazonUrl || '#'
}

function compareProductAgainstCurrent(current: Analysis | null | undefined, product?: SimilarProduct) {
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

function getRecommendationBadge(
  product: SimilarProduct,
  comparison: ReturnType<typeof compareProductAgainstCurrent>,
  index: number,
  isBest: boolean,
  hasBaseline: boolean
): { label: string; className: string } {
  const rating = getNumericValue(product.rating)
  const reviews = getNumericValue(product.reviewCount)

  if (isBest) return { label: 'TOP PICK', className: 'comparison-badge comparison-badge--top' }

  if (hasBaseline) {
    if (comparison.score >= 2) return { label: 'SMART SWAP', className: 'comparison-badge comparison-badge--better' }
    if (comparison.priceDiff !== null && comparison.priceDiff < 0 && comparison.tag !== 'WORSE') {
      return { label: 'SAVES MONEY', className: 'comparison-badge comparison-badge--savings' }
    }
    if (comparison.tag === 'BETTER') return { label: 'UPGRADE', className: 'comparison-badge comparison-badge--better' }
    if (comparison.tag === 'WORSE') return { label: 'TRADEOFF', className: 'comparison-badge comparison-badge--tradeoff' }
    if (reviews !== null && reviews >= 1000) return { label: 'POPULAR', className: 'comparison-badge comparison-badge--popular' }
    return { label: 'SOLID PICK', className: 'comparison-badge comparison-badge--similar' }
  }

  if (index === 0) return { label: 'TOP PICK', className: 'comparison-badge comparison-badge--top' }
  if (rating !== null && rating >= 4.6) return { label: 'HIGHLY RATED', className: 'comparison-badge comparison-badge--better' }
  if (reviews !== null && reviews >= 1000) return { label: 'POPULAR', className: 'comparison-badge comparison-badge--popular' }
  if (getNumericValue(product.price) !== null) return { label: 'GOOD VALUE', className: 'comparison-badge comparison-badge--savings' }
  return { label: 'WORTH A LOOK', className: 'comparison-badge comparison-badge--similar' }
}

function getPriceDiffClassName(diff: number): string {
  if (diff === 0) return 'price-diff price-diff--same'
  return `price-diff ${diff < 0 ? 'price-diff--down' : 'price-diff--up'}`
}

function getRecommendationClass(rec?: Recommendation): string {
  return `recommendation-chip recommendation-chip--${(rec ?? 'COMPARE').toLowerCase()}`
}

function getCompareValueClass(winner: 'left' | 'right' | 'tie', side: 'left' | 'right'): string {
  if (winner === 'tie') return 'compare-value'
  return winner === side ? 'compare-value compare-value--winner' : 'compare-value compare-value--muted'
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function hasDisplayablePrice(product: SimilarProduct): boolean {
  return getNumericValue(product.price) !== null
}

function getFallbackProductRank(product: SimilarProduct, filter: RecommenderFilter): number {
  const title = `${product.title ?? ''} ${product.brand ?? ''}`.toLowerCase()
  const price = getNumericValue(product.price) ?? 999999
  const rating = getNumericValue(product.rating) ?? 0
  const reviews = getNumericValue(product.reviewCount) ?? 0
  const reviewScore = Math.min(reviews, 5000) / 5000
  const durableTerms = ['durable', 'sturdy', 'rugged', 'reinforced', 'waterproof', 'metal', 'steel', 'protective', 'heavy duty', 'reliable']
  const qualityTerms = ['premium', 'pro', 'professional', 'high quality', 'flagship', 'top rated', 'noise cancelling', 'certified', 'trusted']
  const durableScore = durableTerms.filter((term) => title.includes(term)).length
  const qualityScore = qualityTerms.filter((term) => title.includes(term)).length

  if (filter === 'price') return -price + rating * 1.5 + reviewScore * 4
  if (filter === 'durability') return durableScore * 8 + rating * 8 + reviewScore * 10
  if (filter === 'quality') return qualityScore * 8 + rating * 10 + reviewScore * 8
  return rating * 8 + reviewScore * 8 - price / 500
}

function sortFallbackProducts(products: SimilarProduct[], filter: RecommenderFilter): SimilarProduct[] {
  if (filter === 'price') {
    return [...products].sort((a, b) => {
      const priceA = getNumericValue(a.price) ?? 999999
      const priceB = getNumericValue(b.price) ?? 999999
      if (priceA !== priceB) return priceA - priceB
      return (getNumericValue(b.rating) ?? 0) - (getNumericValue(a.rating) ?? 0)
    })
  }
  return [...products].sort((a, b) => getFallbackProductRank(b, filter) - getFallbackProductRank(a, filter))
}

function scanRecordToProduct(record: ScanRecord): SimilarProduct | null {
  const analysis = record.analysis
  const title = analysis.title?.trim()
  if (!title) return null
  return {
    title,
    asin: analysis.asin,
    listingId: analysis.listingId,
    marketplace: analysis.marketplace,
    brand: analysis.brand ?? undefined,
    rating: analysis.rating ?? undefined,
    reviewCount: analysis.reviewCount ?? undefined,
    price: analysis.price ?? undefined,
    image: analysis.image ?? analysis.imageUrl ?? analysis.mainImageUrl ?? analysis.mainImage,
    listingUrl: analysis.listingUrl,
    productUrl: analysis.productUrl,
    amazonUrl: analysis.marketplace === 'amazon' ? analysis.productUrl ?? analysis.listingUrl : undefined,
  }
}

function getProductMarketplace(product: SimilarProduct): RecommenderMarketplace {
  if (product.marketplace === 'amazon' || product.marketplace === 'ebay') return product.marketplace
  const url = `${product.listingUrl ?? ''} ${product.productUrl ?? ''} ${product.amazonUrl ?? ''}`.toLowerCase()
  if (url.includes('ebay.')) return 'ebay'
  if (url.includes('amazon.') || url.includes('/dp/')) return 'amazon'
  return 'all'
}

function productMatchesMarketplace(product: SimilarProduct, marketplace: RecommenderMarketplace): boolean {
  return marketplace === 'all' || getProductMarketplace(product) === marketplace
}

const RECOMMENDATION_TITLE_STOPWORDS = new Set([
  'and', 'with', 'for', 'the', 'new', 'from', 'pack', 'black', 'white', 'blue',
  'red', 'green', 'gray', 'grey', 'size', 'large', 'small', 'medium', 'inch',
  'inches', 'oz', 'ounce', 'ounces', 'men', 'mens', 'women', 'womens', '2024',
  '2025', '2026',
])

function getRecommendationTitleTokens(value?: string): Set<string> {
  const words = String(value ?? '').toLowerCase().match(/[a-z0-9]+/g) ?? []
  return new Set(words.filter((word) => word.length > 2 && !RECOMMENDATION_TITLE_STOPWORDS.has(word)))
}

function getRecommendationIdentityKeys(product: SimilarProduct): string[] {
  const rawKeys = [
    product.listingId,
    product.asin,
    product.listingUrl,
    product.productUrl,
    product.amazonUrl,
  ].map((value) => String(value ?? '').trim().toLowerCase()).filter(Boolean)
  const titleTokens = [...getRecommendationTitleTokens(product.title)].sort().slice(0, 12)
  return titleTokens.length ? [...rawKeys, `title:${titleTokens.join(' ')}`] : rawKeys
}

function productLooksLikeScannedItem(product: SimilarProduct, scannedProducts: SimilarProduct[]): boolean {
  const productKeys = new Set(getRecommendationIdentityKeys(product))
  const productTokens = getRecommendationTitleTokens(product.title)

  return scannedProducts.some((scanned) => {
    const scannedKeys = getRecommendationIdentityKeys(scanned)
    if (scannedKeys.some((key) => productKeys.has(key))) return true

    const scannedTokens = getRecommendationTitleTokens(scanned.title)
    if (productTokens.size < 4 || scannedTokens.size < 4) return false
    const overlap = [...productTokens].filter((token) => scannedTokens.has(token)).length
    const union = new Set([...productTokens, ...scannedTokens]).size
    return overlap / Math.max(1, union) >= 0.88
  })
}

function diversifyRecommendationProducts(
  products: SimilarProduct[],
  history: ScanRecord[],
  filter: RecommenderFilter,
  marketplace: RecommenderMarketplace,
  limit = 5,
): SimilarProduct[] {
  const scannedProducts = history.map(scanRecordToProduct).filter((product): product is SimilarProduct => Boolean(product))
  const sortedProducts = sortFallbackProducts(
    products.filter((product) => productMatchesMarketplace(product, marketplace) && hasDisplayablePrice(product)),
    filter,
  )
  const selected: SimilarProduct[] = []
  const deferred: SimilarProduct[] = []
  const seen = new Set<string>()
  const brandCounts = new Map<string, number>()
  const marketplaceCounts = new Map<string, number>()

  for (const product of sortedProducts) {
    if (productLooksLikeScannedItem(product, scannedProducts)) continue
    const keys = getRecommendationIdentityKeys(product)
    const dedupeKey = keys[0] ?? product.title ?? `${product.brand ?? 'unknown'}-${product.price ?? 'unknown'}`
    if (seen.has(dedupeKey)) continue
    keys.forEach((key) => seen.add(key))
    seen.add(dedupeKey)

    const brand = String(product.brand ?? '').trim().toLowerCase()
    const source = getProductMarketplace(product)
    const brandLimitReached = Boolean(brand) && (brandCounts.get(brand) ?? 0) >= 1
    const marketplaceLimitReached = marketplace === 'all' && source !== 'all' && (marketplaceCounts.get(source) ?? 0) >= 3
    const target = brandLimitReached || marketplaceLimitReached ? deferred : selected
    target.push(product)
    if (!brandLimitReached && brand) brandCounts.set(brand, (brandCounts.get(brand) ?? 0) + 1)
    if (!marketplaceLimitReached && source !== 'all') marketplaceCounts.set(source, (marketplaceCounts.get(source) ?? 0) + 1)
    if (selected.length >= limit) break
  }

  return [...selected, ...deferred].slice(0, limit)
}

function getHistoryRecommendationFallback(
  history: ScanRecord[],
  filter: RecommenderFilter,
  marketplace: RecommenderMarketplace,
): SimilarProduct[] {
  const seen = new Set<string>()
  const candidates: { product: SimilarProduct; score: number }[] = []
  const scannedProducts = history.map(scanRecordToProduct).filter((product): product is SimilarProduct => Boolean(product))

  for (const [recordIndex, record] of history.entries()) {
    const recencyWeight = Math.max(0, 10 - recordIndex) * 14
    const sourceProducts = record.analysis.similarProducts ?? []

    for (const [productIndex, product] of sourceProducts.entries()) {
      const key = product.listingId ?? product.asin ?? product.listingUrl ?? product.productUrl ?? product.title
      if (!productMatchesMarketplace(product, marketplace)) continue
      if (!hasDisplayablePrice(product)) continue
      if (productLooksLikeScannedItem(product, scannedProducts)) continue
      if (!key || seen.has(key)) continue
      seen.add(key)
      const nearbyAlternativeBonus = Math.max(0, 4 - productIndex) * 3
      candidates.push({
        product,
        score: getFallbackProductRank(product, filter) + recencyWeight + nearbyAlternativeBonus,
      })
    }
  }

  return diversifyRecommendationProducts(candidates
    .sort((a, b) => b.score - a.score)
    .map((candidate) => candidate.product), history, filter, marketplace)
}

function getPersonalizedRecommendationReasons(analysis: Analysis | null | undefined, product: SimilarProduct): string[] {
  const reasons: string[] = []
  const comparison = compareProductAgainstCurrent(analysis, product)
  const rating = getNumericValue(product.rating)
  const reviews = getNumericValue(product.reviewCount)

  if (analysis && comparison.priceDiff !== null) {
    if (comparison.priceDiff < 0) reasons.push(`${formatPriceDifference(comparison.priceDiff)} vs scan`)
    else if (comparison.priceDiff === 0) reasons.push('Matches scan price')
  }
  if (rating !== null && rating >= 4.6) reasons.push('Strong rating')
  if (reviews !== null && reviews >= 1000) reasons.push('Review depth')
  if (product.marketplace) reasons.push(product.marketplace === 'ebay' ? 'eBay option' : 'Amazon option')

  return reasons.slice(0, 3)
}

function formatShortDate(date: string): string {
  const parsed = new Date(date)
  if (Number.isNaN(parsed.getTime())) return date
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatChartPrice(value?: number): string {
  return typeof value === 'number' && Number.isFinite(value) ? `$${value.toFixed(2)}` : '--'
}

function getDistinctPriceCallouts(callouts: string[], insights: PriceInsight[]): string[] {
  const seen = new Set<string>()
  const normalized = [...callouts, ...insights.map((insight) => insight.label)]
    .map((callout) => String(callout || '').trim())
    .filter(Boolean)

  return normalized.filter((callout) => {
    const key = callout
      .toLowerCase()
      .replace(/\$\d+(?:\.\d{1,2})?/g, '$')
      .replace(/\b\d+(?:\.\d+)?\b/g, '#')
      .replace(/\s+/g, ' ')
      .trim()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, 4)
}

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

function ProductImage({
  src,
  alt,
  className = 'similar-card-image',
}: {
  src?: string | null
  alt: string
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  const imageSrc = typeof src === 'string' ? src.trim() : ''

  useEffect(() => {
    setFailed(false)
  }, [imageSrc])

  if (!imageSrc || failed) {
    return <ProductImagePlaceholder className={className} />
  }

  return (
    <img
      src={imageSrc}
      alt={alt}
      className={className}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
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
  headerLeading,
  headerTitleSuffix,
  headerActions,
  collapsedSummary,
}: {
  title: string
  children: React.ReactNode
  collapsible?: boolean
  defaultOpen?: boolean
  className?: string
  headerLeading?: React.ReactNode
  headerTitleSuffix?: React.ReactNode
  headerActions?: React.ReactNode
  collapsedSummary?: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className={`section-card ${className} ${open || !collapsible ? 'section-card--open' : 'section-card--closed'} ${collapsedSummary ? 'section-card--with-summary' : ''}`}>
      <div className="section-card-header">
        <div className="section-card-title-row">
          {headerLeading}
          <h3>{title}</h3>
          {headerTitleSuffix}
        </div>
        <div className="section-card-actions">
          {headerActions}
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
      </div>
      {collapsible && !open && collapsedSummary && (
        <div className="section-collapsed-summary">
          {collapsedSummary}
        </div>
      )}
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
  const [open, setOpen] = useState(true)

  return (
    <section className={`section-card verdict-card results-animate ${open ? 'section-card--open' : 'section-card--closed'}`}>
      <div className="verdict-card-header">
        <h3 className="verdict-card-title">AI Analysis</h3>
        <button
          type="button"
          className="collapse-icon-btn"
          onClick={() => setOpen((prev) => !prev)}
          aria-label={open ? 'Collapse AI Analysis' : 'Expand AI Analysis'}
          title={open ? 'Collapse' : 'Expand'}
        >
          <span className={`collapse-chevron ${open ? 'collapse-chevron--open' : ''}`} />
        </button>
      </div>
      <div className={`section-content ${open ? 'open' : ''}`}>
        <div className="section-content-inner">
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
        </div>
      </div>
    </section>
  )
}

// ─── Product Recommendation Scroller ─────────────────────────────────────────

export function ProductRecommendationScroller({ analysis, products }: { analysis?: Analysis | null; products: SimilarProduct[] }) {
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
    const frame = window.requestAnimationFrame(updateScrollState)
    const timeout = window.setTimeout(updateScrollState, 150)
    return () => {
      el.removeEventListener('scroll', updateScrollState)
      window.removeEventListener('resize', updateScrollState)
      ro.disconnect()
      window.cancelAnimationFrame(frame)
      window.clearTimeout(timeout)
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

  const bestIndex = analysis ? getBestAlternativeIndex(analysis, products) : -1

  return (
    <div className="similar-scroll-shell">
      {canScrollLeft && (
        <button type="button" className="similar-scroll-arrow similar-scroll-arrow--left" aria-label="Scroll left" onClick={() => scrollByCard('left')}>
          <span />
        </button>
      )}
      <div className="similar-scroll" ref={scrollRef}>
        {products.map((product, i) => {
          const comparison = compareProductAgainstCurrent(analysis, product)
          const isBest = i === bestIndex
          const badge = getRecommendationBadge(product, comparison, i, isBest, Boolean(analysis))
          const brandLabel = product.brand || (product.marketplace === 'ebay' ? 'eBay listing' : 'Unknown brand')
          const hasRating = product.rating !== null && product.rating !== undefined && product.rating !== ''
          const reviewText = product.reviewCount ? ` · ${product.reviewCount.toLocaleString()} reviews` : ''
          const marketplaceLabel = product.marketplace === 'ebay' ? 'eBay listing' : 'Marketplace listing'
          const reasons = getPersonalizedRecommendationReasons(analysis, product)
          return (
            <a
              key={product.listingId ?? product.asin ?? i}
              href={getCommerceUrl(product)}
              target="_blank"
              rel="noreferrer"
              className={`similar-card ${isBest ? 'similar-card--best' : ''}`}
              onClick={(e) => {
                const url = getCommerceUrl(product)
                if (url !== '#' && window.electronAPI?.openExternal) {
                  e.preventDefault()
                  window.electronAPI.openExternal(url)
                }
              }}
            >
              <div className="similar-card-top">
                <div className="similar-card-badges">
                  <span className={badge.className}>{badge.label}</span>
                </div>
                {product.isPrime && <span className="prime-badge">Prime</span>}
              </div>
              <ProductImage src={product.image} alt={product.title ?? 'Product'} />
              <p className="similar-card-title">{product.title ?? 'Untitled Product'}</p>
              <p className="similar-card-brand">{brandLabel}</p>
              <div className="similar-card-price-row">
                <p className="similar-card-price">{product.price ?? 'No price'}</p>
                {analysis && comparison.priceDiff !== null && (
                  <span className={getPriceDiffClassName(comparison.priceDiff)}>
                    {formatPriceDifference(comparison.priceDiff)}
                  </span>
                )}
              </div>
              <p className="similar-card-rating">
                {hasRating ? `Rating ${product.rating}${reviewText}` : marketplaceLabel}
              </p>
              {reasons.length > 0 && (
                <div className="similar-card-reasons" aria-label="Why Nectar recommended this">
                  {reasons.map((reason) => (
                    <span key={reason}>{reason}</span>
                  ))}
                </div>
              )}
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

function SmartRecommendationsSection({
  analysis,
  products,
  filter,
  marketplace,
  prompt,
  imageDataUrl,
  imageName,
  isLoading,
  isFading,
  hasMemory,
  message,
  defaultOpen,
  onFilterChange,
  onMarketplaceChange,
  onPromptChange,
  onImageUpload,
  onClearImage,
  onRefresh,
  onSubmit,
}: {
  analysis?: Analysis | null
  products: SimilarProduct[]
  filter: RecommenderFilter
  marketplace: RecommenderMarketplace
  prompt: string
  imageDataUrl: string
  imageName: string
  isLoading: boolean
  isFading: boolean
  hasMemory: boolean
  message: string
  defaultOpen: boolean
  onFilterChange: (filter: RecommenderFilter) => void
  onMarketplaceChange: (marketplace: RecommenderMarketplace) => void
  onPromptChange: (prompt: string) => void
  onImageUpload: (file: File | null) => void
  onClearImage: () => void
  onRefresh: () => void
  onSubmit: () => void
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const filterMenuRef = useRef<HTMLDivElement | null>(null)
  const marketplaceMenuRef = useRef<HTMLDivElement | null>(null)
  const [filterOpen, setFilterOpen] = useState(false)
  const [marketplaceOpen, setMarketplaceOpen] = useState(false)

  useEffect(() => {
    if (!filterOpen && !marketplaceOpen) return
    const closeOnOutsideClick = (event: MouseEvent) => {
      const target = event.target as Node
      if (!filterMenuRef.current?.contains(target)) {
        setFilterOpen(false)
      }
      if (!marketplaceMenuRef.current?.contains(target)) setMarketplaceOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [filterOpen, marketplaceOpen])

  const handlePromptPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const imageItem = Array.from(event.clipboardData.items).find((item) => item.type.startsWith('image/'))
    if (!imageItem) return
    const file = imageItem.getAsFile()
    if (!file) return
    event.preventDefault()
    onImageUpload(file)
  }

  const marketplaceLabel = marketplace === 'all' ? 'All marketplaces' : marketplace === 'amazon' ? 'Amazon' : 'eBay'
  const summaryText = isLoading
    ? 'Refreshing picks'
    : products.length > 0
      ? `${products.length} ${products.length === 1 ? 'pick' : 'picks'} by ${filter}`
      : hasMemory
        ? 'Ready to refine saved scans'
        : 'Scan a product to see recommendations'

  return (
    <SectionCard
      title="Recommended for You"
      collapsible
      defaultOpen={defaultOpen}
      className="section-card--recommendations"
      headerTitleSuffix={<span className="recommendation-title-star" aria-hidden="true" />}
      collapsedSummary={(
        <div className="recommendation-summary">
          {products.length > 0 && (
            <div className="recommendation-summary-thumbs" aria-hidden="true">
              {products.slice(0, 3).map((product, index) => (
                <ProductImage
                  key={product.listingId ?? product.asin ?? index}
                  src={product.image}
                  alt=""
                  className="recommendation-summary-thumb"
                />
              ))}
            </div>
          )}
          <div className="recommendation-summary-copy">
            <strong>{summaryText}</strong>
            <span>{marketplaceLabel}</span>
          </div>
        </div>
      )}
      headerActions={(
        <div className="recommendation-filter-control" ref={filterMenuRef}>
          <button
            type="button"
            className="recommendation-filter-main"
            onClick={() => {
              setMarketplaceOpen(false)
              setFilterOpen((prev) => !prev)
            }}
            aria-haspopup="listbox"
            aria-expanded={filterOpen}
          >
            <span className="recommendation-filter-star" aria-hidden="true" />
            <span>Filter</span>
          </button>
          <button
            type="button"
            className="recommendation-filter-chevron-btn"
            onClick={() => {
              setMarketplaceOpen(false)
              setFilterOpen((prev) => !prev)
            }}
            aria-label="Open recommendation filters"
          >
            <span className={`recommendation-filter-chevron ${filterOpen ? 'recommendation-filter-chevron--open' : ''}`} />
          </button>
          {filterOpen && (
            <div className="recommendation-filter-menu" role="listbox" aria-label="Recommendation filters">
              {RECOMMENDER_FILTERS.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`recommendation-filter-option ${filter === option ? 'recommendation-filter-option--selected' : ''}`}
                  onClick={() => {
                    onFilterChange(option)
                    setFilterOpen(false)
                  }}
                  role="option"
                  aria-selected={filter === option}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    >
      <div className={`recommendation-carousel-wrap ${isFading ? 'recommendation-carousel-wrap--fading' : ''}`}>
        {isLoading ? (
          <div className="recommendation-loading">
            <SkeletonLine width="160px" height={110} />
            <SkeletonLine width="160px" height={110} />
          </div>
        ) : products.length > 0 ? (
          <ProductRecommendationScroller analysis={analysis} products={products} />
        ) : message ? (
          <div className="recommendation-empty recommendation-empty--blocked">
            {message}
          </div>
        ) : (
          <div className="recommendation-empty">
            {hasMemory ? 'Refine your search to refresh recommendations.' : 'start scanning to get recommendations!'}
          </div>
        )}
      </div>

      <div className="recommendation-refine">
        {message && products.length > 0 && (
          <p className="recommendation-inline-message">{message}</p>
        )}
        {imageDataUrl && (
          <div className="recommendation-image-preview">
            <img src={imageDataUrl} alt="" className="recommendation-image-preview-thumb" />
            <span className="recommendation-image-preview-name">{imageName || 'Reference image'}</span>
            <button
              type="button"
              className="recommendation-image-preview-remove"
              onClick={onClearImage}
              title="Remove image"
              aria-label="Remove uploaded image"
            >
              x
            </button>
          </div>
        )}
        <textarea
          className="recommendation-prompt"
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          onPaste={handlePromptPaste}
          placeholder={imageName ? 'Add details for this image...' : 'Refine your product selection...'}
          rows={2}
        />
        <div className="recommendation-refine-actions">
          <div className="recommendation-refine-left">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="recommendation-file-input"
              onChange={(e) => onImageUpload(e.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              className={`recommendation-image-btn ${imageName ? 'recommendation-image-btn--active' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              title={imageName ? `Using ${imageName}` : 'Upload reference photo'}
              aria-label="Upload reference photo"
            >
              <svg className="recommendation-image-icon" viewBox="0 0 24 24" aria-hidden="true">
                <rect x="4" y="5" width="16" height="16" rx="2.5" />
                <circle cx="9" cy="10" r="1.6" />
                <path d="M6.5 18.5 11 14l3 3 1.8-1.8 2.7 3.3" />
              </svg>
            </button>
            <div className="recommendation-marketplace-control" ref={marketplaceMenuRef}>
              <button
                type="button"
                className="recommendation-marketplace-main"
                onClick={() => {
                  setFilterOpen(false)
                  setMarketplaceOpen((prev) => !prev)
                }}
                aria-haspopup="listbox"
                aria-expanded={marketplaceOpen}
              >
                Marketplace
              </button>
              <button
                type="button"
                className="recommendation-marketplace-chevron-btn"
                onClick={() => {
                  setFilterOpen(false)
                  setMarketplaceOpen((prev) => !prev)
                }}
                aria-label="Open recommendation marketplaces"
              >
                <span className={`recommendation-marketplace-chevron ${marketplaceOpen ? 'recommendation-marketplace-chevron--open' : ''}`} />
              </button>
              {marketplaceOpen && (
                <div className="recommendation-marketplace-menu" role="listbox" aria-label="Recommendation marketplace">
                  {RECOMMENDER_MARKETPLACES.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={`recommendation-marketplace-option ${marketplace === option ? 'recommendation-marketplace-option--selected' : ''}`}
                      onClick={() => {
                        onMarketplaceChange(option)
                        setMarketplaceOpen(false)
                      }}
                      role="option"
                      aria-selected={marketplace === option}
                    >
                      {option === 'all' ? 'All' : option === 'amazon' ? 'Amazon' : 'eBay'}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          <button
            type="button"
            className="recommendation-refresh-btn"
            onClick={onRefresh}
            disabled={isLoading || (!hasMemory && !prompt.trim() && !imageName)}
            title="Refresh recommendations from scan history"
            aria-label="Refresh recommendations"
          >
            {'\u21bb'}
          </button>
          <button
            type="button"
            className="recommendation-send-btn"
            onClick={onSubmit}
            disabled={isLoading || (!prompt.trim() && !imageName && !hasMemory)}
            title="Send refinement"
            aria-label="Send refinement"
          />
        </div>
      </div>
    </SectionCard>
  )
}

// ─── Scan History Section ─────────────────────────────────────────────────────

function DashboardSidebar({
  activeTab,
  onTabChange,
}: {
  activeTab: DashboardTab
  onTabChange: (tab: DashboardTab) => void
}) {
  const tabs: { id: DashboardTab; label: string }[] = [
    { id: 'home', label: 'Home' },
    { id: 'trends', label: 'Price History' },
  ]

  return (
    <aside className="dashboard-sidebar" aria-label="Dashboard tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`dashboard-tab-btn dashboard-tab-btn--${tab.id} ${activeTab === tab.id ? 'dashboard-tab-btn--active' : ''}`}
          onClick={() => onTabChange(tab.id)}
          title={tab.label}
          aria-label={tab.label}
          aria-current={activeTab === tab.id ? 'page' : undefined}
        >
          <span>{tab.label}</span>
        </button>
      ))}
    </aside>
  )
}

function MiniPriceChart({ data }: { data: PriceIntelligence }) {
  const width = 760
  const height = 318
  const padding = { top: 38, right: 42, bottom: 74, left: 64 }
  const points = data.points.filter((point) => Number.isFinite(point.price))
  const prices = points.map((point) => point.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = Math.max(1, max - min)
  const xFor = (index: number) => padding.left + (index / Math.max(1, points.length - 1)) * (width - padding.left - padding.right)
  const yFor = (price: number) => padding.top + ((max - price) / range) * (height - padding.top - padding.bottom)
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(2)} ${yFor(point.price).toFixed(2)}`).join(' ')
  const annotationPriority = ['high', 'low', 'drop-watch', 'average', 'momentum']
  const priorityFor = (type: string) => {
    const index = annotationPriority.indexOf(type)
    return index >= 0 ? index : annotationPriority.length
  }
  const placedAnnotations: Array<PriceInsight & {
    x: number
    y: number
    labelX: number
    labelY: number
    anchor: 'start' | 'middle' | 'end'
    stemY: number
  }> = []

  data.insights
    .filter((insight) => insight.date && typeof insight.price === 'number')
    .sort((a, b) => priorityFor(a.type) - priorityFor(b.type))
    .forEach((insight) => {
      const index = points.findIndex((point) => point.date === insight.date)
      if (index < 0 || typeof insight.price !== 'number') return
      const x = xFor(index)
      const y = yFor(insight.price)
      const tooClose = placedAnnotations.some((placed) => (
        Math.abs(placed.x - x) < 118 && Math.abs(placed.y - y) < 58
      ))
      if (tooClose || placedAnnotations.length >= 3) return

      const isRightEdge = x > width - 170
      const isLeftEdge = x < padding.left + 120
      const isBottom = y > height - padding.bottom - 34
      const labelX = isRightEdge ? x - 12 : isLeftEdge ? x + 16 : x
      const labelY = isBottom ? y - 44 : Math.max(18, y - 26)
      placedAnnotations.push({
        ...insight,
        x,
        y,
        labelX,
        labelY,
        anchor: isRightEdge ? 'end' : isLeftEdge ? 'start' : 'middle',
        stemY: isBottom ? y - 14 : labelY + 8,
      })
    })

  return (
    <div className="price-chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} className="price-chart" role="img" aria-label="Price trend chart">
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} className="price-chart-axis" />
        <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} className="price-chart-axis" />
        {[0, 0.5, 1].map((step) => {
          const y = padding.top + step * (height - padding.top - padding.bottom)
          const value = max - step * range
          return (
            <g key={step}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} className="price-chart-grid" />
              <text x={padding.left - 9} y={y + 4} textAnchor="end" className="price-chart-label">{formatChartPrice(value)}</text>
            </g>
          )
        })}
        <path d={path} className="price-chart-line" />
        {points.map((point, index) => (
          <circle key={`${point.date}-${index}`} cx={xFor(index)} cy={yFor(point.price)} r={index === points.length - 1 ? 5 : 2.2} className="price-chart-dot" />
        ))}
        {placedAnnotations.map((insight) => {
          return (
            <g key={`${insight.type}-${insight.date}`} className="price-chart-annotation">
              <line x1={insight.x} y1={insight.y - 8} x2={insight.x} y2={insight.stemY} />
              <circle cx={insight.x} cy={insight.y} r={5.5} />
              <text x={insight.labelX} y={insight.labelY} textAnchor={insight.anchor}>{insight.label}</text>
            </g>
          )
        })}
        {points[0] && <text x={padding.left} y={height - 28} className="price-chart-date-label">{formatShortDate(points[0].date)}</text>}
        {points[points.length - 1] && <text x={width - padding.right} y={height - 28} textAnchor="end" className="price-chart-date-label">{formatShortDate(points[points.length - 1].date)}</text>}
      </svg>
    </div>
  )
}

function PriceIntelligencePanel({
  scanHistory,
  selectedScanId,
  isLoading,
  onSelectScan,
  onGenerate,
}: {
  scanHistory: ScanRecord[]
  selectedScanId: string
  isLoading: boolean
  onSelectScan: (id: string) => void
  onGenerate: (record: ScanRecord) => void
}) {
  const selectedScan = scanHistory.find((record) => record.id === selectedScanId) ?? scanHistory[0]
  const intelligence = selectedScan?.priceIntelligence
  const trendPrices = intelligence?.points.map((point) => point.price).filter((price) => Number.isFinite(price)) ?? []
  const firstTrendPrice = trendPrices[0]
  const currentTrendPrice = trendPrices[trendPrices.length - 1]
  const trendLow = trendPrices.length ? Math.min(...trendPrices) : null
  const trendHigh = trendPrices.length ? Math.max(...trendPrices) : null
  const trendAverage = trendPrices.length ? trendPrices.reduce((sum, price) => sum + price, 0) / trendPrices.length : null
  const trendMove = firstTrendPrice != null && currentTrendPrice != null ? currentTrendPrice - firstTrendPrice : null
  const selectedAnalysis = selectedScan?.analysis
  const historyMetrics = [
    { label: 'Current', value: selectedAnalysis?.price ?? formatChartPrice(currentTrendPrice) },
    { label: 'Lowest', value: formatChartPrice(trendLow ?? undefined) },
    { label: 'Highest', value: formatChartPrice(trendHigh ?? undefined) },
    { label: 'Average', value: formatChartPrice(trendAverage ?? undefined) },
    { label: '30-day move', value: trendMove == null ? '--' : `${trendMove >= 0 ? '+' : '-'}$${Math.abs(trendMove).toFixed(2)}` },
    { label: 'Trust score', value: selectedAnalysis?.overallScore != null ? `${selectedAnalysis.overallScore}/100` : '--' },
    { label: 'Rating', value: selectedAnalysis?.rating != null ? `${selectedAnalysis.rating}/5` : '--' },
    { label: 'Reviews', value: selectedAnalysis?.reviewCount != null ? selectedAnalysis.reviewCount.toLocaleString() : '--' },
  ]

  useEffect(() => {
    if (selectedScan && !selectedScan.priceIntelligence && !isLoading) onGenerate(selectedScan)
  }, [selectedScan?.id])

  return (
    <section className="dashboard-tab-panel price-panel">
      <div className="price-panel-header">
        <div>
          <h2>Trend / Price Intelligence</h2>
          <p>Select a scanned product to inspect estimated trajectory and AI price timing.</p>
        </div>
        {selectedScan && (
          <button type="button" className="tool-clear-btn" onClick={() => onGenerate(selectedScan)} disabled={isLoading}>
            Refresh
          </button>
        )}
      </div>
      {scanHistory.length === 0 ? (
        <div className="tool-empty price-empty">
          <strong>No scans yet.</strong>
          <span>Scan a product to unlock trend intelligence.</span>
        </div>
      ) : (
        <div className="price-panel-grid">
          <div className="price-product-list" role="listbox" aria-label="Products with price charts">
            {scanHistory.map((record) => (
              <button
                key={record.id}
                type="button"
                className={`price-product-option ${record.id === selectedScan?.id ? 'price-product-option--active' : ''}`}
                onClick={() => onSelectScan(record.id)}
                role="option"
                aria-selected={record.id === selectedScan?.id}
              >
                <span>{record.analysis.title ?? 'Untitled product'}</span>
                <strong>{record.analysis.price ?? 'No price'}</strong>
              </button>
            ))}
          </div>
          <div className="price-detail">
            <div className="price-current-card">
              <div>
                <span>Current scan</span>
                <h3>{selectedScan?.analysis.title ?? 'Select a product'}</h3>
              </div>
              <strong>{selectedScan?.analysis.price ?? '--'}</strong>
            </div>
            <div className="price-metric-grid" aria-label="Price history metrics">
              {historyMetrics.map((metric) => (
                <div key={metric.label} className="price-metric-card">
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              ))}
            </div>
            {isLoading && !intelligence ? (
              <div className="price-loading">
                <SkeletonLine height={220} />
                <SkeletonLine width="70%" />
              </div>
            ) : intelligence ? (
              <>
                <MiniPriceChart data={intelligence} />
                <div className="price-insight-row">
                  <div className={`price-drop-call ${intelligence.likelyToDrop ? 'price-drop-call--wait' : 'price-drop-call--buy'}`}>
                    <span>{intelligence.likelyToDrop ? 'Likely to drop' : 'Likely stable'}</span>
                    <strong>{Math.round((intelligence.confidence || 0) * 100)}% confidence</strong>
                  </div>
                  <p>{intelligence.narrative}</p>
                </div>
                <div className="price-callouts">
                  {getDistinctPriceCallouts(intelligence.callouts, intelligence.insights).map((callout) => (
                    <span key={callout}>{callout}</span>
                  ))}
                </div>
              </>
            ) : (
              <div className="tool-empty price-empty">
                <strong>Trend intelligence is ready to generate.</strong>
                <span>Select refresh to build a chart for this product.</span>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

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
  const latestScan = scanHistory[0]
  return (
    <SectionCard
      title="Scan History"
      collapsible
      defaultOpen={false}
      className="section-card--history"
      collapsedSummary={(
        <div className="history-summary">
          <div>
            <strong>
              {scanHistory.length > 0
                ? `${scanHistory.length} saved ${scanHistory.length === 1 ? 'scan' : 'scans'}`
                : 'No saved scans'}
            </strong>
            <span>
              {latestScan?.analysis.title ?? 'Completed scans will appear here.'}
            </span>
          </div>
          {latestScan && (
            <span className="history-score">{latestScan.analysis.overallScore ?? '--'}</span>
          )}
        </div>
      )}
    >
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

  const brEbay = br as (typeof br & {
    sellerName?: string
    sellerPositivePct?: number
    sellerReviewCount?: number
    topRatedSeller?: boolean
  })

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
            {isEbay ? (
              <p><strong>Seller:</strong> {brEbay?.sellerName ?? analysis.brand ?? 'N/A'}</p>
            ) : (
              <p><strong>Brand:</strong> {analysis.brand ?? 'N/A'}</p>
            )}
            <p><strong>Price:</strong> {analysis.price ?? 'N/A'}</p>
            <p><strong>Rating:</strong> {formatProductRating(analysis, isEbay)}</p>
            <p><strong>Review Count:</strong> {formatProductReviewCount(analysis, isEbay)}</p>
            {isEbay && analysis.condition && <p><strong>Condition:</strong> {analysis.condition}</p>}
          </div>
        </SectionCard>
      </div>

      {analysis.aiAnalysis && (
        <div className="cascade-item cascade-delay-3">
          <VerdictCard ai={analysis.aiAnalysis} />
        </div>
      )}

      <div className="cascade-item cascade-delay-4">
        <SectionCard title={isEbay ? 'Seller Review Integrity' : 'Review Integrity'} collapsible className="section-card--integrity">
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
            {!isEbay && (
              <>
                <p>
                  <strong>Verified Purchase Ratio:</strong>{' '}
                  {ri?.verifiedPurchaseRatio != null
                    ? `${Math.round((ri.verifiedPurchaseRatio as number) * 100)}%`
                    : 'N/A'}
                </p>
                <p>
                  <strong>Sentiment Consistency:</strong>{' '}
                  {ri?.sentimentConsistencyRatio != null
                    ? `${Math.round((ri.sentimentConsistencyRatio as number) * 100)}%`
                    : 'N/A'}
                </p>
                <p className="keywords-label"><strong>Top Keywords:</strong></p>
                <KeywordPills keywords={ri?.commonKeywords} emptyMessage="No keywords found" />
              </>
            )}
            {isEbay && ri?.verifiedPurchaseRatio != null && (
              <p>
                <strong>Verified Purchase Ratio:</strong>{' '}
                {`${Math.round((ri.verifiedPurchaseRatio as number) * 100)}%`}
              </p>
            )}
            {isEbay && ri?.sentimentConsistencyRatio != null && (
              <p>
                <strong>Sentiment Consistency:</strong>{' '}
                {`${Math.round((ri.sentimentConsistencyRatio as number) * 100)}%`}
              </p>
            )}
          </div>
          <ScoreExplainer metric={isEbay ? 'seller_review_integrity' : 'review_integrity'} analysis={analysis} />
        </SectionCard>
      </div>

      <div className="cascade-item cascade-delay-5">
        <SectionCard title={isEbay ? 'Seller Reputation' : 'Brand Reputation'} collapsible className="section-card--brand">
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
                <p><strong>Seller:</strong> {brEbay?.sellerName ?? 'N/A'}</p>
                <p><strong>Feedback:</strong> {br?.label ?? 'N/A'}</p>
                {brEbay?.sellerPositivePct != null && (
                  <p><strong>Positive Feedback:</strong> {`${brEbay.sellerPositivePct}%`}</p>
                )}
                {brEbay?.sellerReviewCount != null && (
                  <p><strong>Feedback Count:</strong> {brEbay.sellerReviewCount.toLocaleString()}</p>
                )}
                {brEbay?.topRatedSeller && (
                  <p><strong>Status:</strong>{' '}
                    <span style={{ color: '#15803d', fontWeight: 'bold' }}>⭐ Top Rated Seller</span>
                  </p>
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
                <InsightPill key={insight.topic} insight={insight} />
              ))}
            </div>
          ) : (
            <p className="body-text muted">{isEbay ? 'No seller insights yet.' : 'No brand insights yet.'}</p>
          )}
          {!isEbay && (
            <>
              <p className="keywords-label"><strong>Top Keywords:</strong></p>
              <KeywordPills keywords={br?.commonKeywords} emptyMessage="No keywords found" />
            </>
          )}
          <ScoreExplainer metric={isEbay ? 'seller_reputation' : 'brand_reputation'} analysis={analysis} />
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
    <AutoSizingWindow>
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
                  <ProductImage src={image} alt={a.title ?? 'Product'} className="compare-product-image" />
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
    </AutoSizingWindow>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [scanUrl, setScanUrl] = useState('')
  const detectedMarketplace = /amazon\./i.test(scanUrl) ? 'amazon' : /ebay\./i.test(scanUrl) ? 'ebay' : null
  const [isAutoDetected, setIsAutoDetected] = useState(false)
  const [backendStatus, setBackendStatus] = useState('Ready to scan')
  const [analysis, setAnalysis] = useState<Analysis | null>(DEV_PREVIEW ? mockAnalysis : null)
  const [view, setView] = useState<'home' | 'compare'>('home')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasScanned, setHasScanned] = useState<boolean>(DEV_PREVIEW)
  const [isExitingResults, setIsExitingResults] = useState(false)
  const [cancelAvailable, setCancelAvailable] = useState(false)
  const [windowControlsVisible, setWindowControlsVisible] = useState(false)
  const [isExpanded, setIsExpanded] = useState(() => (
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('dashboard')
  ))
  const [dashboardTab, setDashboardTab] = useState<DashboardTab>('home')

  const handleToggleExpand = async () => {
    if (!window.electronAPI?.toggleExpand) {
      setIsExpanded((prev) => !prev)
      return
    }
    const next = await window.electronAPI?.toggleExpand?.()
    if (next !== undefined) setIsExpanded(next)
  }

  const [currentSavedScan, setCurrentSavedScan] = useState<ScanRecord | null>(null)
  const [previousSavedScan, setPreviousSavedScan] = useState<ScanRecord | null>(null)
  const [scanHistory, setScanHistory] = useState<ScanRecord[]>([])
  const [deletingScanIds, setDeletingScanIds] = useState<string[]>([])
  const [isClearingHistory, setIsClearingHistory] = useState(false)
  const [selectedCompareIds, setSelectedCompareIds] = useState<string[]>([])
  const [compareRecords, setCompareRecords] = useState<[ScanRecord, ScanRecord] | null>(null)
  const [recommendationFilter, setRecommendationFilter] = useState<RecommenderFilter>('overall')
  const [recommendationMarketplace, setRecommendationMarketplace] = useState<RecommenderMarketplace>('all')
  const [recommendationPrompt, setRecommendationPrompt] = useState('')
  const [recommendationImageDataUrl, setRecommendationImageDataUrl] = useState('')
  const [recommendationImageName, setRecommendationImageName] = useState('')
  const [recommendedProducts, setRecommendedProducts] = useState<SimilarProduct[]>([])
  const [recommendationMessage, setRecommendationMessage] = useState('')
  const [recommendationsLoading, setRecommendationsLoading] = useState(false)
  const [recommendationsFading, setRecommendationsFading] = useState(false)
  const [selectedPriceScanId, setSelectedPriceScanId] = useState('')
  const [priceTrendLoadingId, setPriceTrendLoadingId] = useState('')

  const scanAbortRef = useRef<AbortController | null>(null)
  const scanIdRef = useRef<string | null>(null)
  // Holds freshly-built history during scan completion so recommendations use
  // the latest saved record before React state has settled.
  const pendingHistoryRef = useRef<ScanRecord[] | null>(null)
  const cancelTimerRef = useRef<number | null>(null)
  const scanDelayResolveRef = useRef<(() => void) | null>(null)
  const scanWasCancelledRef = useRef(false)
  const recommendationRequestIdRef = useRef(0)
  const recommendationPromptDebounceRef = useRef<number | null>(null)
  const recommendationHistoryKey = getRecommendationHistoryKey(scanHistory)

  const fetchRecommendations = async (opts?: { prompt?: string; imageDataUrl?: string; history?: ScanRecord[]; filter?: RecommenderFilter; marketplace?: RecommenderMarketplace; forceLoadingSkeleton?: boolean; skipInitialFade?: boolean }) => {
    const historyForRequest = opts?.history ?? scanHistory
    const promptForRequest = opts?.prompt ?? recommendationPrompt
    const imageForRequest = opts?.imageDataUrl ?? recommendationImageDataUrl
    const filterForRequest = opts?.filter ?? recommendationFilter
    const marketplaceForRequest = opts?.marketplace ?? recommendationMarketplace
    const fallbackProducts = getHistoryRecommendationFallback(historyForRequest, filterForRequest, marketplaceForRequest)
    const isExplicitRefinement = Boolean(opts?.forceLoadingSkeleton || promptForRequest.trim() || imageForRequest)
    const previousProducts = recommendedProducts
    const requestId = recommendationRequestIdRef.current + 1
    recommendationRequestIdRef.current = requestId

    const isLatestRecommendationRequest = () => recommendationRequestIdRef.current === requestId

    if (!historyForRequest.length && !promptForRequest.trim() && !imageForRequest) {
      setRecommendedProducts([])
      setRecommendationMessage('')
      return
    }

    let timeoutId: number | null = null

    try {
      setRecommendationsLoading(true)
      setRecommendationMessage('')

      if (isExplicitRefinement) {
        // Fade out existing products first if any are showing
        if (previousProducts.length && !opts?.skipInitialFade) {
          setRecommendationsFading(true)
          await new Promise((resolve) => window.setTimeout(resolve, RECOMMENDATION_FADE_MS))
          if (!isLatestRecommendationRequest()) return
        }
        // Always clear so the skeleton loader is visible during the API call.
        // previousProducts is captured in closure and restored as fallback on failure.
        setRecommendedProducts([])
        setRecommendationsFading(false)
      } else if (fallbackProducts.length) {
        // For non-refinement background refreshes, show local fallback immediately
        // while the API call runs silently in the background.
        setRecommendedProducts(fallbackProducts)
      }

      const controller = new AbortController()
      timeoutId = window.setTimeout(
        () => controller.abort(),
        isExplicitRefinement ? RECOMMENDATION_REFINEMENT_TIMEOUT_MS : RECOMMENDATION_TIMEOUT_MS
      )
      const response = await fetch(`${API_BASE}/recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Nectar-Secret': NECTAR_SECRET },
        signal: controller.signal,
        body: JSON.stringify({
          history: historyForRequest,
          filter: filterForRequest,
          marketplace: marketplaceForRequest,
          prompt: promptForRequest,
          imageDataUrl: imageForRequest,
        }),
      })
      const data: RecommendationResponse = await response.json()
      if (!isLatestRecommendationRequest()) return
      if (data.rejected) {
        setRecommendedProducts([])
        setRecommendationMessage(data.message || 'Sorry, I cannot help you with that')
        return
      }
      const apiProducts = diversifyRecommendationProducts(
        Array.isArray(data.products) ? data.products : [],
        historyForRequest,
        filterForRequest,
        marketplaceForRequest,
      )
      if (apiProducts.length) {
        setRecommendedProducts(apiProducts)
        setRecommendationMessage('')
        return
      }
      // API returned no products
      if (isExplicitRefinement) {
        setRecommendationMessage('No fresh marketplace matches found for that request. Try a broader phrase or a different marketplace.')
        setRecommendedProducts([])
        return
      }
      setRecommendedProducts(fallbackProducts)
      setRecommendationMessage('')
    } catch (err) {
      if (!isLatestRecommendationRequest()) return
      console.error(err)
      if (isExplicitRefinement) {
        setRecommendationMessage('Search timed out before finding matching products. Try again, broaden the prompt, or switch marketplaces.')
        setRecommendedProducts([])
      } else {
        setRecommendedProducts(fallbackProducts)
        setRecommendationMessage('')
      }
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId)
      if (isLatestRecommendationRequest()) {
        setRecommendationsFading(false)
        setRecommendationsLoading(false)
      }
    }
  }

  const showRecommendationSkeleton = () => {
    recommendationRequestIdRef.current += 1
    setRecommendationsLoading(true)
    setRecommendationsFading(false)
    setRecommendationMessage('')
    setRecommendedProducts([])
  }

  useEffect(() => {
    detectActiveUrl()
    loadCurrentSavedScan().then(setCurrentSavedScan)
    loadPreviousSavedScan().then(setPreviousSavedScan)
    loadScanHistory().then(setScanHistory)
    return () => {
      if (cancelTimerRef.current !== null) window.clearTimeout(cancelTimerRef.current)
      if (recommendationPromptDebounceRef.current !== null) window.clearTimeout(recommendationPromptDebounceRef.current)
      scanDelayResolveRef.current?.()
      scanAbortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!selectedPriceScanId && scanHistory[0]) setSelectedPriceScanId(scanHistory[0].id)
    if (selectedPriceScanId && !scanHistory.some((record) => record.id === selectedPriceScanId)) {
      setSelectedPriceScanId(scanHistory[0]?.id ?? '')
    }
  }, [scanHistory, selectedPriceScanId])

  useEffect(() => {
    // Use pendingHistoryRef when a fresh scan just completed so recommendations
    // do not read the previous scanHistory snapshot.
    const historyToUse = pendingHistoryRef.current ?? scanHistory
    pendingHistoryRef.current = null
    fetchRecommendations({
      history: historyToUse,
      filter: recommendationFilter,
      marketplace: recommendationMarketplace,
      forceLoadingSkeleton: historyToUse.length > 0,
      skipInitialFade: true,
    })
  }, [recommendationFilter, recommendationMarketplace, recommendationHistoryKey])

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
      setRecommendationPrompt('')
      setRecommendationImageDataUrl('')
      setRecommendationImageName('')
      setRecommendationMessage('')
      setSelectedPriceScanId(record.id)
      // FIX: store the fresh history so the useEffect picks it up correctly,
      // then let the effect fire naturally via setScanHistory (no manual fetch call,
      // no skip flag, no stale fallback assignment).
      pendingHistoryRef.current = nextHistory
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

  const handleRecommendationImageUpload = async (file: File | null) => {
    if (!file) {
      setRecommendationImageDataUrl('')
      setRecommendationImageName('')
      return
    }
    try {
      const dataUrl = await fileToDataUrl(file)
      setRecommendationImageDataUrl(dataUrl)
      setRecommendationImageName(file.name)
    } catch {
      setRecommendationImageDataUrl('')
      setRecommendationImageName('')
      setBackendStatus('Could not read the selected image')
    }
  }

  const handleRecommendationImageClear = () => {
    setRecommendationImageDataUrl('')
    setRecommendationImageName('')
  }

  const handleRecommendationFilterChange = (nextFilter: RecommenderFilter) => {
    if (nextFilter === recommendationFilter) return
    if (recommendationPromptDebounceRef.current !== null) {
      window.clearTimeout(recommendationPromptDebounceRef.current)
      recommendationPromptDebounceRef.current = null
    }
    // FIX: don't skip the effect — let it fire so there's exactly ONE fetch call.
    // Let the effect be the single fetch path for filter changes.
    showRecommendationSkeleton()
    setRecommendationFilter(nextFilter)
  }

  const handleRecommendationMarketplaceChange = (nextMarketplace: RecommenderMarketplace) => {
    if (nextMarketplace === recommendationMarketplace) return
    if (recommendationPromptDebounceRef.current !== null) {
      window.clearTimeout(recommendationPromptDebounceRef.current)
      recommendationPromptDebounceRef.current = null
    }
    // FIX: same race condition fix as handleRecommendationFilterChange.
    // Let the useEffect be the single source of truth for triggering the fetch.
    showRecommendationSkeleton()
    setRecommendationMarketplace(nextMarketplace)
  }

  const handleRecommendationPromptChange = (nextPrompt: string) => {
    setRecommendationPrompt(nextPrompt)
    if (recommendationMessage) setRecommendationMessage('')
    if (recommendationPromptDebounceRef.current !== null) {
      window.clearTimeout(recommendationPromptDebounceRef.current)
      recommendationPromptDebounceRef.current = null
    }

    const hasRecommendationInput = Boolean(scanHistory.length || nextPrompt.trim() || recommendationImageDataUrl)
    if (!hasRecommendationInput) {
      recommendationRequestIdRef.current += 1
      setRecommendationsLoading(false)
      setRecommendationsFading(false)
      setRecommendedProducts([])
    }
  }

  const handleRecommendationSubmit = () => {
    if (recommendationPromptDebounceRef.current !== null) {
      window.clearTimeout(recommendationPromptDebounceRef.current)
      recommendationPromptDebounceRef.current = null
    }
    fetchRecommendations({
      prompt: recommendationPrompt,
      history: scanHistory,
      filter: recommendationFilter,
      marketplace: recommendationMarketplace,
      forceLoadingSkeleton: true,
      skipInitialFade: true,
    })
  }

  const handleRecommendationRefresh = () => {
    if (recommendationPromptDebounceRef.current !== null) {
      window.clearTimeout(recommendationPromptDebounceRef.current)
      recommendationPromptDebounceRef.current = null
    }
    fetchRecommendations({
      history: scanHistory,
      filter: recommendationFilter,
      marketplace: recommendationMarketplace,
      forceLoadingSkeleton: true,
      skipInitialFade: true,
    })
  }

  // ── Routing ──

  if (view === 'compare' && compareRecords) {
    return <CompareView records={compareRecords} onBack={() => setView('home')} />
  }

  const handleGeneratePriceTrend = async (record: ScanRecord) => {
    if (!record || priceTrendLoadingId === record.id) return
    setPriceTrendLoadingId(record.id)
    try {
      const response = await fetch(`${API_BASE}/price-trend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Nectar-Secret': NECTAR_SECRET },
        body: JSON.stringify({ scan: record }),
      })
      const data: PriceTrendResponse = await response.json()
      if (!response.ok || !data.points?.length) return
      const priceIntelligence: PriceIntelligence = {
        points: data.points,
        insights: data.insights ?? [],
        narrative: data.narrative ?? 'Price trend intelligence is available for this scan.',
        likelyToDrop: Boolean(data.likelyToDrop),
        confidence: data.confidence ?? 0,
        callouts: data.callouts ?? [],
        generatedAt: new Date().toISOString(),
      }
      const applyTrend = (item: ScanRecord | null) => item?.id === record.id ? { ...item, priceIntelligence } : item
      const nextHistory = scanHistory.map((item) => item.id === record.id ? { ...item, priceIntelligence } : item)
      setScanHistory(nextHistory)
      setCurrentSavedScan((item) => applyTrend(item))
      setPreviousSavedScan((item) => applyTrend(item))
      await storageSet({
        [SCAN_HISTORY_KEY]: nextHistory,
        ...(currentSavedScan?.id === record.id ? { [CURRENT_SCAN_KEY]: { ...currentSavedScan, priceIntelligence } } : {}),
        ...(previousSavedScan?.id === record.id ? { [PREVIOUS_SCAN_KEY]: { ...previousSavedScan, priceIntelligence } } : {}),
      })
    } finally {
      setPriceTrendLoadingId('')
    }
  }

  const recommendationsSection = (
    <SmartRecommendationsSection
      key={`recommendations-${loading ? 'loading' : hasScanned ? 'post-scan' : 'launch'}`}
      analysis={analysis}
      products={recommendedProducts}
      filter={recommendationFilter}
      marketplace={recommendationMarketplace}
      prompt={recommendationPrompt}
      imageDataUrl={recommendationImageDataUrl}
      imageName={recommendationImageName}
      isLoading={recommendationsLoading}
      isFading={recommendationsFading}
      hasMemory={scanHistory.length > 0}
      message={recommendationMessage}
      defaultOpen={!loading && !hasScanned}
      onFilterChange={handleRecommendationFilterChange}
      onMarketplaceChange={handleRecommendationMarketplaceChange}
      onPromptChange={handleRecommendationPromptChange}
      onImageUpload={handleRecommendationImageUpload}
      onClearImage={handleRecommendationImageClear}
      onRefresh={handleRecommendationRefresh}
      onSubmit={handleRecommendationSubmit}
    />
  )

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

  const productAnalysisSection = (
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
            Sync Browser
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
        {loading ? 'Scanning...' : 'Scan Product'}
      </button>
      {loading && cancelAvailable && (
        <button type="button" className="scan-cancel-btn" onClick={handleCancelScan}>
          <span>Cancel Scan</span>
        </button>
      )}
    </SectionCard>
  )

  const homeDashboardLayout = (
    <>
      <div className="dashboard-column dashboard-column--primary">
        <div className="cascade-item cascade-delay-1">{historySection}</div>
      </div>

      {loading && (
        <div className="dashboard-column dashboard-column--results">
          <SkeletonResults />
        </div>
      )}

      {!loading && hasScanned && analysis && (
        <div className="dashboard-column dashboard-column--results">
          <ResultsView analysis={analysis} isExiting={isExitingResults} />
        </div>
      )}

      <div className="dashboard-column dashboard-column--side">
        <div className={`cascade-item ${hasScanned ? 'cascade-delay-7' : 'cascade-delay-2'}`}>
          {productAnalysisSection}
        </div>
        {!loading && (
          <div className={`cascade-item ${hasScanned ? 'cascade-delay-8' : 'cascade-delay-3 popup-fit-stop'}`}>
            {recommendationsSection}
          </div>
        )}
      </div>
    </>
  )

  const dashboardLayout = (
    <>
      {dashboardTab === 'home' && homeDashboardLayout}
      {dashboardTab === 'trends' && (
        <PriceIntelligencePanel
          scanHistory={scanHistory}
          selectedScanId={selectedPriceScanId}
          isLoading={Boolean(priceTrendLoadingId)}
          onSelectScan={setSelectedPriceScanId}
          onGenerate={handleGeneratePriceTrend}
        />
      )}
    </>
  )

  const popupLayout = (
    <>
      <div className="cascade-item cascade-delay-1">{productAnalysisSection}</div>

      {!hasScanned && (
        <>
          <div className="cascade-item cascade-delay-2 popup-fit-stop">{recommendationsSection}</div>
          <div className="cascade-item cascade-delay-3">{historySection}</div>
        </>
      )}
      {loading && <SkeletonResults />}

      {!loading && hasScanned && analysis && (
        <>
          <ResultsView analysis={analysis} isExiting={isExitingResults} />
          <div className="cascade-item cascade-delay-7">{recommendationsSection}</div>
          <div className="cascade-item cascade-delay-8">{historySection}</div>
        </>
      )}
    </>
  )

  return (
    <AutoSizingWindow>
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
        {isExpanded && <DashboardSidebar activeTab={dashboardTab} onTabChange={setDashboardTab} />}
        <div className={`window-controls ${windowControlsVisible ? 'visible' : ''}`}>
          <button className="window-control window-control-expand" onClick={handleToggleExpand} title={isExpanded ? 'Collapse' : 'Expand to dashboard'} />
          <button className="window-control window-control-minimize" onClick={() => window.electronAPI?.minimizeWindow?.()} title="Minimize" />
          <button className="window-control window-control-close" onClick={() => window.electronAPI?.closeWindow?.()} title="Close" />
        </div>
      </header>

      <div
        className={`content${isExpanded ? ' content--dashboard' : ''}${isExpanded && hasScanned && dashboardTab === 'home' ? ' content--dashboard-results' : ''}${isExpanded && dashboardTab !== 'home' ? ' content--dashboard-tool' : ''}`}
        key="home-view"
      >
        {isExpanded ? dashboardLayout : popupLayout}
      </div>
    </AutoSizingWindow>
  )
}
