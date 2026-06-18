import { useState } from "react";

export function useAsyncAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function execute<T>(
    action: () => Promise<T>,
    errorMessage = "Error al ejecutar la acción"
  ): Promise<T | null> {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : errorMessage);
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, setError, setBusy, execute };
}
export default useAsyncAction;
