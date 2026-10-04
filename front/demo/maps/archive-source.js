import { EtagMismatch } from 'pmtiles';

/** PMTiles Source with a bounded, same-origin whole-file fallback. */
export function createArchiveSource(url, { maxBytes, fetchImpl = fetch }) {
  const origin = globalThis.location?.origin;
  const target = new URL(url, globalThis.location?.href);
  if (!origin || target.origin !== origin || !['http:', 'https:'].includes(target.protocol) || target.username || target.password) throw new Error('Archive URL must be same-origin');
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0) throw new Error('Invalid archive limit');
  let whole, pending, mustReload = false, generation = 0;
  async function readBounded(response, limit) {
    const declared = response.headers.get('Content-Length');
    if (declared && Number(declared) > limit) { await response.body?.cancel(); throw new Error('Archive exceeds byte limit'); }
    const reader = response.body?.getReader();
    if (!reader) return new Uint8Array();
    const chunks = []; let length = 0;
    try { while (true) { const { done, value } = await reader.read(); if (done) break; length += value.byteLength; if (length > limit) throw new Error('Archive exceeds byte limit'); chunks.push(value); } }
    catch (error) { await reader.cancel().catch(()=>{}); throw error; }
    const data = new Uint8Array(length); let offset = 0;
    for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength; }
    return data;
  }
  function checkEtag(expected, actual) {
    if (expected && !expected.startsWith('W/') && actual && expected !== actual) {
      whole = undefined;
      mustReload = true;
      throw new EtagMismatch('Archive ETag changed');
    }
  }
  async function request(offset, length, expectedEtag) {
    // Serializing the initial probe means Range-ignoring servers download once.
    if (whole) {
      checkEtag(expectedEtag, whole.etag);
      try { return slice(whole.data, offset, length, whole.etag); }
      catch (error) { whole = undefined; throw error; }
    }
    if (pending) { await pending; return request(offset, length, expectedEtag); }
    let result;
    const acquisitionGeneration = generation;
    const operation = (async () => {
      const response = await fetchImpl(target.href, { headers: { Range: `bytes=${offset}-${offset + length - 1}` }, redirect: 'error', credentials: 'same-origin', cache: mustReload ? 'reload' : undefined });
      if (response.url && new URL(response.url).origin !== target.origin) throw new Error('External archive response');
      const rawEtag = response.headers.get('ETag');
      const etag = rawEtag && !rawEtag.startsWith('W/') ? rawEtag : undefined;
      if (response.status === 200 || response.status === 206) {
        try { checkEtag(expectedEtag, etag); }
        catch (error) { await response.body?.cancel(); throw error; }
      }
      if (response.status === 200) {
        const data = await readBounded(response, maxBytes);
        result = slice(data, offset, length, etag);
        if (generation === acquisitionGeneration) whole = { data, etag };
      }
      else if (response.status === 206) {
        const match = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range') || '');
        if (!match || Number(match[1]) !== offset || Number(match[2]) !== offset + length - 1 || Number(match[3]) > maxBytes || Number(match[3]) <= offset + length - 1) { await response.body?.cancel(); throw new Error('Invalid Content-Range'); }
        const data = await readBounded(response, length);
        if (data.byteLength !== length) throw new Error('Incomplete archive range');
        result = { data: data.buffer, etag };
      } else { await response.body?.cancel(); throw new Error(`Archive HTTP ${response.status}`); }
    })();
    pending = operation;
    try { await operation; return result; } finally { if (pending === operation) pending = undefined; }
  }
  function slice(data, offset, length, etag) { if (offset + length > data.byteLength) throw new Error('Archive range exceeds file'); return { data: data.slice(offset, offset + length).buffer, etag }; }
  return {
    getKey: () => target.href,
    // A consumer can reject a length-valid body during archive parsing. Keep
    // shared readers alive, but never retain bytes from before invalidation.
    invalidate() { generation++; whole = undefined; mustReload = true; },
    getBytes(offset, length, signal, expectedEtag) {
      if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(length) || offset < 0 || length <= 0 || offset + length > maxBytes) return Promise.reject(new Error('Invalid archive range'));
      if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
      const operation = request(offset, length, expectedEtag);
      if (!signal) return operation;
      return new Promise((resolve, reject) => {
        const abort = () => { signal.removeEventListener('abort', abort); reject(new DOMException('Aborted', 'AbortError')); };
        signal.addEventListener('abort', abort, { once: true });
        operation.then(value => { signal.removeEventListener('abort', abort); resolve(value); }, error => { signal.removeEventListener('abort', abort); reject(error); });
      });
    },
  };
}
