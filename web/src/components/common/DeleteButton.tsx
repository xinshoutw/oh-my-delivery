import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ApiRequestError, formatApiError } from '@/lib/api'

interface Props<T> {
  /** Confirmation question shown above the confirm button. */
  confirm: string
  /** Performs the actual delete request. */
  onDelete: () => Promise<T>
  /** Called after a successful delete. Receives the response body. */
  onSuccess?: (data: T) => void
  /** Called on a non-conflict failure (e.g. network). */
  onError?: (err: unknown) => void
  /** Optional renderer for 409 references payload (FK guard hits). */
  renderReferences?: (refs: Record<string, number>) => React.ReactNode
  /** Override rendered button label. Defaults to "刪除". */
  label?: string
  size?: 'sm' | 'icon'
  variant?: 'destructive' | 'ghost' | 'outline'
}

interface ApiErrorDetail {
  message?: string
  references?: Record<string, number>
}

export function DeleteButton<T>({
  confirm,
  onDelete,
  onSuccess,
  onError,
  renderReferences,
  label,
  size = 'sm',
  variant = 'ghost',
}: Props<T>) {
  const [open, setOpen] = useState(false)
  const [refs, setRefs] = useState<Record<string, number> | null>(null)

  const mut = useMutation({
    mutationFn: onDelete,
    onSuccess: (data) => {
      setOpen(false)
      setRefs(null)
      toast.success('已刪除')
      onSuccess?.(data)
    },
    onError: (err) => {
      if (err instanceof ApiRequestError && err.status === 409) {
        const detail = err.detail as ApiErrorDetail | string | undefined
        if (typeof detail === 'object' && detail?.references) {
          setRefs(detail.references)
          toast.error(detail.message ?? '存在引用，無法刪除')
          return
        }
      }
      toast.error(formatApiError(err))
      onError?.(err)
    },
  })

  if (!open) {
    return (
      <Button
        type="button"
        variant={variant}
        size={size}
        onClick={(e) => {
          e.stopPropagation()
          setOpen(true)
          setRefs(null)
        }}
        aria-label="刪除"
        title="刪除"
      >
        <Trash2 className="size-3.5" />
        {label ? <span className="ml-1 text-xs">{label}</span> : null}
      </Button>
    )
  }

  return (
    <div
      className="flex flex-col gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2"
      onClick={(e) => e.stopPropagation()}
    >
      <p className="text-xs">{confirm}</p>
      {refs ? (
        renderReferences ? (
          <div className="text-xs">{renderReferences(refs)}</div>
        ) : (
          <ul className="text-xs text-destructive">
            {Object.entries(refs)
              .filter(([, n]) => n > 0)
              .map(([k, n]) => (
                <li key={k}>
                  {k}: {n}
                </li>
              ))}
          </ul>
        )
      ) : null}
      <div className="flex gap-1.5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => {
            setOpen(false)
            setRefs(null)
          }}
        >
          <X className="size-3" />
          取消
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => mut.mutate()}
          disabled={mut.isPending}
        >
          {mut.isPending ? '刪除中…' : '確認刪除'}
        </Button>
      </div>
    </div>
  )
}
