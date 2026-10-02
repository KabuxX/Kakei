  const prefix = '#transaction/';

  function detailHref(id) {
    return `${prefix}${encodeURIComponent(id)}`;
  }

  function deleteHref(id) {
    return `${detailHref(id)}/delete`;
  }

  function detailIdFromHash(hash) {
    if (!hash.startsWith(prefix) || hash.endsWith('/delete')) return null;
    try {
      return decodeURIComponent(hash.slice(prefix.length)) || null;
    } catch (_) {
      return null;
    }
  }

  function deleteIdFromHash(hash) {
    if (!hash.startsWith(prefix) || !hash.endsWith('/delete')) return null;
    try {
      return decodeURIComponent(hash.slice(prefix.length, -'/delete'.length)) || null;
    } catch (_) {
      return null;
    }
  }

export { detailHref, detailIdFromHash, deleteHref, deleteIdFromHash };
