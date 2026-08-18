// HUD Visual Effects - Subtle animations and enhancements
// Keep it tasteful - no overboard flashiness

/**
 * Animate number changes with smooth transitions
 */
export function animateNumberChange(element, newValue, duration = 600) {
  const oldValue = parseFloat(element.textContent) || 0;
  const startTime = performance.now();

  element.setAttribute('data-score-changed', 'true');

  const animate = (currentTime) => {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);

    // Ease out cubic for smooth deceleration
    const easeProgress = 1 - Math.pow(1 - progress, 3);
    const currentValue = oldValue + (newValue - oldValue) * easeProgress;

    element.textContent = Math.round(currentValue);

    if (progress < 1) {
      requestAnimationFrame(animate);
    } else {
      element.setAttribute('data-score-changed', 'false');
    }
  };

  requestAnimationFrame(animate);
}

/**
 * Create inline sparkline SVG for trend visualization
 */
export function createSparkline(data, width = 60, height = 20, color = 'currentColor') {
  if (!data || data.length < 2) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data.map((value, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.style.display = 'inline-block';
  svg.style.verticalAlign = 'middle';
  svg.style.marginLeft = '8px';
  svg.style.opacity = '0.6';

  const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  polyline.setAttribute('points', points);
  polyline.setAttribute('fill', 'none');
  polyline.setAttribute('stroke', color);
  polyline.setAttribute('stroke-width', '1.5');
  polyline.setAttribute('stroke-linecap', 'round');
  polyline.setAttribute('stroke-linejoin', 'round');

  svg.appendChild(polyline);
  return svg;
}

/**
 * Add sparkline to metric elements
 */
export function enhanceMetricWithSparkline(metricElement, trendData) {
  if (!trendData || trendData.length < 2) return;

  // Remove existing sparkline if any
  const existing = metricElement.querySelector('svg');
  if (existing) existing.remove();

  const sparkline = createSparkline(trendData);
  if (sparkline) {
    metricElement.appendChild(sparkline);
  }
}

/**
 * Subtle entrance animation for hero score
 */
export function animateHeroScore() {
  const scoreElement = document.querySelector('.hero-score-row strong');
  if (!scoreElement) return;

  const finalValue = parseInt(scoreElement.textContent) || 0;
  scoreElement.textContent = '0';

  // Delay slightly for dramatic effect
  setTimeout(() => {
    animateNumberChange(scoreElement, finalValue, 1200);
  }, 300);
}

/**
 * Animate confidence ring fill
 */
export function animateConfidenceRing() {
  const ring = document.querySelector('.confidence-ring');
  if (!ring) return;

  ring.classList.add('animate-in');
}

/**
 * Add pulse effect to new data
 */
export function pulseNewData(element) {
  element.classList.add('pulse-new-data');
  setTimeout(() => {
    element.classList.remove('pulse-new-data');
  }, 2000);
}

/**
 * Observe score changes and animate
 */
export function observeScoreChanges(element) {
  let lastValue = element.textContent;

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'characterData' || mutation.type === 'childList') {
        const newValue = element.textContent;
        if (newValue !== lastValue && !isNaN(parseFloat(newValue))) {
          pulseNewData(element);
          lastValue = newValue;
        }
      }
    });
  });

  observer.observe(element, {
    characterData: true,
    childList: true,
    subtree: true
  });

  return observer;
}

/**
 * Initialize all HUD effects on page load
 */
export function initHudEffects() {
  // Animate hero score on load
  if (document.querySelector('.hero-score-row strong')) {
    animateHeroScore();
  }

  // Animate confidence ring
  if (document.querySelector('.confidence-ring')) {
    setTimeout(() => animateConfidenceRing(), 500);
  }

  // Add sparklines to trend cards (example data - replace with real data)
  document.querySelectorAll('.trend-card-head strong').forEach((el, i) => {
    // Generate example trend data - replace with real historical data
    const trendData = Array.from({ length: 10 }, () =>
      70 + Math.random() * 30
    );
    enhanceMetricWithSparkline(el, trendData);
  });

  // Add sparklines to candidate metrics
  document.querySelectorAll('.candidate-metrics b').forEach((el, i) => {
    // Generate example trend data
    const trendData = Array.from({ length: 8 }, () =>
      50 + Math.random() * 50
    );
    if (Math.random() > 0.5) { // Only add to some metrics
      enhanceMetricWithSparkline(el, trendData);
    }
  });
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHudEffects);
} else {
  initHudEffects();
}
