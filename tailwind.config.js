/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        surface: { DEFAULT: "#161a22", border: "#2a3142" },
        canvas: "#131315",
        "if-border": "rgba(67,70,85,0.2)",
        "if-muted": "#c3c6d7",
        "if-fg": "#e5e1e4",
        "if-link": "#b4c5ff",
      },
      fontFamily: {
        display: ['"Space Grotesk"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
