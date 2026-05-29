import React,{useEffect,useState}from'react'
import{createRoot}from'react-dom/client'
import{Plus,Trash2,Edit3,RefreshCw,Users,Terminal, Settings,LogOut,Activity,PauseCircle,PlayCircle,RotateCcw,Copy,X,ShieldCheck}from'lucide-react'
import'./styles.css'

const API='/api'


function MiniChart({data,keyName}:{data:any[],keyName:string}){
  const values=data.map(x=>Number(x[keyName]||0))
  const max=Math.max(...values,1)
  const points=values.map((v,i)=>{
    const x=(i/Math.max(values.length-1,1))*100
    const y=36-((v/max)*32)
    return `${x},${y}`
  }).join(' ')

  return <svg className="miniChart" viewBox="0 0 100 40" preserveAspectRatio="none">
    <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}

function countryFlag(country:string){
  const map:any={
    Germany:'🇩🇪',
    Iran:'🇮🇷',
    'United States':'🇺🇸',
    USA:'🇺🇸',
    Russia:'🇷🇺',
    France:'🇫🇷',
    Netherlands:'🇳🇱',
    Turkey:'🇹🇷',
    'United Kingdom':'🇬🇧',
    UK:'🇬🇧',
    Canada:'🇨🇦',
    Finland:'🇫🇮',
    Sweden:'🇸🇪',
    Poland:'🇵🇱',
    Romania:'🇷🇴'
  }
  return map[country] || '🌐'
}

function daysLeft(expire:string){
  if(!expire || String(expire).toLowerCase()==='never') return 0
  const d=new Date(expire)
  if(isNaN(d.getTime())) return 0
  const now=new Date()
  now.setHours(0,0,0,0)
  d.setHours(0,0,0,0)
  return Math.max(0, Math.ceil((d.getTime()-now.getTime())/(1000*60*60*24)))
}

function copyText(txt:string){
  try{
    if(navigator.clipboard && window.isSecureContext){
      navigator.clipboard.writeText(txt)
      return true
    }
  }catch(e){}

  const ta=document.createElement('textarea')
  ta.value=txt
  ta.style.position='fixed'
  ta.style.left='-9999px'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()

  let ok=false
  try{
    ok=document.execCommand('copy')
  }catch(e){
    ok=false
  }

  document.body.removeChild(ta)
  return ok
}

function userConfigText(u:any, settings:any){
  const host = String((settings && settings.publicHost) || window.location.hostname || 'SERVER_HOST').trim()
  const port = String((settings && settings.sshPort) || '22').trim()
  const pass = u.passwordPlain

  return [
    'Host: ' + host,
    'Port: ' + port,
    'Username: ' + (u.username || ''),
    'Password: ' + pass,
    'Expire: ' + (u.expire || ''),
    'Days Left: ' + daysLeft(u.expire),
    'Traffic: ' + (u.trafficUsedText || '0 KB') + ' / ' + (u.trafficLimitText || 'unlimited')
  ].join(String.fromCharCode(10))
}

function App(){
  const[token,setToken]=useState(localStorage.getItem('token')||'')
  const[login,setLogin]=useState({username:'',password:''})
  const[users,setUsers]=useState<any[]>([])
  const[selectedCreateNodes,setSelectedCreateNodes]=useState<string[]>(['0'])
  const[nodes,setNodes]=useState<any[]>([])
  const[nodeForm,setNodeForm]=useState({name:'',base_url:'',token:''})
  const[sessions,setSessions]=useState<any[]>([])
  const[logs,setLogs]=useState<any[]>([])
  const[bannedIps,setBannedIps]=useState<any[]>([])
  const[topUsers,setTopUsers]=useState<any[]>([])
  const[system,setSystem]=useState<any>({})
  const[history,setHistory]=useState<any[]>([])
  const[dashboard,setDashboard]=useState<any>({total:0,online:0,active:0,expired:0,suspended:0})
  const[toast,setToast]=useState('')
  const[tab,setTab]=useState('dashboard')
  const[search,setSearch]=useState('')
  const[filter,setFilter]=useState('all')
  const[modal,setModal]=useState<any>(null)
  const[backups,setBackups]=useState<any[]>([])
  const[settings,setSettings]=useState<any>({publicHost:'',sshPort:'22',telegramBotToken:'',telegramChatId:'',telegramEnabled:false,
  telegramNotifyUserCreated:true,
  telegramNotifyUserDeleted:true,
  telegramNotifyUserUpdated:true,
  telegramNotifyTrafficReset:true,
  telegramNotifyPasswordChanged:true,
  telegramNotifyUserSuspended:true,
  telegramNotifyUserUnsuspended:true,
  telegramNotifyExpired:true,
  telegramNotifyTraffic:true,
  telegramNotifyBackupCreated:true,
  telegramNotifyBackupRestored:false,
  telegramNotifyAdminLogin:true,
  telegramNotifyAdminPasswordChanged:false,
  telegramNotifyFail2BanBan:true,
  telegramNotifyFail2BanUnban:false})
  const[settingsDraft,setSettingsDraft]=useState<any>({publicHost:'',sshPort:'22',telegramBotToken:'',telegramChatId:'',telegramEnabled:false,
  telegramNotifyUserCreated:true,
  telegramNotifyUserDeleted:true,
  telegramNotifyUserUpdated:true,
  telegramNotifyTrafficReset:true,
  telegramNotifyPasswordChanged:true,
  telegramNotifyUserSuspended:true,
  telegramNotifyUserUnsuspended:true,
  telegramNotifyExpired:true,
  telegramNotifyTraffic:true,
  telegramNotifyBackupCreated:true,
  telegramNotifyBackupRestored:false,
  telegramNotifyAdminLogin:true,
  telegramNotifyAdminPasswordChanged:false,
  telegramNotifyFail2BanBan:true,
  telegramNotifyFail2BanUnban:false})
  const[configText,setConfigText]=useState('')
  const[autoBackup,setAutoBackup]=useState<any>({enabled:false})
  const[restoreFile,setRestoreFile]=useState<any>(null)
  const[securityData,setSecurityData]=useState<any>({active:false,bannedIps:[]})
  const[security,setSecurity]=useState({oldPassword:'',newPassword:''})
  const[form,setForm]=useState<any>({username:'',password:'',days:30,trafficLimitGb:0,trafficUsedGb:0,maxOnline:1})

  function show(m:string){setToast(m);setTimeout(()=>setToast(''),3000)}

  async function doLogin(e:any){
    e.preventDefault()
    const r=await fetch(API+'/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(login)})
    const j=await r.json().catch(()=>({}))
    if(j.access_token){localStorage.setItem('token',j.access_token);setToken(j.access_token)}
    else show('Login failed')
  }

  async function loadAutoBackup(){
    const r=await fetch(API+'/autobackup/status',{
      headers:{Authorization:'Bearer '+token}
    })

    if(r.ok){
      setAutoBackup(await r.json())
    }
  }

  async function loadSettings(){
    const r=await fetch(API+'/settings',{headers:{Authorization:'Bearer '+token}})
    if(r.ok){
      const j=await r.json()
      setSettings({publicHost:j.publicHost||'',sshPort:j.sshPort||'22',telegramBotToken:j.telegramBotToken||'',telegramChatId:j.telegramChatId||'',telegramEnabled:j.telegramEnabled==='true',
        telegramNotifyUserCreated:j.telegramNotifyUserCreated!=='false',
        telegramNotifyUserDeleted:j.telegramNotifyUserDeleted!=='false',
        telegramNotifyUserUpdated:j.telegramNotifyUserUpdated!=='false',
        telegramNotifyTrafficReset:j.telegramNotifyTrafficReset!=='false',
        telegramNotifyPasswordChanged:j.telegramNotifyPasswordChanged!=='false',
        telegramNotifyUserSuspended:j.telegramNotifyUserSuspended!=='false',
        telegramNotifyUserUnsuspended:j.telegramNotifyUserUnsuspended!=='false',
        telegramNotifyExpired:j.telegramNotifyExpired!=='false',
        telegramNotifyTraffic:j.telegramNotifyTraffic!=='false',
        telegramNotifyBackupCreated:j.telegramNotifyBackupCreated!=='false',
        telegramNotifyBackupRestored:j.telegramNotifyBackupRestored==='true',
        telegramNotifyAdminLogin:j.telegramNotifyAdminLogin!=='false',
        telegramNotifyAdminPasswordChanged:j.telegramNotifyAdminPasswordChanged==='true',
        telegramNotifyFail2BanBan:j.telegramNotifyFail2BanBan!=='false',
        telegramNotifyFail2BanUnban:j.telegramNotifyFail2BanUnban==='true'}); setSettingsDraft({publicHost:j.publicHost||'',sshPort:j.sshPort||'22',telegramBotToken:j.telegramBotToken||'',telegramChatId:j.telegramChatId||'',telegramEnabled:j.telegramEnabled==='true',
        telegramNotifyUserCreated:j.telegramNotifyUserCreated!=='false',
        telegramNotifyUserDeleted:j.telegramNotifyUserDeleted!=='false',
        telegramNotifyUserUpdated:j.telegramNotifyUserUpdated!=='false',
        telegramNotifyTrafficReset:j.telegramNotifyTrafficReset!=='false',
        telegramNotifyPasswordChanged:j.telegramNotifyPasswordChanged!=='false',
        telegramNotifyUserSuspended:j.telegramNotifyUserSuspended!=='false',
        telegramNotifyUserUnsuspended:j.telegramNotifyUserUnsuspended!=='false',
        telegramNotifyExpired:j.telegramNotifyExpired!=='false',
        telegramNotifyTraffic:j.telegramNotifyTraffic!=='false',
        telegramNotifyBackupCreated:j.telegramNotifyBackupCreated!=='false',
        telegramNotifyBackupRestored:j.telegramNotifyBackupRestored==='true',
        telegramNotifyAdminLogin:j.telegramNotifyAdminLogin!=='false',
        telegramNotifyAdminPasswordChanged:j.telegramNotifyAdminPasswordChanged==='true',
        telegramNotifyFail2BanBan:j.telegramNotifyFail2BanBan!=='false',
        telegramNotifyFail2BanUnban:j.telegramNotifyFail2BanUnban==='true'})
    }
  }

  async function saveSettings(){
    const r=await fetch(API+'/settings',{
      method:'POST',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
      body:JSON.stringify(settingsDraft)
    })
    if(r.ok){setSettings(settingsDraft);show('Settings saved')}
  }

  async function testTelegram(){
    await saveSettings()
    const r=await fetch(API+'/telegram/test',{
      method:'POST',
      headers:{Authorization:'Bearer '+token}
    })
    show(r.ok?'Telegram test sent':await r.text())
  }

  async function loadBackups(){
    const r=await fetch(API+'/backup/list2',{
      headers:{Authorization:'Bearer '+token}
    })

    if(r.ok){
      setBackups(await r.json())
    }
  }

  async function loadSecurity(){
    const r=await fetch(API+'/security',{
      headers:{Authorization:'Bearer '+token}
    })

    if(r.ok){
      setSecurityData(await r.json())
    }
  }

  async function loadSystem(){
    const r=await fetch(API+'/system',{
      headers:{Authorization:'Bearer '+token}
    })

    if(r.ok){
      const data=await r.json()
      setSystem(data)
      setHistory(prev=>[...prev.slice(-19),data])
    }
  }

  async function loadTopUsers(){
    const r=await fetch(API+'/top-users',{headers:{Authorization:'Bearer '+token}})
    if(r.ok)setTopUsers(await r.json())
  }

  async function loadSessions(){
    const r=await fetch(API+'/sessions',{headers:{Authorization:'Bearer '+token}})
    if(r.ok)setSessions(await r.json())
  }

  async function loadNodes(){
    const r=await fetch(API+'/nodes',{headers:{Authorization:'Bearer '+token}})
    if(r.ok)setNodes(await r.json())
  }

  async function loadBannedIps(){
    const r=await fetch(API+'/security/banned-ips',{headers:{Authorization:'Bearer '+token}})
    if(r.ok){
      const j=await r.json()
      setBannedIps(j.ips||[])
    }
  }

  async function unbanIp(ip:string){
    const r=await fetch(API+'/security/unban',{
      method:'POST',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
      body:JSON.stringify({ip})
    })
    if(r.ok){
      show('IP unbanned')
      await loadSecurity()
      await loadBannedIps?.()
    }else{
      show(await r.text())
    }
    show('IP unbanned')
    loadBannedIps()
  }

  async function loadLogs(){
    
  const visibleUsers = users.filter((u:any)=>{
    const q = search.toLowerCase().trim()
    const matchSearch = !q || String(u.username || '').toLowerCase().includes(q)
    const matchFilter =
      filter === 'all' ||
      (filter === 'active' && u.status === 'active') ||
      (filter === 'online' && u.online) ||
      (filter === 'suspended' && u.status === 'suspended') ||
      (filter === 'expired' && u.status === 'expired')
    return matchSearch && matchFilter
  })

if(!token)return
    const r=await fetch(API+'/logs',{headers:{Authorization:'Bearer '+token}})
    if(r.ok)setLogs(await r.json())
  }

  async function load(){
    if(!token)return

    const r = await fetch(API + "/users", {
      headers:{Authorization:"Bearer " + token}
    })

    if(r.ok){
      setUsers(await r.json())
    }

    const d = await fetch(API + "/dashboard", {
      headers:{Authorization:"Bearer " + token}
    })

    if(d.ok){
      setDashboard(await d.json())
    }

    await loadLogs()
    await loadBannedIps()
    await loadSystem()
    await loadTopUsers()
    await loadSecurity()
    await loadSessions()
    await loadBackups()
    await loadAutoBackup()
  }

  async function savePassword(){
    const r=await fetch(API+'/auth/change-password',{
      method:'POST',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
      body:JSON.stringify(security)
    })
    if(r.ok){show('Admin password changed');setSecurity({oldPassword:'',newPassword:''})}
    else show(await r.text())
  }

  async function saveUser(){
    const method=modal?.type==='edit'?'PUT':'POST'
    const url=modal?.type==='edit'
      ? API+'/users/'+modal.username
      : API+'/users?node_ids='+selectedCreateNodes.join(',')
    const payload:any={...form}
    delete payload.trafficUsedGb
    delete payload.traffic_used_gb
    const r=await fetch(url,{method,headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(payload)})
    if(r.ok){
      const uname = modal?.username || form.username
      if(form.password && uname){
        await fetch(API+'/users/'+uname+'/save-password',{
          method:'POST',
          headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
          body:JSON.stringify({password:form.password})
        })
      }
      show('Saved')
      setModal(null)
      load()
    }else show(await r.text())
  }

  async function del(u:string){if(!confirm('Delete '+u+'?'))return;await fetch(API+'/users/'+u,{method:'DELETE',headers:{Authorization:'Bearer '+token}});load()}
  async function reset(u:string){if(!confirm('Reset traffic?'))return;await fetch(API+'/users/'+u+'/reset-traffic',{method:'POST',headers:{Authorization:'Bearer '+token}});load()}
  async function toggle(u:any){
    const disabling = u.statusReason !== 'manual_disabled'
    const action = disabling ? 'manual-disable' : 'manual-enable'

    show(disabling ? 'User disabled' : 'User enabled')

    await fetch(API+'/users/'+u.username+'/'+action,{
      method:'POST',
      headers:{Authorization:'Bearer '+token}
    })

    await load()
    setTimeout(()=>load(),1200)
    setTimeout(()=>load(),3500)
    load()
  }
  function logout(){localStorage.clear();setToken('')}

  useEffect(()=>{if(token)load()},[token])
  useEffect(()=>{if(token)loadSettings()},[token])

  useEffect(()=>{
    if(modal?.type==='edit' && modal?.expire){
      const d=daysLeft(modal.expire)
      setForm((prev:any)=>({...prev, days:d}))
    }
  },[modal?.username, modal?.expire])
  useEffect(()=>{
  const visibleUsers = users.filter((u:any)=>{
    const q = search.toLowerCase().trim()
    const matchSearch = !q || String(u.username || '').toLowerCase().includes(q)
    const matchFilter =
      filter === 'all' ||
      (filter === 'active' && u.status === 'active') ||
      (filter === 'online' && u.online) ||
      (filter === 'suspended' && u.status === 'suspended') ||
      (filter === 'expired' && u.status === 'expired')
    return matchSearch && matchFilter
  })

if(!token)return;const t=setInterval(load,7000);return()=>clearInterval(t)},[token])

  
  const visibleUsers = users.filter((u:any)=>{
    const q = search.toLowerCase().trim()
    const matchSearch = !q || String(u.username || '').toLowerCase().includes(q)
    const matchFilter =
      filter === 'all' ||
      (filter === 'active' && u.status === 'active') ||
      (filter === 'online' && u.online) ||
      (filter === 'suspended' && u.status === 'suspended') ||
      (filter === 'expired' && u.status === 'expired')
    return matchSearch && matchFilter
  })

if(!token)return <main className="loginPage">
    <form className="loginCard" onSubmit={doLogin}>
      <div className="logo"><Terminal size={28}/></div>
      <h1>MRSSH</h1>
      <p>Real SSH Panel</p>
      <input placeholder="Username" value={login.username} onChange={e=>setLogin({...login,username:e.target.value})}/>
      <input placeholder="Password" type="password" value={login.password} onChange={e=>setLogin({...login,password:e.target.value})}/>
      <button className="primary">Login</button>
    </form>
    {toast&&<div className="toast">{toast}</div>}
  </main>

  return <main className="shell">
<aside className="side">
      <div className="brand"><div className="logo small"><Terminal size={20}/></div><div><b>MRSSH</b><span>Live Panel</span></div></div>      <button onClick={()=>{setTab('dashboard')}} className={tab==='dashboard'?'active':''}><Activity size={18}/> Dashboard</button>
      <button onClick={()=>{setTab('users')}} className={tab==='users'?'active':''}><Users size={18}/> Users</button>
      <button onClick={()=>{setTab('backup')}} className={tab==='backup'?'active':''}><RefreshCw size={18}/> Backup</button>
      <button onClick={()=>{setTab('sessions')}} className={tab==='sessions'?'active':''}><Users size={18}/> Sessions</button>
      <button onClick={()=>{setTab('settings')}} className={tab==='settings'?'active':''}><Settings size={18}/> Settings</button>

      <button onClick={()=>{setTab('security')}} className={tab==='security'?'active':''}><ShieldCheck size={18}/> Security</button>

      <button onClick={()=>{setTab('logs')}} className={tab==='logs'?'active':''}><Terminal size={18}/> Logs</button>
      <button onClick={logout}><LogOut size={18}/> Logout</button>
    </aside>

    <section className="main">
        {configText&&<div className="modalBack">
          <div className="modal configModal">
            <button className="x" onClick={()=>setConfigText('')}><X size={18}/></button>
            <h2>Copy Config</h2>

            <textarea
              className="configBox"
              readOnly
              value={configText}
              onFocus={e=>e.currentTarget.select()}
            />

            <button className="primary" onClick={()=>{
              const ok=copyText(configText)
              show(ok?'Config copied':'Copy failed')
            }}>Copy</button>
          </div>
        </div>}


      <header className="header">
        <div><h1>{tab==='logs'?'Audit Logs':tab==='security'?'Security':tab==='dashboard'?'Dashboard':tab==='backup'?'Backup & Restore':tab==='sessions'?'Session Manager':tab==='settings'?'Settings':'SSH Users'}</h1><p>MRSSH control panel</p></div>
        <button className="refresh" onClick={tab==='logs'?loadLogs:load}><RefreshCw size={16}/> Refresh</button>
      </header>

      {tab==='dashboard'&&<>
        <div className="stats">
          <div><span>Total Users</span><b>{dashboard.total}</b><small>accounts</small></div>
          <div><span>Online Users</span><b>{dashboard.online}</b><small>live</small></div>
          <div><span>Active</span><b>{dashboard.active}</b><small>enabled</small></div>
          <div><span>Suspended</span><b>{dashboard.suspended}</b><small>disabled</small></div>
          <div><span>Expired</span><b>{dashboard.expired}</b><small>expired</small></div>
          <div><span>CPU Usage</span><b>{system.cpu||0}%</b><small>server load</small></div>
          <div><span>RAM Usage</span><b>{system.ramPercent||0}%</b><small>{system.ramUsedGb||0}GB / {system.ramTotalGb||0}GB</small></div>
        </div>

        <div className="systemGrid">
          <div className="systemCard">
            <div className="systemTop">
              <h3>Disk Usage</h3>
              <b>{system.diskPercent||0}%</b>
            </div>

            <div className="progress">
              <i style={{width:(system.diskPercent||0)+'%'}}></i>
            </div>

            <small>{system.diskUsedGb||0}GB / {system.diskTotalGb||0}GB</small>
          </div>

          <div className="systemCard">
            <div className="systemTop">
              <h3>Network Speed</h3>
            </div>

            <div className="speedRow">
              <span>↓ {system.downloadText||'0 B/s'}</span>
              <span>↑ {system.uploadText||'0 B/s'}</span>
            </div>
          </div>
        </div>


        <div className="chartGrid">
          <div className="chartCard">
            <span>CPU Live</span>
            <b>{system.cpu||0}%</b>
            <MiniChart data={history} keyName="cpu"/>
          </div>
          <div className="chartCard">
            <span>RAM Live</span>
            <b>{system.ramPercent||0}%</b>
            <MiniChart data={history} keyName="ramPercent"/>
          </div>
          <div className="chartCard">
            <span>Download</span>
            <b>{system.downloadText||'0 B/s'}</b>
            <MiniChart data={history} keyName="downloadMbps"/>
          </div>
          <div className="chartCard">
            <span>Upload</span>
            <b>{system.uploadText||'0 B/s'}</b>
            <MiniChart data={history} keyName="uploadMbps"/>
          </div>
        </div>

        <div className="topTrafficCard">
          <div className="panelTop mini">
            <div>
              <h2>Top Traffic Users</h2>
              <p>Highest usage accounts</p>
            </div>
          </div>

          <div className="topTrafficList">
            {topUsers.map((u:any,i:number)=><div className="topTrafficRow" key={u.username}>
              <span className="rank">#{i+1}</span>
              <div>
                <b>{u.username}</b>
                <small>{u.trafficUsedText || '0 KB'} / {u.trafficLimitText || 'unlimited'}</small>
              </div>
              <div className="miniProgress">
                <i style={{width:Math.min(100,Number(u.trafficPercent||0))+'%'}}></i>
              </div>
            </div>)}
          </div>
        </div>

      </>}

      {tab==='users'&&<>
        <div className="panel">
          <div className="panelTop">
            <div><h2>Users</h2><p>Manage SSH accounts</p></div>
            <button className="primary" onClick={()=>{setForm({username:'',password:'StrongPass123!',days:30,trafficLimitGb:0,trafficUsedGb:0,maxOnline:1});setModal({type:'create'})}}><Plus size={17}/> Create User</button>
          </div>

          <div className="tools">
            <input placeholder="Search username..." value={search} onChange={e=>setSearch(e.target.value)} />
            <select value={filter} onChange={e=>setFilter(e.target.value)}>
              <option value="all">All users</option>
              <option value="active">Active</option>
              <option value="online">Online</option>
              <option value="suspended">Suspended</option>
              <option value="expired">Expired</option>
            </select>
          </div>
<div className="mobileList">
            {visibleUsers.map(u=><div className="userCard" key={u.username}>
              <div className="avatar">{u.username[0]?.toUpperCase()}</div>
              <div className="uInfo">
                <b>{u.username}</b>
                <span>Expire: {u.expire} · {daysLeft(u.expire)}d left · Online: {u.connections}</span>
                <span>Σ {u.trafficUsedText} / {u.trafficLimitText}</span>
                <span className="trafficSplit">↓ {u.trafficDownloadText || '0 KB'} · ↑ {u.trafficUploadText || '0 KB'}</span>
                <div className="bar"><i style={{width:Math.min(100,Number(u.trafficPercent||0))+'%'}}></i></div>
                {u.sessions?.length>0&&<span className="sessionLine">IP: {u.sessions[0].ip} · ISP: {u.sessions[0].isp}</span>}
                <em className={'statusBadge '+(u.statusReason||'active')}>
                  {u.online?'online · ':''}{u.statusLabel || u.status || 'Active'}
                </em>
              </div>
              <button title="Copy Config" onClick={(e)=>{
                e.preventDefault()
                e.stopPropagation()
                setConfigText(userConfigText(u,settings))
              }}><Copy size={16}/></button>
              <button onClick={()=>{setForm({password:u.passwordPlain,days:daysLeft(u.expire),trafficLimitGb:u.trafficLimitGb,maxOnline:u.maxOnline});setModal({type:'edit',username:u.username,expire:u.expire})}}><Edit3 size={16}/></button>
              <button onClick={()=>reset(u.username)}><RotateCcw size={16}/></button>
              <button onClick={()=>toggle(u)}>{u.status==='suspended'?<PlayCircle size={16}/>:<PauseCircle size={16}/>}</button>
              <button onClick={()=>del(u.username)}><Trash2 size={16}/></button>
            </div>)}
          </div>
        </div>
      </>}

      {tab==='security'&&<>
        <div className="securityStats">
          <div className="securityStat">
            <span>Fail2Ban</span>
            <b>{securityData.active?'ACTIVE':'OFFLINE'}</b>
          </div>

          <div className="securityStat">
            <span>Failed Attempts</span>
            <b>{securityData.totalFailed||0}</b>
          </div>

          <div className="securityStat">
            <span>Banned IPs</span>
            <b>{securityData.currentBanned||0}</b>
          </div>

          <div className="securityStat">
            <span>Total Bans</span>
            <b>{securityData.totalBanned||0}</b>
          </div>
        </div>

        <div className="panel">
          <div className="panelTop">
            <div>
              <h2>Banned IP Addresses</h2>
              <p>Current blocked attackers</p>
            </div>
          </div>

          <div className="banList">
            {securityData.bannedIps?.map((ip:string)=><div className="banRow" key={ip}>
              <div>
                <b>{ip}</b>
                <small>Blocked by Fail2Ban</small>
              </div>

              <button onClick={()=>unbanIp(ip)}>Unban</button>
            </div>)}

            {!securityData.bannedIps?.length&&<div className="empty">No banned IPs</div>}
          </div>
        </div>

        <div className="panel">
          <div className="panelTop"><div><h2>Admin Security</h2><p>Change admin password</p></div></div>

          <div className="securityBox">
            <label><b>Old Password</b><input type="password" value={security.oldPassword} onChange={e=>setSecurity({...security,oldPassword:e.target.value})}/></label>
            <label><b>New Password</b><input type="password" value={security.newPassword} onChange={e=>setSecurity({...security,newPassword:e.target.value})}/></label>
            <button className="primary" onClick={savePassword}>Save Password</button>
          </div>
        </div>
      </>}

      
      {tab==='backup'&&<div className="panel">
        <div className="panelTop">
          <div>
            <h2>Backup & Restore</h2>
            <p>Portable MRSSH data backups</p>
          </div>

          <button className="primary" onClick={async()=>{
            await fetch(API+'/backup/create2',{
              method:'POST',
              headers:{Authorization:'Bearer '+token}
            })
            loadBackups()
          }}>
            Create Backup
          </button>
        </div>

        <div className="restoreBox">
          <h3>Upload Restore File</h3>
          <input type="file" accept=".tar.gz" onChange={e=>setRestoreFile(e.target.files?.[0]||null)} />
          <button className="primary" onClick={async()=>{
            if(!restoreFile){show('Choose a backup file first');return}
            const fd=new FormData()
            fd.append('file',restoreFile)
            const r=await fetch(API+'/backup/upload',{
              method:'POST',
              headers:{Authorization:'Bearer '+token},
              body:fd
            })
            if(r.ok){show('Backup uploaded');setRestoreFile(null);loadBackups()}
            else show(await r.text())
          }}>Upload Backup</button>
        </div>

        
        <div className="autoBackupCard">
          <div>
            <h3>Automatic Backups</h3>
            <p>Daily backups at 03:00 AM with automatic cleanup.</p>
          </div>

          <div className="autoBackupStats">
            <div>
              <span>Status</span>
              <label className="switch">
                <input type="checkbox" checked={autoBackup.enabled||false} onChange={async(e)=>{
                  const enabled=e.target.checked

                  const r=await fetch(API+'/autobackup/toggle',{
                    method:'POST',
                    headers:{
                      'Content-Type':'application/json',
                      Authorization:'Bearer '+token
                    },
                    body:JSON.stringify({enabled})
                  })

                  if(r.ok){
                    setAutoBackup(await r.json())
                  }
                }}/>
                <span className="slider"></span>
              </label>
            </div>

            <div>
              <span>Schedule</span>
              <b>03:00 AM</b>
            </div>

            <div>
              <span>Retention</span>
              <b>Last 5 backups</b>
            </div>
          </div>
        </div>


        <div className="backupList">
          {backups.map((b:any)=><div className="backupRow" key={b.name}>
            <div>
              <b>{b.name}</b>
              <small>{b.sizeMb} MB</small>
            </div>

            <div className="backupActions">
              <button className="primary" onClick={async()=>{
                const r=await fetch(API+'/backup/download2/'+b.name,{headers:{Authorization:'Bearer '+token}})
                const blob=await r.blob()
                const url=URL.createObjectURL(blob)
                const a=document.createElement('a')
                a.href=url
                a.download=b.name
                a.click()
                URL.revokeObjectURL(url)
              }}>Download</button>

              <button className="dangerBtn" onClick={async()=>{
                if(!confirm('Delete backup '+b.name+'?'))return
                await fetch(API+'/backup/delete',{
                  method:'POST',
                  headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
                  body:JSON.stringify({filename:b.name})
                })
                loadBackups()
              }}>Delete</button>

              <button className="dangerBtn" onClick={async()=>{
                if(!confirm('Restore '+b.name+'? This will replace panel data and recreate users.'))return
                const r=await fetch(API+'/backup/restore',{
                  method:'POST',
                  headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
                  body:JSON.stringify({filename:b.name})
                })
                if(r.ok){show('Backup restored');load()}
                else show(await r.text())
              }}>Restore</button>
            </div>
          </div>)}
        </div>
      </div>}



      {tab==='sessions'&&<div className="panel">
        <div className="panelTop">
          <div>
            <h2>Live SSH Sessions</h2>
            <p>Online users, IP, ISP and session control</p>
          </div>
        </div>

        <div className="sessionManagerList">
          {sessions.map((x:any,i:number)=><div className="sessionManagerRow" key={i}>
            <div>
              <b>{x.username}</b>
              <small>{x.ip} · {x.isp}</small>
              <small>{countryFlag(x.country)} {x.country || 'Unknown'} {x.city || ''}</small>
            </div>

            <div>
              <span>{x.trafficUsedText} / {x.trafficLimitText}</span>
              <small>Connections: {x.connections}</small>
            </div>

            <button className="dangerBtn" onClick={async()=>{
              if(!confirm('Kill session for '+x.username+'?'))return
              await fetch(API+'/users/'+x.username+'/kill-session',{
                method:'POST',
                headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
                body:JSON.stringify({pid:x.pid})
              })
              load()
            }}>Kill</button>
          </div>)}

          {!sessions.length&&<div className="empty">No active SSH sessions.</div>}
        </div>
      </div>}


      {tab==='settings'&&<div className="panel">
        <div className="panelTop">
          <div>
            <h2>Settings</h2>
            <p>Public server settings for copied user configs</p>
          </div>
        </div>

        <div className="settingsForm">
          <label>Public Host / Domain</label>
          <input
            placeholder="example.com or 1.2.3.4"
            value={settingsDraft.publicHost||''}
            onChange={e=>setSettingsDraft({...settingsDraft,publicHost:e.target.value})}
          />

          <label>SSH Port</label>
          <input
            placeholder="22"
            value={settingsDraft.sshPort||'22'}
            onChange={e=>setSettingsDraft({...settingsDraft,sshPort:e.target.value})}
          />

          <hr/>

          <label>Telegram Enabled</label>
          <input
            type="checkbox"
            checked={!!settingsDraft.telegramEnabled}
            onChange={e=>setSettingsDraft({...settingsDraft,telegramEnabled:e.target.checked})}
          />

          <label>Telegram Bot Token</label>
          <input
              type="password"
            placeholder="123456:ABC..."
            value={settingsDraft.telegramBotToken||''}
            onChange={e=>setSettingsDraft({...settingsDraft,telegramBotToken:e.target.value})}
          />

          <label>Telegram Chat ID</label>
          <input
            placeholder="123456789"
            value={settingsDraft.telegramChatId||''}
            onChange={e=>setSettingsDraft({...settingsDraft,telegramChatId:e.target.value})}
          />

          <div className="telegramChecks">
            <h3>Telegram Events</h3>

            {[
              ['telegramNotifyUserCreated','User Created'],
              ['telegramNotifyUserDeleted','User Deleted'],
              ['telegramNotifyUserUpdated','User Updated'],
              ['telegramNotifyTrafficReset','Traffic Reset'],
              ['telegramNotifyPasswordChanged','Password Changed'],
              ['telegramNotifyUserSuspended','User Suspended'],
              ['telegramNotifyUserUnsuspended','User Unsuspended'],
              ['telegramNotifyExpired','User Expired'],
              ['telegramNotifyTraffic','Traffic Limit Reached'],
              ['telegramNotifyBackupCreated','Backup Created'],
              ['telegramNotifyBackupRestored','Backup Restored'],
              ['telegramNotifyAdminLogin','Admin Login'],
              ['telegramNotifyAdminPasswordChanged','Admin Password Changed'],
              ['telegramNotifyFail2BanBan','Fail2Ban Ban'],
              ['telegramNotifyFail2BanUnban','Fail2Ban Unban']
            ].map(([key,label])=>
              <label className="checkRow" key={key}>
                <input
                  type="checkbox"
                  checked={!!settingsDraft[key]}
                  onChange={e=>setSettingsDraft({...settingsDraft,[key]:e.target.checked})}
                />
                <span>{label}</span>
              </label>
            )}
          </div>

          <button className="primary" onClick={testTelegram}>Test Telegram</button>

          <button className="primary" onClick={saveSettings}>Save Settings</button>
        </div>
      </div>}

            {tab==='logs'&&<div className="panel">
        <div className="panelTop"><div><h2>Audit Logs</h2><p>Latest admin and system activity</p></div></div>
        <div className="logList">
          {logs.map((l:any)=><div className="logRow" key={l.id}>
            <b>{l.action}</b>
            <span>{l.username||'-'}</span>
            <small>{l.detail||''}</small>
            <em>{new Date((l.created_at||0)*1000).toLocaleString()}</em>
          </div>)}
          {!logs.length&&<div className="empty">No logs found.</div>}
        </div>
      </div>}
    </section>

    {modal&&<div className="overlay"><div className="modal">
      <button className="close" onClick={()=>setModal(null)}><X size={18}/></button>
      <h2>{modal.type==='edit'?modal.username:'Create User'}</h2>
      {modal.type==='create'&&<label><b>Username</b><input value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/></label>}
      <label><b>Password</b><input value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></label>
      <label><b>Days</b><input type="number" value={form.days} onChange={e=>setForm({...form,days:e.target.value})}/></label>
      <label><b>Traffic Limit GB</b><input type="number" value={form.trafficLimitGb} onChange={e=>setForm({...form,trafficLimitGb:e.target.value})}/></label>
      <label><b>Traffic Used GB</b><input type="number" value={form.trafficUsedGb} onChange={e=>setForm({...form,trafficUsedGb:e.target.value})}/></label>
      <label><b>Max Online</b><input type="number" value={form.maxOnline} onChange={e=>setForm({...form,maxOnline:e.target.value})}/></label>
      <button className="primary" onClick={saveUser}>Save</button>
    </div></div>}

    {toast&&<div className="toast">{toast}</div>}
  </main>
}

createRoot(document.getElementById('root')!).render(<App/>)
