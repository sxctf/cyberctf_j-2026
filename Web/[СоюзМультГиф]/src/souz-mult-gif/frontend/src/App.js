import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom';
import CartoonList from './components/CartoonList';
import CartoonEditor from './components/CartoonEditor';
import AcceptInvite from './components/AcceptInvite';
import Profile from './components/Profile';
import Register from './components/Register';
import BackgroundAnimation from './components/BackgroundAnimation';
import axios from 'axios';
import './App.css';

function Login() {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState('login');
  const navigate = useNavigate();

  const handleLogin = async () => {
    try {
      const res = await axios.post('/api/login', { login: login, password }, { withCredentials: true });
      if (res.data.require2FA) {
        setStep('2fa');
      } else {
        navigate('/cartoons');
      }
    } catch (err) {
      alert('Ошибка входа. Неправильный логин или пароль.');
    }
  };

  const handle2FA = async () => {
    try {
      const res = await axios.post('/api/login/2fa', { login: login, code }, { withCredentials: true });
      if (res.data.success) navigate('/cartoons');
    } catch (err) {
      alert('Неверный код 2FA');
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2 style={{ textAlign: 'center', color: '#d94f1a' }}>🎬 СОЮЗМУЛЬТГИФ</h2>
        {step === 'login' && (
          <>
            <input placeholder="Логин" value={login} onChange={e => setLogin(e.target.value)} />
            <input type="password" placeholder="Пароль" value={password} onChange={e => setPassword(e.target.value)} />
            <button className="btn" id="login-btn" onClick={handleLogin}>Войти</button>
          </>
        )}
        {step === '2fa' && (
          <>
            <input placeholder="Код 2FA" value={code} onChange={e => setCode(e.target.value)} />
            <button className="btn" id="check-btn" onClick={handle2FA}>Подтвердить</button>
          </>
        )}
      </div>
    </div>
  );
}

function Logout({ onLogout }) {
  const navigate = useNavigate();
  const handleLogout = () => {
    document.cookie = 'auth=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    onLogout();
    navigate('/');
  };
  return <button className="btn" onClick={handleLogout}>Выйти</button>;
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        await axios.get('/api/me', { withCredentials: true });
        setIsAuthenticated(true);
      } catch {
        setIsAuthenticated(false);
      }
    };
    checkAuth();
  }, []);

  return (
    <>
      <BackgroundAnimation />
      <BrowserRouter>
        <div className="navbar">
          <div className="nav-brand">СОЮЗМУЛЬТГИФ</div>
          <div className="nav-links">
            <Link to="/">Главная</Link>
            <Link to="/cartoons">Мультфильмы</Link>
            {isAuthenticated ? (
              <>
                <Link to="/profile">Профиль</Link>
                <Logout onLogout={() => setIsAuthenticated(false)} />
              </>
            ) : (
              <>
                <Link to="/login">Войти</Link>
                <Link to="/register">Регистрация</Link>
              </>
            )}
          </div>
        </div>
        <div className="container">
          <Routes>
            <Route path="/" element={
              <div className="hero">
                <h1>СОЮЗМУЛЬТГИФ</h1>
                <p>Коллективная анимация — по ГОСТ 2.0</p>
                {!isAuthenticated && (
                  <div style={{ marginTop: '1rem' }}>
                    <Link to="/login"><button className="btn">Войти в мастерскую</button></Link>
                  </div>
                )}
              </div>
            } />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/cartoons" element={<CartoonList />} />
            <Route path="/cartoon/:id" element={<CartoonEditor />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/invite" element={<AcceptInvite />} />
          </Routes>
        </div>
      </BrowserRouter>
      </>
  );
}

export default App;