interface NavbarProps {
  usage: number
  maxUsage: number
}

export default function Navbar({ usage, maxUsage }: NavbarProps) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '14px 18px',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      borderRadius: '16px 16px 0 0',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 20 }}>🍊</span>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 800,
            fontSize: 15,
            letterSpacing: '0.05em',
            color: 'var(--orange)',
          }}>Nectar</div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 8,
            letterSpacing: '0.2em',
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
          }}>Product Analyzer</div>
        </div>
      </div>

      {/* Usage pill */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        color: 'var(--text-muted)',
        letterSpacing: '0.1em',
        marginRight: 10,
      }}>
        USAGE{' '}
        <span style={{ color: usage >= maxUsage ? 'var(--red)' : 'var(--orange)' }}>
          {usage}/{maxUsage}
        </span>
      </div>

      {/* Premium button */}
      <button style={{
        background: 'transparent',
        border: '1px solid var(--orange)',
        borderRadius: 8,
        color: 'var(--orange)',
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: '0.15em',
        padding: '5px 10px',
        cursor: 'pointer',
        textTransform: 'uppercase',
        transition: 'all 0.2s',
      }}
        onMouseEnter={e => {
          (e.target as HTMLButtonElement).style.background = 'var(--orange)'
          ;(e.target as HTMLButtonElement).style.color = '#000'
        }}
        onMouseLeave={e => {
          (e.target as HTMLButtonElement).style.background = 'transparent'
          ;(e.target as HTMLButtonElement).style.color = 'var(--orange)'
        }}
      >
        Go Premium
      </button>
    </div>
  )
}