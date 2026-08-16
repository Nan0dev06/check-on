/* Thin fetch wrapper over the FastAPI layer in api/.
 *
 * There is no client-side fallback data anywhere in this app. If a request
 * fails the screen says the check did not run — it never renders a quieter
 * placeholder in place of an answer, because that is exactly the false
 * reassurance the product exists to avoid.
 */

async function request(path, options) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} — ${body.slice(0, 200)}`)
  }
  return res.json()
}

export const api = {
  person: () => request('/api/person'),
  symptoms: () => request('/api/symptoms'),

  medications: () => request('/api/medications'),
  matchDrug: (q) => request(`/api/drugs/match?q=${encodeURIComponent(q)}`),
  suggestDrugs: (q) => request(`/api/drugs/suggest?q=${encodeURIComponent(q)}`),
  addMedication: (body) =>
    request('/api/medications', { method: 'POST', body: JSON.stringify(body) }),

  logTap: (symptom) =>
    request('/api/taps', { method: 'POST', body: JSON.stringify({ symptom }) }),
  undoTap: (symptom) =>
    request(`/api/taps/latest?symptom=${encodeURIComponent(symptom)}`, {
      method: 'DELETE',
    }),

  checkinQuestions: () => request('/api/checkin/questions'),
  submitCheckin: (answers) =>
    request('/api/checkin', { method: 'POST', body: JSON.stringify({ answers }) }),

  flags: () => request('/api/flags'),
  flag: (symptom) => request(`/api/flags/${symptom}`),
  recheck: (symptom) =>
    request(`/api/flags/${symptom}/recheck`, { method: 'POST' }),

  trend: () => request('/api/trend'),
  doctorList: () => request('/api/doctor-list'),
  notifications: () => request('/api/notifications'),
  addToDoctorList: (item) =>
    request('/api/doctor-list', { method: 'POST', body: JSON.stringify({ item }) }),
}
