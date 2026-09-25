// Nombre de marca configurable por deploy — este mismo código corre para
// más de un cliente (TaxiCarga, Mionca, ...), cada uno con su propio
// frontend_materio/.env.local (VITE_BRAND_NAME=...), igual que ya se hace
// con VITE_MAPBOX_TOKEN. Un solo punto de verdad para todos los textos
// de cara al cliente que mencionan el nombre de la marca.
export const BRAND_NAME = import.meta.env.VITE_BRAND_NAME || 'TaxiCarga'
