import { LandingNav } from "@/components/landing/landing-nav"
import { Hero } from "@/components/landing/hero"
import { HowItWorks } from "@/components/landing/how-it-works"
import { WhyEvidence } from "@/components/landing/why-evidence"
import { Roadmap } from "@/components/landing/roadmap"
import { Walkthrough } from "@/components/landing/walkthrough"

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <LandingNav />
      <Hero />
      <HowItWorks />
      <WhyEvidence />
      <Roadmap />
      <Walkthrough />
    </main>
  )
}
