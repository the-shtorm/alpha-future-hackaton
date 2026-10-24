import { useEffect, useRef, type ReactNode } from 'react';
import { Button } from '@alfalab/core-components-button';
import { Input } from '@alfalab/core-components-input';

export { Button };
export function Icon({ name, size = 22 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    arrow: 'M4 12h16 M14 6l6 6-6 6',
    back: 'M20 12H4 M10 6l-6 6 6 6',
    check: 'M5 12l4 4L19 6',
    close: 'M6 6l12 12 M6 18L18 6',
    search: 'M21 21l-6-6 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
    brief: 'M3 7h18v14H3z M8 7V3h8v4 M3 12h18 M10 12v3h4v-3',
    shield: 'M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6z M8 12l3 3 5-6',
    clock: 'M12 6v6l4 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
    file: 'M6 2h8l4 4v16H6z M14 2v5h5 M9 12h6 M9 16h6',
    wallet: 'M3 5h18v15H3z M3 5l14-3v3 M15 10h6v5h-6z',
    spark: 'M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
    home: 'M3 10l9-7 9 7 M5 9v12h14V9 M10 21v-7h4v7',
    user: 'M20 21v-2a8 8 0 0 0-16 0v2 M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.file} />
    </svg>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    const onCancel = (event: Event) => {
      event.preventDefault();
      close.current();
    };
    dialog.addEventListener('cancel', onCancel);
    return () => {
      dialog.removeEventListener('cancel', onCancel);
      dialog.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? 'wide' : ''}`}
      aria-labelledby="modal-title"
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-content">
        <button className="icon-button modal-close" aria-label="Закрыть" onClick={onClose}>
          <Icon name="close" />
        </button>
        <h2 id="modal-title">{title}</h2>
        {children}
      </div>
    </dialog>
  );
}
export function Field({
  label,
  value,
  onChange,
  hint,
  error,
  type = 'text',
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  type?: 'text' | 'number' | 'date' | 'password';
  required?: boolean;
}) {
  if (type === 'date')
    return (
      <label className={`date-field ${error ? 'invalid' : ''}`}>
        <span>
          {label}
          {required ? ' *' : ''}
        </span>
        <input
          type="date"
          aria-label={label}
          value={value}
          onInput={(e) => onChange(e.currentTarget.value)}
          onChange={(e) => onChange(e.target.value)}
          max={new Date().toISOString().slice(0, 10)}
          required={required}
        />
        {error && <small role="alert">{error}</small>}
      </label>
    );
  return (
    <Input
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      block
      size={56}
      hint={hint}
      error={error}
      type={type}
      required={required}
      {...(type === 'password' ? { autoComplete: 'current-password' } : { autoComplete: 'off' })}
    />
  );
}
export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="select-field">
      <span>{label}</span>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {Object.entries(options).map(([key, text]) => (
          <option key={key} value={key}>
            {text}
          </option>
        ))}
      </select>
      <span className="select-chevron" aria-hidden="true">
        ⌄
      </span>
    </label>
  );
}
export function Banner({
  children,
  tone = 'info',
}: {
  children: ReactNode;
  tone?: 'info' | 'error' | 'success';
}) {
  return (
    <div className={`banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon name={tone === 'success' ? 'check' : 'shield'} size={20} />
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name="file" size={30} />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
