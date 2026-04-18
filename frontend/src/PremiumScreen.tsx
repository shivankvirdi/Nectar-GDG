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
      'One product scan at a time',
    ],
    highlight: false,
    cta: 'Current Plan',
  },
  {
    name: 'PRO',
    price: '$19.99',
    period: '/mo',
    desc: 'For e-commerce & dropshippers',
    features: [
      'Everything in Free',
      '1,500 scans per month',
      'Deep sentiment analysis',
      'Bulk analysis (up to 50 at once)',
      'Side-by-side product comparison',
      'Search by keyword and URL',
      'Analysis history database',
    ],
    highlight: true,
    cta: 'Upgrade to Pro',
  },
  {
    name: 'BUSINESS',
    price: '$149.99',
    period: '/mo',
    desc: 'For retailers & agencies',
    features: [
      'Everything in Pro',
      '20,000+ scans per month',
      'Reputation trend forecasting',
      'Multi-platform analysis',
      'Demographic & geographic sentiment',
      'Bulk analysis (up to 2,000 at once)',
      'Custom white-label reports',
      'Price and sentiment change alerts',
      'Audit logs',
    ],
    highlight: false,
    cta: 'Upgrade to Business',
  },
]

export default function PremiumScreen({ onBack }: Props) {
  return (
    <>
      <header className="top-header">
        <div className="brand-row">
          <img src="/icons/logo.png" alt="Nectar logo" className="brand-logo" />
          <div className="brand-block">
            <h1>Nectar</h1>
            <p>AMAZON PRODUCT ANALYZER</p>
          </div>
        </div>

        <button className="premium-btn" onClick={onBack}>
          ← Back
        </button>
      </header>

      <div className="content">
        <div className="premium-hero">
          <p className="premium-hero-title">Choose Your Plan</p>
          <p className="premium-hero-subtitle">
            Unlock the full power of Nectar
          </p>
        </div>

        {plans.map((plan) => (
          <section
            key={plan.name}
            className={`premium-plan-card ${plan.highlight ? 'premium-plan-card--highlight' : ''}`}
          >
            {plan.highlight && (
              <div className="premium-badge">POPULAR</div>
            )}

            <div className="premium-plan-top">
              <div>
                <p className={`premium-plan-name ${plan.highlight ? 'premium-plan-name--highlight' : ''}`}>
                  {plan.name}
                </p>
                <p className={`premium-plan-desc ${plan.highlight ? 'premium-plan-desc--highlight' : ''}`}>
                  {plan.desc}
                </p>
              </div>

              <div className="premium-plan-price-wrap">
                <span className={`premium-plan-price ${plan.highlight ? 'premium-plan-price--highlight' : ''}`}>
                  {plan.price}
                </span>
                <span className={`premium-plan-period ${plan.highlight ? 'premium-plan-period--highlight' : ''}`}>
                  {plan.period}
                </span>
              </div>
            </div>

            <div className="premium-feature-list">
              {plan.features.map((feature) => (
                <p
                  key={feature}
                  className={`premium-feature ${plan.highlight ? 'premium-feature--highlight' : ''}`}
                >
                  <span
                    className={`premium-feature-icon ${plan.highlight ? 'premium-feature-icon--highlight' : ''}`}
                  >
                    ✦
                  </span>
                  {feature}
                </p>
              ))}
            </div>

            <button
              className={`premium-plan-cta ${plan.highlight ? 'premium-plan-cta--highlight' : ''}`}
            >
              {plan.cta}
            </button>
          </section>
        ))}
      </div>
    </>
  )
}