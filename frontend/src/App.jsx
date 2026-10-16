import { useState } from 'react';
import Auth from './components/Auth.jsx';
import Dashboard from './components/Dashboard.jsx';
import Chat from './components/Chat.jsx';

export default function App() {
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem('session')); } catch { return null; }
  });
  const [room, setRoom] = useState(null); // the room currently open, or null = on the dashboard

  const login = (data) => {
    localStorage.setItem('session', JSON.stringify(data));
    setSession(data);
  };
  const logout = () => {
    localStorage.removeItem('session');
    setSession(null);
    setRoom(null);
  };

  if (!session) return <Auth onLogin={login} />;
  if (room) return <Chat session={session} room={room} onBack={() => setRoom(null)} onLogout={logout} />;
  return <Dashboard session={session} onOpenRoom={setRoom} onLogout={logout} />;
}
