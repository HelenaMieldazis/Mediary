/**
 * Remove do Cache Storage do navegador caches de respostas da API que
 * versões antigas do service worker possam ter deixado (eles continham
 * dados de saúde). Nunca lança erro: falhas são ignoradas.
 */
export async function limparCacheApi(): Promise<void> {
  if (typeof window === 'undefined' || !('caches' in window)) return;
  try {
    await caches.delete('api-cache');
  } catch {
    // Cache Storage indisponível (ex.: modo privado); nada a fazer.
  }
}
