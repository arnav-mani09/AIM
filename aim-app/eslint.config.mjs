import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  ...nextVitals,
  {
    rules: {
      // New in React 19's hooks rules. The dashboard pages load data and reset
      // lists inside effects; that works, but re-renders more than needed.
      // Warn until the data loading is reworked (Phase 2 review screen).
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
];

export default eslintConfig;
