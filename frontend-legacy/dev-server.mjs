#!/usr/bin/env node
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
process.chdir(__dirname);

const server = await createServer({
  root: __dirname,
  configFile: resolve(__dirname, 'vite.config.ts'),
  server: {
    host: '127.0.0.1',
    port: 5180,
  },
});
await server.listen();
server.printUrls();
