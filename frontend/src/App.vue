<template>
  <div v-if="loading" class="auth-loading">Loading...</div>
  <div v-else-if="needsAuth && !authenticated" class="auth-gate">
    <div class="auth-box">
      <h1>MiroFish</h1>
      <p>Enter password to continue</p>
      <form @submit.prevent="login">
        <input
          v-model="password"
          type="password"
          placeholder="Password"
          autofocus
        />
        <button type="submit" :disabled="submitting">
          {{ submitting ? 'Verifying...' : 'Enter' }}
        </button>
        <p v-if="error" class="auth-error">Incorrect password</p>
      </form>
    </div>
  </div>
  <router-view v-else />
</template>

<script setup>
import { ref, onMounted } from 'vue'

const loading = ref(true)
const needsAuth = ref(false)
const authenticated = ref(false)
const password = ref('')
const error = ref(false)
const submitting = ref(false)

onMounted(async () => {
  try {
    const saved = sessionStorage.getItem('mirofish_auth')
    if (saved) {
      authenticated.value = true
      loading.value = false
      return
    }
    const res = await fetch('/api/auth/check')
    const data = await res.json()
    needsAuth.value = data.required
    if (!data.required) authenticated.value = true
  } catch {
    needsAuth.value = false
    authenticated.value = true
  }
  loading.value = false
})

async function login() {
  error.value = false
  submitting.value = true
  try {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: password.value })
    })
    const data = await res.json()
    if (data.authenticated) {
      authenticated.value = true
      sessionStorage.setItem('mirofish_auth', '1')
    } else {
      error.value = true
    }
  } catch {
    error.value = true
  }
  submitting.value = false
}
</script>

<style>
/* Global styles */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #000000;
  background-color: #ffffff;
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #f1f1f1; }
::-webkit-scrollbar-thumb { background: #000000; }
::-webkit-scrollbar-thumb:hover { background: #333333; }
button { font-family: inherit; }

/* Auth gate */
.auth-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  font-size: 1.2rem;
  color: #666;
}

.auth-gate {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: #0a0e27;
}

.auth-box {
  text-align: center;
  padding: 40px;
  border-radius: 16px;
  background: rgba(20, 25, 60, 0.9);
  border: 1px solid rgba(123, 47, 255, 0.3);
  min-width: 320px;
}

.auth-box h1 {
  font-size: 2rem;
  font-weight: 800;
  background: linear-gradient(135deg, #00d4ff, #7b2fff, #ff2d95);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 8px;
}

.auth-box p {
  color: #8892b0;
  margin-bottom: 20px;
  font-size: 0.9rem;
}

.auth-box input {
  display: block;
  width: 100%;
  padding: 12px 16px;
  border: 1px solid rgba(123, 47, 255, 0.4);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.3);
  color: #e0e6ff;
  font-size: 1rem;
  font-family: inherit;
  outline: none;
  margin-bottom: 12px;
}

.auth-box input:focus {
  border-color: #00d4ff;
}

.auth-box button {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #7b2fff, #00d4ff);
  color: white;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}

.auth-box button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-error {
  color: #ff2d95 !important;
  margin-top: 12px;
}
</style>
