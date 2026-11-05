import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import InviteModal from './InviteModal';

function CartoonList() {
  const [cartoons, setCartoons] = useState([]);
  const [title, setTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [inviteUrl, setInviteUrl] = useState('');

  const loadCartoons = async () => {
    try {
      const res = await axios.get('/api/cartoons', { withCredentials: true });
      setCartoons(res.data.cartoons);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadCartoons(); }, []);

  const createCartoon = async () => {
    if (!title) return;
    await axios.post('/api/cartoons', { title }, { withCredentials: true });
    setTitle('');
    loadCartoons();
  };

  const generateInvite = async (cartoonId) => {
    try {
      const res = await axios.post(`/api/cartoons/${cartoonId}/invites`, {}, { withCredentials: true });
      const fullUrl = `${window.location.origin}${res.data.inviteUrl}`;
      setInviteUrl(fullUrl);
      setModalOpen(true);
    } catch (err) {
      if (err.response?.status === 403) {
        alert('Только владелец может создавать приглашения.');
      } else {
        alert('Ошибка при создании приглашения');
      }
    }
  };

  const deleteCartoon = async (cartoonId) => {
    if (window.confirm('Удалить мультфильм?')) {
      try {
        await axios.delete(`/api/cartoons/${cartoonId}`, { withCredentials: true });
        loadCartoons();
      } catch (err) {
        if (err.response?.status === 403) {
          alert('Только владелец может удалить мультфильм.');
        } else {
          alert('Ошибка при удалении мультфильма');
        }
      }
    }
  };

  if (loading) return <div>Загрузка...</div>;

  return (
    <div>
      <InviteModal isOpen={modalOpen} onClose={() => setModalOpen(false)} inviteUrl={inviteUrl} />
      <h2>Мои мультфильмы</h2>
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Название" style={{ flex: 1, background: '#1f1a0f', border: '1px solid #c9a03d', padding: '0.5rem' }} />
        <button className="btn" onClick={createCartoon}>Создать</button>
      </div>
      <div className="card-grid">
        {cartoons.map(c => (
          <div key={c.id} className="session-card">
            <h3 style={{ fontFamily: "'Roboto Condensed', sans-serif", color: '#d94f1a', fontSize: '1.3rem', margin: '0.5rem 0' }}>
              {c.title}
            </h3>
            <p>Владелец: {c.ownerLogin}</p>
            <p>Участников: {c.participants.length}</p>
            <div style={{ marginTop: '1rem' }}>
              <Link to={`/cartoon/${c.id}`}><button className="btn">Рисовать</button></Link>
              <button className="btn" style={{ marginLeft: '0.5rem' }} onClick={() => generateInvite(c.id)}>Пригласить</button>
            </div>
            <div style={{ marginTop: '0.5rem' }}>
              {c.ownerLogin === c.participants[0] && (
                <button className="btn" style={{ marginLeft: '4rem', background: '#a33c12' }} onClick={() => deleteCartoon(c.id)}>Удалить</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default CartoonList;