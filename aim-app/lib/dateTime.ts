export function formatLocalDateTime(value: string): string {
  const trimmed = value?.trim();
  if (!trimmed) return "";
  const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(trimmed);
  const normalized = hasTimezone ? trimmed : `${trimmed}Z`;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return trimmed;
  }
  return parsed.toLocaleString();
}
