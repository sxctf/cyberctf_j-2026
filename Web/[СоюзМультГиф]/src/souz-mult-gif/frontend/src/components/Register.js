import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

function Register() {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  const handleRegister = async () => {
    try {
      await axios.post('/api/register', { login, password });
      setMessage('Регистрация успешна! Теперь войдите.');
      setTimeout(() => navigate('/login'), 2000);
    } catch (err) {
      setMessage(err.response?.data?.error || 'Ошибка регистрации');
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2 style={{ textAlign: 'center', color: '#d94f1a' }}>Регистрация аниматора</h2>
        <input placeholder="Логин" value={login} onChange={e => setLogin(e.target.value)} />
        <input type="password" placeholder="Пароль" value={password} onChange={e => setPassword(e.target.value)} />
        <button className="btn" onClick={handleRegister}>Зарегистрироваться</button>
        {message && <p style={{ marginTop: '1rem' }}>{message}</p>}
        <p style={{ marginTop: '1rem', fontSize: '0.8rem' }}>
          Уже есть аккаунт? <a href="/login" style={{ color: '#c9a03d' }}>Войти</a>
        </p>
      </div>
    </div>
  );
}

export default Register;