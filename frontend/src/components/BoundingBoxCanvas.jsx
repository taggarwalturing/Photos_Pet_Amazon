import { useRef, useState, useEffect, useCallback } from 'react';

/**
 * Transparent canvas overlay for drawing bounding-box blur regions.
 *
 * Props:
 *   containerRef – ref to the element the canvas should cover
 *   boxes / setBoxes – state array of { x, y, width, height } in normalised 0-1 coords
 *   disabled – disables drawing when true
 *
 * Coordinates are normalised to the <img> element INSIDE the container,
 * not the container itself. This ensures blur regions align with the image
 * even when the image doesn't fill the container (aspect ratio padding).
 */
export default function BoundingBoxCanvas({ containerRef, boxes, setBoxes, disabled }) {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [start, setStart] = useState(null);
  const [current, setCurrent] = useState(null);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });
  const [imgOffset, setImgOffset] = useState({ x: 0, y: 0, w: 0, h: 0 });

  // Find the <img> element inside the container and get its displayed rect
  const getImgRect = useCallback(() => {
    const el = containerRef?.current;
    if (!el) return null;
    const img = el.querySelector('img');
    if (!img) return null;

    const containerRect = el.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();

    return {
      // Image position relative to the container
      x: imgRect.left - containerRect.left,
      y: imgRect.top - containerRect.top,
      w: imgRect.width,
      h: imgRect.height,
    };
  }, [containerRef]);

  const syncSize = useCallback(() => {
    const el = containerRef?.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setCanvasSize({ w: width, h: height });
    const cvs = canvasRef.current;
    if (cvs) {
      cvs.width = width;
      cvs.height = height;
    }
    // Update image offset
    const ir = getImgRect();
    if (ir) setImgOffset(ir);
  }, [containerRef, getImgRect]);

  useEffect(() => {
    syncSize();
    window.addEventListener('resize', syncSize);
    // Also sync when images load (dimensions change)
    const el = containerRef?.current;
    const img = el?.querySelector('img');
    if (img) {
      img.addEventListener('load', syncSize);
    }
    return () => {
      window.removeEventListener('resize', syncSize);
      if (img) img.removeEventListener('load', syncSize);
    };
  }, [syncSize, containerRef]);

  // Redraw whenever boxes, current drag, or size change
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    ctx.clearRect(0, 0, cvs.width, cvs.height);

    const { x: ox, y: oy, w: iw, h: ih } = imgOffset;
    if (!iw || !ih) return;

    // Draw existing boxes (normalised to image, offset by image position)
    boxes.forEach((box, i) => {
      const bx = ox + box.x * iw;
      const by = oy + box.y * ih;
      const bw = box.width * iw;
      const bh = box.height * ih;

      ctx.fillStyle = 'rgba(239, 68, 68, 0.25)';
      ctx.fillRect(bx, by, bw, bh);
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.8)';
      ctx.lineWidth = 2;
      ctx.strokeRect(bx, by, bw, bh);

      // Delete button (top-right corner)
      const btnSize = 20;
      const btnX = bx + bw - btnSize - 4;
      const btnY = by + 4;
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.beginPath();
      ctx.roundRect(btnX, btnY, btnSize, btnSize, 4);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(btnX + 5, btnY + 5);
      ctx.lineTo(btnX + btnSize - 5, btnY + btnSize - 5);
      ctx.moveTo(btnX + btnSize - 5, btnY + 5);
      ctx.lineTo(btnX + 5, btnY + btnSize - 5);
      ctx.stroke();

      // Index label
      ctx.fillStyle = 'rgba(239, 68, 68, 0.85)';
      ctx.beginPath();
      ctx.roundRect(bx + 4, by + 4, 22, 20, 4);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(i + 1), bx + 15, by + 14);
    });

    // Draw in-progress rect
    if (drawing && start && current) {
      const sx = start.x;
      const sy = start.y;
      const cw = current.x - sx;
      const ch = current.y - sy;
      ctx.fillStyle = 'rgba(99, 102, 241, 0.2)';
      ctx.fillRect(sx, sy, cw, ch);
      ctx.strokeStyle = 'rgba(99, 102, 241, 0.8)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(sx, sy, cw, ch);
      ctx.setLineDash([]);
    }
  }, [boxes, drawing, start, current, canvasSize, imgOffset]);

  const getPos = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const handleMouseDown = (e) => {
    if (disabled) return;
    const { x: ox, y: oy, w: iw, h: ih } = imgOffset;

    // Check if clicking a delete button
    const pos = getPos(e);
    for (let i = boxes.length - 1; i >= 0; i--) {
      const box = boxes[i];
      const bx = ox + box.x * iw;
      const by = oy + box.y * ih;
      const bw = box.width * iw;
      const btnSize = 20;
      const btnX = bx + bw - btnSize - 4;
      const btnY = by + 4;
      if (pos.x >= btnX && pos.x <= btnX + btnSize && pos.y >= btnY && pos.y <= btnY + btnSize) {
        setBoxes(boxes.filter((_, idx) => idx !== i));
        return;
      }
    }

    setDrawing(true);
    setStart(pos);
    setCurrent(pos);
  };

  const handleMouseMove = (e) => {
    if (!drawing) return;
    setCurrent(getPos(e));
  };

  const handleMouseUp = () => {
    if (!drawing || !start || !current) {
      setDrawing(false);
      return;
    }

    const { x: ox, y: oy, w: iw, h: ih } = imgOffset;
    if (!iw || !ih) {
      setDrawing(false);
      return;
    }

    const minPx = 10;
    const dx = Math.abs(current.x - start.x);
    const dy = Math.abs(current.y - start.y);

    if (dx > minPx && dy > minPx) {
      // Convert canvas pixel coords to image-relative normalised coords
      const rawX = Math.min(start.x, current.x);
      const rawY = Math.min(start.y, current.y);

      // Subtract image offset, then normalise to image size
      const nx = Math.max(0, Math.min(1, (rawX - ox) / iw));
      const ny = Math.max(0, Math.min(1, (rawY - oy) / ih));
      const nw = Math.max(0, Math.min(1 - nx, dx / iw));
      const nh = Math.max(0, Math.min(1 - ny, dy / ih));

      if (nw > 0.005 && nh > 0.005) {
        setBoxes([...boxes, { x: nx, y: ny, width: nw, height: nh }]);
      }
    }

    setDrawing(false);
    setStart(null);
    setCurrent(null);
  };

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 z-20"
      style={{ cursor: disabled ? 'default' : 'crosshair' }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    />
  );
}
