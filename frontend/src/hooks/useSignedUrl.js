import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5001';
const URL_CACHE = new Map();
const CACHE_TTL_MS = 50 * 60 * 1000; // 50 minutes (URLs valid for 60)

function getCachedUrl(imageId, folder) {
  const key = `${imageId}:${folder || ''}`;
  const entry = URL_CACHE.get(key);
  if (entry && Date.now() - entry.ts < CACHE_TTL_MS) {
    return entry.url;
  }
  URL_CACHE.delete(key);
  return null;
}

function setCachedUrl(imageId, folder, url) {
  const key = `${imageId}:${folder || ''}`;
  URL_CACHE.set(key, { url, ts: Date.now() });
}

export function getProxyUrl(imageId) {
  if (!imageId) return '';
  return `${API_BASE}/api/images/proxy/${imageId}?t=${Date.now()}`;
}

export async function fetchSignedUrl(imageId, folder = null) {
  if (!imageId) return '';

  const cached = getCachedUrl(imageId, folder);
  if (cached) return cached;

  try {
    const params = folder ? { folder } : {};
    const res = await axios.get(`${API_BASE}/api/images/signed-url/${imageId}`, { params });
    const signedUrl = res.data?.signed_url;
    if (signedUrl) {
      if (signedUrl.startsWith('/api/')) {
        const fullUrl = `${API_BASE}${signedUrl}`;
        setCachedUrl(imageId, folder, fullUrl);
        return fullUrl;
      }
      setCachedUrl(imageId, folder, signedUrl);
      return signedUrl;
    }
  } catch (err) {
    console.warn(`Failed to get signed URL for image ${imageId}, falling back to proxy`, err);
  }

  return getProxyUrl(imageId);
}

export default function useSignedUrl(imageId, folder = null, refreshKey = null) {
  const [url, setUrl] = useState(() => getCachedUrl(imageId, folder) || '');
  const [loading, setLoading] = useState(!url);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!imageId) {
      setUrl('');
      setLoading(false);
      return;
    }

    const cached = getCachedUrl(imageId, folder);
    if (cached) {
      setUrl(cached);
      setLoading(false);
      return;
    }

    setLoading(true);
    fetchSignedUrl(imageId, folder).then((signedUrl) => {
      if (mountedRef.current) {
        setUrl(signedUrl);
        setLoading(false);
      }
    });
  }, [imageId, folder, refreshKey]);

  return { url, loading };
}

export function invalidateSignedUrl(imageId) {
  for (const key of URL_CACHE.keys()) {
    if (key.startsWith(`${imageId}:`)) {
      URL_CACHE.delete(key);
    }
  }
}
