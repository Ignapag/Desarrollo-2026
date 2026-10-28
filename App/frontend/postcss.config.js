// Configuración de PostCSS: procesa Tailwind 4 (vía su plugin oficial) y agrega
// prefijos de navegador con Autoprefixer al compilar los estilos de la app.
export default {
  plugins: {
    '@tailwindcss/postcss': {},
    autoprefixer: {},
  },
}
