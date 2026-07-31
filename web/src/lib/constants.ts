/**
 * Max areas comparable at once. Mirrors the backend's CENSUS_MAX_GEO_CODES
 * (api/config.py): the server rejects more with a 422, so the picker caps here
 * to keep the limit a friendly stop rather than a request error.
 */
export const MAX_GEO_CODES = 12;
