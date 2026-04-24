import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Pages project-page deploy lives at plnech.github.io/le_archive/.
// The `BASE_PATH` env lets CI and local preview share one config; local dev
// (`npm run dev`) ignores `base` so the server still serves from "/".
const base = process.env.BASE_PATH ?? '/'

// https://vite.dev/config/
export default defineConfig({
  base,
  plugins: [react()],
})
