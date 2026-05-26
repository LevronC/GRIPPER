import { Navbar } from '../landing/components/Navbar'
import { Hero } from '../landing/components/Hero'
import { Products } from '../landing/components/Products'
import { Features } from '../landing/components/Features'
import { ProSection } from '../landing/components/ProSection'
import { Community, TrustSection } from '../landing/components/Community'
import { Footer } from '../landing/components/Footer'

export default function LandingPage() {
  return (
    <div className="landing-theme app-theme min-h-svh bg-canvas text-ink">
      <Navbar />
      <main>
        <Hero />
        <Products />
        <Features />
        <ProSection />
        <Community />
        <TrustSection />
      </main>
      <Footer />
    </div>
  )
}
