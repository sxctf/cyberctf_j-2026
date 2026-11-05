import React, { useState, useEffect } from 'react';
import axios from 'axios';

function Profile() {
  const [login, setLogin] = useState('');

  useEffect(() => {
    axios.get('/api/me', { withCredentials: true })
      .then(res => setLogin(res.data.login))
      .catch(() => setLogin('Не авторизован'));
  }, []);

  return (
    <div className="auth-card" style={{ margin: '0 auto', maxWidth: '500px' }}>
      <h2 style={{ textAlign: 'center', color: '#d94f1a' }}>Карточка аниматора</h2>
      <p><strong>Текущий логин:</strong> <span style={{ background: '#1f1a0f', padding: '2px 6px' }}>{login}</span></p>
    </div>
  );
}

export default Profile;