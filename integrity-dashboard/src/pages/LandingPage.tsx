import React, { useState } from 'react';
import { CinematicHeader } from '../components/landing/CinematicHeader';
import { HeroSection } from '../components/landing/HeroSection';
import { AgentPrimitivesSection, DevQuickstartSection, ProgrammableEscrowsSection, EconomicUseCasesSection, PrivacyArchitectureSection, AisMathSection } from '../components/landing/CoreFeatures';
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
            
            <AgentPrimitivesSection />
            <AisMathSection />
            <ProgrammableEscrowsSection />
            <EconomicUseCasesSection />
            <PrivacyArchitectureSection />
            
            <DevQuickstartSection setContactType={setContactType} setIsContactOpen={setIsContactOpen} />

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

