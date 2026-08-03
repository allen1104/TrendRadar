import { useEffect, useState } from 'react'

import {
  type ReportType,
  type SubscriptionChannel,
} from '../api/reports'
import {
  usePutSubscription,
  useResetRssToken,
  useSubscription,
} from '../hooks/useReport'

const ALL_TYPES: ReportType[] = ['AI', 'TECH', 'GITHUB', 'AGENT']

export function SubscriptionPage() {
  const { data: sub } = useSubscription()
  const putSub = usePutSubscription()
  const resetToken = useResetRssToken()

  const [reportTypes, setReportTypes] = useState<ReportType[]>([])
  const [channel, setChannel] = useState<SubscriptionChannel>('SITE')
  const [webhookUrl, setWebhookUrl] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)

  useEffect(() => {
    if (sub) {
      setReportTypes(sub.reportTypes ?? [])
      setChannel(sub.channel)
      setWebhookUrl(sub.webhookUrl ?? '')
      setEnabled(sub.enabled)
    }
  }, [sub])

  async function handleSave() {
    try {
      await putSub.mutateAsync({
        reportTypes,
        channel,
        webhookUrl: channel === 'WEBHOOK' ? webhookUrl : null,
        enabled,
      })
      setSavedMsg('已保存')
      setTimeout(() => setSavedMsg(null), 2000)
    } catch (e: unknown) {
      setSavedMsg(`失败：${(e as Error).message}`)
    }
  }

  function toggleType(t: ReportType) {
    setReportTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    )
  }

  async function handleResetToken() {
    if (!confirm('重置后旧 RSS 链接立即失效，确定？')) return
    await resetToken.mutateAsync()
  }

  const rssUrl = sub?.rssToken
    ? `${window.location.origin}${sub.rssUrl ?? `/api/v1/reports/rss?token=${sub.rssToken}`}`
    : null

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-3xl font-bold">订阅设置</h1>

      {/* 日报类型 */}
      <section className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="mb-3 text-lg font-semibold">日报类型</h2>
        <div className="grid grid-cols-2 gap-3">
          {ALL_TYPES.map((t) => (
            <label
              key={t}
              className={`flex cursor-pointer items-center gap-2 rounded border p-3 transition ${
                reportTypes.includes(t)
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:bg-gray-50'
              }`}
            >
              <input
                type="checkbox"
                checked={reportTypes.includes(t)}
                onChange={() => toggleType(t)}
              />
              <span className="text-sm">{t}</span>
            </label>
          ))}
        </div>
      </section>

      {/* 渠道 */}
      <section className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="mb-3 text-lg font-semibold">推送渠道</h2>
        <div className="space-y-2">
          {(['SITE', 'EMAIL', 'WEBHOOK'] as SubscriptionChannel[]).map(
            (c) => (
              <label
                key={c}
                className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-gray-50"
              >
                <input
                  type="radio"
                  name="channel"
                  value={c}
                  checked={channel === c}
                  onChange={() => setChannel(c)}
                />
                <span className="text-sm">{c}</span>
              </label>
            ),
          )}
        </div>
        {channel === 'WEBHOOK' && (
          <div className="mt-3">
            <label className="block text-xs text-gray-600">Webhook URL</label>
            <input
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://example.com/webhook"
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
        )}
      </section>

      {/* 启用 */}
      <section className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span className="text-sm">启用订阅</span>
        </label>
      </section>

      {/* RSS */}
      <section className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="mb-3 text-lg font-semibold">RSS 私有源</h2>
        {rssUrl ? (
          <>
            <div className="mb-2 flex gap-2">
              <input
                type="text"
                readOnly
                value={rssUrl}
                className="flex-1 rounded border border-gray-300 bg-gray-50 px-3 py-2 text-xs"
              />
              <button
                onClick={() => navigator.clipboard.writeText(rssUrl)}
                className="rounded bg-gray-200 px-3 py-1 text-xs hover:bg-gray-300"
              >
                复制
              </button>
            </div>
            <button
              onClick={handleResetToken}
              className="text-xs text-red-500 hover:underline"
            >
              重置令牌（立即失效旧链接）
            </button>
          </>
        ) : (
          <p className="text-sm text-gray-500">
            保存订阅设置后将自动生成 RSS 令牌
          </p>
        )}
      </section>

      <button
        onClick={handleSave}
        disabled={putSub.isPending}
        className="w-full rounded bg-blue-500 px-4 py-2 text-sm text-white hover:bg-blue-600 disabled:opacity-50"
      >
        {putSub.isPending ? '保存中…' : '保存设置'}
      </button>
      {savedMsg && (
        <p className="mt-2 text-center text-sm text-gray-700">{savedMsg}</p>
      )}
    </div>
  )
}