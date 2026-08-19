/**
 * Advanced HUD Components - Phase 2
 * Terminal + Matrix + Jarvis + Futurism + Doctor Who
 * Hexagonal containers, circular patterns, data streams, tactical readouts
 */

import { useEffect, useRef, useState } from 'react';

/**
 * Data Stream Background (Matrix-style scrolling)
 */
export function DataStreamOverlay() {
  return <div className="data-stream-overlay" aria-hidden="true" />;
}

/**
 * Particle Field Background
 */
export function ParticleField({ count = 50 }) {
  const particles = Array.from({ length: count }, (_, i) => ({
    id: i,
    left: `${Math.random() * 100}%`,
    top: `${Math.random() * 100}%`,
    animationDelay: `${Math.random() * 5}s`,
    animationDuration: `${3 + Math.random() * 4}s`,
  }));

  return (
    <div className="particle-field" aria-hidden="true">
      {particles.map(p => (
        <div
          key={p.id}
          className="particle"
          style={{
            left: p.left,
            top: p.top,
            animation: `particle-float ${p.animationDuration} ease-in-out ${p.animationDelay} infinite`,
          }}
        />
      ))}
      <style>{`
        @keyframes particle-float {
          0%, 100% { transform: translateY(0) translateX(0); opacity: 0.3; }
          50% { transform: translateY(-20px) translateX(10px); opacity: 0.8; }
        }
      `}</style>
    </div>
  );
}

/**
 * Grid Overlay Background
 */
export function GridOverlay() {
  return <div className="grid-overlay" aria-hidden="true" />;
}

/**
 * Gallifreyan Pattern Overlay (Doctor Who inspired)
 */
export function GallifreyanOverlay({ top, left, right, bottom }) {
  const style = { top, left, right, bottom };

  return (
    <div className="gallifreyan-overlay" style={style} aria-hidden="true">
      <div className="gallifreyan-circle circle-1" />
      <div className="gallifreyan-circle circle-2" />
      <div className="gallifreyan-circle circle-3" />
      <div className="orbit-dot" style={{ top: '10%', left: '50%' }} />
      <div className="orbit-dot" style={{ top: '50%', left: '90%' }} />
      <div className="orbit-dot" style={{ top: '90%', left: '50%' }} />
      <div className="orbit-dot" style={{ top: '50%', left: '10%' }} />
    </div>
  );
}

/**
 * Radial Progress Gauge
 */
export function RadialGauge({ value, max = 100, label, size = 120 }) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;

  return (
    <div className="radial-gauge" style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120">
        <circle
          className="gauge-bg"
          cx="60"
          cy="60"
          r={radius}
        />
        <circle
          className="gauge-fill"
          cx="60"
          cy="60"
          r={radius}
          style={{
            '--gauge-circumference': circumference,
            '--gauge-offset': offset,
          }}
        />
      </svg>
      <div className="gauge-value">{Math.round(value)}</div>
      {label && <div className="gauge-label">{label}</div>}
    </div>
  );
}

/**
 * Arc Segment Progress (half-circle gauge)
 */
export function ArcStat({ value, max = 100, label }) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
  const radius = 40;
  const circumference = Math.PI * radius; // Half circle
  const offset = circumference - (percentage / 100) * circumference;

  // SVG path for a half-circle arc
  const startAngle = 180;
  const endAngle = 0;
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;

  const startX = 50 + radius * Math.cos((startAngle * Math.PI) / 180);
  const startY = 50 + radius * Math.sin((startAngle * Math.PI) / 180);
  const endX = 50 + radius * Math.cos((endAngle * Math.PI) / 180);
  const endY = 50 + radius * Math.sin((endAngle * Math.PI) / 180);

  const pathBg = `M ${startX} ${startY} A ${radius} ${radius} 0 ${largeArc} 1 ${endX} ${endY}`;

  return (
    <div className="arc-stat">
      <svg viewBox="0 0 100 100">
        <path className="arc-bg" d={pathBg} />
        <path
          className="arc-fill"
          d={pathBg}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="arc-stat-value">{Math.round(value)}</div>
      {label && <div className="terminal-label" style={{ marginTop: '4px', textAlign: 'center' }}>{label}</div>}
    </div>
  );
}

/**
 * Target Reticle
 */
export function TargetReticle({ children }) {
  return (
    <div className="target-reticle" aria-hidden="true">
      <div className="crosshair crosshair-h" />
      <div className="crosshair crosshair-v" />
      {children}
    </div>
  );
}

/**
 * Status Blip (pulsing indicator)
 */
export function StatusBlip({ active = true }) {
  if (!active) return null;
  return <div className="status-blip" aria-hidden="true" />;
}

/**
 * Coordinate Label (tactical positioning)
 */
export function CoordLabel({ x, y, label }) {
  return (
    <div className="coord-label" style={{ top: y, left: x }}>
      {label}
    </div>
  );
}

/**
 * Terminal Readout (data block with border accent)
 */
export function TerminalReadout({ label, value, children }) {
  return (
    <div className="terminal-readout">
      {label && <div className="terminal-label">{label}</div>}
      {value !== undefined && <div className="terminal-value">{value}</div>}
      {children}
    </div>
  );
}

/**
 * Tactical Frame (corner brackets container)
 */
export function TacticalFrame({ children, className = '' }) {
  return (
    <div className={`tactical-frame ${className}`}>
      <div style={{ position: 'relative' }}>
        {children}
      </div>
    </div>
  );
}

/**
 * Hexagonal Container
 */
export function HexContainer({ children, className = '' }) {
  return (
    <div className={`hex-container ${className}`}>
      {children}
    </div>
  );
}

/**
 * Holographic Layer (with parallax on hover)
 */
export function HoloLayer({ children, className = '' }) {
  const ref = useRef(null);
  const [transform, setTransform] = useState('');

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const handleMouseMove = (e) => {
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left - rect.width / 2;
      const y = e.clientY - rect.top - rect.height / 2;
      const rotateX = (y / rect.height) * 10;
      const rotateY = -(x / rect.width) * 10;
      setTransform(`perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`);
    };

    const handleMouseLeave = () => {
      setTransform('');
    };

    el.addEventListener('mousemove', handleMouseMove);
    el.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      el.removeEventListener('mousemove', handleMouseMove);
      el.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  return (
    <div
      ref={ref}
      className={`holo-layer ${className}`}
      style={{ transform, transition: transform ? 'none' : 'transform 0.3s ease-out' }}
    >
      {children}
    </div>
  );
}

/**
 * Enhanced Number Display with Glow
 */
export function GlowNumber({ value, className = '' }) {
  return (
    <span className={`terminal-value ${className}`}>
      {value}
    </span>
  );
}

/**
 * Initialize all background effects
 */
export function initAdvancedHUD() {
  // Add background layers to body if not already present
  if (typeof document === 'undefined') return;

  const root = document.getElementById('root');
  if (!root) return;

  // Check if already initialized
  if (root.querySelector('.data-stream-overlay')) return;

  // Create container for background effects
  const bgContainer = document.createElement('div');
  bgContainer.style.position = 'fixed';
  bgContainer.style.inset = '0';
  bgContainer.style.pointerEvents = 'none';
  bgContainer.style.zIndex = '0';

  // Add data stream overlay
  const dataStream = document.createElement('div');
  dataStream.className = 'data-stream-overlay';
  bgContainer.appendChild(dataStream);

  // Add grid overlay
  const grid = document.createElement('div');
  grid.className = 'grid-overlay';
  bgContainer.appendChild(grid);

  root.insertBefore(bgContainer, root.firstChild);
}
