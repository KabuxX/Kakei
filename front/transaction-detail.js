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

  function removePersistedTransaction(items, id, storage, key) {
    const remaining = items.filter((item) => item.id !== id);
    storage.setItem(key, JSON.stringify(remaining));
    return remaining;
  }

  return { detailHref, detailIdFromHash, removePersistedTransaction };
})();

globalThis.KakeiDetail = KakeiDetail;
if (typeof module !== 'undefined') module.exports = KakeiDetail;
