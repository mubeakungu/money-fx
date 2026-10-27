// Inlines the demo build's JS and CSS into dist-demo/money-fx-demo.html.
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'

const dir = 'dist-demo/assets'
const files = readdirSync(dir)
const js = readFileSync(`${dir}/${files.find((f) => f.endsWith('.js'))}`, 'utf8').replaceAll('</script', '<\\/script')
const css = readFileSync(`${dir}/${files.find((f) => f.endsWith('.css'))}`, 'utf8')
const html = `<title>money fx</title>
<style>${css}</style>
<div id="root"></div>
<script type="module">${js}</script>
`
writeFileSync('dist-demo/money-fx-demo.html', html)
console.log(`money-fx-demo.html ${(html.length / 1024).toFixed(0)} KB`)
