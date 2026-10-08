import React, { useEffect, useRef, useState } from 'react'

const jsonFetch = async (url, options) => {
  const response = await fetch(url, options)
  const body = await response.text()
  let data
  try { data = body ? JSON.parse(body) : {} } catch { data = { detail: body || `Server returned HTTP ${response.status}.` } }
  if (!response.ok) throw new Error(data.detail || 'Something went wrong. Please try again.')
  return data
}

function Sparkle({ small = false }) { return <span className={`sparkle ${small ? 'sparkle-small' : ''}`} aria-hidden="true">✳</span> }

export default function App() {
  const [auth, setAuth] = useState(null)
  const [identity, setIdentity] = useState({ name: '', dob: '' })
  const [dobText, setDobText] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [authError, setAuthError] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [finished, setFinished] = useState(false)
  const [visitChoicePending, setVisitChoicePending] = useState(false)
  const [welcomeChoicesVisible, setWelcomeChoicesVisible] = useState(true)
  const [helpChoicesVisible, setHelpChoicesVisible] = useState(false)
  const [chatSlotChoices, setChatSlotChoices] = useState([])
  const [chatSelectedSlot, setChatSelectedSlot] = useState(null)
  const [bookingStep, setBookingStep] = useState('')
  const [days, setDays] = useState([])
  const [specialties, setSpecialties] = useState([])
  const [doctors, setDoctors] = useState([])
  const [slots, setSlots] = useState([])
  const [booking, setBooking] = useState({ day: null, specialty: null, doctor: null, slot: null, appointment: null })
  const [bookingBusy, setBookingBusy] = useState(false)
  const [manageMode, setManageMode] = useState('')
  const [appointments, setAppointments] = useState([])
  const [manageTarget, setManageTarget] = useState(null)
  const [manageDays, setManageDays] = useState([])
  const [manageSlots, setManageSlots] = useState([])
  const [feedbackSent, setFeedbackSent] = useState({})
  const [activeFeedback, setActiveFeedback] = useState(null)
  const [feedbackReason, setFeedbackReason] = useState('confusing')
  const [feedbackComment, setFeedbackComment] = useState('')
  const [remindersBusy, setRemindersBusy] = useState(false)
  const endRef = useRef(null)
  const sendingRef = useRef(false)

  // Auth/session live only in React memory. Refreshing intentionally returns to sign-in.
  async function beginSession(authToken, patient) {
    const data = await jsonFetch('/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ auth_token: authToken }) })
    setAuth({ token: authToken, patient })
    setSessionId(data.session_id)
    setMessages([{ role: 'assistant', text: data.assistant_message }])
    setFeedbackSent({})
  }

  async function accessPatient(event) {
    event.preventDefault()
    setAuthBusy(true); setAuthError('')
    try {
      const match = dobText.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/)
      if (!match) throw new Error('Enter your date of birth as DD/MM/YYYY.')
      const [, day, month, year] = match
      const isoDob = `${year}-${month}-${day}`
      const d = Number(day), m = Number(month), y = Number(year)
      const parsed = new Date(Date.UTC(y, m - 1, d))
      if (parsed.getUTCFullYear() !== y || parsed.getUTCMonth() !== m - 1 || parsed.getUTCDate() !== d) throw new Error('Enter a valid date as DD/MM/YYYY.')
      const today = new Date()
      const todayUTC = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
      if (parsed.getTime() > todayUTC) throw new Error('Date of birth cannot be in the future.')
      const data = await jsonFetch('/api/auth', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...identity, dob: isoDob }) })
      await beginSession(data.auth_token, data.patient)
      if (data.created) setMessages((current) => [...current, { role: 'assistant', text: 'Welcome! Your local demo profile is ready. You can now book a visit or ask a clinic-policy question.' }])
    } catch (err) { setAuthError(err.message) } finally { setAuthBusy(false) }
  }

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, busy])

  async function sendMessage(value = draft) {
    const text = value.trim()
    if (!text || !sessionId || busy || finished || sendingRef.current) return
    sendingRef.current = true
    setDraft(''); setError(''); setMessages((current) => [...current, { role: 'user', text }]); setBusy(true)
    try {
      const data = await jsonFetch(`/api/sessions/${sessionId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
      setMessages((current) => [...current, { role: 'assistant', text: data.assistant_message }]); setFinished(data.finished)
      if (data.selected_slot && !data.slot_choices?.length) setChatSelectedSlot(data.selected_slot)
      else if (data.finished && !data.selected_slot) setChatSelectedSlot(null)
      setVisitChoicePending(data.assistant_message.toLowerCase().includes('choose one of the visit types'))
      setHelpChoicesVisible(data.assistant_message.toLowerCase().includes('what would you like to do'))
      if (data.slot_choices?.length) { setChatSlotChoices(data.slot_choices); setChatSelectedSlot(null) }
    } catch (err) { setError(err.message) } finally { sendingRef.current = false; setBusy(false) }
  }

  function onSubmit(event) { event.preventDefault(); sendMessage() }

  function chooseVisitType(reason) { setVisitChoicePending(false); sendMessage(reason) }
  async function chooseChatSlot(slot) {
    setChatSlotChoices([]); setBusy(true); setError('')
    try {
      const data = await jsonFetch(`/api/sessions/${sessionId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: slot.slot_id }) })
      setMessages((current) => [...current, { role: 'user', text: `${formatDate(slot.date)} at ${slot.time} with ${slot.provider}` }, { role: 'assistant', text: data.assistant_message }])
      setChatSelectedSlot(data.selected_slot || slot)
      setFinished(data.finished)
    } catch (err) { setError(err.message); setChatSlotChoices((current) => current.length ? current : [slot]) } finally { setBusy(false) }
  }
  async function confirmChatSlot() {
    await sendMessage('yes')
    setChatSelectedSlot(null)
  }
  function chooseHelpOption(option) {
    setHelpChoicesVisible(false)
    if (option === 'policy') startPolicyQuestion()
    else sendMessage(option)
  }
  function startPolicyQuestion() {
    setMessages((current) => [...current, { role: 'assistant', text: 'Of course. What would you like to know about clinic policies?' }])
  }
  function chooseWelcomeOption(option) {
    setWelcomeChoicesVisible(false)
    if (option === 'book') openBooking()
    else if (option === 'visit') sendMessage('I want to schedule an appointment')
    else startPolicyQuestion()
  }

  async function openBooking() {
    setError(''); setManageMode(''); setBookingStep('day'); setBooking({ day: null, specialty: null, doctor: null, slot: null, appointment: null })
    try { setDays(await jsonFetch('/api/scheduling/days')) } catch (err) { setError(err.message) }
  }

  async function openAppointments() {
    setBookingStep(''); setManageMode('list'); setError('')
    try { setAppointments(await jsonFetch(`/api/sessions/${sessionId}/appointments`)) } catch (err) { setError(err.message) }
  }

  async function editAppointment(appointment) {
    setManageTarget(appointment); setManageMode('edit-day')
    try { setManageDays((await jsonFetch('/api/scheduling/days')).map((day) => ({ ...day, label: formatDate(day.id) }))) } catch (err) { setError(err.message) }
  }

  async function chooseManageDay(day) {
    setBookingBusy(true); setError('')
    try {
      const params = new URLSearchParams({ day: day.id, specialty_id: manageTarget.specialty_id, doctor_id: manageTarget.doctor_id })
      const items = await jsonFetch(`/api/scheduling/slots?${params}`)
      setManageTarget((x) => ({ ...x, selectedDay: { ...day, label: formatDate(day.id) } })); setManageSlots(items); setManageMode('edit-slot')
    } catch (err) { setError(err.message) } finally { setBookingBusy(false) }
  }

  async function saveReschedule(slot) {
    setBookingBusy(true); setError('')
    try {
      await jsonFetch(`/api/sessions/${sessionId}/appointments/${manageTarget.appointment_id}/reschedule`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slot_id: slot.slot_id }) })
      setManageMode('list'); setAppointments(await jsonFetch(`/api/sessions/${sessionId}/appointments`))
    } catch (err) { setError(err.message) } finally { setBookingBusy(false) }
  }

  async function cancelAppointment(appointment) {
    if (!window.confirm(`Cancel your appointment with ${appointment.provider} on ${formatDate(appointment.date)} at ${appointment.time}?`)) return
    setError('')
    try {
      await jsonFetch(`/api/sessions/${sessionId}/appointments/${appointment.appointment_id}/cancel`, { method: 'POST' })
      setAppointments(await jsonFetch(`/api/sessions/${sessionId}/appointments`))
    } catch (err) { setError(err.message) }
  }

  function formatDate(value) {
    if (!value) return ''
    const parsed = new Date(`${value}T12:00:00`)
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  }

  async function chooseDay(day) {
    setBookingBusy(true); setError('')
    try {
      const items = await jsonFetch(`/api/scheduling/specialties?day=${encodeURIComponent(day.id)}`)
      setBooking((x) => ({ ...x, day: { ...day, label: formatDate(day.id) }, specialty: null, doctor: null, slot: null })); setSpecialties(items); setBookingStep('specialty')
    } catch (err) { setError(err.message) } finally { setBookingBusy(false) }
  }

  async function chooseSpecialty(specialty) {
    setBookingBusy(true); setError('')
    try {
      const items = await jsonFetch(`/api/scheduling/doctors?day=${encodeURIComponent(booking.day.id)}&specialty_id=${encodeURIComponent(specialty.id)}`)
      setBooking((x) => ({ ...x, specialty, doctor: null, slot: null })); setDoctors(items); setBookingStep('doctor')
    } catch (err) { setError(err.message) } finally { setBookingBusy(false) }
  }

  async function chooseDoctor(doctor) {
    setBookingBusy(true); setError('')
    try {
      const params = new URLSearchParams({ day: booking.day.id, specialty_id: booking.specialty.id, doctor_id: doctor.id })
      const items = await jsonFetch(`/api/scheduling/slots?${params}`)
      setBooking((x) => ({ ...x, doctor, slot: null })); setSlots(items); setBookingStep('slot')
    } catch (err) { setError(err.message) } finally { setBookingBusy(false) }
  }

  async function chooseSlot(slot) {
    setBookingBusy(true); setError('')
    try {
      const data = await jsonFetch(`/api/sessions/${sessionId}/select-slot`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slot_id: slot.slot_id }) })
      setBooking((x) => ({ ...x, slot: data.slot })); setBookingStep('confirm')
    } catch (err) { setError(err.message) } finally { setBookingBusy(false) }
  }

  async function confirmBooking() {
    setBookingBusy(true); setError('')
    try {
      const data = await jsonFetch(`/api/sessions/${sessionId}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slot_id: booking.slot.slot_id }) })
      setBooking((x) => ({ ...x, appointment: { ...data.appointment, date: formatDate(data.appointment.date) } })); setBookingStep('done')
    } catch (err) { setError(err.message); setBookingStep('slot') } finally { setBookingBusy(false) }
  }

  async function submitFeedback(index, positive) {
    if (!sessionId) return
    try {
      await jsonFetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId, turn_id: `${sessionId}:${index}`, rating: positive ? 5 : 2, reason: positive ? 'helpful' : feedbackReason, comment: !positive ? feedbackComment.trim() || null : null }) })
      setFeedbackSent((current) => ({ ...current, [index]: true })); setActiveFeedback(null); setFeedbackComment('')
    } catch (err) { setError(err.message) }
  }

  async function previewReminders() {
    setRemindersBusy(true)
    try {
      const data = await jsonFetch(`/api/sessions/${sessionId}/reminders/preview`, { method: 'POST' })
      const text = data.count ? `Local reminder preview${data.count === 1 ? '' : 's'} (nothing was sent):\n\n${data.reminders.map((item) => item.message).join('\n\n')}` : 'You have no upcoming appointments to preview. No messages were sent.'
      setMessages((current) => [...current, { role: 'assistant', text }])
    } catch (err) { setMessages((current) => [...current, { role: 'assistant', text: `I could not prepare reminder previews: ${err.message}` }]) } finally { setRemindersBusy(false) }
  }

  function signOut() { setAuth(null); setSessionId(null); setMessages([]); setBookingStep(''); setIdentity({ name: '', dob: '' }); setDobText('') }

  if (!auth) return <div className="auth-page"><section className="auth-card"><a className="brand auth-brand" href="#home"><span className="brand-mark"><Sparkle small /></span><span>ajCares<span className="brand-ai">.ai</span></span></a><p className="modal-eyebrow">YOUR CARE, MADE SIMPLER</p><h1>Welcome to ajCares</h1><p className="auth-intro">Sign in or create your local demo profile with your name and date of birth.</p><form className="registration-form" onSubmit={accessPatient}><label>Full name<input autoFocus required minLength="2" maxLength="120" value={identity.name} onChange={(e) => setIdentity({ ...identity, name: e.target.value })} placeholder="e.g. Taylor Example" /></label><label>Date of birth<input required type="text" inputMode="numeric" autoComplete="bday" maxLength="10" placeholder="DD/MM/YYYY" value={dobText} onChange={(e) => { const value = e.target.value.replace(/[^\d/]/g, '').slice(0, 10); setDobText(value); setAuthError('') }} /></label>{authError && <p className="registration-error" role="alert">{authError}</p>}<button className="create-profile-button" disabled={authBusy}>{authBusy ? 'Opening your profile…' : 'Continue'}</button></form><p className="modal-footnote">Local demo only. Name and date of birth are not secure authentication credentials. Use fictional details.</p></section></div>

  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#home"><span className="brand-mark"><Sparkle small /></span><span>ajCares<span className="brand-ai">.ai</span></span></a><div className="side-label">YOUR CARE</div><button className="nav-item selected" onClick={() => { setBookingStep(''); setManageMode('') }}><span className="nav-icon">◌</span> Care assistant<span className="active-dot" /></button><button className="nav-item registration-link" onClick={openBooking}><span className="nav-icon">＋</span> Book appointment</button><button className="nav-item registration-link" onClick={openAppointments}><span className="nav-icon">▤</span> My appointments</button><button className="nav-item registration-link" onClick={previewReminders} disabled={remindersBusy}><span className="nav-icon">◷</span> {remindersBusy ? 'Preparing previews…' : 'Preview reminders'}</button><div className="profile-chip"><span className="profile-check">✓</span><span><strong>{auth.patient.name}</strong><small>Signed in · demo</small></span></div><div className="side-card"><div className="side-card-icon"><Sparkle small /></div><div><strong>A little help, anytime</strong><p>Book a visit or get answers about your clinic.</p></div></div><div className="sidebar-bottom"><div className="demo-badge"><span /> Demo workspace</div><p>Fictional patient records<br />for demonstration only</p></div></aside>
    <main className="main-panel"><header className="topbar"><div className="mobile-brand"><span className="brand-mark"><Sparkle small /></span> ajCares<span className="brand-ai">.ai</span></div><div className="topbar-actions"><span className="secure-label">◇ Welcome, {auth.patient.name}</span><button className="sign-out" onClick={signOut}>Sign out</button></div></header>
      <section className="chat-area" aria-label="Care assistant"><div className="conversation"><div className="date-divider"><span>YOUR CARE, MADE SIMPLER</span></div>
        {!bookingStep && !manageMode && <><div className="welcome"><div className="welcome-icon"><Sparkle /></div><h1>How can we help<br className="desktop-break" /> you today?</h1><p>A friendly place to get started with your care.</p></div><div className="quick-actions"><button onClick={openBooking}><span>＋</span><strong>Book an appointment</strong><small>Choose a day, doctor and time</small><b>→</b></button><button onClick={startPolicyQuestion}><span>✳</span><strong>Ask a clinic question</strong><small>Type your clinic policy question</small><b>→</b></button></div></>}
        {manageMode && <section className="booking-panel"><div className="booking-heading"><div><p className="modal-eyebrow">MY APPOINTMENTS</p><h1>{manageMode === 'list' ? 'Your booked visits' : 'Change appointment'}</h1></div><button className="booking-close" onClick={() => setManageMode('')}>×</button></div>
          {manageMode === 'list' && (appointments.length ? <div className="appointment-list">{appointments.map((a) => <article className="appointment-card" key={a.appointment_id}><div><strong>{a.specialty || a.reason}</strong><p>{formatDate(a.date)} · {a.time}</p><p>{a.provider} · {a.clinic}</p><small>Confirmation: {a.appointment_id}</small></div><div className="appointment-actions"><button className="secondary-button" onClick={() => editAppointment(a)}>Change day / time</button><button className="cancel-button" onClick={() => cancelAppointment(a)}>Cancel</button></div></article>)}</div> : <p className="booking-note">You don’t have any active appointments.</p>)}
          {manageMode === 'edit-day' && <><h2>Choose a new day for {manageTarget?.provider}</h2><p className="booking-note">Your doctor will stay the same.</p><div className="choice-grid day-grid">{manageDays.map((day) => <button key={day.id} onClick={() => chooseManageDay(day)} disabled={bookingBusy}>{day.label}</button>)}</div></>}
          {manageMode === 'edit-slot' && <><h2>Available times with {manageTarget?.provider}</h2><p className="booking-note">{manageTarget?.selectedDay?.label} · {manageTarget?.clinic}</p><div className="choice-grid slot-grid">{manageSlots.filter((slot) => slot.slot_id !== manageTarget.slot_id).map((slot) => <button key={slot.slot_id} onClick={() => saveReschedule(slot)} disabled={bookingBusy}>{slot.time}<small>Confirm change</small></button>)}</div>{!manageSlots.filter((slot) => slot.slot_id !== manageTarget.slot_id).length && <p className="booking-note">No other available times with this doctor on that day.</p>}<button className="back-button" onClick={() => setManageMode('edit-day')}>← Choose another day</button></>}
          {bookingBusy && <p className="booking-note">Loading…</p>}{error && <p className="registration-error" role="alert">{error}</p>}
        </section>}
        {bookingStep && <section className="booking-panel"><div className="booking-heading"><div><p className="modal-eyebrow">APPOINTMENT BOOKING</p><h1>{bookingStep === 'done' ? 'You’re all set' : 'Choose your appointment'}</h1></div><button className="booking-close" onClick={() => setBookingStep('')}>×</button></div><div className="step-track">{['Day','Specialty','Doctor','Time'].map((s, i) => <span key={s} className={(i <= ['day','specialty','doctor','slot','confirm','done'].indexOf(bookingStep)) ? 'current' : ''}>{i + 1}. {s}</span>)}</div>
          {bookingStep === 'day' && <><h2>Which day works for you?</h2><p className="booking-note">Choose a date in the next seven days.</p><div className="choice-grid day-grid">{days.map((day) => <button key={day.id} onClick={() => chooseDay(day)} disabled={bookingBusy}>{day.label}<small>{day.available_slots} times available</small></button>)}</div></>}
          {bookingStep === 'specialty' && <><h2>Select a specialty</h2><div className="choice-grid">{specialties.map((item) => <button key={item.id} onClick={() => chooseSpecialty(item)} disabled={bookingBusy}><strong>{item.name}</strong><small>{item.description}</small></button>)}</div></>}
          {bookingStep === 'doctor' && <><h2>Choose a doctor</h2><div className="choice-grid">{doctors.map((item) => <button key={item.id} onClick={() => chooseDoctor(item)} disabled={bookingBusy}><strong>{item.name}</strong><small>{item.experience} · {item.clinic}</small></button>)}</div></>}
          {bookingStep === 'slot' && <><h2>Available times with {booking.doctor?.name}</h2><p className="booking-note">{booking.day?.label} · {booking.doctor?.clinic}</p><div className="choice-grid slot-grid">{slots.map((item) => <button key={item.slot_id} onClick={() => chooseSlot(item)} disabled={bookingBusy}>{item.time}</button>)}</div></>}
          {bookingStep === 'confirm' && <><h2>Review before booking</h2><div className="booking-summary"><strong>{booking.specialty?.name}</strong><p>{booking.day?.label} at {booking.slot?.time}</p><p>{booking.doctor?.name} · {booking.doctor?.clinic}</p></div><div className="booking-buttons"><button className="secondary-button" onClick={() => setBookingStep('slot')}>Choose another time</button><button className="create-profile-button" onClick={confirmBooking} disabled={bookingBusy}>{bookingBusy ? 'Booking…' : 'Confirm appointment'}</button></div><p className="booking-note">The appointment is not booked until you confirm.</p></>}
          {bookingStep === 'done' && <div className="booking-summary success-summary"><span className="success-mark">✓</span><strong>Appointment confirmed</strong><p>{formatDate(booking.appointment?.date)} · {booking.appointment?.time}</p><p>{booking.appointment?.provider} · {booking.appointment?.clinic}</p><small>Confirmation: {booking.appointment?.appointment_id}</small><button className="create-profile-button" onClick={() => setBookingStep('')}>Done</button></div>}
          {['specialty','doctor','slot'].includes(bookingStep) && <button className="back-button" onClick={() => setBookingStep(({ specialty: 'day', doctor: 'specialty', slot: 'doctor' })[bookingStep])}>← Back</button>}
          {bookingBusy && <p className="booking-note" aria-live="polite">Loading choices…</p>}{error && <p className="registration-error" role="alert">{error}</p>}
        </section>}
        {!bookingStep && !manageMode && <div className="message-list" aria-live="polite">{messages.map((message, index) => <div key={index} className={`message-row ${message.role}`}>{message.role === 'assistant' && <div className="avatar"><Sparkle small /></div>}<div className={`message-stack ${message.role}`}><div className={`bubble ${message.role}`}><div className="message-author">{message.role === 'assistant' ? 'ajCares' : 'You'}</div><div>{message.text}</div></div>{message.role === 'assistant' && index > 0 && <div className="message-feedback">{feedbackSent[index] ? <span className="feedback-thanks">Thanks for your feedback</span> : <><span>Was this helpful?</span><button onClick={() => submitFeedback(index, true)}>↗</button><button onClick={() => setActiveFeedback(index)}>↘</button></>}{activeFeedback === index && <div className="feedback-form"><label>What could be better?<select value={feedbackReason} onChange={(e) => setFeedbackReason(e.target.value)}><option value="confusing">Confusing answer</option><option value="wrong_policy">Policy answer seemed wrong</option><option value="misunderstood">It misunderstood me</option><option value="unsafe_action">Unsafe or incorrect action</option><option value="other">Something else</option></select></label><textarea maxLength="500" placeholder="Optional note" value={feedbackComment} onChange={(e) => setFeedbackComment(e.target.value)} /><button className="feedback-submit" onClick={() => submitFeedback(index, false)}>Send feedback</button></div>}</div>}</div></div>)}{busy && <div className="message-row assistant"><div className="avatar"><Sparkle small /></div><div className="bubble assistant typing"><span /><span /><span /></div></div>}{chatSlotChoices.length > 0 && <div className="chat-slot-choices">{chatSlotChoices.map((slot) => <button key={slot.slot_id} onClick={() => chooseChatSlot(slot)} disabled={busy}><strong>{formatDate(slot.date)} · {slot.time}</strong><span>{slot.provider}</span><small>{slot.clinic || slot.specialty}</small></button>)}</div>}{chatSelectedSlot && <div className="chat-confirm-card"><div><strong>Confirm this appointment?</strong><p>{formatDate(chatSelectedSlot.date)} · {chatSelectedSlot.time} with {chatSelectedSlot.provider}</p><small>{chatSelectedSlot.clinic || chatSelectedSlot.specialty}</small></div><button onClick={confirmChatSlot} disabled={busy}>Confirm booking</button><button className="secondary-button" onClick={() => { setChatSelectedSlot(null); sendMessage('choose another time') }} disabled={busy}>Choose another</button></div>}{welcomeChoicesVisible && messages.length === 1 && <div className="welcome-chat-choices"><button onClick={() => chooseWelcomeOption('book')}><strong>Book appointment</strong><small>Choose day, specialty, doctor & time</small></button><button onClick={() => chooseWelcomeOption('visit')}><strong>Checkup / Follow-up</strong><small>Tell the assistant which visit you need</small></button><button onClick={() => chooseWelcomeOption('policy')}><strong>Clinic policy question</strong><small>Ask about hours and clinic policies</small></button></div>}{helpChoicesVisible && <div className="visit-type-choices"><button onClick={() => chooseHelpOption('Checkup')} disabled={busy}>Checkup</button><button onClick={() => chooseHelpOption('Follow-up')} disabled={busy}>Follow-up</button><button onClick={() => chooseHelpOption('policy')} disabled={busy}>Clinic policy</button></div>}{visitChoicePending && <div className="visit-type-choices"><button onClick={() => chooseVisitType('Checkup')} disabled={busy}>Checkup</button><button onClick={() => chooseVisitType('Follow-up')} disabled={busy}>Follow-up</button></div>}<div ref={endRef} /></div>}{error && !bookingStep && <div className="error-note" role="alert">{error}<button onClick={() => setError('')}>Dismiss</button></div>}</div></section>
      {!bookingStep && !manageMode && <footer className="composer-wrap"><form className="composer" onSubmit={onSubmit}><textarea aria-label="Your message" placeholder={finished ? 'This conversation is complete.' : 'Ask a clinic question…'} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }} disabled={busy || finished || !sessionId} rows="1" /><button className="send-button" aria-label="Send message" type="submit" disabled={!draft.trim() || busy || finished}><span>↑</span></button></form><div className="composer-meta"><span>Press <kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for a new line</span></div><p className="disclaimer">ajCares is a scheduling demo, not medical advice. For emergencies, contact local emergency services.</p></footer>}
    </main>
  </div>
}
