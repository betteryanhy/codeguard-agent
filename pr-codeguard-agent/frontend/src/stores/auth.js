import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  function saveToken(t) {
    token.value = t
    localStorage.setItem('token', t)
  }

  function saveUser(u) {
    user.value = u
    localStorage.setItem('user', JSON.stringify(u))
  }

  async function login(username, password) {
    const res = await api.login(username, password)
    saveToken(res.data.access_token)
    saveUser(res.data.user)
    return res.data
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  function isAuthenticated() {
    return !!token.value
  }

  return { token, user, login, logout, isAuthenticated, saveToken, saveUser }
})
