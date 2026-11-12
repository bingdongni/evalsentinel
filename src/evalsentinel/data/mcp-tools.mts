// Collect evidence through the selected native implementation; do not port JSON-RPC.
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { writeFile } from 'node:fs/promises';

const [checkout, url, output] = process.argv.slice(2);
const { connectFor } = await import(pathToFileURL(resolve(checkout, 'src/connection/index.ts')).href);
const { withWireRecorder, wireSchemaChecks } = await import(pathToFileURL(resolve(checkout, 'src/validation/wire-schema.ts')).href);
const MAX_PAGES = 32;
await withWireRecorder(async () => {
  const conn = await connectFor('2026-07-28')(url);
  const evidence = { discovery: null, pages: [], complete: false, error: null, checks: [], attemptedParams: null };
  try {
    evidence.discovery = await conn.discover();
    if (!Object.hasOwn(evidence.discovery.capabilities ?? {}, 'tools')) {
      throw new Error('Tools capability not declared; inventory not exercised');
    }
    const cursors = new Set();
    let params = {};
    for (let page = 0; page < MAX_PAGES; page++) {
      evidence.attemptedParams = params;
      const result = await conn.request('tools/list', params);
      evidence.pages.push({ params, result });
      if (!result || result.resultType !== 'complete' || !Array.isArray(result.tools)) {
        throw new Error('Invalid or incomplete tools/list result');
      }
      if (!Object.hasOwn(result, 'nextCursor')) {
        evidence.complete = true;
        break;
      }
      const cursor = result.nextCursor;
      if (typeof cursor !== 'string' || cursors.has(cursor)) {
        throw new Error('Invalid or repeated pagination cursor; traversal incomplete');
      }
      cursors.add(cursor);
      params = { cursor };
    }
    if (!evidence.complete) throw new Error('Tool inventory exceeded 32 pages; traversal incomplete');
  } catch (error) {
    evidence.error = {
      type: error?.constructor?.name ?? 'Error', message: String(error?.message ?? error),
      ...(typeof error?.code === 'number' ? { code: error.code } : {})
    };
  } finally {
    evidence.checks = wireSchemaChecks('2026-07-28');
    await conn.close();
    await writeFile(output, JSON.stringify(evidence, null, 2) + '\n');
  }
});
