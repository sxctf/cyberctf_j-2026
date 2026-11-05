import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import DrawingCanvas from './DrawingCanvas';

function CartoonEditor() {
  const { id } = useParams();
  const [cartoon, setCartoon] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    axios.get(`/api/cartoons/${id}`, { withCredentials: true })
      .then(res => setCartoon(res.data.cartoon))
      .catch(() => navigate('/cartoons'));
    axios.get('/api/me', { withCredentials: true })
      .then(res => setCurrentUser(res.data))
      .catch(() => setCurrentUser(null));
  }, [id, navigate]);

  const isOwner = currentUser && cartoon && currentUser.login === cartoon.ownerLogin;

  const downloadGif = async () => {
    if (!isOwner) return;
    // Получаем все кадры заново
    const res = await axios.get(`/api/cartoons/${id}`, { withCredentials: true });
    const frames = res.data.frames;
    if (frames.length === 0) {
      alert('Нет кадров для создания GIF');
      return;
    }
    // Загружаем все изображения
    const images = await Promise.all(frames.map(f => {
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.src = f.imageData;
      });
    }));
    // Создаём GIF
    const gif = new GIF({
      workers: 2,
      quality: 10,
      width: 400,
      height: 400,
      workerScript: '/gif.worker.js'
    });
    images.forEach(img => {
      gif.addFrame(img, { delay: 200 });
    });
    gif.on('finished', (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${cartoon.title}.gif`;
      a.click();
      URL.revokeObjectURL(url);
    });
    gif.render();
  };

  if (!cartoon) return <div>Загрузка...</div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>🎞️ {cartoon.title}</h2>
        {isOwner && (
          <button className="btn btn-warning" onClick={downloadGif} style={{ background: '#d94f1a', color: '#1a160d' }}>
            📀 Скачать GIF
          </button>
        )}
      </div>
      <DrawingCanvas cartoonId={cartoon.id} />
      <div style={{ marginTop: '1rem' }}>
        <button className="btn" onClick={() => navigate('/cartoons')}>← К списку</button>
      </div>
    </div>
  );
}

export default CartoonEditor;