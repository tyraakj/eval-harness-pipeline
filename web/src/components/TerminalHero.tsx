'use client';

import React, { useEffect, useState, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { useTerminalContext } from '../context/TerminalContext';
import styles from './TerminalHero.module.css';

const TABS = ['glyph run', 'glyph compare', 'results.jsonl', 'ci integration'];

const TAB_CONTENT = [
  // 0: glyph run — modelled on actual CLI output
  (
    <div key="run">
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>$ glyph run \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--factory examples.simple_graph:create_evaluation \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--dataset datasets/example.jsonl \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--output artifacts/baseline.jsonl</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorCyan}>glyph run</span></div>
      <div className={styles.cliLine}><span className={styles.colorDim}>  500 cases | 4 workers | datasets/example.jsonl</span></div>
      <br/>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] ContainsAll&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;500/500&nbsp;&nbsp;100.0%</div>
      <div className={styles.cliLine}>[<span className={styles.colorWarn}>WARN</span>] OutcomeState&nbsp;&nbsp;&nbsp;&nbsp;480/500&nbsp;&nbsp;&nbsp;96.0%</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] ToolPolicy&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;495/500&nbsp;&nbsp;&nbsp;99.0%</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Trajectory&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;490/500&nbsp;&nbsp;&nbsp;98.0%</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorCyan}>Overall: 98.2%</span> — artifacts/baseline.jsonl</div>
    </div>
  ),
  // 1: glyph compare
  (
    <div key="compare">
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>$ glyph compare \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--candidate artifacts/candidate.jsonl \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--baseline artifacts/baseline.jsonl \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--max-regressions 0</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorDim}>Comparing 500 paired trials…</span></div>
      <br/>
      <div className={styles.cliLine}>  Baseline&nbsp;&nbsp; 94.5%</div>
      <div className={styles.cliLine}>  Candidate&nbsp;&nbsp;98.2%&nbsp;&nbsp;<span className={styles.colorPass}>+3.7%</span></div>
      <br/>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] 0 regressions (threshold: 0)</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Security suite 100%</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorCyan}>STATUS: MERGEABLE</span></div>
    </div>
  ),
  // 2: results.jsonl
  (
    <div key="results">
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>$ glyph artifacts summary \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--artifact artifacts/baseline.jsonl</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorDim}>sha256:a1b2c3d4e5f6…  immutable  4.2 MB</span></div>
      <br/>
      <div className={styles.cliLine} style={{ color: '#dcdcaa' }}>
        &#123;<br/>
        &nbsp;&nbsp;&quot;trial_id&quot;:&nbsp;&quot;tr_9a8b7c6d&quot;,<br/>
        &nbsp;&nbsp;&quot;provenance&quot;:&nbsp;&#123;<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&quot;git_hash&quot;:&nbsp;&quot;a1b2c3d4&quot;,<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&quot;target&quot;:&nbsp;&quot;LangGraphTarget@2.3.0&quot;<br/>
        &nbsp;&nbsp;&#125;,<br/>
        &nbsp;&nbsp;&quot;scores&quot;:&nbsp;&#123;&nbsp;&quot;contains_all&quot;:&nbsp;1.0&nbsp;&#125;<br/>
        &#125;
      </div>
    </div>
  ),
  // 3: ci integration
  (
    <div key="ci">
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>$ glyph release \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--deterministic artifacts/candidate.jsonl \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--baseline artifacts/baseline.jsonl \</div>
      <div className={styles.cliLine} style={{ color: '#94a3b8' }}>&nbsp;&nbsp;--policy strict</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorDim}>Verifying provenance hashes…</span></div>
      <div className={styles.cliLine}><span className={styles.colorDim}>Applying strict release policy…</span></div>
      <br/>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Pass rate 98.2% ≥ 95.0%</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] 0 critical regressions</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Security suite 100%</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Provenance hash verified</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorCyan}>RELEASE GATE: PASS</span> — annotating PR #442</div>
    </div>
  )
];

export default function TerminalHero() {
  const { activeIndex, setActiveIndex } = useTerminalContext();
  const [isHovering, setIsHovering] = useState(false);
  
  const indicatorRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const tabsContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isHovering) return;
    
    const interval = setInterval(() => {
      setActiveIndex((prev) => (prev + 1) % TABS.length);
    }, 5000);
    
    return () => clearInterval(interval);
  }, [isHovering, setActiveIndex]);

  useGSAP(() => {
    if (!indicatorRef.current || !tabsContainerRef.current) return;
    
    const activeTab = tabsContainerRef.current.children[activeIndex] as HTMLElement;
    if (activeTab) {
      gsap.to(indicatorRef.current, {
        x: activeTab.offsetLeft,
        width: activeTab.offsetWidth,
        duration: 0.3,
        ease: "power2.out",
      });
    }

    if (contentRef.current) {
      gsap.fromTo(
        contentRef.current,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.3, ease: "power2.out" }
      );
    }
  }, [activeIndex]);

  return (
    <div 
      className={styles.terminalContainer}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      <div className={styles.titleBar}>
        <div className={styles.trafficLights}>
          <div className={`${styles.dot} ${styles.dotRed}`} />
          <div className={`${styles.dot} ${styles.dotYellow}`} />
          <div className={`${styles.dot} ${styles.dotGreen}`} />
        </div>
        <div className={styles.titleText}>glyph — eval-harness-pipeline</div>
      </div>

      <div className={styles.tabsContainer} ref={tabsContainerRef}>
        {TABS.map((tab, idx) => (
          <div 
            key={tab} 
            className={`${styles.tab} ${idx === activeIndex ? styles.activeTab : ''}`}
            onClick={() => setActiveIndex(idx)}
          >
            {tab}
          </div>
        ))}
        {/* Absolute sliding indicator, managed by GSAP */}
        <div ref={indicatorRef} className={styles.activeIndicator} style={{ width: 0, bottom: 0, left: 0 }} />
      </div>

      <div className={styles.terminalBody}>
        <div ref={contentRef}>
          {TAB_CONTENT[activeIndex]}
        </div>
      </div>
    </div>
  );
}
