'use client';

import * as React from 'react';
import { FileText, Upload, X } from 'lucide-react';
import type { ResumeMeta } from '@/lib/types';
import { cn } from '@/lib/utils';

const MAX_BYTES = 10 * 1024 * 1024;

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ResumeUpload({
  resume,
  onChange,
}: {
  resume: ResumeMeta | null;
  onChange: (resume: ResumeMeta | null) => void;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const [reading, setReading] = React.useState(false);

  function accept(file: File | undefined) {
    if (!file) return;
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setError('Please upload a PDF file.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('That file is larger than 10 MB. Please upload a smaller PDF.');
      return;
    }
    setError(null);
    setReading(true);
    const reader = new FileReader();
    reader.onload = () => {
      setReading(false);
      const dataUrl = typeof reader.result === 'string' ? reader.result : undefined;
      onChange({ name: file.name, size: file.size, dataUrl });
    };
    reader.onerror = () => {
      setReading(false);
      setError('That PDF could not be read. Please try another file.');
    };
    reader.readAsDataURL(file);
  }

  if (resume) {
    return (
      <div className="rounded-xl border border-border bg-white p-4">
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-tint text-brand">
            <FileText size={19} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{resume.name}</p>
            <p className="mt-0.5 text-[13px] text-muted">{formatSize(resume.size)} · PDF</p>
            {!resume.dataUrl ? (
              <p className="mt-1 text-[12px] font-medium text-warn">Re-upload this PDF so we can read it.</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => {
              onChange(null);
              setError(null);
              if (inputRef.current) inputRef.current.value = '';
            }}
            aria-label="Remove resume"
            className="grid size-9 place-items-center rounded-xl border border-border text-muted transition-colors hover:border-danger hover:text-danger"
          >
            <X size={16} />
          </button>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-3 text-sm font-semibold text-brand hover:underline"
        >
          Replace file
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={(event) => accept(event.target.files?.[0])}
        />
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files?.[0]);
        }}
        className={cn(
          'flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-border bg-white px-4 py-8 text-center transition-colors',
          dragging ? 'border-brand bg-brand-tint' : 'hover:border-brand',
        )}
      >
        <span className="grid size-11 place-items-center rounded-xl bg-brand-tint text-brand">
          <Upload size={20} />
        </span>
        <span className="text-sm font-semibold text-ink">
          {reading ? 'Reading your PDF…' : <>Drop your resume here, or <span className="text-brand">browse</span></>}
        </span>
        <span className="text-[13px] text-muted">PDF only, up to 10 MB</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        onChange={(event) => accept(event.target.files?.[0])}
      />
      {error ? <p className="mt-1.5 text-[13px] font-medium text-danger">{error}</p> : null}
    </div>
  );
}
