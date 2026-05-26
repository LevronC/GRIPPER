type AppBackgroundProps = {
  variant?: 'default' | 'auth'
}

export function AppBackground({ variant = 'default' }: AppBackgroundProps) {
  return (
    <>
      <div
        className="pointer-events-none absolute inset-0 opacity-50"
        aria-hidden="true"
        style={{
          background:
            variant === 'auth'
              ? 'radial-gradient(ellipse 70% 55% at 50% -5%, rgba(56,189,248,0.22), transparent 60%)'
              : 'radial-gradient(ellipse 80% 50% at 50% -10%, rgba(56,189,248,0.18), transparent 55%)',
        }}
      />
      <div
        className="pointer-events-none absolute bottom-0 right-0 h-[50%] w-[50%] opacity-30 blur-[120px]"
        aria-hidden="true"
        style={{
          background: 'radial-gradient(circle, rgba(129,140,248,0.15), transparent 70%)',
        }}
      />
    </>
  )
}
