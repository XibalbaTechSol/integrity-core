import { useDashboard } from '../../context/useDashboard';
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react';

export function ToastManager() {
  const { toasts, removeToast } = useDashboard();

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map(toast => (
        <div key={toast.id} className={`toast toast-${toast.type}`}>
          {toast.type === 'success' && <CheckCircle size={18} color="var(--success)" />}
          {toast.type === 'error' && <AlertCircle size={18} color="var(--danger)" />}
          {toast.type === 'info' && <Info size={18} color="var(--primary)" />}
          
          <div style={{ flex: 1, fontSize: '0.875rem' }}>{toast.message}</div>
          
          <button onClick={() => removeToast(toast.id)} className="btn-ghost" style={{ padding: '4px' }}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
