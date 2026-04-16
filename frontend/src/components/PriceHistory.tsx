import PriceChart from './PriceChart'

interface Props {
  usage: number
  onBack: () => void
}

export default function PriceHistory({ usage, onBack }: Props) {
  const maxUsage = 2
  const percent = (usage / maxUsage) * 100

  return (
    <div className="screen">
      <div className="navbar">
        <div>
          <div className="logo">🍊 Nectar</div>
          <div className="subtitle">PRODUCT ANALYZER</div>
        </div>

        <button className="premium-btn" onClick={onBack}>
          ← Back
        </button>
      </div>

      <div className="usage-bar">
        <span>USAGE</span>
        <span>{usage}/{maxUsage}</span>
      </div>

      <div className="progress">
        <div
          className="progress-fill"
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="ad-banner">
        <span className="ad-label">SPONSORED</span>
        <div>Get 20% off Nectar Pro today!</div>
      </div>

      <div className="graph-box">
        <p className="section-title">PRICE HISTORY</p>
        <PriceChart />
      </div>

      <button className="alert-btn">
        🔔 SET PRICE DROP ALERT
      </button>

      <div className="modules">
        <div className="module">📋 Review Summary</div>
      </div>
    </div>
  )
}