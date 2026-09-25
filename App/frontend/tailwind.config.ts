// tailwind.config.ts
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        crema: "#F4E7CC",
        hueso: "#FFFDF7",
        naranja: "#E85D2C",
        "naranja-quemado": "#AC3400",
        "amarillo-sol": "#F6B42C",
        "verde-monu": "#1C5A3F",
        "verde-oscuro": "#00422A",
        carbon: "#191C1A",
      },
      fontFamily: {
        jakarta: ['"Plus Jakarta Sans"', "sans-serif"],
        inter: ["Inter", "sans-serif"],
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
    },
  },
  plugins: [],
} satisfies Config;