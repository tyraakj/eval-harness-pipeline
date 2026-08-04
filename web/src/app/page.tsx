'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import styles from './page.module.css';

import TerminalHero from '../components/TerminalHero';
import DashboardPreview from '../components/DashboardPreview';

export default function Home() {
  const [email, setEmail] = useState('');

  // Framer motion variants
  const floatVariants = {
    animate: {
      y: [0, -10, 0],
      transition: { duration: 6, repeat: Infinity, ease: "easeInOut" }
    }
  };

  return (
    <div className={styles.pageWrapper}>
      {/* Floating Navbar */}
      <nav className={styles.navbarContainer}>
        <div className={styles.navLogo}>glyph <span className={styles.navBadge}>beta</span></div>
        
        <div className={styles.navLinks}>
          <span className={styles.navLink}><span className={styles.iconGreen}>■</span> datasets</span>
          <span className={styles.navLink}><span className={styles.iconYellow}>◆</span> sandboxes</span>
          <span className={styles.navLink}><span className={styles.iconPurple}>✦</span> graders</span>
          <span className={styles.navLink}><span className={styles.iconOutline}>⬡</span> pricing</span>
        </div>

        <button className={styles.navCta}>try it now</button>
      </nav>

      {/* Main Split Hero Section */}
      <div className={styles.heroSplit}>
        <div className={styles.heroTextContainer}>
          <h1 className={styles.heroTitle}>
            <span style={{textTransform: 'lowercase'}}>glyph</span> brings versioned datasets, <span className={styles.highlightBox}>bounded execution</span> and deterministic grading into one connected workspace
          </h1>
          <p className={styles.heroSubtitle}>
            Developer-first LLM evaluation. Bring your code, we handle the execution, grading, and visualization.
          </p>
        </div>

        <div className={styles.heroComponents}>
          <div className={styles.heroTerminal}>
            <TerminalHero />
          </div>
          <div className={styles.heroDashboard}>
            <DashboardPreview />
          </div>
        </div>
      </div>
    </div>
  );
}
