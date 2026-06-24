import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export async function apiGet(url, params = {}) {
  const res = await api.get(url, { params })
  return res.data
}

export async function apiPost(url, data = {}) {
  const res = await api.post(url, data)
  return res.data
}
