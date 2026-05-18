export const ALL_SOURCES = ['olx', 'cartrade', 'cars24', 'spinny', 'carwale', 'cardekho'] as const
export type Source = typeof ALL_SOURCES[number]

export const SOURCE_COLORS: Record<string, string> = {
  cardekho: 'text-orange-400',
  carwale:  'text-blue-400',
  cars24:   'text-green-400',
  olx:      'text-purple-400',
  spinny:   'text-cyan-400',
  cartrade: 'text-rose-400',
}
