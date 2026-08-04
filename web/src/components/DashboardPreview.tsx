'use client';

import React, { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { useTerminalContext } from '../context/TerminalContext';

const DashboardPreview = () => {
  const { activeIndex } = useTerminalContext();
  const contentRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (contentRef.current) {
      gsap.fromTo(
        contentRef.current,
        { opacity: 0, scale: 0.98 },
        { opacity: 1, scale: 1, duration: 0.4, ease: "power2.out" }
      );
    }
  }, [activeIndex]);

  const renderContent = () => {
    switch (activeIndex) {
      case 0: // grader.py
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, color: '#1a1a1a' }}>Grading Suite: val_v1</h3>
              <span style={{ backgroundColor: '#dcfce7', color: '#16a34a', padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600 }}>98.2% PASS</span>
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
              <div style={{ flex: 1, background: '#f9f9f9', padding: '1rem', borderRadius: '8px', border: '1px solid #eaeaea' }}>
                <div style={{ fontSize: '0.8rem', color: '#666', marginBottom: '8px' }}>Format</div>
                <div style={{ width: '100%', height: '8px', background: '#e5e7eb', borderRadius: '4px' }}>
                  <div style={{ width: '100%', height: '100%', background: '#4ade80', borderRadius: '4px' }}></div>
                </div>
              </div>
              <div style={{ flex: 1, background: '#f9f9f9', padding: '1rem', borderRadius: '8px', border: '1px solid #eaeaea' }}>
                <div style={{ fontSize: '0.8rem', color: '#666', marginBottom: '8px' }}>Tone</div>
                <div style={{ width: '100%', height: '8px', background: '#e5e7eb', borderRadius: '4px' }}>
                  <div style={{ width: '96%', height: '100%', background: '#facc15', borderRadius: '4px' }}></div>
                </div>
              </div>
            </div>
            <div style={{ marginTop: '1rem', border: '1px solid #eaeaea', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>Recent Traces</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#444', padding: '0.5rem 0', borderBottom: '1px solid #eaeaea' }}>
                <span>Run #941: Summarize Q3...</span>
                <span style={{ color: '#16a34a' }}>PASS</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#444', padding: '0.5rem 0' }}>
                <span>Run #942: Extract dates...</span>
                <span style={{ color: '#16a34a' }}>PASS</span>
              </div>
            </div>
          </div>
        );
      case 1: // security_suite.py
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, color: '#1a1a1a' }}>Security & Policy</h3>
              <span style={{ backgroundColor: '#fee2e2', color: '#dc2626', padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600 }}>1 ALERT</span>
            </div>
            <div style={{ background: '#fff1f2', border: '1px solid #fecdd3', padding: '1rem', borderRadius: '8px', marginTop: '1rem' }}>
              <div style={{ color: '#be123c', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.5rem' }}>PII Leakage Detected</div>
              <div style={{ fontSize: '0.8rem', color: '#9f1239' }}>Model emitted simulated SSN in response to prompt injection vector [redteam-404].</div>
            </div>
            <div style={{ marginTop: '1rem', border: '1px solid #eaeaea', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>Blocked Vectors</div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ background: '#f3f4f6', padding: '4px 8px', borderRadius: '16px', fontSize: '0.75rem' }}>Ignore Previous</span>
                <span style={{ background: '#f3f4f6', padding: '4px 8px', borderRadius: '16px', fontSize: '0.75rem' }}>System Extraction</span>
                <span style={{ background: '#f3f4f6', padding: '4px 8px', borderRadius: '16px', fontSize: '0.75rem' }}>DAN Jailbreak</span>
              </div>
            </div>
          </div>
        );
      case 2: // evidence.jsonl
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h3 style={{ margin: 0, color: '#1a1a1a' }}>Evidence Viewer</h3>
            <div style={{ background: '#1e1e1e', borderRadius: '8px', padding: '1rem', overflowX: 'hidden', height: '180px' }}>
              <pre style={{ margin: 0, color: '#dcdcaa', fontSize: '0.75rem', fontFamily: 'monospace' }}>
{`{
  "trace_id": "tr-a9f81",
  "dataset_version": "v1.4.0",
  "model": "claude-3-5-sonnet",
  "latency_ms": 1240,
  "tokens": {
    "prompt": 450,
    "completion": 124
  },
  "tools_called": ["search_db", "fetch_docs"]
}`}
              </pre>
            </div>
          </div>
        );
      case 3: // ci_gate.sh
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, color: '#1a1a1a' }}>PR #442</h3>
              <span style={{ backgroundColor: '#e0e7ff', color: '#4338ca', padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600 }}>MERGEABLE</span>
            </div>
            <div style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '1rem' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: '#4ade80', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>✓</div>
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Regression Check Passed</div>
                  <div style={{ fontSize: '0.75rem', color: '#666' }}>98.2% vs baseline 94.5%</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '1rem' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: '#4ade80', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>✓</div>
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Performance Budget</div>
                  <div style={{ fontSize: '0.75rem', color: '#666' }}>P95 Latency 1.8s (Limit: 2.0s)</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: '#e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>-</div>
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#666' }}>Pending Approval</div>
                  <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Awaiting code review</div>
                </div>
              </div>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div style={{ 
      background: 'rgba(255, 255, 255, 0.95)', 
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      borderRadius: '12px', 
      boxShadow: '0 30px 60px rgba(0,0,0,0.1), 0 0 0 1px rgba(255,255,255,0.5) inset',
      padding: '2rem',
      height: '100%',
      display: 'flex',
      flexDirection: 'column'
    }}>
      <div style={{ fontSize: '0.75rem', color: '#888', fontWeight: 600, letterSpacing: '0.05em', marginBottom: '1.5rem', textTransform: 'uppercase' }}>
        Glyph Dashboard
      </div>
      <div ref={contentRef} style={{ flex: 1 }}>
        {renderContent()}
      </div>
    </div>
  );
};

export default DashboardPreview;
