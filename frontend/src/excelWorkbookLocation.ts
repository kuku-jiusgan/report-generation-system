export function workbookLocation(config: Record<string, unknown> | undefined) {
  const value = config?.workbookLocation;
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}
export function columnNumber(value: string) { let result = 0; for (const char of value.toUpperCase()) result = result * 26 + char.charCodeAt(0) - 64; return result; }
export function columnLetters(value: number) { let result = ""; for (let current = value; current > 0; current = Math.floor((current - 1) / 26)) result = String.fromCharCode(65 + ((current - 1) % 26)) + result; return result; }
