declare module 'archiver' {
  import { Readable } from 'stream';

  interface ArchiverOptions {
    zlib?: {
      level?: number;
    };
  }

  interface Archiver extends NodeJS.ReadWriteStream {
    pipe<T extends NodeJS.WritableStream>(destination: T): T;
    file(filepath: string, options?: { name?: string }): this;
    append(source: string | Buffer | Readable, options?: { name?: string }): this;
    finalize(): Promise<void>;
    on(event: 'error', listener: (err: Error) => void): this;
    on(event: string, listener: (...args: unknown[]) => void): this;
  }

  function archiver(format: 'zip' | 'tar', options?: ArchiverOptions): Archiver;

  export = archiver;
}
