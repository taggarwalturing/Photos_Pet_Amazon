import { useState, useEffect, useRef } from 'react';
import { fetchSignedUrl, getProxyUrl, getThumbUrl, getViewUrl } from '../hooks/useSignedUrl';

/**
 * SignedImage component for displaying images at different resolutions.
 *
 * Props:
 *   thumbnail={true}  → 400px gallery grid (smallest, fastest)
 *   view={true}       → 1200px annotation/review view (medium, fast)
 *   (neither)         → full-res via signed URL (largest, slowest)
 */
export default function SignedImage({ imageId, folder, refreshKey, fallbackToProxy = true, thumbnail = false, view = false, ...imgProps }) {
  const [src, setSrc] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!imageId) {
      setSrc('');
      return;
    }

    if (thumbnail) {
      // Fast path: 400px thumbnail, no signed-url round-trip
      if (mountedRef.current) setSrc(getThumbUrl(imageId));
      return;
    }

    if (view) {
      // Medium path: 1200px view image, no signed-url round-trip
      if (mountedRef.current) setSrc(getViewUrl(imageId));
      return;
    }

    fetchSignedUrl(imageId, folder).then((url) => {
      if (mountedRef.current) setSrc(url);
    });
  }, [imageId, folder, refreshKey, thumbnail, view]);

  const handleError = () => {
    if (fallbackToProxy && imageId) {
      setSrc(getProxyUrl(imageId));
    }
  };

  if (!src) return null;

  return <img src={src} onError={handleError} {...imgProps} />;
}
