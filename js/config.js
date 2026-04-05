// config.js — placeholders only, no real keys here
// Border Pulse v1.0 | South Asia Geopolitical Intelligence Dashboard

const CONFIG = {
  // Backend API URL — change to Railway URL in production
  // e.g. https://borderpulse-api.up.railway.app
    API_BASE_URL: 'https://borderpulse-production-c562.up.railway.app',

  // Refresh intervals
  REFRESH_INTERVAL_NEWS:    15 * 60 * 1000,  // 15 minutes
  REFRESH_INTERVAL_SUMMARY: 60 * 60 * 1000,  // 60 minutes
  REFRESH_INTERVAL_ECONOMIC: 30 * 60 * 1000, // 30 minutes
  REFRESH_INTERVAL_TENSION: 15 * 60 * 1000,  // 15 minutes

  // Map defaults
  MAP_CENTER: [28.6, 77.2], // New Delhi
  MAP_ZOOM: 5,
  MAP_BOUNDS: [[5, 60], [40, 100]], // South Asia region

  // Theatres
  THEATRES: ['loc', 'lac', 'bangladesh', 'naval'],

  THEATRE_LABELS: {
    loc:        'Line of Control',
    lac:        'Line of Actual Control',
    bangladesh: 'India-Bangladesh',
    naval:      'Bay of Bengal / Naval',
  },

  THEATRE_SHORT: {
    loc:        'LoC',
    lac:        'LAC',
    bangladesh: 'BD',
    naval:      'Naval',
  },

  THEATRE_COLOURS: {
    loc:        '#E63946',
    lac:        '#457B9D',
    bangladesh: '#F4A261',
    naval:      '#2EC4B6',
  },

  // News feed
  NEWS_MAX_ARTICLES: 30,
  NEWS_DEDUPE_THRESHOLD: 3, // collapse if same story appears 3+ times

  // Tension thresholds
  TENSION_ALERT_THRESHOLD: 70,
  TENSION_ZONES: {
    stable:   { min: 0,  max: 30, colour: '#2EC4B6' },
    warning:  { min: 31, max: 60, colour: '#F4A261' },
    high:     { min: 61, max: 80, colour: '#E63946' },
    critical: { min: 81, max: 100, colour: '#E63946' },
  },

  // State media domains (shown with warning badge)
  STATE_MEDIA_DOMAINS: [
    'xinhuanet.com', 'globaltimes.cn', 'ptv.com.pk', 'presstv.ir',
    'xinhua.net', 'chinadaily.com.cn',
  ],

  // AI Summary prompt (used by backend; reproduced here for reference)
  AI_SYSTEM_PROMPT: `You are a neutral geopolitical intelligence analyst specialising in South Asia. Given the latest news headlines and data for a specific border theatre, produce a concise 3-sentence situation briefing. Rules: (1) Strictly neutral — no political bias toward any country. (2) State facts only — no speculation. (3) End with a one-word status: ESCALATING / STABLE / DE-ESCALATING. (4) Maximum 80 words total. Format: [Briefing text]. Status: [WORD]`,

  // Economic tickers
  ECONOMIC_PAIRS: [
    { id: 'INR_USD', label: 'INR/USD', flag: '🇮🇳' },
    { id: 'PKR_USD', label: 'PKR/USD', flag: '🇵🇰' },
    { id: 'BDT_USD', label: 'BDT/USD', flag: '🇧🇩' },
    { id: 'BRENT',   label: 'Brent Crude', flag: '🛢️' },
  ],
};

// Freeze config to prevent accidental mutation
Object.freeze(CONFIG);
Object.freeze(CONFIG.THEATRES);
Object.freeze(CONFIG.THEATRE_LABELS);
Object.freeze(CONFIG.THEATRE_COLOURS);
Object.freeze(CONFIG.TENSION_ZONES);
Object.freeze(CONFIG.STATE_MEDIA_DOMAINS);
Object.freeze(CONFIG.ECONOMIC_PAIRS);
