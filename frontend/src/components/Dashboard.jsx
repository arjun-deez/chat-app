import { useEffect, useMemo, useRef, useState } from 'react';
import { API, request } from '../api.js';
import { APP_NAME, LOGO } from '../brand.js';

const TABS = ['Discover', 'My rooms', 'Activity'];

// Fallback cover for rooms with no image: a repeatable gradient + initials,
// picked from the room's name so it's the same every time you see that room.
const PALETTE = [
  ['#a71f36', '#25262e'], ['#25262e', '#8d1a2e'], ['#e8bdb0', '#25262e'],
  ['#8d1a2e', '#5b5d68'], ['#25262e', '#a71f36'], ['#a71f36', '#5b5d68'],
];
function bannerColors(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function timeAgo(iso) {
  const mins = Math.max(1, Math.round((Date.now() - new Date(iso)) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function RoomCard({ room, onJoin, busy }) {
  const [from, to] = bannerColors(room.name);
  const [showPwForm, setShowPwForm] = useState(false);
  const [pw, setPw] = useState('');
  const initials = room.name.trim().slice(0, 2).toUpperCase();
  const locked = room.hasPassword && !room.isMember;
  const cover = room.imageUrl?.startsWith('/') ? `${API}${room.imageUrl}` : room.imageUrl;

  const go = (e) => {
    e?.preventDefault();
    onJoin(room, locked ? pw : undefined);
  };
  const handleCardClick = () => { if (!showPwForm) (locked ? setShowPwForm(true) : go()); };

  return (
    <article className="room-card">
      <button
        className="room-cover"
        style={cover ? { backgroundImage: `url(${cover})` } : { background: `linear-gradient(135deg, ${from}, ${to})` }}
        onClick={handleCardClick}
        disabled={(room.full && !room.isMember) || busy}
        aria-label={`Open ${room.name}`}
      >
        {!cover && <span className="room-initials">{initials}</span>}
        <span className="room-scrim" />
        {room.hasPassword && <span className="room-lock" title="Password protected">🔒</span>}
        <span className="room-cover-text">
          <strong>{room.name}</strong>
          <small>
            {room.memberCount} / {room.memberLimit} members
            {room.full && !room.isMember ? ' · Full' : ''}
          </small>
        </span>
        <span className="room-arrow" aria-hidden="true">{busy ? '…' : '→'}</span>
      </button>

      {room.lastVisitedAt && <p className="room-visited">Visited {timeAgo(room.lastVisitedAt)}</p>}

      {showPwForm && (
        <form className="room-pw-form" onSubmit={go}>
          <input type="password" autoFocus placeholder="Room password" value={pw}
                 onChange={(e) => setPw(e.target.value)} />
          <button className="primary" disabled={busy}>{busy ? '…' : 'Enter'}</button>
        </form>
      )}
    </article>
  );
}

export default function Dashboard({ session, onOpenRoom, onLogout }) {
  const { token, user } = session;
  const [rooms, setRooms] = useState([]);
  const [tab, setTab] = useState('Discover');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [limit, setLimit] = useState(10);
  const [password, setPassword] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [joiningId, setJoiningId] = useState(null);
  const fileRef = useRef(null);

  const load = () => {
    request('/api/rooms', { token })
      .then(setRooms)
      .catch((err) => (err.status === 401 ? onLogout() : setError(err.message)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]);

  const visible = useMemo(() => {
    if (tab === 'My rooms') return rooms.filter((r) => r.isOwner);
    if (tab === 'Activity')
      return rooms.filter((r) => r.lastVisitedAt).sort((a, b) => b.lastVisitedAt.localeCompare(a.lastVisitedAt));
    return rooms;
  }, [rooms, tab]);

  const pickImage = (e) => {
    const file = e.target.files[0];
    setImageFile(file || null);
    setImagePreview(file ? URL.createObjectURL(file) : null);
  };

  const resetForm = () => {
    setName(''); setLimit(10); setPassword(''); setImageFile(null); setImagePreview(null);
    if (fileRef.current) fileRef.current.value = '';
    setShowForm(false);
  };

  const createRoom = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const form = new FormData();
      form.append('name', name);
      form.append('memberLimit', String(limit));
      form.append('password', password);
      if (imageFile) form.append('image', imageFile);
      const room = await request('/api/rooms', { method: 'POST', token, body: form, isForm: true });
      resetForm();
      load();
      onOpenRoom({ id: room.id, name: room.name });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const enterRoom = async (room, pw) => {
    setError('');
    setJoiningId(room.id);
    try {
      if (!room.isMember) await request(`/api/rooms/${room.id}/join`, { method: 'POST', token, body: { password: pw } });
      onOpenRoom({ id: room.id, name: room.name });
    } catch (err) {
      setError(err.message);
      load();
    } finally {
      setJoiningId(null);
    }
  };

  const openCount = rooms.length;

  return (
    <div className="dashboard">
      <header>
        <div className="brand">
          <img src={LOGO} alt="" width="36" height="36" />
          <span>{APP_NAME}</span>
        </div>
        <div className="who-am-i">
          {user.username} <button className="link" onClick={onLogout}>Log out</button>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>

      <main>
        {tab === 'Discover' && (
          <div className="hero">
            <h1>Pick a room, start talking.</h1>
            <p>{openCount} room{openCount === 1 ? '' : 's'} open right now.</p>
          </div>
        )}

        <div className="dash-top">
          <h2>{tab}</h2>
          <button className="primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Create room'}
          </button>
        </div>

        {showForm && (
          <form className="create-room" onSubmit={createRoom}>
            <div className="create-room-fields">
              <label>
                Room name
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required />
              </label>
              <label className="limit">
                Member limit
                <input type="number" min={2} max={500} value={limit}
                       onChange={(e) => setLimit(e.target.value)} required />
              </label>
              <label>
                Password <small>(optional)</small>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                       placeholder="Leave blank for open room" />
              </label>
            </div>
            <div className="create-room-image">
              <input type="file" ref={fileRef} accept="image/*" onChange={pickImage} hidden id="room-image" />
              <label htmlFor="room-image" className="image-picker" style={imagePreview ? { backgroundImage: `url(${imagePreview})` } : undefined}>
                {!imagePreview && <span>+ Cover image<br /><small>optional</small></span>}
              </label>
              {imagePreview && (
                <button type="button" className="link" onClick={() => { setImageFile(null); setImagePreview(null); if (fileRef.current) fileRef.current.value = ''; }}>
                  Remove image
                </button>
              )}
            </div>
            <button className="primary create-submit" disabled={busy}>{busy ? 'Creating…' : 'Create & open'}</button>
          </form>
        )}

        {error && <p className="error bar" role="alert">{error}</p>}

        {loading ? (
          <p className="empty">Loading rooms…</p>
        ) : visible.length === 0 ? (
          <p className="empty">
            {tab === 'My rooms' ? "You haven't created a room yet." :
             tab === 'Activity' ? 'No rooms visited yet.' : 'No rooms yet. Create the first one.'}
          </p>
        ) : (
          <div className="room-grid">
            {visible.map((r) => (
              <RoomCard key={r.id} room={r} onJoin={enterRoom} busy={joiningId === r.id} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
