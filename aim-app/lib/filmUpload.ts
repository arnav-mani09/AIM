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
  /** Jersey color names, so AIM knows which team is yours. */
  valleyJersey?: string | null;
  opponentJersey?: string | null;
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
    throwIfAborted(signal);
    if (!session) {
      const started = await startFilmUpload(token, teamId, {
        title: options.title,
        notes: options.notes ?? null,
        game_id: options.gameId ?? null,
        filename: file.name,
        content_type: file.type || "video/mp4",
        size_bytes: file.size,
        valley_jersey: options.valleyJersey ?? null,
        opponent_jersey: options.opponentJersey ?? null,
      });
      session = {
        uploadId: started.upload.id,
        partSize: started.part_size,
        partCount: started.part_count,
      };
    }
    options.onSession?.(session);
    throwIfAborted(signal);

    const active = session;
    if (
      !Number.isSafeInteger(active.partSize) ||
      active.partSize <= 0 ||
      !Number.isSafeInteger(active.partCount) ||
      active.partCount <= 0 ||
      active.partCount !== Math.ceil(file.size / active.partSize)
    ) {
      throw new Error("Upload session does not match this file.");
    }
    const loaded = new Map<number, number>();
    const confirmed = new Set<number>();
    const done = await listFilmUploadParts(token, teamId, active.uploadId);
    throwIfAborted(signal);
    for (const part of done) {
      const partNumber = part.part_number;
      const expectedSize = Math.min(active.partSize, file.size - (partNumber - 1) * active.partSize);
      if (
        Number.isInteger(partNumber) &&
        partNumber >= 1 &&
        partNumber <= active.partCount &&
        part.size === expectedSize
      ) {
        loaded.set(partNumber, part.size);
        confirmed.add(partNumber);
      }
    }
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
    if (signal?.aborted) stop.abort();
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
        confirmed.add(partNumber);
        loaded.set(partNumber, body.size);
        reportProgress();
      }
    };
    let failure: { error: unknown } | undefined;
    try {
      await Promise.all(
        Array.from({ length: Math.min(CONCURRENT_PARTS, remaining.length) }, () =>
          worker().catch((error) => {
            failure ??= { error };
            stop.abort();
          })
        )
      );
    } finally {
      signal?.removeEventListener("abort", onOuterAbort);
    }
    if (failure) throw failure.error;
    throwIfAborted(signal);
    if (confirmed.size !== active.partCount) throw new Error("Upload incomplete.");

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

function throwIfAborted(signal: AbortSignal | undefined) {
  if (signal?.aborted) throw new Error("Upload paused.");
}

async function withRetries(signal: AbortSignal | undefined, attempt: () => Promise<void>) {
  for (let i = 0; ; i += 1) {
    throwIfAborted(signal);
    try {
      return await attempt();
    } catch (error) {
      if (signal?.aborted || i >= RETRY_DELAYS_MS.length) throw error;
      await new Promise<void>((resolve, reject) => {
        const abort = () => {
          clearTimeout(timer);
          reject(new Error("Upload paused."));
        };
        const timer = setTimeout(() => {
          signal?.removeEventListener("abort", abort);
          resolve();
        }, RETRY_DELAYS_MS[i]);
        signal?.addEventListener("abort", abort, { once: true });
      });
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
    throwIfAborted(signal);
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
    xhr.onabort = () => {
      signal?.removeEventListener("abort", abort);
      reject(new Error("Upload paused."));
    };
    signal?.addEventListener("abort", abort);
    xhr.send(body);
  });
}
