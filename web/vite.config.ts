import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Relative base so the built files also open from a plain folder or any sub-path.
export default defineConfig({
  plugins: [react()],
  base: './',
});
