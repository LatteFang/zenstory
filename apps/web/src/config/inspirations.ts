import { parseEnvBoolean } from "./env";

/** Optional project-template library. Enable the matching server flag as well. */
export const inspirationsConfig = {
  enabled: parseEnvBoolean(import.meta.env.VITE_INSPIRATIONS_ENABLED, false),
};
