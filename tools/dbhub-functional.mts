// Real SQL controls through the original native Connection, without a model.
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { writeFile } from 'node:fs/promises';
const [checkout, url, output] = process.argv.slice(2);
const { connectFor } = await import(pathToFileURL(resolve(checkout, 'src/connection/index.ts')).href);
const { withWireRecorder, wireSchemaChecks } = await import(pathToFileURL(resolve(checkout, 'src/validation/wire-schema.ts')).href);
await withWireRecorder(async () => {
  const conn = await connectFor('2026-07-28')(url);
  try {
    const discovery = await conn.discover();
    const good = await conn.request('tools/call', { name: 'execute_sql', arguments: { sql: 'SELECT name FROM sentinel_items ORDER BY id' } });
    const bad = await conn.request('tools/call', { name: 'execute_sql', arguments: { sql: 'SELECT nonexistent FROM sentinel_items' } });
    await writeFile(output, JSON.stringify({ discovery, good, bad, checks: wireSchemaChecks('2026-07-28') }, null, 2) + '\n');
  } finally {
    await conn.close();
  }
});
