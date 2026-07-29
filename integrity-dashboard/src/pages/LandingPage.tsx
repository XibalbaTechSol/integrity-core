import React, { useState } from 'react';
import { CinematicHeader } from '../components/landing/CinematicHeader';
import { HeroSection } from '../components/landing/HeroSection';
import { TrustGapSection, DevQuickstartSection, ProgrammableEscrowsSection, EconomicUseCasesSection, PrivacyArchitectureSection } from '../components/landing/CoreFeatures';
import { EcosystemFeatures } from '../components/landing/EcosystemFeatures';
import { FAQSection } from '../components/landing/FAQSection';
import { ContactFormSection } from '../components/landing/ContactFormSection';
import { Footer } from '../components/landing/Footer';
import { ContactModal } from '../components/ui/ContactModal';
import { RegistryExplorer } from '../components/ui/RegistryExplorer';

export const LandingPage = () => {
    const [isContactOpen, setIsContactOpen] = useState(false);
    const [contactType, setContactType] = useState<'investor' | 'developer'>('investor');
    const [isRegistryOpen, setIsRegistryOpen] = useState(false);

    return (
        <div style={{ background: 'var(--navy-deep)', color: 'white', minHeight: '100vh', overflowX: 'hidden' }}>
            <CinematicHeader setIsContactOpen={setIsContactOpen} setContactType={setContactType} />
            <HeroSection setContactType={setContactType} setIsContactOpen={setIsContactOpen} setIsRegistryOpen={setIsRegistryOpen} />
            
            <TrustGapSection />
            <ProgrammableEscrowsSection />
            <EconomicUseCasesSection />
            <PrivacyArchitectureSection />
            
            <div style={{ padding: '80px 0', background: 'var(--navy-deep)' }}>
                <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                    <h2 style={{ fontSize: '2.5rem', fontWeight: 800 }}>Start Building</h2>
                    <p style={{ color: 'rgba(255,255,255,0.6)' }}>Integrate the Integrity Protocol into your stack.</p>
                </div>
                <DevQuickstartSection setContactType={setContactType} setIsContactOpen={setIsContactOpen} />
            </div>

            <EcosystemFeatures setIsContactOpen={setIsContactOpen} setContactType={setContactType} />
            
            <FAQSection />
            <ContactFormSection />
            <Footer />
            
            {/* Modals */}
            <ContactModal 
                isOpen={isContactOpen} 
                onClose={() => setIsContactOpen(false)} 
                initialType={contactType} 
            />
            
            <RegistryExplorer 
                isOpen={isRegistryOpen} 
                onClose={() => setIsRegistryOpen(false)} 
            />
        </div>
    );
};

