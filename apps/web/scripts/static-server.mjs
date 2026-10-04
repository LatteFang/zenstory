#!/usr/bin/env node
import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer } from 'node:http'
import { extname, join, normalize, resolve } from 'node:path'

const root = resolve(process.env.STATIC_ROOT || 'dist')
const port = Number(process.env.PORT || 8080)
const types = new Map([
  ['.css', 'text/css; charset=utf-8'], ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'], ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'], ['.map', 'application/json; charset=utf-8'],
  ['.png', 'image/png'], ['.svg', 'image/svg+xml'], ['.txt', 'text/plain; charset=utf-8'],
  ['.webp', 'image/webp'], ['.woff', 'font/woff'], ['.woff2', 'font/woff2'],
])

function resolveFile(pathname) {
  const decoded = decodeURIComponent(pathname).replace(/^\/+/, '')
  const candidate = resolve(root, normalize(decoded || 'index.html'))
  if (!candidate.startsWith(`${root}/`) && candidate !== root) return null
  if (existsSync(candidate) && statSync(candidate).isFile()) return candidate
  const directoryIndex = join(candidate, 'index.html')
  if (existsSync(directoryIndex) && statSync(directoryIndex).isFile()) return directoryIndex
  if (!extname(decoded)) return join(root, 'index.html')
  return null
}

createServer((request, response) => {
  let file
  try {
    file = resolveFile(new URL(request.url || '/', 'http://localhost').pathname)
  } catch {
    response.writeHead(400).end('Bad request')
    return
  }
  if (!file || !existsSync(file)) {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Not found')
    return
  }
  response.writeHead(200, {
    'Content-Type': types.get(extname(file)) || 'application/octet-stream',
    'X-Content-Type-Options': 'nosniff',
  })
  if (request.method === 'HEAD') response.end()
  else createReadStream(file).pipe(response)
}).listen(port, '0.0.0.0', () => console.log(`Serving ${root} on :${port}`))
