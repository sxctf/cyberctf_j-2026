import React, { useRef, useState, useEffect } from 'react';
import axios from 'axios';

function DrawingCanvas({ cartoonId, onFrameSaved }) {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [brushColor, setBrushColor] = useState('#d94f1a');
  const [brushSize, setBrushSize] = useState(5);
  const [framesList, setFramesList] = useState([]);
  const [selectedFrame, setSelectedFrame] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [animationInterval, setAnimationInterval] = useState(null);
  const CANVAS_SIZE = 640; // увеличенный размер

  // Загрузка существующих кадров
  useEffect(() => {
    if (cartoonId) {
      axios.get(`/api/cartoons/${cartoonId}`, { withCredentials: true })
        .then(res => setFramesList(res.data.frames))
        .catch(console.error);
    }
  }, [cartoonId]);

  // Инициализация canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    canvas.width = CANVAS_SIZE;
    canvas.height = CANVAS_SIZE;
    ctx.fillStyle = '#f0e6b2';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = brushColor;
    ctx.lineWidth = brushSize;
    ctx.lineCap = 'round';
    ctx.beginPath();
    if (previewData) {
      const img = new Image();
      img.onload = () => {
        ctx.drawImage(img, 0, 0);
        ctx.beginPath();
      };
      img.src = previewData;
    }
  }, [previewData, brushColor, brushSize, CANVAS_SIZE]);

  // Очистка интервала при размонтировании
  useEffect(() => {
    return () => {
      if (animationInterval) clearInterval(animationInterval);
    };
  }, [animationInterval]);

  const startDrawing = (e) => {
    setDrawing(true);
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    let x = (e.clientX - rect.left) * scaleX;
    let y = (e.clientY - rect.top) * scaleY;
    x = Math.min(Math.max(0, x), canvas.width);
    y = Math.min(Math.max(0, y), canvas.height);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const stopDrawing = () => setDrawing(false);

  const draw = (e) => {
    if (!drawing) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    let x = (e.clientX - rect.left) * scaleX;
    let y = (e.clientY - rect.top) * scaleY;
    x = Math.min(Math.max(0, x), canvas.width);
    y = Math.min(Math.max(0, y), canvas.height);
    ctx.strokeStyle = brushColor;
    ctx.lineWidth = brushSize;
    ctx.lineTo(x, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const clearCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#f0e6b2';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
  };

  const saveFrame = async () => {
    const canvas = canvasRef.current;
    const imageData = canvas.toDataURL();
    try {
      if (selectedFrame !== null) {
        await axios.put(`/api/cartoons/${cartoonId}/frames/${selectedFrame}`, { imageData }, { withCredentials: true });
      } else {
        await axios.post(`/api/cartoons/${cartoonId}/frames`, { imageData }, { withCredentials: true });
      }
      const res = await axios.get(`/api/cartoons/${cartoonId}`, { withCredentials: true });
      setFramesList(res.data.frames);
      setSelectedFrame(null);
      if (onFrameSaved) onFrameSaved();
    } catch (err) {
      alert('Ошибка сохранения');
    }
  };

  const loadFrame = (frame) => {
    setPreviewData(frame.imageData);
    setSelectedFrame(frame.id);
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#f0e6b2';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0);
      ctx.beginPath();
    };
    img.src = frame.imageData;
  };

  const deleteFrame = async (frameId) => {
    if (window.confirm('Удалить кадр?')) {
      await axios.delete(`/api/cartoons/${cartoonId}/frames/${frameId}`, { withCredentials: true });
      const res = await axios.get(`/api/cartoons/${cartoonId}`, { withCredentials: true });
      setFramesList(res.data.frames);
      if (selectedFrame === frameId) {
        setSelectedFrame(null);
        setPreviewData(null);
        clearCanvas();
      }
    }
  };

  const stopAnimation = () => {
    if (animationInterval) {
      clearInterval(animationInterval);
      setAnimationInterval(null);
    }
  };

  const playAnimation = () => {
    if (framesList.length === 0) return;
    stopAnimation();
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let idx = 0;
    const interval = setInterval(() => {
      const img = new Image();
      img.onload = () => {
        ctx.fillStyle = '#f0e6b2';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        ctx.beginPath();
      };
      img.src = framesList[idx].imageData;
      idx = (idx + 1) % framesList.length;
    }, 200);
    setAnimationInterval(interval);
  };

  return (
    <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
      <div>
        <canvas
          ref={canvasRef}
          onMouseDown={startDrawing}
          onMouseUp={stopDrawing}
          onMouseMove={draw}
          onMouseLeave={stopDrawing}
          style={{ border: '2px solid #c9a03d', background: '#f0e6b2', cursor: 'crosshair', width: `${CANVAS_SIZE}px`, height: `${CANVAS_SIZE}px` }}
        />
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <input type="color" value={brushColor} onChange={e => setBrushColor(e.target.value)} />
          <input type="range" min="1" max="20" value={brushSize} onChange={e => setBrushSize(e.target.value)} />
          <button className="btn" onClick={clearCanvas}>Очистить</button>
          <button className="btn btn-warning" onClick={saveFrame}>Сохранить кадр</button>
          <button className="btn" onClick={playAnimation}>Просмотр</button>
          <button className="btn" onClick={stopAnimation}>Стоп</button>
        </div>
      </div>
      <div style={{ width: '320px' }}>
        <h4>Кадры ({framesList.length})</h4>
        <div style={{ maxHeight: '500px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {framesList.map(f => (
            <div key={f.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: '#2c261a', padding: '0.3rem' }}>
              <img src={f.imageData} alt={`frame ${f.order}`} style={{ width: '50px', height: '50px', border: '1px solid #c9a03d' }} />
              <span>Кадр {f.order+1}</span>
              <button className="btn" onClick={() => loadFrame(f)}>Загрузить</button>
              <button className="btn" onClick={() => deleteFrame(f.id)}>🗑️</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default DrawingCanvas;