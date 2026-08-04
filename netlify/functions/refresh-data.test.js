import { workflowProgress } from './refresh-data.mjs'

describe('workflowProgress', () => {
  it('weights completed workflow stages and reports the active stage', () => {
    const jobs = [{ steps: [
      { name: 'Select the Eastern-time refresh window', status: 'completed', conclusion: 'success' },
      { name: 'Run actions/checkout@v4', status: 'completed', conclusion: 'success' },
      { name: 'Restore the Yahoo/Alpha Vantage/SEC response cache', status: 'completed', conclusion: 'success' },
      { name: 'Run actions/setup-python@v5', status: 'completed', conclusion: 'success' },
      { name: 'Run pip install -r pipeline/requirements.txt', status: 'completed', conclusion: 'success' },
      { name: 'Append point-in-time estimate snapshots', status: 'completed', conclusion: 'success' },
      { name: 'Fetch and score stock research', status: 'completed', conclusion: 'success' },
      { name: 'Fetch ETF growth screen', status: 'in_progress', conclusion: null },
    ] }]

    expect(workflowProgress(jobs)).toEqual({ percent: 50, stage: 'Fetch ETF growth screen' })
  })
})
