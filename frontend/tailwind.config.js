/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0B0C10",
        surface: "#13151B",
        surfaceRaised: "#191C24",
        primaryText: "#F5F7FA",
        secondaryText: "#9AA3B2",
        accent: "#8B7CFF",
        success: "#3BC98A",
        warning: "#F0B45A",
        error: "#F06A6A",
        hairline: "#2A2F3A"
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['Fira Code', 'monospace']
      }
    },
  },
  plugins: [],
}
