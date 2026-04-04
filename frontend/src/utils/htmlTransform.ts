/** キャッシュされたHTMLをiframe表示用に変換する */

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** HTMLレスポンスからタイトルを抽出 */
export function extractTitle(html: string, fallback: string): string {
  const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)
  return m ? m[1].replace(/<[^>]+>/g, '').trim() : fallback
}

/** HTMLの絶対パスをキャッシュプレフィックス経由に書き換え、baseタグ・リンクインターセプトを注入 */
export function transformForIframe(html: string, domain: string, path: string): string {
  const cachePrefix = `/api/cache/${domain}`

  // 絶対パス書き換え
  html = html.replace(
    /((?:src|href|action)\s*=\s*["'])\/(?!\/)/gi,
    `$1${cachePrefix}/`,
  )

  // <base>タグ
  const baseDir = path.replace(/[^/]*$/, '')
  const baseTag = `<base href="${cachePrefix}/${baseDir}">`
  if (/<head/i.test(html)) {
    html = html.replace(/<head([^>]*)>/i, `<head$1>${baseTag}`)
  } else {
    html = baseTag + html
  }

  // リンクインターセプト: iframe内クリックを親フレームにpostMessage
  const interceptScript = `
    <script>
      document.addEventListener('click', function(e) {
        var a = e.target.closest('a');
        if (!a) return;
        e.preventDefault();
        e.stopPropagation();
        var href = a.href;
        if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
        var m = href.match(/\\/api\\/cache\\/([^\\/]+)\\/(.*)/);
        if (m) {
          window.parent.postMessage({ type: 'navigate', url: 'https://' + m[1] + '/' + m[2] }, '*');
        } else if (href.startsWith('http')) {
          window.parent.postMessage({ type: 'navigate', url: href }, '*');
        }
      }, true);
    </script>
  `
  if (html.includes('</body>')) {
    html = html.replace('</body>', interceptScript + '</body>')
  } else {
    html += interceptScript
  }

  return html
}

/** エラー表示用HTML */
export function errorHtml(message: string): string {
  return `<p style="color:#888;padding:20px;font-family:sans-serif">${escHtml(message)}</p>`
}

/** HTML文字列からCSS/JS/画像のURLを抽出し、/api/cache/ パスで返す */
export function extractSubResources(html: string, domain: string): string[] {
  const cachePrefix = `/api/cache/${encodeURIComponent(domain)}/`
  const patterns = [
    /<link[^>]+href=["']([^"']+)["'][^>]*>/gi,
    /<script[^>]+src=["']([^"']+)["'][^>]*>/gi,
    /<img[^>]+src=["']([^"']+)["'][^>]*>/gi,
  ]
  const urls: string[] = []
  for (const re of patterns) {
    let m: RegExpExecArray | null
    while ((m = re.exec(html)) !== null) {
      const ref = m[1]
      if (ref.startsWith('data:')) continue
      if (ref.startsWith(cachePrefix)) {
        urls.push(ref)
      } else if (ref.startsWith('/') && !ref.startsWith('//')) {
        urls.push(`${cachePrefix}${ref.slice(1)}`)
      }
    }
  }
  return urls
}

/** ページが見つからない時のHTML */
export function notFoundHtml(url: string): string {
  return `<div style="color:#888;padding:20px;font-family:sans-serif">
    <p>このページはローカルにありません</p>
    <p style="font-size:0.85em;margin-top:8px;word-break:break-all">${escHtml(url)}</p>
  </div>`
}
