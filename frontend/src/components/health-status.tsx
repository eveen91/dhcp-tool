'use client';

import { useEffect, useState } from 'react';
import { getHealth } from '../lib/api/client';

type HealthState = 'checking' | 'available' | 'unavailable';

export function HealthStatus() {
  const [state, setState] = useState<HealthState>('checking');

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        await getHealth(controller.signal);
        if (!controller.signal.aborted) setState('available');
      } catch {
        if (!controller.signal.aborted) setState('unavailable');
      }
    }

    void checkHealth();
    return () => controller.abort();
  }, []);

  const labels: Record<HealthState, string> = {
    checking: 'Sprawdzanie połączenia…',
    available: 'API dostępne',
    unavailable: 'API niedostępne',
  };

  return (
    <div className="health" role="status" aria-live="polite" data-state={state}>
      <span className="health-dot" aria-hidden="true" />
      <span>{labels[state]}</span>
    </div>
  );
}
