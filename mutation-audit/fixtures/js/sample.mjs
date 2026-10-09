export function isAdult(age) {
  return age >= 18;
}

export function clamp(x, lo, hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

export function scale(x, factor) {
  return x * factor;
}
