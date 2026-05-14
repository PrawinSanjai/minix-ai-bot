const EMOTION_PATTERNS = [
  { key: 'stressed', patterns: [/stress/i, /overwhelm/i, /exhaust/i, /tire/i, /drain/i, /burnout/i, /pressure/i, /burden/i] },
  { key: 'anxious', patterns: [/anxi/i, /worr/i, /nervous/i, /panic/i, /fear/i, /scared/i, /dread/i, /uneasy/i, /restless/i] },
  { key: 'sad', patterns: [/sad/i, /depress/i, /unhappy/i, /lonely/i, /grief/i, /heart/i, /miss/i, /cry/i, /tear/i, /blue/i, /down/i] },
  { key: 'angry', patterns: [/angry/i, /anger/i, /frustrat/i, /annoy/i, /irritat/i, /mad/i, /rage/i, /upset/i] },
  { key: 'happy', patterns: [/happy/i, /glad/i, /joy/i, /grateful/i, /thank/i, /bless/i, /wonder/i, /amaz/i, /great/i, /love/i, /excite/i] },
  { key: 'seeking', patterns: [/hopeless/i, /help/i, /guid/i, /confus/i, /lost/i, /direction/i, /purpose/i] },
]

export function detectEmotion(text) {
  for (const { key, patterns } of EMOTION_PATTERNS) {
    if (patterns.some(p => p.test(text))) return key
  }
  return 'neutral'
}

export const EMOTION_LABELS = {
  stressed: 'You seem stressed — I\'m here for you',
  anxious: 'I can sense your anxiety — let\'s breathe together',
  sad: 'I hear your sadness — your feelings are valid',
  angry: 'It\'s okay to feel frustrated — let it out',
  happy: 'I can feel your warmth — that\'s beautiful',
  seeking: 'You\'re seeking clarity — let\'s explore this',
  neutral: 'I\'m listening — tell me more',
}

export const EMOTION_ICONS = {
  stressed: 'fa-solid fa-cloud',
  anxious: 'fa-solid fa-heart-pulse',
  sad: 'fa-regular fa-face-frown',
  angry: 'fa-solid fa-bolt',
  happy: 'fa-regular fa-face-smile',
  seeking: 'fa-regular fa-compass',
  neutral: 'fa-regular fa-face-smile',
}
