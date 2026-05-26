import { Link } from 'react-router-dom'
import { routes } from '../../lib/routes'

type BrandLogoProps = {
  to?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = {
  sm: 'text-lg',
  md: 'text-xl',
  lg: 'text-3xl',
}

export function BrandLogo({ to = routes.home, size = 'md', className = '' }: BrandLogoProps) {
  const content = (
    <span className={`font-display tracking-tight text-ink ${sizes[size]} ${className}`}>
      GRIPPER<span className="text-accent">.terminal</span>
    </span>
  )

  if (!to) return content

  return (
    <Link to={to} className="inline-block transition-opacity hover:opacity-90">
      {content}
    </Link>
  )
}
