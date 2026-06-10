/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Roboto",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          '"Noto Sans KR"',
          "sans-serif",
        ],
      },
      // 색상 값은 index.css의 CSS 변수(:root / .dark)에서 정의 — 토큰 이름은 유지
      colors: {
        apple: {
          bg: "rgb(var(--c-bg) / <alpha-value>)",
          surface: "rgb(var(--c-surface) / <alpha-value>)",
          text: "rgb(var(--c-text) / <alpha-value>)",
          secondary: "rgb(var(--c-secondary) / <alpha-value>)",
          tertiary: "rgb(var(--c-tertiary) / <alpha-value>)",
          blue: "rgb(var(--c-blue) / <alpha-value>)",
          "blue-hover": "rgb(var(--c-blue-hover) / <alpha-value>)",
          green: "rgb(var(--c-green) / <alpha-value>)",
          orange: "rgb(var(--c-orange) / <alpha-value>)",
          red: "rgb(var(--c-red) / <alpha-value>)",
          purple: "rgb(var(--c-purple) / <alpha-value>)",
        },
      },
      borderRadius: {
        "2xl": "16px",
        "3xl": "20px",
      },
      boxShadow: {
        "apple-sm": "0 1px 3px rgba(0,0,0,var(--shadow-alpha))",
        apple: "0 2px 12px rgba(0,0,0,var(--shadow-alpha))",
        "apple-lg": "0 4px 24px rgba(0,0,0,var(--shadow-alpha-lg))",
        "apple-hover": "0 8px 32px rgba(0,0,0,var(--shadow-alpha-lg))",
      },
    },
  },
  plugins: [],
};
