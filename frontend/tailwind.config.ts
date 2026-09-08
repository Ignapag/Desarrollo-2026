// tailwind.config.ts
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        crema: "#F5F0E8",
        naranja: "#E8621A",
        "naranja-suave": "#FFF0E8",
        carbon: "#1A1A1A",
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
