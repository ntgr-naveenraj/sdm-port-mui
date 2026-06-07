/**
 * Native file/folder pickers (Tauri desktop). In plain browser, paths are not exposed — returns null.
 */

/** Files chosen via `<input type="file">` sometimes expose `.path` (Tauri / Electron / some WebViews). */
export function fileInputAbsolutePath(file: File | undefined | null): string | null {
  if (!file) return null;
  const p = (file as File & { path?: string }).path;
  return typeof p === "string" && p.length > 0 ? p : null;
}

export async function pickSshPrivateKeyPath(): Promise<string | null> {
  try {
    const { open } = await import("@tauri-apps/api/dialog");
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [
        { name: "SSH private key", extensions: ["pem", "ppk", "key", ""] },
      ],
    });
    if (selected === null || selected === undefined) return null;
    return Array.isArray(selected) ? selected[0] ?? null : selected;
  } catch {
    return null;
  }
}

/** Folder picker (POSIX-style paths work best for AP destination dirs). */
export async function pickFolderPath(): Promise<string | null> {
  try {
    const { open } = await import("@tauri-apps/api/dialog");
    const selected = await open({
      multiple: false,
      directory: true,
    });
    if (selected === null || selected === undefined) return null;
    return Array.isArray(selected) ? selected[0] ?? null : selected;
  } catch {
    return null;
  }
}

/** Multiple files (paths on API host) for batch upload lists. */
export async function pickMultipleFilePaths(): Promise<string[] | null> {
  try {
    const { open } = await import("@tauri-apps/api/dialog");
    const selected = await open({
      multiple: true,
      directory: false,
    });
    if (selected === null || selected === undefined) return null;
    return Array.isArray(selected) ? selected : [selected];
  } catch {
    return null;
  }
}
