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

export { detailHref, detailIdFromHash };
