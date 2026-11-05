import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

function AcceptInvite() {
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const action = params.get('action');
    const cartoonId = params.get('cartoonId');
    const token = params.get('token');

    if (action === 'join' && cartoonId && token) {
      const url = `/api/cartoons/${cartoonId}/invites/${token}`;
      axios.put(url, {}, { withCredentials: true })
        .then(() => {
          alert('Вы присоединились к мультфильму!');
          navigate('/cartoons');
        })
        .catch(err => {
          alert('Ошибка: приглашение недействительно');
          navigate('/');
        });
    } else {
      navigate('/');
    }
  }, [navigate]);

  return <div>Обработка приглашения...</div>;
}

export default AcceptInvite;