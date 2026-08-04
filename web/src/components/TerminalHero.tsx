'use client';

import React, { useEffect, useState, useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { useTerminalContext } from '../context/TerminalContext';
import styles from './TerminalHero.module.css';

const TABS = ['grader.py', 'security_suite.py', 'evidence.jsonl', 'ci_gate.sh'];

const TAB_CONTENT = [
  // 0: grader.py
  (
    <div key="grader">
      <div className={styles.cliLine}>$ glyph run grader.py --dataset val_v1</div>
      <div className={styles.cliLine}><span className={styles.colorDim}>&gt; Loading grading heuristics... done</span></div>
      <div className={styles.cliLine}><span className={styles.colorDim}>&gt; Evaluating 500 samples across 4 parallel workers...</span></div>
      <br/>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Format Validation (500/500)</div>
      <div className={styles.cliLine}>[<span className={styles.colorWarn}>WARN</span>] Tone Alignment (480/500) - 20 cases marginally flagged</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Accuracy vs Ground Truth (495/500)</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorCyan}>Overall Score: 98.2%</span> - Ready for review.</div>
    </div>
  ),
  // 1: security_suite.py
  (
    <div key="security">
      <div className={styles.cliLine}>$ glyph run security_suite.py --model claud-3.5-sonnet</div>
      <div className={styles.cliLine}><span className={styles.colorDim}>&gt; Injecting adversarial prompts from redteam_bank...</span></div>
      <br/>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Prompt Injection Defenses</div>
      <div className={styles.cliLine}>[<span className={styles.colorFail}>FAIL</span>] PII Leakage Detection - <span className={styles.colorDim}>Model emitted simulated SSN on trial #142</span></div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] System Prompt Extraction Defenses</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorFail}>SECURITY GATE FAILED</span>. View trace: glyph.dev/runs/a9f81</div>
    </div>
  ),
  // 2: evidence.jsonl
  (
    <div key="evidence">
      <div className={styles.cliLine}>$ head -n 3 evidence.jsonl | jq</div>
      <div className={styles.cliLine} style={{ color: '#dcdcaa' }}>
        &#123;<br/>
        &nbsp;&nbsp;"id": "case-941",<br/>
        &nbsp;&nbsp;"input": "Summarize the Q3 report",<br/>
        &nbsp;&nbsp;"output": "In Q3, revenue grew by 15%...",<br/>
        &nbsp;&nbsp;"grader_scores": &#123; "accuracy": 1.0, "hallucination": 0.0 &#125;<br/>
        &#125;
      </div>
      <div className={styles.cliLine}><span className={styles.colorDim}>... (499 more records)</span></div>
    </div>
  ),
  // 3: ci_gate.sh
  (
    <div key="cigate">
      <div className={styles.cliLine}>$ ./ci_gate.sh --compare HEAD~1</div>
      <div className={styles.cliLine}><span className={styles.colorDim}>&gt; Fetching baseline evaluation from main branch...</span></div>
      <br/>
      <div className={styles.cliLine}>Baseline Pass Rate: 94.5%</div>
      <div className={styles.cliLine}>Candidate Pass Rate: 98.2%</div>
      <br/>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Regression threshold met. (+3.7%)</div>
      <div className={styles.cliLine}>[<span className={styles.colorPass}>PASS</span>] Performance budget maintained. (Latency &lt; 2s)</div>
      <br/>
      <div className={styles.cliLine}><span className={styles.colorCyan}>STATUS: MERGEABLE</span>. Annotating PR #442...</div>
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
