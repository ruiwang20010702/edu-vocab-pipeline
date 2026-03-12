import type { QcIssue } from './types'

export function QcResultBanner({ passed, message, issues }: { passed: boolean; message: string; issues?: QcIssue[] }) {
  return (
    <div className={`text-xs px-3 py-2 rounded-xl font-medium ${passed ? 'bg-green-50 text-green-600 border border-green-200 text-center' : 'bg-orange-50 text-orange-600 border border-orange-200'}`}>
      <div className={passed ? '' : 'font-bold mb-1'}>{message}</div>
      {!passed && issues && issues.length > 0 && (
        <ul className="space-y-0.5 text-left">
          {issues.map((iss, i) => (
            <li key={i}>{iss.message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
