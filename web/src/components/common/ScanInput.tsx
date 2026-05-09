import { useState } from 'react'
import { Camera } from 'lucide-react'
import { Input, type InputProps } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { QRScanner } from './QRScanner'
import { cn } from '@/lib/utils'

interface Props extends Omit<InputProps, 'onChange'> {
  value: string
  onChange: (next: string) => void
  scannerTitle?: string
  onScan?: (raw: string) => void
}

export function ScanInput({
  value,
  onChange,
  scannerTitle,
  onScan,
  className,
  placeholder,
  ...rest
}: Props) {
  const [scannerOpen, setScannerOpen] = useState(false)

  return (
    <>
      <div className={cn('flex items-stretch gap-2', className)}>
        <Input
          {...rest}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1"
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="開啟相機掃描"
          onClick={() => setScannerOpen(true)}
        >
          <Camera className="size-4" />
        </Button>
      </div>
      <QRScanner
        open={scannerOpen}
        onClose={() => setScannerOpen(false)}
        onResult={(raw) => {
          const trimmed = raw.trim()
          onChange(trimmed)
          onScan?.(trimmed)
        }}
        title={scannerTitle}
      />
    </>
  )
}
