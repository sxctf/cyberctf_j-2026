import React from 'react';

function InviteModal({ isOpen, onClose, inviteUrl }) {
  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0,
      width: '100%', height: '100%',
      backgroundColor: 'rgba(0,0,0,0.8)',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      zIndex: 1000,
      fontFamily: 'PT Mono, monospace'
    }} onClick={onClose}>
      <div style={{
        background: '#2c261a',
        border: '2px solid #d94f1a',
        borderRadius: '8px',
        padding: '2rem',
        maxWidth: '500px',
        width: '90%',
        boxShadow: '0 0 20px rgba(217,79,26,0.3)'
      }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ color: '#d94f1a', marginTop: 0, textAlign: 'center' }}>📢 Приглашение создано!</h3>
        <p style={{ color: '#e6d5b8', marginBottom: '0.5rem' }}>Отправьте эту ссылку соавтору:</p>
        <div style={{
          background: '#1f1a0f',
          border: '1px solid #c9a03d',
          padding: '0.8rem',
          wordBreak: 'break-all',
          borderRadius: '4px',
          marginBottom: '1.5rem',
          color: '#facc15',
          fontSize: '0.9rem'
        }}>
          {inviteUrl}
        </div>
        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
          <button className="btn" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}

export default InviteModal;