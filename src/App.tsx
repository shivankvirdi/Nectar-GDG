import { useEffect, useState } from 'react'
import './App.css'

export default function App() {
  const [currentUrl, setCurrentUrl] = useState('Loading...')
  const [backendStatus, setBackendStatus] = useState('Waiting for backend...')

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
        setBackendStatus(`Sent to backend: ${data.ok ? 'success' : 'failed'}`)
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
        <button className="premium">Go Premium</button>
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
        <h3>Review Integrity</h3>
        <div className="progress">
          <div className="progress-fill"></div>
        </div>
        <p className="desc">
          Most reviews appear organic and verified.
        </p>
      </div>
    </div>
  )
}
