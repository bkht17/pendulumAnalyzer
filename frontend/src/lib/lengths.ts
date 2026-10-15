/**
 * Разбор списка длин: «60 40 20», «60; 40; 20», «60, 40, 20», «62,5 40».
 * Запятая без пробела — десятичный разделитель (как принято в русском), с пробелом — разделитель списка.
 */
export function parseLengths(input: string): number[] {
  return input
    .split(/[;\s]+|,\s+/)
    .map((part) => Number(part.replace(",", ".")))
    .filter((value) => Number.isFinite(value) && value > 0 && value <= 500);
}
