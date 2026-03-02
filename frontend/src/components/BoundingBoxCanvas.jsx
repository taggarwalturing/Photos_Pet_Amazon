import { useRef, useState, useEffect, useCallback } from 'react';

/**
 * Transparent canvas overlay for drawing bounding-box blur regions.
 *
 * Props:
 *   containerRef – ref to the element the canvas should cover
 *   boxes / setBoxes – state array of { x, y, width, height } in normalised 0-1 coords
 *   disabled – disables drawing when true
 */
export default function BoundingBoxCanvas({ containerRef, boxes, setBoxes, disabled }) {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [start, setStart] = useState(null);
  const [current, setCurrent] = useState(null);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });

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
  }, [containerRef]);

  useEffect(() => {
    syncSize();
    window.addEventListener('resize', syncSize);
    return () => window.removeEventListener('resize', syncSize);
  }, [syncSize]);

  // Redraw whenever boxes, current drag, or size change
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext('2d');
    ctx.clearRect(0, 0, cvs.width, cvs.height);

    const { w, h } = canvasSize;
    if (!w || !h) return;

    // Draw existing boxes
    boxes.forEach((box, i) => {
      const bx = box.x * w;
      const by = box.y * h;
      const bw = box.width * w;
      const bh = box.height * h;

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
  }, [boxes, drawing, start, current, canvasSize]);

  const getPos = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const handleMouseDown = (e) => {
    if (disabled) return;
    const { w, h } = canvasSize;

    // Check if clicking a delete button
    const pos = getPos(e);
    for (let i = boxes.length - 1; i >= 0; i--) {
      const box = boxes[i];
      const bx = box.x * w;
      const by = box.y * h;
      const bw = box.width * w;
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

    const { w, h } = canvasSize;
    const minPx = 10;
    const dx = Math.abs(current.x - start.x);
    const dy = Math.abs(current.y - start.y);

    if (dx > minPx && dy > minPx) {
      const nx = Math.min(start.x, current.x) / w;
      const ny = Math.min(start.y, current.y) / h;
      const nw = dx / w;
      const nh = dy / h;
      setBoxes([...boxes, { x: nx, y: ny, width: nw, height: nh }]);
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
