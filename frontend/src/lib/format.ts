const cache = new Map<number, Intl.NumberFormat>();

function formatter(digits: number): Intl.NumberFormat {
  let f = cache.get(digits);
  if (!f) {
    f = new Intl.NumberFormat("ru-RU", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      useGrouping: false,
    });
    cache.set(digits, f);
  }
  return f;
}

export const DASH = "—";

export function num(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return formatter(digits).format(value);
}

/** Сколько знаков после запятой нужно, чтобы показать погрешность двумя значащими цифрами. */
export function digitsForSigma(sigma: number): number {
  if (!(sigma > 0) || !Number.isFinite(sigma)) return 3;
  return Math.min(Math.max(1 - Math.floor(Math.log10(sigma)), 0), 6);
}

/** «1,4216 ± 0,0023» — значение округлено до той же точности, что и погрешность. */
export function pm(value: number | null | undefined, sigma: number | null | undefined, fallbackDigits = 4): string {
  if (value === null || value === undefined) return DASH;
  if (sigma === null || sigma === undefined || !(sigma > 0)) return num(value, fallbackDigits);
  const digits = digitsForSigma(sigma);
  return `${num(value, digits)} ± ${num(sigma, digits)}`;
}

export function ms(seconds: number | null | undefined, digits?: number): string {
  if (seconds === null || seconds === undefined) return DASH;
  const value = seconds * 1000;
  return `${num(value, digits ?? (value < 10 ? 2 : value < 100 ? 1 : 0))} мс`;
}

export function pct(value: number | null | undefined, digits = 2, signed = false): string {
  if (value === null || value === undefined) return DASH;
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${num(value, digits)} %`;
}

export function pValue(p: number | null | undefined): string {
  if (p === null || p === undefined) return DASH;
  return p < 0.001 ? "< 0,001" : num(p, 3);
}

/** Секундомер: 12,34 или 1:02,34 */
export function clock(seconds: number): string {
  const whole = Math.floor(seconds);
  const hundredths = Math.floor((seconds - whole) * 100);
  const minutes = Math.floor(whole / 60);
  const secs = whole % 60;
  const tail = `${String(secs).padStart(minutes ? 2 : 1, "0")},${String(hundredths).padStart(2, "0")}`;
  return minutes ? `${minutes}:${tail}` : tail;
}

export function bytes(size: number): string {
  if (size < 1024 * 1024) return `${num(size / 1024, 0)} КБ`;
  return `${num(size / 1024 / 1024, 1)} МБ`;
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
