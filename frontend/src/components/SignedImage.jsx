import { useState, useEffect, useRef } from 'react';
import { fetchSignedUrl, getProxyUrl } from '../hooks/useSignedUrl';

export default function SignedImage({ imageId, folder, refreshKey, fallbackToProxy = true, ...imgProps }) {
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
    fetchSignedUrl(imageId, folder).then((url) => {
      if (mountedRef.current) setSrc(url);
    });
  }, [imageId, folder, refreshKey]);

  const handleError = () => {
    if (fallbackToProxy && imageId) {
      setSrc(getProxyUrl(imageId));
    }
  };

  if (!src) return null;

  return <img src={src} onError={handleError} {...imgProps} />;
}
