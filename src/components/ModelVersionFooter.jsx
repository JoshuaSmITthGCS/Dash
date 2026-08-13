import { useData } from '../lib/useData'

export default function ModelVersionFooter() {
  const { data } = useData('report.json')
  const version = data?.model_metadata
  if (!data) return null
  const semantic = version?.semantic_version || data.model_version || 'unknown'
  const commit = version?.git_commit_sha?.slice(0, 8) || 'unknown'
  const config = version?.config_hash?.slice(0, 8) || 'unknown'
  return <footer className="model-version-footer" aria-label="Published research model version">
    Model {semantic} · commit {commit} · config {config}
  </footer>
}
