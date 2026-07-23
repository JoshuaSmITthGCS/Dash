import { useData } from '../lib/useData'
import { Loading, Empty } from '../components/Bits.jsx'

export default function PolicyRadar() {
  const { data, loading } = useData('advisor.json')
  if (loading) return <Loading />
  if (!data) return <Empty />
  return <>
    <div className="page-head"><div><h1 className="page-title">Market <span className="accent">pulse</span></h1><p className="page-sub">Company news and sentiment are supporting evidence—not a substitute for earnings, cash flow, or balance-sheet quality.</p></div></div>
    <div className="sec-label">Latest sourced coverage</div>
    <div className="grid">{(data.news || []).map((item, index) => <a className="card card-pad news-card" href={item.url} target="_blank" rel="noreferrer" key={`${item.url}-${index}`}>
      <div><span className="chip">{item.ticker}</span> <span className="chip">{item.source || 'Unknown source'}</span></div>
      <strong>{item.title}</strong>
      <p>{item.summary}</p>
    </a>)}</div>
    {!data.news?.length && <Empty note="No company news returned in this refresh." />}
  </>
}
