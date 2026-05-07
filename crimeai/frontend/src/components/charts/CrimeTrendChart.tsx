import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { monthName } from '@/utils'

interface CrimeTrendChartProps {
  data: Array<{ year: number; month: number; count: number }>
}

export default function CrimeTrendChart({ data }: CrimeTrendChartProps) {
  const chartData = data.map((d) => ({
    label: `${monthName(d.month)} '${String(d.year).slice(2)}`,
    crimes: d.count,
  }))

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="crimeGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#1f6feb" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#1f6feb" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: '#8b949e', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: '#8b949e', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            background: '#1c2128',
            border: '1px solid #30363d',
            borderRadius: '8px',
            fontSize: '12px',
            color: '#e6edf3',
          }}
        />
        <Area
          type="monotone"
          dataKey="crimes"
          stroke="#1f6feb"
          strokeWidth={2}
          fill="url(#crimeGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
