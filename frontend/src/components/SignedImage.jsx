import { useState, useEffect, useRef } from 'react';
import { fetchSignedUrl, getProxyUrl, getThumbUrl } from '../hooks/useSignedUrl';

export default function SignedImage({ imageId, folder, refreshKey, fallbackToProxy = true, thumbnail = false, ...imgProps }) {
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
      // Fast path: use thumbnail endpoint directly (no signed-url round-trip)
      if (mountedRef.current) setSrc(getThumbUrl(imageId));
      return;
    }

    fetchSignedUrl(imageId, folder).then((url) => {
      if (mountedRef.current) setSrc(url);
    });
  }, [imageId, folder, refreshKey, thumbnail]);

  const handleError = () => {
    if (fallbackToProxy && imageId) {
      // For thumbnails, fall back to full proxy on error
      setSrc(getProxyUrl(imageId));
    }
  };

  if (!src) return null;

  return <img src={src} onError={handleError} {...imgProps} />;
}
