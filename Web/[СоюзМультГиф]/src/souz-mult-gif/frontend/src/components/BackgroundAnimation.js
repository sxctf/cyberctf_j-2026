import React, { useEffect, useRef } from 'react';

function BackgroundAnimation() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationId;
    let time = 0;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', resize);
    resize();

    const draw = () => {
      if (!ctx) return;
      time += 0.01;
      const w = canvas.width;
      const h = canvas.height;
      
      // Полупрозрачный слой для эффекта "мерцания"
      ctx.fillStyle = 'rgba(26, 22, 13, 0.15)';
      ctx.fillRect(0, 0, w, h);
      
      // Абстрактные линии (ретро-волны)
      ctx.beginPath();
      for (let x = 0; x < w; x += 30) {
        const y = h / 2 + Math.sin(x * 0.01 + time) * 80 + Math.cos(x * 0.02 + time * 1.3) * 40;
        ctx.moveTo(x, y);
        ctx.lineTo(x + 20, y + 5);
      }
      ctx.strokeStyle = 'rgba(217, 79, 26, 0.3)';
      ctx.lineWidth = 2;
      ctx.stroke();
      
      // Плавающие точки (звёзды/шумы)
      for (let i = 0; i < 120; i++) {
        const x = (i * 131) % w;
        const y = (i * 253 + time * 50) % h;
        const rad = 1.5 + Math.sin(i + time) * 0.8;
        ctx.beginPath();
        ctx.arc(x, y, rad, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(201, 160, 61, ${0.2 + Math.sin(time + i) * 0.1})`;
        ctx.fill();
      }
      
      // Ретро-полосы (эффект ЭЛТ)
      ctx.fillStyle = 'rgba(0,0,0,0.05)';
      for (let i = 0; i < h; i += 4) {
        ctx.fillRect(0, i, w, 1);
      }
      
      animationId = requestAnimationFrame(draw);
    };
    
    draw();
    
    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', resize);
    };
  }, []);
  
  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: -1,
        pointerEvents: 'none'
      }}
    />
  );
}

export default BackgroundAnimation;