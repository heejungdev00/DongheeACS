import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getVehicles = () => api.get('/vehicles').then(r => r.data)
export const getMissions = () => api.get('/missions').then(r => r.data)
export const getLogs     = () => api.get('/logs').then(r => r.data)
export const getStatus   = () => api.get('/status').then(r => r.data)
export const getAlarms   = () => api.get('/alarms').then(r => r.data)
export const createMission = () => api.post('/missions/create').then(r => r.data)
export const deleteMissionTracking = (missionId) => api.delete(`/tracking/${missionId}`).then(r => r.data)
export const forceInsertVehicle = () => api.post('/vehicles/forceinsert').then(r => r.data)