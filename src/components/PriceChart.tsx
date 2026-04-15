import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer
} from 'recharts'

const data = [
  { month: 'Oct', price: 120 },
  { month: 'Nov', price: 90 },
  { month: 'Dec', price: 130 },
  { month: 'Jan', price: 100 },
  { month: 'Feb', price: 80 }
]

export default function PriceChart() {
  return (
    <div style={{ width: '100%', height: 180 }}>
      <ResponsiveContainer>
        <LineChart data={data}>
          <XAxis dataKey="month" stroke="#666" />
          <YAxis hide />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#f97316"
            strokeWidth={2}
            dot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}