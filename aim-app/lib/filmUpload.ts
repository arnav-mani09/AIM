import {
  type GameUploadRecord,
  completeFilmUpload,
  listFilmUploadParts,
  signFilmUploadParts,
  startFilmUpload,
} from "@/lib/teamApi";

// Film goes straight from the browser to Cloudflare R2 in fixed-size parts.
// The backend starts and completes the upload and signs each part; the file
// itself never passes through our servers.

const CONCURRENT_PARTS = 4;
const RETRY_DELAYS_MS = [1000, 3000, 9000];

export type FilmUploadSession = {
  uploadId: number;
  partSize: number;
  partCount: number;
};

export type FilmUploadOptions = {
  token: string;
  teamId: number;
  file: File;
  title: string;
  notes?: string | null;
  gameId?: number | null;
  /** Pass the session from a failed attempt to upload only the missing parts. */
  resume?: FilmUploadSession | null;
  onSession?: (session: FilmUploadSession) => void;
  onProgress?: (uploadedBytes: number, totalBytes: number) => void;
  signal?: AbortSignal;
};

export class FilmUploadError extends Error {
  constructor(message: string, public session: FilmUploadSession | null) {
    super(message);
    this.name = "FilmUploadError";
  }
}

export async function uploadFilm(options: FilmUploadOptions): Promise<GameUploadRecord> {
  const { token, teamId, file, signal } = options;
  let session = options.resume ?? null;
  try {
    if (!session) {
      const started = await startFilmUpload(token, teamId, {
        title: options.title,
        notes: options.notes ?? null,
        game_id: options.gameId ?? null,
        filename: file.name,
        content_type: file.type || "video/mp4",
        size_bytes: file.size,
      });
      session = {
        uploadId: started.upload.id,
        partSize: started.part_size,
        partCount: started.part_count,
      };
    }
    options.onSession?.(session);

    const active = session;
    const loaded = new Map<number, number>();
    const done = await listFilmUploadParts(token, teamId, active.uploadId);
    for (const part of done) loaded.set(part.part_number, part.size);
    const reportProgress = () => {
      let total = 0;
      loaded.forEach((bytes) => (total += bytes));
      options.onProgress?.(total, file.size);
    };
    reportProgress();

    const remaining: number[] = [];
    for (let n = 1; n <= active.partCount; n += 1) {
      if (!loaded.has(n)) remaining.push(n);
    }

    // One failed part stops the others, so a resume starts from a settled state.
    const stop = new AbortController();
    const onOuterAbort = () => stop.abort();
    signal?.addEventListener("abort", onOuterAbort);
    const worker = async () => {
      for (let n = remaining.shift(); n !== undefined && !stop.signal.aborted; n = remaining.shift()) {
        const partNumber = n;
        const body = file.slice((partNumber - 1) * active.partSize, partNumber * active.partSize);
        await withRetries(stop.signal, async () => {
          // Sign right before sending so a slow connection never uses an expired link.
          const [signed] = await signFilmUploadParts(token, teamId, active.uploadId, [partNumber]);
          await putPart(signed.url, body, stop.signal, (bytes) => {
            loaded.set(partNumber, bytes);
            reportProgress();
          });
        });
        loaded.set(partNumber, body.size);
        reportProgress();
      }
    };
    try {
      await Promise.all(
        Array.from({ length: Math.min(CONCURRENT_PARTS, remaining.length) }, () =>
          worker().catch((error) => {
            stop.abort();
            throw error;
          })
        )
      );
    } finally {
      signal?.removeEventListener("abort", onOuterAbort);
    }
    // Paused between parts: nothing threw, but some parts never went out.
    let sent = 0;
    loaded.forEach((bytes) => (sent += bytes));
    if (sent < file.size) throw new Error("Upload paused.");

    return await completeFilmUpload(token, teamId, active.uploadId);
  } catch (error) {
    if (error instanceof FilmUploadError) throw error;
    const message = signal?.aborted
      ? "Upload paused."
      : error instanceof Error
        ? error.message
        : "Upload failed";
    throw new FilmUploadError(message, session);
  }
}

async function withRetries(signal: AbortSignal | undefined, attempt: () => Promise<void>) {
  for (let i = 0; ; i += 1) {
    try {
      return await attempt();
    } catch (error) {
      if (signal?.aborted || i >= RETRY_DELAYS_MS.length) throw error;
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[i]));
    }
  }
}

function putPart(
  url: string,
  body: Blob,
  signal: AbortSignal | undefined,
  onProgress: (bytes: number) => void
): Promise<void> {
  // XHR rather than fetch: fetch can't report upload progress.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    xhr.open("PUT", url);
    xhr.upload.onprogress = (event) => onProgress(event.loaded);
    xhr.onload = () => {
      signal?.removeEventListener("abort", abort);
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Part upload failed (${xhr.status})`));
    };
    xhr.onerror = () => {
      signal?.removeEventListener("abort", abort);
      reject(new Error("Network error while uploading"));
    };
    xhr.onabort = () => reject(new Error("Upload paused."));
    signal?.addEventListener("abort", abort);
    xhr.send(body);
  });
}
