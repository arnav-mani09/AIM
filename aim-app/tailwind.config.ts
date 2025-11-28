import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./src/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: "#f5f7fb",
        card: "#ffffff",
        accent: "#1a4d84",
        accentMuted: "rgba(26, 77, 132, 0.08)",
        subtext: "#54627a",
        stroke: "#dfe6f1"
      },
      fontFamily: {
        grotesk: ["Space Grotesk", "system-ui", "sans-serif"]
      },
      boxShadow: {
        soft: "0 20px 45px rgba(15, 35, 73, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
