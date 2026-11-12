// Use the selected checkout's original connection and validator, not a client port.
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const [checkout, url, output] = process.argv.slice(2);
const connection = await import(pathToFileURL(resolve(checkout, 'src/connection/index.ts')).href);
const validation = await import(pathToFileURL(resolve(checkout, 'src/validation/wire-schema.ts')).href);
const { writeFile } = await import('node:fs/promises');
await validation.withWireRecorder(async () => {
  const conn = await connection.connectFor('2026-07-28')(url);
  try {
    const discovery = await conn.discover();
    const checks = validation.wireSchemaChecks('2026-07-28');
    await writeFile(output, JSON.stringify({ discovery, checks }, null, 2) + '\n');
  } finally {
    await conn.close();
  }
});
