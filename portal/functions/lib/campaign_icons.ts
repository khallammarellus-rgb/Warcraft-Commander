/** Hosted custom unit icons — R2 storage per table game. */

import { unzip } from "fflate";

export const ICON_KMZ_PREFIX = "assets/player_custom_icons/";
export const MAX_ICON_BYTES = 512 * 1024;

export function iconR2Key(gameId: string, filename: string): string {
  const safe = filename.replace(/[/\\]/g, "").replace(/\.\./g, "");
  return `games/${gameId}/icons/${safe}`;
}

export function iconsPrefix(gameId: string): string {
  return `games/${gameId}/icons/`;
}

export function archivePrefix(gameId: string): string {
  return `games/${gameId}/archive/`;
}

export async function extractIconsFromKmz(data: Uint8Array): Promise<Record<string, Uint8Array>> {
  return new Promise((resolve, reject) => {
    unzip(data, (err, files) => {
      if (err) return reject(err);
      const out: Record<string, Uint8Array> = {};
      for (const [path, bytes] of Object.entries(files)) {
        const norm = path.replace(/\\/g, "/");
        const lower = norm.toLowerCase();
        const idx = lower.indexOf(ICON_KMZ_PREFIX);
        if (idx < 0) continue;
        const rel = norm.slice(idx + ICON_KMZ_PREFIX.length);
        const filename = rel.split("/").pop() || "";
        if (!filename.toLowerCase().endsWith(".png")) continue;
        if (bytes.length > MAX_ICON_BYTES) continue;
        out[filename] = bytes;
      }
      resolve(out);
    });
  });
}

export async function storeIconsFromKmzBuffer(
  bucket: R2Bucket,
  gameId: string,
  data: Uint8Array,
): Promise<{ count: number; bytes: number; filenames: string[] }> {
  const icons = await extractIconsFromKmz(data);
  let bytes = 0;
  const filenames: string[] = [];
  for (const [name, data] of Object.entries(icons)) {
    await bucket.put(iconR2Key(gameId, name), data, {
      httpMetadata: { contentType: "image/png" },
    });
    bytes += data.length;
    filenames.push(name);
  }
  return { count: filenames.length, bytes, filenames };
}

export async function purgeR2Prefix(
  bucket: R2Bucket,
  prefix: string,
): Promise<{ deleted: number; bytes: number }> {
  let deleted = 0;
  let bytes = 0;
  let cursor: string | undefined;
  do {
    const listed = await bucket.list({ prefix, cursor });
    for (const obj of listed.objects) {
      await bucket.delete(obj.key);
      deleted += 1;
      bytes += obj.size;
    }
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);
  return { deleted, bytes };
}

export async function purgeGameIcons(
  bucket: R2Bucket,
  gameId: string,
): Promise<{ deleted: number; bytes: number }> {
  return purgeR2Prefix(bucket, iconsPrefix(gameId));
}

export async function purgeGameArchives(
  bucket: R2Bucket,
  gameId: string,
): Promise<{ deleted: number; bytes: number }> {
  const prefixes = [
    archivePrefix(gameId),
    `games/${gameId}/announcements/`,
  ];
  let deleted = 0;
  let bytes = 0;
  for (const prefix of prefixes) {
    const result = await purgeR2Prefix(bucket, prefix);
    deleted += result.deleted;
    bytes += result.bytes;
  }
  return { deleted, bytes };
}