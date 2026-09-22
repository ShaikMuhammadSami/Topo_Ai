import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"


async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8")
}


test("frontend health endpoint is static, local, and non-secret", async () => {
  const health = await source("app/healthz/route.ts")

  assert.match(health, /status:\s*"ok"/)
  assert.match(health, /component:\s*"frontend"/)
  assert.match(health, /dynamic\s*=\s*"force-static"/)
  assert.doesNotMatch(
    health,
    /process\.env|fetch\(|TOPO_BACKEND_URL|DATABASE|credential|secret|filesystem/i,
  )
})


test("production packaging keeps the browser same-origin contract", async () => {
  const [configuration, api] = await Promise.all([
    source("next.config.mjs"),
    source("lib/topo-api.ts"),
  ])

  assert.match(configuration, /output:\s*"standalone"/)
  assert.match(configuration, /process\.env\.TOPO_BACKEND_URL/)
  assert.match(configuration, /source:\s*"\/api\/:path\*"/)
  assert.doesNotMatch(configuration, /NEXT_PUBLIC_TOPO_API_URL/)
  assert.match(api, /path\.startsWith\("\/api\/"\)/)
  assert.match(api, /credentials:\s*"same-origin"/)
  assert.doesNotMatch(api, /NEXT_PUBLIC_TOPO_API_URL/)
})


test("container source is locked, non-root, standalone, and context-bounded", async () => {
  const [dockerfile, dockerignore] = await Promise.all([
    source("Dockerfile"),
    source(".dockerignore"),
  ])

  assert.match(
    dockerfile,
    /^FROM node:24-bookworm-slim@sha256:[0-9a-f]{64} AS base$/m,
  )
  assert.match(dockerfile, /RUN npm ci/)
  assert.match(dockerfile, /\.next\/standalone/)
  assert.match(dockerfile, /USER 10001:10001/)
  assert.match(dockerfile, /ENTRYPOINT \["node"\]/)
  assert.match(dockerfile, /CMD \["server\.js"\]/)
  assert.match(dockerfile, /topo\.component="frontend"/)

  assert.equal(dockerignore.split(/\r?\n/, 1)[0], "**")
  for (const required of [
    "!package-lock.json",
    "!app/**",
    "!components/**",
    "!lib/**",
    "!public/**",
    "**/node_modules/",
    "**/.next/",
    "**/.git/",
    "**/.env*",
    "**/test/",
    "**/*.log",
  ]) {
    assert.match(dockerignore, new RegExp(required.replaceAll("*", "\\*")))
  }
})


test("production dependency security patches are exact in package and lock", async () => {
  const packageManifest = JSON.parse(await source("package.json"))
  const lockManifest = JSON.parse(await source("package-lock.json"))

  assert.equal(packageManifest.dependencies.next, "16.3.3")
  assert.equal(packageManifest.devDependencies.postcss, "8.5.28")
  assert.equal(lockManifest.packages[""].dependencies.next, "16.3.3")
  assert.equal(lockManifest.packages[""].devDependencies.postcss, "8.5.28")
  assert.equal(lockManifest.packages["node_modules/next"].version, "16.3.3")
  assert.equal(lockManifest.packages["node_modules/postcss"].version, "8.5.28")
  assert.equal(packageManifest.dependencies.nodemon, undefined)
  assert.equal(packageManifest.dependencies.shadcn, undefined)
  assert.equal(packageManifest.devDependencies.nodemon, "^3.1.14")
  assert.equal(packageManifest.devDependencies.shadcn, "^4.8.0")
  assert.equal(lockManifest.packages[""].dependencies.nodemon, undefined)
  assert.equal(lockManifest.packages[""].dependencies.shadcn, undefined)
  assert.equal(lockManifest.packages[""].devDependencies.nodemon, "^3.1.14")
  assert.equal(lockManifest.packages[""].devDependencies.shadcn, "^4.8.0")
  assert.equal(lockManifest.packages["node_modules/nodemon"].version, "3.1.14")
  assert.equal(lockManifest.packages["node_modules/nodemon"].dev, true)
  assert.equal(lockManifest.packages["node_modules/shadcn"].version, "4.11.0")
  assert.equal(lockManifest.packages["node_modules/shadcn"].dev, true)
  assert.equal(packageManifest.dependencies["baseline-browser-mapping"], undefined)
  assert.equal(
    packageManifest.devDependencies["baseline-browser-mapping"],
    undefined,
  )
  assert.equal(
    lockManifest.packages["node_modules/baseline-browser-mapping"].version,
    "2.11.25",
  )
})
