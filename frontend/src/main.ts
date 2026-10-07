import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { initTheme } from './stores/appState'

initTheme() // 挂载前先落主题，避免启动时闪一下浅色
createApp(App).mount('#app')
