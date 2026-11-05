import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

function SessionView() {
  const { id } = useParams();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState([]);
  const logRef = useRef(null);

  useEffect(() => {
    axios.get(`/api/render-sessions/${id}`, { withCredentials: true })
      .then(res => {
        setSession(res.data.session);
        setLoading(false);
      })
      .catch(() => {
        alert('Доступ запрещён или сессия не найдена');
        setLoading(false);
      });
  }, [id]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  const startRender = async () => {
    if (rendering) return;
    setRendering(true);
    setProgress(0);
    setLog(['[--] Инициализация рендер-движка 0.84...']);
    for (let i = 0; i <= 100; i += 5) {
      await new Promise(r => setTimeout(r, 120));
      setProgress(i);
      if (i % 20 === 0) {
        setLog(prev => [...prev, `[Кадр ${i/20}] Построение освещения...`]);
      }
    }
    setLog(prev => [...prev, '[✅] Рендер завершён. Результат принят ОТК.']);
    try {
      await axios.post(`/api/render-sessions/${id}/render`, {}, { withCredentials: true });
    } catch(e) { console.error(e); }
    setRendering(false);
  };

  if (loading) return <div>Загрузка данных сессии...</div>;
  if (!session) return <div>Сессия не найдена</div>;

  return (
    <div className="session-detail">
      <div style={{ borderBottom: '2px solid #c9a03d', paddingBottom: '0.5rem' }}>
        <h2 style={{ margin: 0 }}>🎞️ {session.title}</h2>
        <div style={{ fontSize: '0.8rem' }}>Код сессии: {session.id} | Владелец: {session.ownerLogin}</div>
      </div>
      <div style={{ marginTop: '1rem' }}>
        <strong>Участники (коллектив):</strong>
        <ul className="participant-list">
          {session.participants.map((p, idx) => <li key={idx}>{p}</li>)}
        </ul>
      </div>
      <button className="btn btn-warning" onClick={startRender} disabled={rendering}>
        {rendering ? 'РЕНДЕРИНГ...' : 'ЗАПУСТИТЬ РЕНДЕРИНГ'}
      </button>
      {rendering && (
        <div className="render-progress">
          <div className="render-bar" style={{ width: `${progress}%` }}></div>
        </div>
      )}
      {log.length > 0 && (
        <div style={{ marginTop: '1.5rem' }}>
          <strong>Лог работы вычислителя:</strong>
          <div className="render-log" ref={logRef}>
            {log.map((msg, i) => <div key={i} style={{ fontFamily: 'monospace', borderBottom: '1px dotted #5e4f2e', padding: '2px 0' }}>{msg}</div>)}
          </div>
        </div>
      )}
    </div>
  );
}

export default SessionView;