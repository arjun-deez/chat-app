import { useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';
import { API, request } from '../api.js';
import { APP_NAME, LOGO } from '../brand.js';

const formatSize = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const formatTime = (d) => new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export default function Chat({ session, room, onBack, onLogout }) {
  const { token, user } = session;
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const socketRef = useRef(null);
  const bottomRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    // 1. load this room's history
    request(`/api/rooms/${room.id}/messages`, { token })
      .then(setMessages)
      .catch((err) => (err.status === 401 ? onLogout() : setError(err.message)));

    // 2. open the real-time connection and join this room
    const socket = io(API, { auth: { token } });
    socketRef.current = socket;
    socket.on('connect', () => socket.emit('join_room', room.id));
    socket.on('message', (msg) => setMessages((prev) => [...prev, msg]));
    socket.on('connect_error', (err) => err.message === 'Unauthorized' && onLogout());
    return () => { socket.emit('leave_room'); socket.disconnect(); };
  }, [token, room.id]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const send = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    socketRef.current.emit('message', text);
    setText('');
  };

  const upload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setError('');
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      await request(`/api/rooms/${room.id}/files`, { method: 'POST', body: form, token, isForm: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      fileRef.current.value = '';
    }
  };

  return (
    <div className="chat">
      <header>
        <div className="brand">
          <button className="link back" onClick={onBack} aria-label="Back to rooms">←</button>
          <img src={LOGO} alt="" width="36" height="36" />
          <div>
            <span>{room.name}</span>
            <small>{APP_NAME}</small>
          </div>
        </div>
        <div className="who-am-i">
          {user.username} <button className="link" onClick={onLogout}>Log out</button>
        </div>
      </header>

      <div className="messages">
        {messages.length === 0 && <p className="empty">No messages yet. Say hello or share a file.</p>}
        {messages.map((m) => {
          const mine = m.user === user.id;
          return (
            <div key={m._id} className={`msg ${mine ? 'mine' : ''}`}>
              {!mine && <div className="who">{m.username}</div>}
              {m.text && <p>{m.text}</p>}
              {m.file && (
                <div className="file">
                  {m.file.mimetype?.startsWith('image/') && (
                    <img src={`${API}${m.file.url}`} alt={m.file.name} />
                  )}
                  <a href={`${API}${m.file.url}`} target="_blank" rel="noreferrer" download={m.file.name}>
                    {m.file.name} <small>({formatSize(m.file.size)})</small>
                  </a>
                </div>
              )}
              <time>{formatTime(m.createdAt)}</time>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {error && <p className="error bar" role="alert">{error}</p>}

      <form className="composer" onSubmit={send}>
        <input type="file" ref={fileRef} onChange={upload} hidden />
        <button type="button" onClick={() => fileRef.current.click()} disabled={uploading} aria-label="Share a file">
          {uploading ? 'Uploading…' : 'Attach'}
        </button>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a message" maxLength={2000} />
        <button className="primary">Send</button>
      </form>
    </div>
  );
}
