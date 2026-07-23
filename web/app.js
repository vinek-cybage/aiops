const { useState, useEffect, useRef } = React;

const API = '';  // same origin — FastAPI serves both

// ── Service Catalog (auto-discovered from Loki + Tempo) ───────────────────────
const useCatalog = () => {
  const [catalog, setCatalog] = useState({ apps: [], services: [] });
  useEffect(() => {
    const load = () => fetch(`${API}/api/catalog`).then(r => r.json()).then(setCatalog).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);
  return catalog;
};

// ── Toast ──────────────────────────────────────────────────────────────────────
const Toast = ({ msg, type, onClose }) => {
  useEffect(() => { const t = setTimeout(onClose, 3000); return () => clearTimeout(t); }, []);
  return <div className={`toast toast-${type}`}>{msg}</div>;
};

// ── Shared components ──────────────────────────────────────────────────────────
const SevDot = ({ sev, status }) => {
  const cls = status === 'resolved' ? 'dot-green' : (sev === 'critical' || sev === 'high') ? 'dot-red' : 'dot-yellow';
  return <div className={`status-dot ${cls}`} />;
};

const IncidentRow = ({ inc, onClick, selected }) => (
  <div onClick={onClick} style={{
    padding:'11px 14px', background: selected ? '#6366f108' : '#0f1117',
    border:`1px solid ${selected ? '#6366f1' : '#1e2130'}`, borderRadius:10,
    cursor:'pointer', transition:'all .15s', marginBottom:5,
  }}>
    <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:6}}>
      <SevDot sev={inc.severity} status={inc.status} />
      <span style={{fontSize:12,fontWeight:600,flex:1}}>{inc.title}</span>
      <span className={`badge badge-${inc.status === 'resolved' ? 'resolved' : 'open'}`}>{inc.status}</span>
    </div>
    <div style={{display:'flex',gap:6,flexWrap:'wrap',alignItems:'center'}}>
      <span className={`badge badge-${inc.severity}`}>{inc.severity}</span>
      <span className="badge badge-team">👤 {inc.team}</span>
      {(inc.services || []).map(s => <span key={s} className="badge badge-service">⬡ {s}</span>)}
      {inc.occurrences > 1 && <span className="badge badge-recurring">↺ Recurring {inc.occurrences}×</span>}
      {(inc.cascades||[]).length > 0 && <span className="badge badge-cascade">⬡ {inc.cascades.length} Cascade{inc.cascades.length > 1 ? 's' : ''}</span>}
      <span style={{fontSize:10,color:'#4b5563',marginLeft:'auto'}}>{inc.inc_id}</span>
    </div>
  </div>
);

// ── Dashboard ──────────────────────────────────────────────────────────────────
const Dashboard = ({ incidents, navigate }) => {
  const open = incidents.filter(i => i.status === 'open');
  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-subtitle">Real-time overview of incidents detected by AI</div>
        </div>
      </div>
      <div className="page-content">
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:12}}>
          {[
            {icon:'⚠', bg:'#ef444415', label:'Open Incidents',  val:open.length,                                      color:'#f87171'},
            {icon:'✓', bg:'#34d39915', label:'Resolved',        val:incidents.filter(i=>i.status==='resolved').length, color:'#34d399'},
            {icon:'↺', bg:'#6366f115', label:'Recurring (2+×)', val:incidents.filter(i=>i.occurrences>1).length,       color:'#a78bfa'},
          ].map(c => (
            <div key={c.label} className="card" style={{padding:16}}>
              <div style={{width:32,height:32,borderRadius:8,background:c.bg,display:'flex',alignItems:'center',justifyContent:'center',fontSize:14,marginBottom:10}}>{c.icon}</div>
              <div style={{fontSize:11,color:'#6b7280',fontWeight:500,marginBottom:4}}>{c.label}</div>
              <div style={{fontSize:22,fontWeight:700,color:c.color}}>{c.val}</div>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="card-header">
            <div className="card-title">⚠ Active Incidents</div>
            <span className="card-action" onClick={() => navigate('incidents')}>View all →</span>
          </div>
          <div style={{padding:'8px 10px'}}>
            {open.length === 0
              ? <div style={{textAlign:'center',padding:'24px',color:'#4b5563'}}>No incidents yet — inject a fault in the Demo Service</div>
              : open.map(i => <IncidentRow key={i.id} inc={i} onClick={() => navigate('detail', i.inc_id)} />)
            }
          </div>
        </div>
      </div>
    </>
  );
};

// ── Incidents list ─────────────────────────────────────────────────────────────
const IncidentsPage = ({ incidents, navigate, catalog }) => {
  const [status,  setStatus]  = useState('all');
  const [sev,     setSev]     = useState('all');
  const [appF,    setAppF]    = useState('all');
  const [svcF,    setSvcF]    = useState('all');

  const filtered = incidents.filter(i => {
    if (status !== 'all' && i.status   !== status) return false;
    if (sev    !== 'all' && i.severity !== sev)    return false;
    if (appF   !== 'all' && i.app      !== appF)   return false;
    if (svcF   !== 'all' && !(i.services || []).includes(svcF)) return false;
    return true;
  });

  const Pill = ({ val, active, onClick }) => (
    <button className={`filter-btn ${active ? 'active' : ''}`} onClick={onClick}>
      {val === 'all' ? 'All' : val}
    </button>
  );

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Incidents</div>
          <div className="page-subtitle">{incidents.filter(i=>i.status==='open').length} open · {incidents.filter(i=>i.status==='resolved').length} resolved</div>
        </div>
      </div>

      {/* Filter bar */}
      <div style={{display:'flex',flexDirection:'column',gap:6,padding:'10px 16px',borderBottom:'1px solid #1e2130',background:'#13151f'}}>
        <div style={{display:'flex',gap:6,flexWrap:'wrap',alignItems:'center'}}>
          <span style={{fontSize:10,color:'#4b5563',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',width:48}}>Status</span>
          {['all','open','resolved'].map(f => <Pill key={f} val={f} active={status===f} onClick={() => setStatus(f)} />)}
          <span style={{margin:'0 4px',color:'#1e2130'}}>|</span>
          <span style={{fontSize:10,color:'#4b5563',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',width:32}}>Sev</span>
          {['all','critical','high','medium','low'].map(f => <Pill key={f} val={f} active={sev===f} onClick={() => setSev(f)} />)}
          <span style={{marginLeft:'auto',fontSize:11,color:'#4b5563'}}>{filtered.length} incidents</span>
        </div>
        {(catalog.apps.length > 0 || catalog.services.length > 0) && (
          <div style={{display:'flex',gap:6,flexWrap:'wrap',alignItems:'center'}}>
            <span style={{fontSize:10,color:'#4b5563',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',width:48}}>App</span>
            <Pill val="all" active={appF==='all'} onClick={() => setAppF('all')} />
            {catalog.apps.map(a => <Pill key={a} val={a} active={appF===a} onClick={() => setAppF(a)} />)}
            {catalog.services.length > 0 && <>
              <span style={{margin:'0 4px',color:'#1e2130'}}>|</span>
              <span style={{fontSize:10,color:'#4b5563',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',width:48}}>Service</span>
              <Pill val="all" active={svcF==='all'} onClick={() => setSvcF('all')} />
              {catalog.services.map(s => <Pill key={s} val={s} active={svcF===s} onClick={() => setSvcF(s)} />)}
            </>}
          </div>
        )}
      </div>

      <div className="page-content">
        <div className="card">
          <div style={{padding:'8px 10px'}}>
            {filtered.length === 0
              ? <div style={{textAlign:'center',padding:'32px',color:'#4b5563'}}>No incidents match this filter</div>
              : filtered.map(i => <IncidentRow key={i.id} inc={i} onClick={() => navigate('detail', i.inc_id)} />)
            }
          </div>
        </div>
      </div>
    </>
  );
};

// ── Incident Detail ────────────────────────────────────────────────────────────
const IncidentDetail = ({ incId, navigate, onResolve }) => {
  const [inc, setInc] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/incidents/${incId}`)
      .then(r => r.json())
      .then(d => { setInc(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [incId]);

  if (loading) return <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'100%',color:'#4b5563'}}>Loading…</div>;
  if (!inc)    return <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'100%',color:'#f87171'}}>Incident not found</div>;

  const EV_COLOR = { log:'#818cf8', metric:'#fb923c', pattern:'#34d399' };
  const EV_ICON  = { log:'▤', metric:'◈', pattern:'◎' };

  return (
    <>
      <div className="topbar">
        <span className="card-action" onClick={() => navigate('incidents')}>← Back</span>
        <div style={{marginLeft:16}}>
          <div className="page-title">{inc.inc_id} — {inc.title}</div>
          <div style={{display:'flex',gap:6,marginTop:4,flexWrap:'wrap'}}>
            <span className={`badge badge-${inc.severity}`}>{inc.severity}</span>
            <span className={`badge badge-${inc.status==='resolved'?'resolved':'open'}`}>{inc.status}</span>
            <span className="badge badge-team">👤 {inc.team}</span>
            {inc.occurrences > 1 && <span className="badge badge-recurring">↺ Recurring {inc.occurrences}×</span>}
            {(inc.cascades||[]).length > 0 && <span className="badge badge-cascade">⬡ {inc.cascades.length} Cascade{inc.cascades.length > 1 ? 's' : ''}</span>}
          </div>
        </div>
        {inc.status === 'open' && (
          <div className="topbar-right">
            <button className="btn btn-success" onClick={() => onResolve(inc.inc_id)}>✓ Mark Resolved</button>
          </div>
        )}
      </div>

      <div className="page-content">
        <div style={{display:'grid',gridTemplateColumns:'1fr 300px',gap:14}}>

          {/* LEFT */}
          <div style={{display:'flex',flexDirection:'column',gap:14}}>

            <div className="card">
              <div className="card-header"><div className="card-title">💡 AI Summary</div></div>
              <div style={{padding:'14px 16px',fontSize:12,color:'#c4b5fd',background:'#6366f108',lineHeight:1.7}}>
                {inc.ai_summary}
              </div>
            </div>

            <div className="card">
              <div className="card-header"><div className="card-title">🔍 Root Cause Hypotheses</div></div>
              <div style={{padding:'12px 16px'}}>
                {(inc.hypotheses || []).map(h => (
                  <div key={h.rank} className={`hyp-item ${h.rank===1?'top':''}`}>
                    <div className="hyp-rank" style={{background:h.rank===1?'#6366f1':'#1e2130',color:h.rank===1?'#fff':'#9ca3af'}}>{h.rank}</div>
                    <div style={{flex:1}}>
                      <div style={{fontSize:12,lineHeight:1.5}}>{h.text}</div>
                      <div style={{display:'flex',alignItems:'center',gap:8,marginTop:6}}>
                        <div className="conf-bar">
                          <div className="conf-fill" style={{width:h.confidence+'%',background:h.confidence>=80?'#f87171':h.confidence>=60?'#fbbf24':'#6b7280'}} />
                        </div>
                        <span style={{fontSize:11,fontWeight:600,color:h.confidence>=80?'#f87171':h.confidence>=60?'#fbbf24':'#6b7280'}}>{h.confidence}% confidence</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="card-header"><div className="card-title">📎 Supporting Evidence</div></div>
              <div style={{padding:'12px 16px'}}>
                {(inc.evidence || []).map((e, i) => (
                  <div key={i} className="ev-item">
                    <div className="ev-icon" style={{background:(EV_COLOR[e.type]||'#818cf8')+'20',color:EV_COLOR[e.type]||'#818cf8'}}>{EV_ICON[e.type]||'▤'}</div>
                    <div>
                      <div style={{fontSize:11,fontWeight:600,color:'#e2e8f0',marginBottom:2}}>{e.label}</div>
                      <div style={{fontSize:11,color:'#9ca3af',lineHeight:1.5}}>{e.text}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* RIGHT */}
          <div style={{display:'flex',flexDirection:'column',gap:14}}>

            {inc.occurrences > 1 && (
              <div className="card" style={{borderColor:'#fbbf2440'}}>
                <div className="card-header">
                  <div className="card-title"><span className="badge badge-recurring">↺ Recurring</span></div>
                </div>
                <div style={{padding:'12px 14px',display:'flex',flexDirection:'column',gap:6}}>
                  <div style={{fontSize:12,color:'#fbbf24'}}>Occurred <strong>{inc.occurrences} times</strong></div>
                  <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginTop:4}}>
                    {[['First seen', new Date(inc.first_seen).toLocaleString()],
                      ['Last seen',  new Date(inc.last_seen).toLocaleString()]].map(([k,v]) => (
                      <div key={k} style={{background:'#0f1117',borderRadius:6,padding:'6px 10px'}}>
                        <div style={{fontSize:10,color:'#4b5563',marginBottom:2}}>{k}</div>
                        <div style={{fontSize:11,color:'#e2e8f0'}}>{v}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {(inc.cascades||[]).length > 0 && (
              <div className="card" style={{borderColor:'#fb923c40'}}>
                <div className="card-header">
                  <div className="card-title"><span className="badge badge-cascade">⬡ Downstream Cascades</span></div>
                  <span style={{fontSize:10,color:'#4b5563'}}>{inc.cascades.length} affected</span>
                </div>
                <div style={{padding:'10px 14px',display:'flex',flexDirection:'column',gap:6}}>
                  {inc.cascades.map((c, i) => (
                    <div key={i} style={{display:'flex',alignItems:'flex-start',gap:10,padding:'8px 10px',background:'#0f1117',borderRadius:8,border:'1px solid #1e2130'}}>
                      <div style={{width:6,height:6,borderRadius:'50%',background:'#fb923c',flexShrink:0,marginTop:4,boxShadow:'0 0 6px #fb923c80'}} />
                      <div style={{flex:1}}>
                        <div style={{fontSize:12,fontWeight:500,color:'#fb923c',marginBottom:2}}>{c.service}</div>
                        <div style={{fontSize:11,color:'#9ca3af',lineHeight:1.4}}>{c.symptom}</div>
                        <div style={{fontSize:10,color:'#4b5563',marginTop:3}}>{new Date(c.detected_at).toLocaleTimeString()}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="card">
              <div className="card-header"><div className="card-title">📋 Timeline</div></div>
              <div style={{padding:'12px 14px',display:'flex',flexDirection:'column',gap:10}}>
                {(inc.timeline || []).map((t, i) => (
                  <div key={i} style={{display:'flex',gap:10,alignItems:'flex-start'}}>
                    <span style={{fontSize:10,color:'#4b5563',fontFamily:'monospace',whiteSpace:'nowrap',paddingTop:1}}>{t.time}</span>
                    <div style={{width:6,height:6,borderRadius:'50%',background:t.color,flexShrink:0,marginTop:4,boxShadow:`0 0 6px ${t.color}80`}} />
                    <span style={{fontSize:11,color:'#9ca3af',lineHeight:1.4}}>{t.event}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="card-header"><div className="card-title">⬡ Affected Services</div></div>
              <div style={{padding:'12px 14px',display:'flex',flexWrap:'wrap',gap:6}}>
                {(inc.services || []).map(s => <span key={s} className="badge badge-service">⬡ {s}</span>)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

// ── Service Tag Picker ─────────────────────────────────────────────────────────
const ServicePicker = ({ selected, catalog, onChange }) => {
  const all = [...new Set([...catalog.apps, ...catalog.services])].sort();
  const toggle = (s) => onChange(selected.includes(s) ? selected.filter(x => x !== s) : [...selected, s]);
  return (
    <div style={{display:'flex',flexDirection:'column',gap:6}}>
      <div style={{display:'flex',flexWrap:'wrap',gap:4,minHeight:32,padding:'6px 8px',background:'#0f1117',border:'1px solid #1e2130',borderRadius:8}}>
        {selected.length === 0
          ? <span style={{fontSize:11,color:'#4b5563'}}>No services selected</span>
          : selected.map(s => (
            <span key={s} style={{display:'inline-flex',alignItems:'center',gap:4,padding:'2px 8px',borderRadius:20,background:'#2d1f4d',color:'#c084fc',fontSize:10,fontWeight:500}}>
              ⬡ {s}
              <span style={{cursor:'pointer',opacity:.7,marginLeft:2}} onClick={() => toggle(s)}>✕</span>
            </span>
          ))
        }
      </div>
      {all.length > 0 ? (
        <div style={{display:'flex',flexWrap:'wrap',gap:4}}>
          {all.map(s => {
            const isApp = catalog.apps.includes(s);
            const sel   = selected.includes(s);
            return (
              <span key={s} onClick={() => toggle(s)} style={{
                cursor:'pointer',padding:'2px 8px',borderRadius:20,fontSize:10,fontWeight:500,
                background: sel ? (isApp ? '#1e3a5f' : '#2d1f4d') : '#13151f',
                color:      sel ? (isApp ? '#60a5fa' : '#c084fc') : '#6b7280',
                border:`1px solid ${sel ? (isApp ? '#60a5fa40' : '#c084fc40') : '#1e2130'}`,
                transition:'all .1s',
              }}>
                {isApp ? '▦' : '⬡'} {s}
              </span>
            );
          })}
        </div>
      ) : (
        <span style={{fontSize:10,color:'#4b5563'}}>No services discovered yet — waiting for logs/traces</span>
      )}
      <div style={{display:'flex',gap:4,marginTop:2}}>
        <span style={{fontSize:10,color:'#4b5563'}}>▦ = App &nbsp; ⬡ = Service</span>
      </div>
    </div>
  );
};

// ── Admin Page ─────────────────────────────────────────────────────────────────
const AdminPage = ({ currentUser, showToast, catalog }) => {
  const [teams, setTeams]   = useState([]);
  const [users, setUsers]   = useState([]);
  const [tForm, setTForm]   = useState({ name:'', services:[] });
  const [uForm, setUForm]   = useState({ name:'', team_id:'', role:'member' });

  const headers = { 'X-User-Id': String(currentUser?.id || '') };

  const reload = () => {
    fetch(`${API}/api/teams`).then(r=>r.json()).then(setTeams);
    fetch(`${API}/api/users`).then(r=>r.json()).then(setUsers);
  };
  useEffect(reload, []);

  const addTeam = async () => {
    if (!tForm.name.trim()) return;
    const r = await fetch(`${API}/api/teams`, { method:'POST', headers:{...headers,'Content-Type':'application/json'}, body: JSON.stringify({name:tForm.name, services:tForm.services}) });
    if (r.ok) { showToast('Team created','success'); setTForm({name:'', services:[]}); reload(); }
    else showToast('Failed to create team','error');
  };

  const delTeam = async (id) => {
    await fetch(`${API}/api/teams/${id}`, { method:'DELETE', headers });
    showToast('Team deleted','success'); reload();
  };

  const addUser = async () => {
    if (!uForm.name.trim()) return;
    const r = await fetch(`${API}/api/users`, { method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body: JSON.stringify({name:uForm.name, team_id: uForm.team_id ? parseInt(uForm.team_id) : null, role:uForm.role}) });
    if (r.ok) { showToast('User created','success'); setUForm({name:'',team_id:'',role:'member'}); reload(); }
    else showToast('Failed to create user','error');
  };

  const delUser = async (id) => {
    await fetch(`${API}/api/users/${id}`, { method:'DELETE', headers });
    showToast('User deleted','success'); reload();
  };

  return (
    <>
      <div className="topbar">
        <div>
          <div className="page-title">Admin</div>
          <div className="page-subtitle">Manage teams, services, and users</div>
        </div>
        {catalog.last_updated && (
          <div style={{marginLeft:'auto',fontSize:10,color:'#4b5563'}}>
            <span className="live-dot" style={{display:'inline-block',marginRight:5}} />
            Catalog: {catalog.apps.length} apps · {catalog.services.length} services
          </div>
        )}
      </div>
      <div className="page-content">
        <div className="admin-grid">

          <div className="card">
            <div className="card-header"><div className="card-title">⬡ Teams</div></div>
            <div style={{padding:14,display:'flex',flexDirection:'column',gap:8}}>
              {teams.map(t => (
                <div key={t.id} className="table-row">
                  <div style={{flex:1}}>
                    <div style={{fontSize:12,fontWeight:500,marginBottom:3}}>{t.name}</div>
                    <div>{(t.services||[]).map(s=><span key={s} className="tag">⬡ {s}</span>)}</div>
                  </div>
                  <button className="del-btn" onClick={()=>delTeam(t.id)}>Remove</button>
                </div>
              ))}
              <div style={{borderTop:'1px solid #1e2130',paddingTop:10,marginTop:4,display:'flex',flexDirection:'column',gap:8}}>
                <div className="form-field">
                  <label className="form-label">Team Name</label>
                  <input className="form-input" placeholder="e.g. Payments Team" value={tForm.name} onChange={e=>setTForm({...tForm,name:e.target.value})} />
                </div>
                <div className="form-field">
                  <label className="form-label">Assign Services</label>
                  <ServicePicker selected={tForm.services} catalog={catalog} onChange={v => setTForm({...tForm, services:v})} />
                </div>
                <button className="btn btn-primary" style={{alignSelf:'flex-start'}} onClick={addTeam}>+ Add Team</button>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header"><div className="card-title">👤 Users</div></div>
            <div style={{padding:14,display:'flex',flexDirection:'column',gap:8}}>
              {users.map(u => (
                <div key={u.id} className="table-row">
                  <div style={{flex:1}}>
                    <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:2}}>
                      <span style={{fontSize:12,fontWeight:500}}>{u.name}</span>
                      <span className={`badge ${u.role==='admin'?'badge-critical':'badge-info'}`} style={{fontSize:9}}>{u.role}</span>
                    </div>
                    <div style={{fontSize:10,color:'#4b5563'}}>{u.team_name || 'No team'}</div>
                  </div>
                  <button className="del-btn" onClick={()=>delUser(u.id)}>Remove</button>
                </div>
              ))}
              <div style={{borderTop:'1px solid #1e2130',paddingTop:10,marginTop:4,display:'flex',flexDirection:'column',gap:8}}>
                <div className="form-row">
                  <div className="form-field">
                    <label className="form-label">Name</label>
                    <input className="form-input" placeholder="e.g. Dave" value={uForm.name} onChange={e=>setUForm({...uForm,name:e.target.value})} />
                  </div>
                  <div className="form-field">
                    <label className="form-label">Role</label>
                    <select className="form-input" value={uForm.role} onChange={e=>setUForm({...uForm,role:e.target.value})}>
                      <option value="member">Member</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                </div>
                <div className="form-field">
                  <label className="form-label">Team</label>
                  <select className="form-input" value={uForm.team_id} onChange={e=>setUForm({...uForm,team_id:e.target.value})}>
                    <option value="">No team (admin)</option>
                    {teams.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
                <button className="btn btn-primary" style={{alignSelf:'flex-start'}} onClick={addUser}>+ Add User</button>
              </div>
            </div>
          </div>

        </div>
      </div>
    </>
  );
};

// ── Root App ───────────────────────────────────────────────────────────────────
function App() {
  const [page,        setPage]        = useState('dashboard');
  const [incId,       setIncId]       = useState(null);
  const [incidents,   setIncidents]   = useState([]);
  const [toast,       setToast]       = useState(null);
  const [users,       setUsers]       = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const catalog = useCatalog();

  const showToast = (msg, type='success') => setToast({ msg, type });
  const navigate  = (p, id = null) => { setPage(p); if (id) setIncId(id); };

  const authHeaders = currentUser ? { 'X-User-Id': String(currentUser.id) } : {};

  const fetchIncidents = () =>
    fetch(`${API}/api/incidents`, { headers: authHeaders })
      .then(r => r.json()).then(setIncidents).catch(console.error);

  const fetchUsers = () =>
    fetch(`${API}/api/users`).then(r => r.json()).then(data => {
      setUsers(data);
      if (!currentUser && data.length > 0) {
        const savedId = localStorage.getItem('aiops_user_id');
        const saved   = savedId ? data.find(u => u.id === parseInt(savedId)) : null;
        const adminUser = data.find(u => u.role === 'admin');
        setCurrentUser(saved || adminUser || data[0]);
      }
    }).catch(console.error);

  useEffect(() => { fetchUsers(); }, []);
  useEffect(() => { if (currentUser !== null) fetchIncidents(); }, [currentUser]);

  useEffect(() => {
    if (currentUser === null) return;
    const t = setInterval(fetchIncidents, 10000);
    return () => clearInterval(t);
  }, [currentUser]);

  const handleResolve = async (id) => {
    await fetch(`${API}/api/incidents/${id}/resolve`, { method:'PATCH', headers: authHeaders });
    await fetchIncidents();
    showToast(`${id} resolved`, 'success');
    navigate('incidents');
  };

  const isAdmin    = currentUser?.role === 'admin';
  const openCount  = incidents.filter(i => i.status === 'open').length;
  const activePage = page === 'detail' ? 'incidents' : page;

  const NAV_ITEMS = [
    {icon:'▦', label:'Dashboard', page:'dashboard'},
    {icon:'⚠', label:'Incidents', page:'incidents', badge:true},
    ...(isAdmin ? [{icon:'⚙', label:'Admin', page:'admin'}] : []),
  ];

  const renderPage = () => {
    switch (page) {
      case 'dashboard': return <Dashboard incidents={incidents} navigate={navigate} />;
      case 'incidents': return <IncidentsPage incidents={incidents} navigate={navigate} catalog={catalog} />;
      case 'detail':    return <IncidentDetail incId={incId} navigate={navigate} onResolve={handleResolve} />;
      case 'admin':     return isAdmin ? <AdminPage currentUser={currentUser} showToast={showToast} catalog={catalog} /> : <Dashboard incidents={incidents} navigate={navigate} />;
      default:          return <Dashboard incidents={incidents} navigate={navigate} />;
    }
  };

  const initials = (name='?') => name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-icon">⬡</div>
          <span className="logo-text">AIOps</span>
        </div>
        <nav className="nav">
          <div className="nav-section">Main</div>
          {NAV_ITEMS.map(({icon, label, page:p, badge}) => (
            <div key={p} className={`nav-item ${activePage===p?'active':''}`} onClick={()=>navigate(p)}>
              <span style={{fontSize:14}}>{icon}</span> {label}
              {badge && openCount > 0 && <span className="nav-badge">{openCount}</span>}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div style={{fontSize:10,color:'#4b5563',marginBottom:6,fontWeight:500,textTransform:'uppercase',letterSpacing:'.06em'}}>Viewing as</div>
          <select
            style={{width:'100%',background:'#0f1117',border:'1px solid #1e2130',borderRadius:8,padding:'6px 10px',color:'#e2e8f0',fontSize:12,fontFamily:'Inter,sans-serif',cursor:'pointer',outline:'none',marginBottom:8}}
            value={currentUser?.id || ''}
            onChange={e => {
              const u = users.find(u => u.id === parseInt(e.target.value));
              if (u) { setCurrentUser(u); localStorage.setItem('aiops_user_id', u.id); navigate('dashboard'); }
            }}>
            {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
            <div className="avatar">{initials(currentUser?.name)}</div>
            <div>
              <div style={{fontSize:12,fontWeight:500}}>{currentUser?.name || '…'}</div>
              <div style={{fontSize:10,color:'#4b5563'}}>{currentUser?.team_name || 'Administrator'} · {currentUser?.role}</div>
            </div>
          </div>
        </div>
      </aside>
      <div className="page-shell">{renderPage()}</div>
      {toast && <Toast msg={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
