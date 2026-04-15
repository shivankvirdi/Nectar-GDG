interface Props {
  usage: number
  onScan: () => void
}

export default function HomeScreen({ usage, onScan }: Props) {
  const maxUsage = 2
  const percent = (usage / maxUsage) * 100

  return (
    <div className="screen">
      {/* NAVBAR */}
      <div className="navbar">
        <div>
          <div className="logo">🍊 Nectar</div>
          <div className="subtitle">PRODUCT ANALYZER</div>
        </div>
        <button className="premium-btn">Go Premium</button>
      </div>

      {/* USAGE */}
      <div className="usage-bar">
        <span>USAGE</span>
        <span>{usage}/{maxUsage}</span>
      </div>

      {/* PROGRESS */}
      <div className="progress">
        <div
          className="progress-fill"
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* AD */}
      <div className="ad-banner">
        <span className="ad-label">SPONSORED</span>
        <div>Get 20% off Nectar Pro today!</div>
      </div>

      {/* BUTTON */}
      <button className="scan-btn" onClick={onScan}>
        ☐ SCAN FOR PRODUCT
      </button>

      {/* FOOTER */}
      <p className="free-notice">
        FREE VERSION: <span style={{ color: 'var(--orange)' }}>3/7</span> ANALYSIS MODULES ACTIVE
      </p>
    </div>
  )
}