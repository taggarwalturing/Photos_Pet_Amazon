import { useState, useEffect, useRef } from 'react';
import { fetchSignedUrl, getProxyUrl, getThumbUrl, getViewUrl, getFullUrl } from '../hooks/useSignedUrl';

/**
 * SignedImage component for displaying images at different resolutions.
 *
 * Props:
 *   thumbnail={true}  → 400px gallery grid (smallest, fastest)
 *   view={true}       → 1200px annotation/review view (medium, fast)
 *   full={true}       → full-res via proxy (original quality)
 *   (neither)         → full-res via signed URL (largest, slowest)
 */
export default function SignedImage({ imageId, folder, refreshKey, fallbackToProxy = true, thumbnail = false, view = false, full = false, ...imgProps }) {
  const [src, setSrc] = useState('');
  const mountedRef = useRef(true);
  const retriesRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!imageId) {
      setSrc('');
      return;
    }

    retriesRef.current = 0;

    const bust = refreshKey ? `&t=${refreshKey}` : '';

    if (thumbnail) {
      if (mountedRef.current) setSrc(getThumbUrl(imageId) + bust);
      return;
    }

    if (full) {
      if (mountedRef.current) setSrc(getFullUrl(imageId) + bust);
      return;
    }

    if (view) {
      if (mountedRef.current) setSrc(getViewUrl(imageId) + bust);
      return;
    }

    fetchSignedUrl(imageId, folder).then((url) => {
      if (mountedRef.current) setSrc(url);
    });
  }, [imageId, folder, refreshKey, thumbnail, view, full]);

  const handleError = () => {
    if (!fallbackToProxy || !imageId) return;
    const attempt = retriesRef.current;
    retriesRef.current += 1;

    if (attempt === 0) {
      setSrc(getViewUrl(imageId));
    } else if (attempt === 1) {
      setSrc(getProxyUrl(imageId));
    }
  };

  if (!src) return null;

  return <img src={src} onError={handleError} {...imgProps} />;
}
