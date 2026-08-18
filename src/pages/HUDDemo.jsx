/**
 * HUD Demo Page - Phase 2 Showcase
 * Terminal + Matrix + Jarvis + Futurism + Doctor Who
 */

import React, { useEffect, useState } from 'react';
import {
  RadialGauge,
  ArcStat,
  TacticalFrame,
  HexContainer,
  HoloLayer,
  TargetReticle,
  StatusBlip,
  TerminalReadout,
  CoordLabel,
  GlowNumber,
  GallifreyanOverlay,
  ParticleField,
  DataStreamOverlay,
  GridOverlay,
} from '../lib/hudAdvanced.jsx';

export default function HUDDemo() {
  const [score, setScore] = useState(85);
  const [confidence, setConfidence] = useState(72);
  const [performance, setPerformance] = useState(91);

  // Simulate data changes
  useEffect(() => {
    const interval = setInterval(() => {
      setScore(prev => Math.min(Math.max(prev + (Math.random() - 0.5) * 5, 60), 100));
      setConfidence(prev => Math.min(Math.max(prev + (Math.random() - 0.5) * 3, 50), 100));
      setPerformance(prev => Math.min(Math.max(prev + (Math.random() - 0.5) * 4, 70), 100));
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="dashboard-container" style={{ position: 'relative', minHeight: '100vh', padding: 'var(--sp-6)', background: 'var(--surface-canvas-bg)' }}>
      {/* Background Effects */}
      <DataStreamOverlay />
      <GridOverlay />
      <ParticleField count={30} />

      {/* Gallifreyan Patterns */}
      <GallifreyanOverlay top="10%" right="5%" />
      <GallifreyanOverlay bottom="15%" left="8%" />

      {/* Page Header */}
      <div style={{ position: 'relative', zIndex: 2, marginBottom: 'var(--sp-8)' }}>
        <CoordLabel x="0" y="0" label="SYS-DASHBOARD-01" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
          <StatusBlip active={true} />
          <div>
            <div className="terminal-label">VALUESIGNAL TACTICAL INTERFACE</div>
            <h1 style={{
              font: 'var(--fw-bold) var(--fs-mega) var(--font-mono)',
              letterSpacing: '-0.03em',
              color: 'var(--brand-primary)',
              textShadow: '0 0 20px rgba(0, 212, 255, 0.4)',
              margin: 'var(--sp-2) 0'
            }}>
              HUD PHASE 2
            </h1>
            <div className="terminal-label">TERMINAL + MATRIX + JARVIS + FUTURISM + DOCTOR WHO</div>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div style={{
        position: 'relative',
        zIndex: 2,
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 'var(--sp-6)',
        marginBottom: 'var(--sp-8)'
      }}>
        {/* Radial Gauges Section */}
        <TacticalFrame>
          <div style={{ padding: 'var(--sp-4)' }}>
            <div className="terminal-label" style={{ marginBottom: 'var(--sp-4)' }}>
              RADIAL PERFORMANCE METRICS
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--sp-4)' }}>
              <RadialGauge value={score} max={100} label="RESEARCH SCORE" />
              <RadialGauge value={confidence} max={100} label="CONFIDENCE" />
              <RadialGauge value={performance} max={100} label="PERFORMANCE" />
            </div>
          </div>
        </TacticalFrame>

        {/* Arc Stats Section */}
        <TacticalFrame>
          <div style={{ padding: 'var(--sp-4)' }}>
            <div className="terminal-label" style={{ marginBottom: 'var(--sp-4)' }}>
              ARC SEGMENT INDICATORS
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'flex-end', gap: 'var(--sp-4)' }}>
              <ArcStat value={78} max={100} label="MOMENTUM" />
              <ArcStat value={92} max={100} label="QUALITY" />
              <ArcStat value={65} max={100} label="VALUE" />
            </div>
          </div>
        </TacticalFrame>

        {/* Terminal Readouts */}
        <TacticalFrame>
          <div style={{ padding: 'var(--sp-4)', display: 'grid', gap: 'var(--sp-3)' }}>
            <div className="terminal-label">TACTICAL READOUTS</div>
            <TerminalReadout label="MARKET BREADTH" value="73.2% ADV" />
            <TerminalReadout label="VOLATILITY INDEX" value="12.4 VIX" />
            <TerminalReadout label="RISK EXPOSURE" value="64.8% EQT" />
            <TerminalReadout label="CORRELATION" value="0.72 SPY" />
          </div>
        </TacticalFrame>
      </div>

      {/* Hexagonal Grid */}
      <div style={{ position: 'relative', zIndex: 2, marginBottom: 'var(--sp-8)' }}>
        <div className="terminal-label" style={{ marginBottom: 'var(--sp-4)' }}>
          HEXAGONAL METRIC CONTAINERS
        </div>
        <div className="hex-grid">
          <HexContainer>
            <div style={{ textAlign: 'center', padding: 'var(--sp-4)' }}>
              <div className="terminal-label">SHARPE RATIO</div>
              <GlowNumber value="1.84" />
              <div className="terminal-label" style={{ marginTop: 'var(--sp-2)', opacity: 0.6 }}>
                RISK-ADJUSTED
              </div>
            </div>
          </HexContainer>

          <HexContainer>
            <div style={{ textAlign: 'center', padding: 'var(--sp-4)' }}>
              <div className="terminal-label">MAX DRAWDOWN</div>
              <GlowNumber value="-8.2%" />
              <div className="terminal-label" style={{ marginTop: 'var(--sp-2)', opacity: 0.6 }}>
                WORST DECLINE
              </div>
            </div>
          </HexContainer>

          <HexContainer>
            <div style={{ textAlign: 'center', padding: 'var(--sp-4)' }}>
              <div className="terminal-label">ANNUAL RETURN</div>
              <GlowNumber value="+24.6%" />
              <div className="terminal-label" style={{ marginTop: 'var(--sp-2)', opacity: 0.6 }}>
                ANNUALIZED
              </div>
            </div>
          </HexContainer>

          <HexContainer>
            <div style={{ textAlign: 'center', padding: 'var(--sp-4)' }}>
              <div className="terminal-label">BETA</div>
              <GlowNumber value="0.92" />
              <div className="terminal-label" style={{ marginTop: 'var(--sp-2)', opacity: 0.6 }}>
                MARKET CORRELATION
              </div>
            </div>
          </HexContainer>
        </div>
      </div>

      {/* Holographic Layer Demo */}
      <div style={{ position: 'relative', zIndex: 2, marginBottom: 'var(--sp-8)' }}>
        <div className="terminal-label" style={{ marginBottom: 'var(--sp-4)' }}>
          HOLOGRAPHIC DEPTH LAYERS (HOVER TO ACTIVATE)
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 'var(--sp-4)' }}>
          <HoloLayer>
            <div style={{
              padding: 'var(--sp-5)',
              background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(0, 212, 255, 0.05))',
              border: '1px solid rgba(0, 212, 255, 0.3)',
              borderRadius: 'var(--r-lg)',
              textAlign: 'center'
            }}>
              <div className="terminal-label">LAYER ALPHA</div>
              <div style={{ margin: 'var(--sp-3) 0' }}>
                <TargetReticle>
                  <GlowNumber value="A1" />
                </TargetReticle>
              </div>
              <div className="terminal-label" style={{ opacity: 0.6 }}>PARALLAX ENABLED</div>
            </div>
          </HoloLayer>

          <HoloLayer>
            <div style={{
              padding: 'var(--sp-5)',
              background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.05), rgba(0, 212, 255, 0.1))',
              border: '1px solid rgba(0, 212, 255, 0.3)',
              borderRadius: 'var(--r-lg)',
              textAlign: 'center'
            }}>
              <div className="terminal-label">LAYER BETA</div>
              <div style={{ margin: 'var(--sp-3) 0' }}>
                <TargetReticle>
                  <GlowNumber value="B2" />
                </TargetReticle>
              </div>
              <div className="terminal-label" style={{ opacity: 0.6 }}>PARALLAX ENABLED</div>
            </div>
          </HoloLayer>

          <HoloLayer>
            <div style={{
              padding: 'var(--sp-5)',
              background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(0, 212, 255, 0.05))',
              border: '1px solid rgba(0, 212, 255, 0.3)',
              borderRadius: 'var(--r-lg)',
              textAlign: 'center'
            }}>
              <div className="terminal-label">LAYER GAMMA</div>
              <div style={{ margin: 'var(--sp-3) 0' }}>
                <TargetReticle>
                  <GlowNumber value="G3" />
                </TargetReticle>
              </div>
              <div className="terminal-label" style={{ opacity: 0.6 }}>PARALLAX ENABLED</div>
            </div>
          </HoloLayer>
        </div>
      </div>

      {/* Status Grid */}
      <TacticalFrame>
        <div style={{ padding: 'var(--sp-5)' }}>
          <div className="terminal-label" style={{ marginBottom: 'var(--sp-4)' }}>
            SYSTEM STATUS MATRIX
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--sp-3)' }}>
            {[
              { label: 'DATA STREAM', status: 'ACTIVE', value: '99.8%' },
              { label: 'NETWORK SYNC', status: 'NOMINAL', value: '< 50MS' },
              { label: 'COMPUTE LOAD', status: 'OPTIMAL', value: '34.2%' },
              { label: 'CACHE HIT', status: 'EFFICIENT', value: '96.4%' },
              { label: 'API CALLS', status: 'MINIMAL', value: '142/HR' },
              { label: 'RENDER FPS', status: 'STABLE', value: '60 FPS' },
            ].map((item, i) => (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--sp-2)',
                padding: 'var(--sp-2)',
                background: 'rgba(0, 0, 0, 0.2)',
                borderLeft: '2px solid var(--brand-primary)',
                borderRadius: '4px'
              }}>
                <StatusBlip active={true} />
                <div style={{ flex: 1 }}>
                  <div className="terminal-label" style={{ fontSize: 'var(--fs-2xs)' }}>{item.label}</div>
                  <div style={{
                    font: 'var(--fw-semibold) var(--fs-sm) var(--font-mono)',
                    color: 'var(--brand-primary)',
                    marginTop: '2px'
                  }}>
                    {item.value}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </TacticalFrame>

      {/* Footer Coordinates */}
      <div style={{
        position: 'relative',
        zIndex: 2,
        marginTop: 'var(--sp-12)',
        paddingTop: 'var(--sp-4)',
        borderTop: '1px solid rgba(0, 212, 255, 0.2)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 'var(--sp-4)'
      }}>
        <div className="terminal-label">
          VALUESIGNAL TACTICAL HUD v2.0 · PHASE 2 PROTOTYPE
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-4)' }}>
          <div className="terminal-label">COORD: 40.7128°N, 74.0060°W</div>
          <div className="terminal-label">TIME: {new Date().toISOString().slice(11, 19)} UTC</div>
          <StatusBlip active={true} />
        </div>
      </div>
    </div>
  );
}
