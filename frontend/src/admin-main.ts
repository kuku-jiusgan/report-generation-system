import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import AdminRoot from './AdminRoot.vue'

createApp(AdminRoot).use(ElementPlus).mount('#app')
