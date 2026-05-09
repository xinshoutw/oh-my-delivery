import { useEffect, useRef, useState } from 'react'
import { BrowserMultiFormatReader, type IScannerControls } from '@zxing/browser'
import { X, Camera, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  open: boolean
  onClose: () => void
  onResult: (text: string) => void
  title?: string
}

export function QRScanner({ open, onClose, onResult, title = '掃描 QR Code' }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const controlsRef = useRef<IScannerControls | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [activeDeviceId, setActiveDeviceId] = useState<string | null>(null)


  useEffect(() => {
    if (!open) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setError(null)

    const start = async () => {
      try {
        const list = await navigator.mediaDevices.enumerateDevices()
        const cams = list.filter((d) => d.kind === 'videoinput')
        if (!cancelled) setDevices(cams)
        const preferred =
          activeDeviceId ?? cams.find((d) => /back|rear|environment/i.test(d.label))?.deviceId ?? null
        if (!cancelled && preferred) setActiveDeviceId(preferred)

        if (!videoRef.current) return
        const reader = new BrowserMultiFormatReader()
        const constraints: MediaStreamConstraints = preferred
          ? { video: { deviceId: { exact: preferred } } }
          : { video: { facingMode: 'environment' } }
        const ctrl = await reader.decodeFromConstraints(
          constraints,
          videoRef.current,
          (result, err) => {
            if (cancelled) return
            if (result) {
              const text = result.getText()
              if (text) {
                ctrl.stop()
                onResult(text)
                onClose()
              }
            }
            if (err && err.name !== 'NotFoundException') {
              // ignore "not found" — it just means no QR in this frame
            }
          },
        )
        if (cancelled) {
          ctrl.stop()
          return
        }
        controlsRef.current = ctrl
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : '無法開啟相機'
          setError(msg)
        }
      }
    }

    void start()
    return () => {
      cancelled = true
      controlsRef.current?.stop()
      controlsRef.current = null
    }
  }, [open, activeDeviceId, onClose, onResult])

  if (!open) return null

  const switchCamera = () => {
    if (devices.length < 2) return
    const idx = devices.findIndex((d) => d.deviceId === activeDeviceId)
    const next = devices[(idx + 1) % devices.length]
    controlsRef.current?.stop()
    controlsRef.current = null
    setActiveDeviceId(next.deviceId)
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/95 safe-top safe-bottom">
      <div className="flex h-14 items-center justify-between px-4 text-white">
        <div className="flex items-center gap-2">
          <Camera className="size-5" />
          <span className="text-sm font-medium">{title}</span>
        </div>
        <button
          type="button"
          aria-label="關閉掃描"
          onClick={onClose}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10 hover:bg-white/20"
        >
          <X className="size-5" />
        </button>
      </div>

      <div className="relative flex-1 overflow-hidden">
        <video ref={videoRef} className="h-full w-full object-cover" muted playsInline />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="aspect-square w-72 max-w-[80vw] rounded-2xl border-2 border-white/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]" />
        </div>
      </div>

      <div className="flex flex-col gap-3 px-4 py-4 text-white">
        {error ? (
          <p className="rounded-md bg-destructive/80 px-3 py-2 text-sm">{error}</p>
        ) : (
          <p className="text-center text-xs text-white/80">將 QR Code 對準框內，自動辨識後關閉</p>
        )}
        <div className="flex gap-2">
          {devices.length > 1 ? (
            <Button variant="secondary" className="flex-1" onClick={switchCamera}>
              <RotateCcw className="size-4" />
              切換相機
            </Button>
          ) : null}
          <Button variant="outline" className="flex-1" onClick={onClose}>
            關閉
          </Button>
        </div>
      </div>
    </div>
  )
}
