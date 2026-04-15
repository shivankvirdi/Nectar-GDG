import { useState } from 'react'
import HomeScreen from './components/HomeScreen'
import PriceHistory from './components/PriceHistory'
import './index.css'

export default function App() {
  const [screen, setScreen] = useState<'home' | 'price'>('home')
  const [usage, setUsage] = useState(0)

  function handleScan() {
    setUsage(prev => Math.min(prev + 1, 2))
    setScreen('price')
  }

  return (
    <div>
      {screen === 'home' ? (
        <HomeScreen
          usage={usage}
          onScan={handleScan}
        />
      ) : (
        <PriceHistory
          usage={usage}
          onBack={() => setScreen('home')}
        />
      )}
    </div>
  )
}