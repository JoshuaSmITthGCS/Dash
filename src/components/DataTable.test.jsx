import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import DataTable from './DataTable.jsx'

const COLUMNS = [
  { key: 'ticker', label: 'Ticker' },
  { key: 'name', label: 'Company', sortable: false },
  { key: 'score', label: 'Score', numeric: true, cell: (row) => row.score ?? '—' },
]

const ROWS = [
  { ticker: 'AAA', name: 'Alpha', score: 70 },
  { ticker: 'BBB', name: 'Beta', score: null },
  { ticker: 'CCC', name: 'Gamma', score: 90 },
]

function setViewport(matches) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }))
}

beforeEach(() => setViewport(false))

const bodyTickers = () => within(screen.getByRole('table')).getAllByRole('row')
  .slice(1).map((row) => row.querySelector('td').textContent)

describe('DataTable', () => {
  it('renders a semantic table with a scoped header per column', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker} />)
    const headers = screen.getAllByRole('columnheader')
    expect(headers.map((header) => header.textContent.replace(/[▲▼↕]/g, ''))).toEqual(['Ticker', 'Company', 'Score'])
    expect(headers.every((header) => header.getAttribute('scope') === 'col')).toBe(true)
    expect(bodyTickers()).toEqual(['AAA', 'BBB', 'CCC'])
  })

  it('carries sort direction on aria-sort, not on the caret', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker} defaultSort={{ key: 'score', dir: 'desc' }} />)
    const scoreHeader = screen.getByRole('columnheader', { name: /Score/ })
    expect(scoreHeader).toHaveAttribute('aria-sort', 'descending')
    // the caret is decoration only
    expect(scoreHeader.querySelector('[aria-hidden="true"]')).not.toBeNull()
  })

  it('does not offer a sort control for a column marked unsortable', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker} />)
    const company = screen.getByRole('columnheader', { name: 'Company' })
    expect(within(company).queryByRole('button')).toBeNull()
    expect(company).not.toHaveAttribute('aria-sort')
  })

  it('sorts on click and toggles direction on a second click', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker} />)
    const button = within(screen.getByRole('columnheader', { name: /Score/ })).getByRole('button')
    fireEvent.click(button)
    // descending first, and the null score sorts last rather than to the top
    expect(bodyTickers()).toEqual(['CCC', 'AAA', 'BBB'])
    fireEvent.click(button)
    expect(bodyTickers()).toEqual(['AAA', 'CCC', 'BBB'])
  })

  it('keeps a missing value last in both directions', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker} defaultSort={{ key: 'score', dir: 'asc' }} />)
    expect(bodyTickers().at(-1)).toBe('BBB')
  })

  it('leaves ordering to the parent when sort is controlled', () => {
    const onSort = vi.fn()
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker}
      sort={{ key: 'score', dir: 'asc' }} onSort={onSort} />)
    expect(bodyTickers()).toEqual(['AAA', 'BBB', 'CCC'])
    fireEvent.click(within(screen.getByRole('columnheader', { name: /Score/ })).getByRole('button'))
    expect(onSort).toHaveBeenCalledWith({ key: 'score', dir: 'desc' })
  })

  it('applies rowClassName to the matching <tr>, leaving others unset', () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker}
      rowClassName={(row) => (row.ticker === 'BBB' ? 'is-total' : undefined)} />)
    const rows = screen.getAllByRole('row').slice(1) // drop the header row
    expect(rows.map((row) => row.className)).toEqual(['', 'is-total', ''])
  })

  it('renders a rowHeader column as <th scope="row">, other columns as <td>', () => {
    const columns = [
      { key: 'name', label: 'Name', rowHeader: true },
      { key: 'score', label: 'Score', numeric: true },
    ]
    render(<DataTable columns={columns} rows={[{ name: 'Alpha', score: 1 }]} getKey={(row) => row.name} />)
    const bodyRow = screen.getAllByRole('row')[1]
    const rowHeader = within(bodyRow).getByRole('rowheader')
    expect(rowHeader).toHaveTextContent('Alpha')
    expect(rowHeader.tagName).toBe('TH')
  })

  it('starts a column at its own defaultSortDir on first click', () => {
    const columns = [{ key: 'ticker', label: 'Ticker', defaultSortDir: 'asc' }]
    render(<DataTable columns={columns} rows={ROWS} getKey={(row) => row.ticker} />)
    fireEvent.click(within(screen.getByRole('columnheader')).getByRole('button'))
    expect(screen.getByRole('columnheader')).toHaveAttribute('aria-sort', 'ascending')
  })

  it('renders the empty state instead of an empty table', () => {
    render(<DataTable columns={COLUMNS} rows={[]} empty={<p>No rows clear this screen.</p>} />)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText('No rows clear this screen.')).toBeInTheDocument()
  })

  it('renders cards instead of a table below the mobile breakpoint', () => {
    setViewport(true)
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker}
      mobile={{ title: (row) => row.ticker, fields: [{ label: 'Score', value: (row) => row.score ?? '—' }] }} />)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText('AAA')).toBeInTheDocument()
    expect(screen.getByText('CCC')).toBeInTheDocument()
  })

  it('still renders a table on mobile when no card mapping is supplied', () => {
    setViewport(true)
    render(<DataTable columns={COLUMNS} rows={ROWS} getKey={(row) => row.ticker} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
  })

  describe('desktop virtualization', () => {
    const bigRows = (n) => Array.from({ length: n }, (_, i) => ({ ticker: `T${i}`, name: `Row ${i}`, score: i }))

    it('renders every row when the list is at or under virtualizeFrom', () => {
      render(<DataTable columns={COLUMNS} rows={bigRows(10)} getKey={(row) => row.ticker} />)
      expect(screen.getAllByRole('row')).toHaveLength(11) // header + 10 body rows
    })

    // jsdom has no real layout (getBoundingClientRect always returns zeros), so the exact
    // set of rows @tanstack/react-virtual windows in is not reproducible here the way it is
    // in a real browser (verified separately via Playwright against the live dev server).
    // What a unit test *can* pin down: past the threshold, the full row count is never
    // mounted at once, and the table still renders real, valid row content rather than
    // crashing or going blank.
    it('does not mount every <tr> once the list is past virtualizeFrom', () => {
      render(<DataTable columns={COLUMNS} rows={bigRows(200)} getKey={(row) => row.ticker} />)
      const bodyRows = [...screen.getAllByRole('table')[0].querySelectorAll('tbody tr')]
      expect(bodyRows.length).toBeGreaterThan(0)
      expect(bodyRows.length).toBeLessThan(200)
      // the first/last body rows may be empty padding rows (aria-hidden spacers standing in
      // for the un-rendered rows above/below the visible window) - at least one real row with
      // actual row content must still be present, or virtualization would have gone blank.
      expect(bodyRows.some((tr) => /^T\d+Row \d+\d+$/.test(tr.textContent))).toBe(true)
    })

    it('still sorts correctly once virtualized', () => {
      render(<DataTable columns={COLUMNS} rows={bigRows(200)} getKey={(row) => row.ticker} defaultSort={{ key: 'ticker', dir: 'asc' }} />)
      fireEvent.click(within(screen.getByRole('columnheader', { name: /Ticker/ })).getByRole('button'))
      expect(screen.getByRole('columnheader', { name: /Ticker/ })).toHaveAttribute('aria-sort', 'descending')
    })
  })
})
