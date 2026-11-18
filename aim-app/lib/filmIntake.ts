export const MAX_FILM_BYTES = 5 * 1024 ** 3;

export function validateFilmLink(value: string): string | null {
  try {
    const source = new URL(value.trim());
    if (source.protocol !== "https:" || source.username || source.password) {
      return "Use an HTTPS download link without a username or password.";
    }
    if (source.hostname === "localhost" || source.hash) {
      return "Use the original direct video download link, without a page fragment.";
    }
    return null;
  } catch {
    return "Paste a complete HTTPS video download link.";
  }
}

export function validateFilmFile(file: Pick<File, "size" | "name" | "type">): string | null {
  if (file.size <= 0) return "This file is empty. Choose the original game video.";
  if (file.size > MAX_FILM_BYTES) return "Choose a video of 5 GB or smaller.";
  if (!/\.(mp4|mov)$/i.test(file.name) || (file.type && !["video/mp4", "video/quicktime"].includes(file.type))) {
    return "Choose an MP4 or MOV video.";
  }
  return null;
}

export function filmStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    importing: "Importing video", uploading: "Upload incomplete", processing: "Preparing video",
    ready: "Video ready", error: "Needs attention", pending: "Queued",
  };
  return labels[status] ?? "Updating";
}
