/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./projects/templates/**/*.html",
    "./projects/static/projects/**/*.js",
  ],
  theme: {
    extend: {
      boxShadow: {
        ds: "0 1px 3px rgba(0,0,0,0.1)",
      },
    },
  },
  plugins: [],
};
