/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Display"',
          '"SF Pro Text"',
          '"Segoe UI"',
          "Roboto",
          '"Noto Sans KR"',
          "sans-serif",
        ],
      },
      colors: {
        apple: {
          bg: "#f5f5f7",
          surface: "#ffffff",
          text: "#1d1d1f",
          secondary: "#86868b",
          tertiary: "#d2d2d7",
          blue: "#0071e3",
          "blue-hover": "#0077ed",
          green: "#34c759",
          orange: "#ff9500",
          red: "#ff3b30",
          purple: "#af52de",
        },
      },
      borderRadius: {
        "2xl": "16px",
        "3xl": "20px",
      },
      boxShadow: {
        "apple-sm": "0 1px 3px rgba(0,0,0,0.08)",
        apple: "0 2px 12px rgba(0,0,0,0.08)",
        "apple-lg": "0 4px 24px rgba(0,0,0,0.12)",
        "apple-hover": "0 8px 32px rgba(0,0,0,0.12)",
      },
    },
  },
  plugins: [],
};
