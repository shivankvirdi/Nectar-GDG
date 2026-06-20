import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  cacheDir: '.vite-cache',
  envPrefix: ['VITE_', 'NECTAR_'],
})
