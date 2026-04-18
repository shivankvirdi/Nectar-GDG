interface Props {
  onBack: () => void
}

const plans = [
  {
    name: 'FREE',
    price: '$0',
    period: '/mo',
    desc: 'For casual shoppers',
    features: [
      '50 scans per month',
      'Full product analysis',
      'Review Integrity score',
      'Brand Reputation score',
      'Similar product suggestions',
      'One product at a time',
    ],
    highlight: false,
    cta: 'Current Plan',
  },
  {
    name: 'PRO',
    price: '$59',
    period: '/mo',
    desc: 'For sellers & dropshippers',
    features: [
      '1,500 scans per month',
      'Everything in Free',
      'AI-powered pro/con analysis',
      'Deep sentiment analysis',
      'Bulk analysis (up to 50 at once)',
      'Side-by-side product comparison',
      'Search by keyword, not just URL',
    ],
    highlight: true,
    cta: 'Get Pro',
  },
  {
    name: 'BUSINESS',
    price: '$349',
    period: '/mo',
    desc: 'For retailers & agencies',
    features: [
      '20,000+ scans per month',
      'Everything in Pro',
      'Reputation trend forecasting',
      'Multi-platform analysis',
      'Demographic & geo sentiment',
      'Bulk analysis (up to 2,000)',
      'Custom white-label reports',
      'Analysis history database',
      '$0.02 per scan over limit',
    ],
    highlight: false,
    cta: 'Get Business',
  },
]

export default function PremiumScreen({ onBack }: Props) {
  return (
    <div className="screen">

      <div className="top-header">
        <div className="brand-row">
          <img src="/icons/logo.png" alt="Nectar logo" className="brand-logo" />
          <div className="brand-block">
            <h1>Nectar</h1>
            <p>SMART PRODUCT ANALYZER</p>
          </div>
        </div>
        <button className="premium-btn" onClick={onBack}>← Back</button>
      </div>

      <div style={{ textAlign: 'center', margin: '12px 16px 16px' }}>
        <p style={{ fontSize: 18, fontWeight: 800, color: 'var(--text)', letterSpacing: '0.05em' }}>
          Choose Your Plan
        </p>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
          Unlock the full power of Nectar
        </p>
      </div>

      <div style={{ padding: '0 16px 16px' }}>
        {plans.map((plan) => (
          <div
            key={plan.name}
            style={{
              background: plan.highlight ? 'var(--brand)' : 'var(--surface2)',
              border: plan.highlight ? 'none' : '1px solid var(--border)',
              borderRadius: 14,
              padding: '14px 16px',
              marginBottom: 10,
              position: 'relative',
            }}
          >
            {plan.highlight && (
              <div style={{
                position: 'absolute',
                top: -10,
                right: 14,
                background: '#fff',
                color: 'var(--brand)',
                fontSize: 9,
                fontWeight: 800,
                letterSpacing: '0.15em',
                padding: '3px 8px',
                borderRadius: 999,
              }}>
                POPULAR
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <p style={{
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: '0.2em',
                  color: plan.highlight ? '#fff' : 'var(--text-muted)',
                }}>
                  {plan.name}
                </p>
                <p style={{
                  fontSize: 10,
                  color: plan.highlight ? 'rgba(255,255,255,0.7)' : 'var(--text-muted)',
                  marginTop: 2,
                }}>
                  {plan.desc}
                </p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: 22, fontWeight: 800, color: plan.highlight ? '#fff' : 'var(--text)' }}>
                  {plan.price}
                </span>
                <span style={{ fontSize: 10, color: plan.highlight ? 'rgba(255,255,255,0.7)' : 'var(--text-muted)' }}>
                  {plan.period}
                </span>
              </div>
            </div>

            <div style={{ margin: '10px 0 12px' }}>
              {plan.features.map((f) => (
                <p key={f} style={{
                  fontSize: 11,
                  color: plan.highlight ? 'rgba(255,255,255,0.9)' : 'var(--text)',
                  marginBottom: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}>
                  <span style={{ color: plan.highlight ? '#fff' : 'var(--brand)', fontSize: 10 }}>✦</span>
                  {f}
                </p>
              ))}
            </div>

            <button style={{
              width: '100%',
              padding: '9px',
              borderRadius: 10,
              border: plan.highlight ? 'none' : '1px solid var(--brand)',
              background: plan.highlight ? 'rgba(0,0,0,0.2)' : 'transparent',
              color: plan.highlight ? '#fff' : 'var(--brand)',
              fontWeight: 700,
              fontSize: 11,
              letterSpacing: '0.1em',
              cursor: 'pointer',
              fontFamily: 'var(--font-display)',
            }}>
              {plan.cta}
            </button>
          </div>
        ))}
      </div>

    </div>
  )
}