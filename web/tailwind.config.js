/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        clinical: {
          teal: {
            50: "#f0fdfa",
            100: "#ccfbf1",
            200: "#99f6e4",
            300: "#5eead4",
            400: "#2dd4bf",
            500: "#14b8a6",
            600: "#0d9488",
            700: "#0f766e",
            800: "#115e59",
            900: "#134e4a",
          },
          amber: {
            500: "#f59e0b",
            600: "#d97706",
          },
          red: {
            500: "#ef4444",
            600: "#dc2626",
          },
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        kannada: [
          '"Noto Sans Kannada"',
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
