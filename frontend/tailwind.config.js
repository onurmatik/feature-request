/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      boxShadow: {
        ds: "0 1px 3px rgba(0,0,0,0.1)",
      },
    },
  },
  plugins: [],
};
