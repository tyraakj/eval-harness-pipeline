'use client';

import React, { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import { useTerminalContext } from '../context/TerminalContext';

/* ─── tiny inline SVG icons ─── */
const Icon = {
  home: (active: boolean) => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? '#fff' : '#64748b'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
  ),
  grid: (active: boolean) => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? '#fff' : '#64748b'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
  ),
  shield: (active: boolean) => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? '#fff' : '#64748b'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
  ),
  file: (active: boolean) => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? '#fff' : '#64748b'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
  ),
  chart: (active: boolean) => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={active ? '#fff' : '#64748b'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
  ),
  check: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
  ),
  x: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
  ),
  alert: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
  ),
  lock: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
  ),
  hash: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></svg>
  ),
  merge: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>
  ),
};

/* ─── shared micro-styles ─── */
const S = {
  card: {
    background: 'white',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    overflow: 'hidden' as const,
  },
  metricLabel: {
    fontSize: '0.65rem',
    fontWeight: 600 as const,
    color: '#94a3b8',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
  },
  metricValue: {
    fontSize: '1.35rem',
    fontWeight: 700 as const,
    color: '#0f172a',
    marginTop: '2px',
  },
  badge: (bg: string, fg: string) => ({
    display: 'inline-flex' as const,
    alignItems: 'center' as const,
    gap: '4px',
    fontSize: '0.65rem',
    fontWeight: 600 as const,
    padding: '3px 8px',
    borderRadius: '999px',
    background: bg,
    color: fg,
    lineHeight: 1,
  }),
  sectionTitle: {
    fontSize: '0.75rem',
    fontWeight: 600 as const,
    color: '#0f172a',
    padding: '0.75rem 1rem',
    borderBottom: '1px solid #f1f5f9',
    display: 'flex' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
  },
};

/* ─── mini sparkline (pure inline SVG) ─── */
const Sparkline = ({ data, color, width = 60, height = 20 }: { data: number[]; color: string; width?: number; height?: number }) => {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(' ');
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

/* ─── mini donut ─── */
const MiniDonut = ({ value, size = 36, color = '#22c55e' }: { value: number; size?: number; color?: string }) => {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - value);
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f1f5f9" strokeWidth="4" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="4" strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" />
    </svg>
  );
};

/* ═══════════════════════════════════════════════════════════ */

const DashboardPreview = () => {
  const { activeIndex } = useTerminalContext();
  const contentRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (contentRef.current) {
      gsap.fromTo(contentRef.current, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' });
    }
  }, [activeIndex]);

  /* ─── Tab 0 : Evaluation Runs ─── */
  const renderEvaluation = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {/* KPI row */}
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        {[
          { label: 'Pass Rate', value: '98.2%', spark: [91, 93, 92, 95, 97, 96, 98], color: '#22c55e' },
          { label: 'Eval Time', value: '14.2s', spark: [22, 18, 20, 16, 15, 14, 14], color: '#6366f1' },
          { label: 'Token Budget', value: '42.1k', spark: [30, 35, 38, 40, 39, 41, 42], color: '#f59e0b' },
        ].map((m) => (
          <div key={m.label} style={{ flex: 1, ...S.card, padding: '0.75rem 0.85rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <div>
              <div style={S.metricLabel}>{m.label}</div>
              <div style={S.metricValue}>{m.value}</div>
            </div>
            <Sparkline data={m.spark} color={m.color} />
          </div>
        ))}
      </div>

      {/* Grader matrix */}
      <div style={S.card}>
        <div style={S.sectionTitle}>
          <span>Deterministic Grader Matrix</span>
          <span style={S.badge('#f0fdf4', '#16a34a')}>500 cases</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {[
            { name: 'ContainsAllGrader', pct: 100, passed: 500, total: 500, color: '#22c55e' },
            { name: 'ToolPolicyGrader', pct: 99, passed: 495, total: 500, color: '#22c55e' },
            { name: 'OutcomeStateGrader', pct: 96, passed: 480, total: 500, color: '#eab308' },
            { name: 'TrajectoryGrader', pct: 98, passed: 490, total: 500, color: '#22c55e' },
          ].map((g, i) => (
            <div key={g.name} style={{ display: 'flex', alignItems: 'center', padding: '0.55rem 1rem', borderBottom: i < 3 ? '1px solid #f8fafc' : 'none', gap: '0.75rem' }}>
              <div style={{ width: '130px', fontSize: '0.78rem', fontWeight: 500, color: '#334155' }}>{g.name}</div>
              <div style={{ flex: 1, height: '5px', background: '#f1f5f9', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ width: `${g.pct}%`, height: '100%', background: g.color, borderRadius: '3px', transition: 'width 0.6s ease' }} />
              </div>
              <div style={{ fontSize: '0.7rem', fontWeight: 600, color: g.color, width: '50px', textAlign: 'right' }}>{g.passed}/{g.total}</div>
            </div>
          ))}
        </div>
      </div>

      {/* suite tags */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {['capability', 'regression', 'security'].map((s) => (
          <span key={s} style={S.badge('#f1f5f9', '#475569')}>
            {s}
          </span>
        ))}
        <span style={{ ...S.badge('#eff6ff', '#2563eb') }}>v1.0.0 — support-quality</span>
      </div>
    </div>
  );

  /* ─── Tab 1 : Sandbox & Security ─── */
  const renderSecurity = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {/* violation alert */}
      <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '10px', padding: '0.85rem 1rem', display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
        <div style={{ marginTop: '2px' }}>{Icon.alert}</div>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.82rem', color: '#dc2626', marginBottom: '4px' }}>ToolPolicyGrader — Violation Intercepted</div>
          <div style={{ fontSize: '0.78rem', color: '#7f1d1d', lineHeight: 1.5 }}>
            Agent invoked <code style={{ background: '#fee2e2', padding: '1px 5px', borderRadius: '4px', fontSize: '0.72rem' }}>read_file(&quot;/etc/passwd&quot;)</code>. Blocked by SandboxProvider isolation layer.
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.75rem' }}>
        {/* capability matrix */}
        <div style={{ flex: 1, ...S.card }}>
          <div style={S.sectionTitle}>Sandbox Capabilities</div>
          <div style={{ padding: '0.6rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {[
              { cap: 'Filesystem (chroot)', allowed: true },
              { cap: 'Network Egress', allowed: false },
              { cap: 'Subprocess Exec', allowed: false },
              { cap: 'Database Access', allowed: true },
            ].map((c) => (
              <div key={c.cap} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.78rem' }}>
                <span style={{ color: '#334155' }}>{c.cap}</span>
                {c.allowed
                  ? <span style={S.badge('#dcfce7', '#16a34a')}>{Icon.check} Scoped</span>
                  : <span style={S.badge('#fee2e2', '#dc2626')}>{Icon.x} Blocked</span>}
              </div>
            ))}
          </div>
        </div>

        {/* trajectory */}
        <div style={{ flex: 1, ...S.card, background: '#0f172a', border: '1px solid #1e293b' }}>
          <div style={{ ...S.sectionTitle, color: '#94a3b8', borderBottomColor: '#1e293b' }}>
            Trajectory Trace
            <span style={S.badge('#1e293b', '#f87171')}>error</span>
          </div>
          <pre style={{ padding: '0.6rem 1rem', margin: 0, fontSize: '0.7rem', lineHeight: 1.6, color: '#94a3b8', fontFamily: "'Courier New', monospace" }}>
{`▸ tool_call  read_file
  {"path": "/app/config.json"}
◂ tool_result `}<span style={{ color: '#4ade80' }}>success</span>{`

▸ tool_call  read_file
  {"path": "/etc/passwd"}
◂ tool_result `}<span style={{ color: '#f87171' }}>BLOCKED (Policy)</span>{`

▸ finish     `}<span style={{ color: '#f87171' }}>error</span>
          </pre>
        </div>
      </div>
    </div>
  );

  /* ─── Tab 2 : Immutable Evidence ─── */
  const renderEvidence = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', height: '100%' }}>
      {/* provenance bar */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <span style={S.badge('#f1f5f9', '#475569')}>{Icon.hash} sha256:a1b2c3…f4e5</span>
        <span style={S.badge('#f1f5f9', '#475569')}>{Icon.lock} immutable</span>
        <span style={S.badge('#eff6ff', '#2563eb')}>4.2 MB · 500 records</span>
      </div>

      {/* JSON preview */}
      <div style={{ ...S.card, flex: 1, display: 'flex', flexDirection: 'column', background: '#0f172a', border: '1px solid #1e293b' }}>
        <div style={{ padding: '0.5rem 1rem', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 600, color: '#94a3b8' }}>trial_record.jsonl</span>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <span style={S.badge('#1e293b', '#94a3b8')}>Export</span>
            <span style={S.badge('#1e293b', '#94a3b8')}>Verify Hash</span>
          </div>
        </div>
        <pre style={{ padding: '1rem', margin: 0, fontSize: '0.72rem', lineHeight: 1.55, color: '#e2e8f0', fontFamily: "'Courier New', monospace", flex: 1, overflowY: 'auto' }}>
{`{
  `}<span style={{ color: '#7dd3fc' }}>&quot;trial_id&quot;</span>{`: `}<span style={{ color: '#fde68a' }}>&quot;tr_9a8b7c6d&quot;</span>{`,
  `}<span style={{ color: '#7dd3fc' }}>&quot;provenance&quot;</span>{`: {
    `}<span style={{ color: '#7dd3fc' }}>&quot;git_hash&quot;</span>{`:  `}<span style={{ color: '#fde68a' }}>&quot;a1b2c3d4&quot;</span>{`,
    `}<span style={{ color: '#7dd3fc' }}>&quot;target&quot;</span>{`:    `}<span style={{ color: '#fde68a' }}>&quot;LangGraphTarget@2.3.0&quot;</span>{`,
    `}<span style={{ color: '#7dd3fc' }}>&quot;model&quot;</span>{`:     `}<span style={{ color: '#fde68a' }}>&quot;gpt-4o-2024-08-06&quot;</span>{`
  },
  `}<span style={{ color: '#7dd3fc' }}>&quot;budget&quot;</span>{`: { `}<span style={{ color: '#7dd3fc' }}>&quot;timeout_s&quot;</span>{`: `}<span style={{ color: '#a5f3fc' }}>30</span>{`, `}<span style={{ color: '#7dd3fc' }}>&quot;max_tools&quot;</span>{`: `}<span style={{ color: '#a5f3fc' }}>8</span>{` },
  `}<span style={{ color: '#7dd3fc' }}>&quot;scores&quot;</span>{`: {
    `}<span style={{ color: '#7dd3fc' }}>&quot;contains_all&quot;</span>{`: `}<span style={{ color: '#a5f3fc' }}>1.0</span>{`,
    `}<span style={{ color: '#7dd3fc' }}>&quot;tool_policy&quot;</span>{`:  `}<span style={{ color: '#a5f3fc' }}>1.0</span>{`
  },
  `}<span style={{ color: '#7dd3fc' }}>&quot;telemetry&quot;</span>{`: { `}<span style={{ color: '#7dd3fc' }}>&quot;latency_ms&quot;</span>{`: `}<span style={{ color: '#a5f3fc' }}>1240</span>{`, `}<span style={{ color: '#7dd3fc' }}>&quot;tokens&quot;</span>{`: `}<span style={{ color: '#a5f3fc' }}>574</span>{` }
}`}
        </pre>
      </div>
    </div>
  );

  /* ─── Tab 3 : CI Release Gate ─── */
  const renderCIGate = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {/* header */}
      <div style={{ ...S.card, padding: '0.85rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {Icon.merge} Regression Analysis
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>PR #442 candidate vs main baseline</div>
        </div>
        <span style={S.badge('#dcfce7', '#16a34a')}>MERGEABLE</span>
      </div>

      {/* comparison table */}
      <div style={S.card}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
              {['Metric', 'Baseline', 'Candidate', 'Δ'].map((h) => (
                <th key={h} style={{ padding: '0.6rem 1rem', fontSize: '0.68rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              { metric: 'Overall Pass Rate', base: '94.5%', cand: '98.2%', delta: '+3.7%', color: '#22c55e' },
              { metric: 'P95 Latency', base: '2.1s', cand: '1.8s', delta: '−0.3s', color: '#22c55e' },
              { metric: 'Token Cost / Run', base: '$0.012', cand: '$0.014', delta: '+$0.002', color: '#eab308' },
              { metric: 'Security Suite', base: '100%', cand: '100%', delta: '0', color: '#64748b' },
            ].map((r, i) => (
              <tr key={r.metric} style={{ borderBottom: i < 3 ? '1px solid #f8fafc' : 'none' }}>
                <td style={{ padding: '0.6rem 1rem', fontSize: '0.8rem', fontWeight: 500, color: '#334155' }}>{r.metric}</td>
                <td style={{ padding: '0.6rem 1rem', fontSize: '0.8rem', color: '#94a3b8' }}>{r.base}</td>
                <td style={{ padding: '0.6rem 1rem', fontSize: '0.8rem', color: '#0f172a', fontWeight: 600 }}>{r.cand}</td>
                <td style={{ padding: '0.6rem 1rem', fontSize: '0.8rem', color: r.color, fontWeight: 600 }}>{r.delta}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* gate checklist */}
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <div style={{ flex: 1, ...S.card }}>
          <div style={S.sectionTitle}>Release Policy — <span style={{ color: '#6366f1' }}>strict</span></div>
          <div style={{ padding: '0.6rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {[
              { rule: 'Pass rate ≥ 95%', pass: true },
              { rule: 'Zero critical regressions', pass: true },
              { rule: 'Security suite 100%', pass: true },
              { rule: 'Provenance hash match', pass: true },
            ].map((c) => (
              <div key={c.rule} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: '#334155' }}>
                {c.pass ? Icon.check : Icon.x}
                {c.rule}
              </div>
            ))}
          </div>
        </div>
        <div style={{ flex: 1, ...S.card, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
          <MiniDonut value={0.982} size={56} />
          <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', fontWeight: 600, color: '#0f172a' }}>98.2%</div>
          <div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>composite score</div>
        </div>
      </div>
    </div>
  );

  /* ─── select panel ─── */
  const panels = [renderEvaluation, renderSecurity, renderEvidence, renderCIGate];
  const breadcrumbs = [
    'Runs / Suite #941 — support-quality v1.0.0',
    'Sandboxes / Policy Intercepts',
    'Artifacts / trial_record.jsonl',
    'CI/CD / PR #442 Release Gate',
  ];
  const statusLabels = [
    { dot: '#22c55e', text: '2 / 2 passed' },
    { dot: '#ef4444', text: '1 violation' },
    { dot: '#6366f1', text: 'verified' },
    { dot: '#22c55e', text: 'mergeable' },
  ];

  const sidebarIcons = [Icon.grid, Icon.shield, Icon.file, Icon.chart];

  return (
    <div style={{
      background: 'rgba(255,255,255,0.97)',
      backdropFilter: 'blur(24px)',
      WebkitBackdropFilter: 'blur(24px)',
      borderRadius: '12px',
      boxShadow: '0 30px 60px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)',
      height: '100%',
      display: 'flex',
      overflow: 'hidden',
      fontFamily: 'var(--font-sans)',
    }}>
      {/* Sidebar */}
      <div style={{
        width: '52px',
        background: '#0f172a',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '0.85rem 0',
        gap: '0.5rem',
        flexShrink: 0,
      }}>
        {/* logo */}
        <div style={{ width: '28px', height: '28px', background: 'linear-gradient(135deg, #6366f1, #a855f7)', borderRadius: '7px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 800, fontSize: '0.85rem', marginBottom: '0.75rem' }}>g</div>

        {sidebarIcons.map((iconFn, i) => (
          <div key={i} onClick={() => {}} style={{
            width: '34px',
            height: '34px',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: i === activeIndex ? 'rgba(99,102,241,0.25)' : 'transparent',
            cursor: 'pointer',
            transition: 'background 0.2s',
          }}>
            {iconFn(i === activeIndex)}
          </div>
        ))}
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* header bar */}
        <div style={{
          height: '44px',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          padding: '0 1.25rem',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {breadcrumbs[activeIndex]}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
            <div style={{ width: '7px', height: '7px', borderRadius: '50%', background: statusLabels[activeIndex].dot }} />
            <span style={{ fontSize: '0.72rem', fontWeight: 600, color: '#334155' }}>{statusLabels[activeIndex].text}</span>
          </div>
        </div>

        {/* body */}
        <div style={{ padding: '1rem 1.25rem', flex: 1, overflowY: 'auto' }}>
          <div ref={contentRef} style={{ height: '100%' }}>
            {panels[activeIndex]()}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPreview;
