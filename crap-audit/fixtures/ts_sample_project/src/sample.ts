export function outer(x: number): number {
  function inner(y: number): number {
    if (y > 0) {
      if (y > 10) {
        if (y > 20) {
          if (y > 30) {
            if (y > 40) {
              return y * 5;
            }
            return y * 4;
          }
          return y * 3;
        }
        return y * 2;
      }
      return y + 1;
    }
    return -y;
  }
  return inner(x);
}

export function uncoveredFn(x: number): number {
  if (x > 0) {
    if (x > 10) {
      if (x > 20) {
        return 3;
      }
      return 2;
    }
    return 1;
  }
  return 0;
}

export const arrowFn = (x: number): number => {
  if (x > 0) {
    return x * 2;
  }
  return 0;
};

export function branchlessFn(x: number): number {
  return x + 1;
}
