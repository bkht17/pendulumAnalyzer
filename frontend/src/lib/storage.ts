// Мелкие пользовательские удобства (имя оператора и т. п.). Хранилище может быть недоступно
// (приватный режим, запрет cookies) — тогда просто работаем без него.
const PREFIX = "pendulum-lab:";

export function readLocal(key: string, fallback: string): string {
  try {
    return localStorage.getItem(PREFIX + key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writeLocal(key: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + key, value);
  } catch {
    /* игнорируем */
  }
}
