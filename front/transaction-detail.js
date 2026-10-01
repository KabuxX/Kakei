const KakeiDetail = (() => {
  const prefix = '#transaction/';

  function detailHref(id) {
    return `${prefix}${encodeURIComponent(id)}`;
  }

  function detailIdFromHash(hash) {
    if (!hash.startsWith(prefix)) return null;
    try {
      return decodeURIComponent(hash.slice(prefix.length)) || null;
    } catch (_) {
      return null;
    }
  }

  function removePersistedTransaction(items, id, storage, key, isValid = () => true) {
    const raw = storage.getItem(key);
    const current = raw === null ? items : JSON.parse(raw);
    if (!Array.isArray(current)) throw new Error('保存された取引データが不正です。');
    const remaining = current.filter(isValid).filter((item) => item.id !== id);
    storage.setItem(key, JSON.stringify(remaining));
    return remaining;
  }

  function removePersistedSamples(items, storage, key, isValid = () => true) {
    const raw = storage.getItem(key);
    const current = raw === null ? items : JSON.parse(raw);
    if (!Array.isArray(current)) throw new Error('保存された取引データが不正です。');
    const remaining = current.filter(isValid).filter((item) => !item.id.startsWith('sample-'));
    storage.setItem(key, JSON.stringify(remaining));
    return remaining;
  }

  return { detailHref, detailIdFromHash, removePersistedTransaction, removePersistedSamples };
})();

globalThis.KakeiDetail = KakeiDetail;
if (typeof module !== 'undefined') module.exports = KakeiDetail;
