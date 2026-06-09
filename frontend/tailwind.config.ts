import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bonch: {
          orange: "#f05a1a",
          ink: "#101114",
          panel: "#181a1f",
          panelSoft: "#202329",
          line: "#2c3038",
          muted: "#9aa3af",
        },
      },
      boxShadow: {
        panel: "0 18px 55px rgba(0, 0, 0, 0.28)",
      },
    },
  },
};

export default config;
