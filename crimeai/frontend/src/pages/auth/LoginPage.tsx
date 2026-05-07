import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Shield, Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { useLogin } from '@/hooks/useAuth'
import { cn } from '@/utils'

const loginSchema = z.object({
  email: z.string().email('Valid email required'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
})
type LoginForm = z.infer<typeof loginSchema>

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false)
  const login = useLogin()

  const { register, handleSubmit, formState: { errors } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = (data: LoginForm) => login.mutate(data)

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center px-4">
      {/* Background grid */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(31,111,235,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(31,111,235,0.03)_1px,transparent_1px)] bg-[size:40px_40px]" />

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent-blue mb-4 shadow-glow-blue">
            <Shield size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-text-primary">CrimeAI</h1>
          <p className="text-sm text-text-secondary mt-1">Intelligence & Predictive Policing</p>
        </div>

        {/* Card */}
        <div className="card-elevated p-6 space-y-5">
          <div>
            <h2 className="text-base font-semibold text-text-primary">Sign in</h2>
            <p className="text-xs text-text-muted mt-0.5">Authorised personnel only</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Email Address
              </label>
              <input
                {...register('email')}
                type="email"
                className="input"
                placeholder="officer@police.gov.in"
                autoComplete="email"
              />
              {errors.email && (
                <p className="text-2xs text-severity-high mt-1">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  className="input pr-9"
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((p) => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              {errors.password && (
                <p className="text-2xs text-severity-high mt-1">{errors.password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={login.isPending}
              className={cn('btn-primary w-full justify-center', login.isPending && 'opacity-70')}
            >
              {login.isPending ? (
                <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Signing in…</>
              ) : 'Sign In'}
            </button>
          </form>

          {/* Demo credentials */}
          <div className="pt-2 border-t border-border-subtle">
            <p className="text-2xs text-text-muted mb-2 font-medium">Demo credentials</p>
            <div className="space-y-1">
              {[
                { label: 'Admin', email: 'admin@crimeai.app', pass: 'Admin@1234' },
                { label: 'Officer', email: 'officer01@crimeai.app', pass: 'Officer@01' },
              ].map(({ label, email, pass }) => (
                <div key={label} className="flex items-center justify-between text-2xs text-text-muted bg-bg-tertiary rounded px-2 py-1">
                  <span className="font-mono">{email}</span>
                  <span className="text-text-muted font-mono ml-2">{pass}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <p className="text-center text-2xs text-text-muted mt-6">
          © 2025 CrimeAI. Law Enforcement Use Only.
        </p>
      </div>
    </div>
  )
}
