import { useState } from 'react'
import StockCard from './StockCard'
import ScoreBandView from './ScoreBandView'

/**
 * Stock Card Grid
 *
 * Mobile-first responsive grid of stock cards.
 * Supports two view modes: cards (individual) or bands (grouped by tier)
 */
export default function StockCardGrid({ stocks, viewMode = 'cards', onStockClick }) {
  const [expandedStocks, setExpandedStocks] = useState(new Set([]))

  const toggleStock = (ticker) => {
    const newExpanded = new Set(expandedStocks)
    if (newExpanded.has(ticker)) {
      newExpanded.delete(ticker)
    } else {
      newExpanded.add(ticker)
    }
    setExpandedStocks(newExpanded)
  }

  const handleStockClick = (stock) => {
    toggleStock(stock.ticker)
    if (onStockClick) {
      onStockClick(stock)
    }
  }

  if (viewMode === 'bands') {
    return <ScoreBandView stocks={stocks} onStockClick={handleStockClick} />
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 400px), 1fr))',
      gap: 16
    }}>
      {stocks.map((stock, index) => (
        <StockCard
          key={stock.ticker}
          stock={stock}
          rank={index + 1}
          totalStocks={stocks.length}
          defaultExpanded={expandedStocks.has(stock.ticker)}
        />
      ))}
    </div>
  )
}

/**
 * View Mode Switcher Component
 */
export function ViewModeSwitcher({ viewMode, onViewModeChange }) {
  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <button
        className={`tab ${viewMode === 'cards' ? 'active' : ''}`}
        onClick={() => onViewModeChange('cards')}
        style={{ fontSize: 13 }}
      >
        📇 Cards
      </button>
      <button
        className={`tab ${viewMode === 'bands' ? 'active' : ''}`}
        onClick={() => onViewModeChange('bands')}
        style={{ fontSize: 13 }}
      >
        🎯 Tiers
      </button>
      <button
        className={`tab ${viewMode === 'table' ? 'active' : ''}`}
        onClick={() => onViewModeChange('table')}
        style={{ fontSize: 13 }}
      >
        📊 Table
      </button>
    </div>
  )
}
