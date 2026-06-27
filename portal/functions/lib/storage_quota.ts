/** R2 storage quota — stay under Cloudflare free tier (10 GB). */

export const STORAGE_KV_KEY = "r2_storage_total_bytes";

/** 9.5 GB hard stop (bytes). */
export const STORAGE_HARD_CAP_BYTES = Math.floor(9.5 * 1024 * 1024 * 1024);

/** Per-file limits. */
export const MAX_KMZ_UPLOAD_BYTES = 8 * 1024 * 1024;
export const MAX_GHOST_AAR_BYTES = 512 * 1024;
export const MAX_ADHOC_ANNOUNCE_BYTES = 256 * 1024;

export interface StorageUsage {
  used_bytes: number;
  cap_bytes: number;
  remaining_bytes: number;
  percent_used: number;
  uploads_blocked: boolean;
}

export async function getStorageUsage(kv: KVNamespace): Promise<StorageUsage> {
  const raw = await kv.get(STORAGE_KV_KEY);
  const used = raw ? Number(raw) : 0;
  const safeUsed = Number.isFinite(used) && used >= 0 ? used : 0;
  const remaining = Math.max(0, STORAGE_HARD_CAP_BYTES - safeUsed);
  return {
    used_bytes: safeUsed,
    cap_bytes: STORAGE_HARD_CAP_BYTES,
    remaining_bytes: remaining,
    percent_used: Math.round((safeUsed / STORAGE_HARD_CAP_BYTES) * 1000) / 10,
    uploads_blocked: safeUsed >= STORAGE_HARD_CAP_BYTES,
  };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export async function assertCanStore(
  kv: KVNamespace,
  sizeBytes: number,
  label: string,
): Promise<{ ok: true } | { ok: false; error: string; usage: StorageUsage }> {
  if (sizeBytes <= 0) {
    return { ok: false, error: "Empty upload", usage: await getStorageUsage(kv) };
  }
  const usage = await getStorageUsage(kv);
  if (usage.uploads_blocked) {
    return {
      ok: false,
      error: `Storage full (${formatBytes(usage.used_bytes)} / ${formatBytes(usage.cap_bytes)}). Contact white cell.`,
      usage,
    };
  }
  if (usage.used_bytes + sizeBytes > STORAGE_HARD_CAP_BYTES) {
    return {
      ok: false,
      error: `${label} would exceed storage cap (${formatBytes(sizeBytes)} needed, ${formatBytes(usage.remaining_bytes)} left). Hard stop at 9.5 GB.`,
      usage,
    };
  }
  return { ok: true };
}

export async function addStorageUsage(kv: KVNamespace, sizeBytes: number): Promise<StorageUsage> {
  const usage = await getStorageUsage(kv);
  const next = usage.used_bytes + sizeBytes;
  await kv.put(STORAGE_KV_KEY, String(next));
  return getStorageUsage(kv);
}

export async function subtractStorageUsage(kv: KVNamespace, sizeBytes: number): Promise<StorageUsage> {
  const usage = await getStorageUsage(kv);
  const next = Math.max(0, usage.used_bytes - Math.max(0, sizeBytes));
  await kv.put(STORAGE_KV_KEY, String(next));
  return getStorageUsage(kv);
}