export async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Errore HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {}
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}
