import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"
import { test } from "node:test"
import ts from "typescript"

const code = ts.transpileModule(readFileSync(new URL("../src/features/skip-2fa/id-scu-skip2fa.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText

function createPage(storage = new Map(), response = { data: { user2factor: true } }) {
  const appended = []
  const element = () => ({ style: {}, appendChild() {}, addEventListener() {}, remove() {} })
  class XHR {
    open(...args) { this.openArgs = args }
    get responseText() { return this.text }
    get response() { return this.responseType === "json" ? JSON.parse(this.text) : this.text }
  }
  const context = vm.createContext({
    exports: {}, console: { log() {}, warn() {} }, Response, URL, XMLHttpRequest: XHR,
    document: {
      documentElement: { dataset: { __scu_skip2fa: "true" } },
      createElement: element, getElementById: () => element(),
      body: { appendChild: (el) => appended.push(el) }
    },
    sessionStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    window: { fetch: async () => new Response(JSON.stringify(response)), location: {} }
  })
  vm.runInContext(code, context)
  context.exports.initSkip2Fa()
  return { context, storage, appended }
}
const settingUrl = "https://id.scu.edu.cn/api/bff/v1.2/commons/user_setting_info"
const loginUrl = "https://id.scu.edu.cn/api/bff/v1.2/commons/sp_logged"

test("enabled fetch modifies only the expected endpoint", async () => {
  const { context } = createPage()
  assert.equal((await (await context.window.fetch(settingUrl)).json()).data.user2factor, false)
  assert.equal((await (await context.window.fetch("https://id.scu.edu.cn/other")).json()).data.user2factor, true)
})
for (const code of ["505", 505]) {
  test(`server rejection ${typeof code} disables interception across same-tab navigation`, async () => {
    const { context, storage, appended } = createPage(new Map(), { code, data: { info: "2factor-pending" } })
    assert.equal((await (await context.window.fetch(loginUrl)).json()).code, code)
    assert.equal(appended.length, 1)
    const next = createPage(storage)
    assert.equal((await (await next.context.window.fetch(settingUrl)).json()).data.user2factor, true)
  })
}
test("other 505 errors do not disable interception", async () => {
  const page = createPage(new Map(), { code: "505", data: { info: "unrelated" } })
  await page.context.window.fetch(loginUrl)
  assert.equal(page.storage.size, 0)
  assert.equal(page.appended.length, 0)
})
test("XHR preserves default asynchronous requests and explicit synchronous requests", () => {
  const { context } = createPage()
  const xhr = new context.XMLHttpRequest()
  xhr.open("GET", settingUrl)
  assert.equal(xhr.openArgs[2], true)
  xhr.open("GET", settingUrl, false)
  assert.equal(xhr.openArgs[2], false)
})
test("XHR rejection also survives navigation", () => {
  const { context, storage, appended } = createPage()
  const xhr = new context.XMLHttpRequest()
  xhr.open("GET", loginUrl)
  Object.assign(xhr, { readyState: 4, status: 200, text: JSON.stringify({ code: "505", data: { info: "2factor-pending" } }) })
  assert.equal(JSON.parse(xhr.responseText).code, "505")
  assert.equal(storage.get("scu-plus:skip2fa-rejected"), "true")
  assert.equal(appended.length, 1)
})
test("document_start tolerates a missing root element", async () => {
  const { context } = createPage()
  context.document.documentElement = null
  assert.equal((await (await context.window.fetch(settingUrl)).json()).data.user2factor, true)
})
