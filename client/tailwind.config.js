/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#f7f3ec',
        blush: '#e8d9cf',
        clay: '#8a7461',
        ink: '#242021',
      },
      fontFamily: {
        display: ['Georgia', 'ui-serif', 'serif'],
      },
    },
  },
  plugins: [],
};
