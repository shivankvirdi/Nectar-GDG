import { useRef, useEffect } from 'react';

interface NavbarProps {
  usage: number
  maxUsage: number
}

export default function Navbar({ usage, maxUsage }: NavbarProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (closeButtonRef.current) {
      // Set the webkit-app-region property directly on the element
      closeButtonRef.current.style.setProperty('webkit-app-region', 'no-drag');
    }
  }, []);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '14px 18px',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      borderRadius: '16px 16px 0 0',
      overflow: 'visible',
      position: 'relative',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <img
          src="/Icons/logo.png"
          style={{
            width: 18,
            height: 18,
            objectFit: 'contain'
          }}
          alt="Nectar Logo"
        />
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
        flexShrink: 0,
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
        flexShrink: 0,
      }}
        onMouseEnter={e => {
          (e.target as HTMLButtonElement).style.background = 'var(--orange)'
            ; (e.target as HTMLButtonElement).style.color = '#000'
        }}
        onMouseLeave={e => {
          (e.target as HTMLButtonElement).style.background = 'transparent'
            ; (e.target as HTMLButtonElement).style.color = 'var(--orange)'
        }}
      >
        Go Premium
      </button>

      {/* Close button */}
      <button
        onClick={() => {
          if ((window as any).electronAPI?.closeWindow) {
            (window as any).electronAPI.closeWindow();
          }
        }}
        style={{
          width: 10,
          height: 10,
          minWidth: 10,
          borderRadius: '50%',
          border: 'none',
          background: 'transparent',
          color: '#9ca3af',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 6,
          fontWeight: 400,
          padding: 0,
          lineHeight: 1,
          opacity: 0.25,
          transition: 'all 0.12s ease',
        }}
        onMouseEnter={(e) => {
          const el = e.target as HTMLButtonElement;
          el.style.opacity = '1';
          el.style.color = '#ffffff';
          el.style.background = '#ef4444';
        }}
        onMouseLeave={(e) => {
          const el = e.target as HTMLButtonElement;
          el.style.opacity = '0.25';
          el.style.color = '#9ca3af';
          el.style.background = 'transparent';
        }}
      >
        x
      </button>
    </div>
  );
}