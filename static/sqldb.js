// sql.js ラッパー — SQLiteデータセットの検索・ページ取得

let SQL = null;
const openDBs = new Map();
const MAX_OPEN = 3;

async function initSQL() {
  if (SQL) return SQL;
  SQL = await initSqlJs({
    locateFile: file => `https://sql.js.org/dist/${file}`
  });
  return SQL;
}

async function openDataset(name) {
  if (openDBs.has(name)) return openDBs.get(name);

  // LRU制限
  if (openDBs.size >= MAX_OPEN) {
    const oldest = openDBs.keys().next().value;
    openDBs.get(oldest).close();
    openDBs.delete(oldest);
  }

  const sql = await initSQL();
  const buffer = await dbStore.load(name);
  if (!buffer) return null;

  const db = new sql.Database(new Uint8Array(buffer));
  openDBs.set(name, db);
  return db;
}

function closeAllDatasets() {
  for (const [name, db] of openDBs) {
    db.close();
  }
  openDBs.clear();
}

async function searchAll(query, limit = 50) {
  const datasets = await dbStore.listMeta();
  if (datasets.length === 0) return [];

  await initSQL();
  const results = [];
  const errors = [];

  for (const ds of datasets) {
    let db;
    try {
      db = await openDataset(ds.name);
      if (!db) { errors.push(`${ds.name}: load failed`); continue; }
    } catch (e) {
      errors.push(`${ds.name}: open error: ${e.message}`);
      continue;
    }

    try {
      // まずテーブル存在確認
      const tables = db.exec("SELECT name FROM sqlite_master WHERE type='table'");
      const tableNames = tables.length > 0 ? tables[0].values.map(r => r[0]) : [];

      if (!tableNames.includes('pages_fts')) {
        // FTS5テーブルがない場合、LIKE検索にフォールバック
        const stmt = db.prepare(`
          SELECT id, url, title, domain,
                 substr(content_text, 1, 200) as snippet,
                 0 as rank
          FROM pages
          WHERE content_text LIKE '%' || ? || '%' OR title LIKE '%' || ? || '%'
          LIMIT ?
        `);
        stmt.bind([query, query, limit]);
        while (stmt.step()) {
          const row = stmt.getAsObject();
          row.dataset = ds.name;
          results.push(row);
        }
        stmt.free();
        continue;
      }

      const stmt = db.prepare(`
        SELECT p.id, p.url, p.title, p.domain,
               snippet(pages_fts, 1, '<b>', '</b>', '...', 32) as snippet,
               rank
        FROM pages_fts
        JOIN pages p ON p.id = pages_fts.rowid
        WHERE pages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
      `);
      stmt.bind([query, limit]);
      while (stmt.step()) {
        const row = stmt.getAsObject();
        row.dataset = ds.name;
        results.push(row);
      }
      stmt.free();
    } catch (e) {
      // FTS5エラーならLIKEフォールバック
      errors.push(`${ds.name}: FTS error: ${e.message}`);
      try {
        const stmt = db.prepare(`
          SELECT id, url, title, domain,
                 substr(content_text, 1, 200) as snippet,
                 0 as rank
          FROM pages
          WHERE content_text LIKE '%' || ? || '%' OR title LIKE '%' || ? || '%'
          LIMIT ?
        `);
        stmt.bind([query, query, limit]);
        while (stmt.step()) {
          const row = stmt.getAsObject();
          row.dataset = ds.name;
          results.push(row);
        }
        stmt.free();
      } catch (e2) {
        errors.push(`${ds.name}: LIKE fallback error: ${e2.message}`);
      }
    }
  }

  if (errors.length > 0) {
    console.warn('Search errors:', errors);
  }

  results.sort((a, b) => a.rank - b.rank);
  return results.slice(0, limit);
}

async function getPage(datasetName, pageId) {
  const db = await openDataset(datasetName);
  if (!db) return null;

  let stmt;
  try {
    stmt = db.prepare('SELECT content_html, mime, title, url FROM pages WHERE id = ?');
    stmt.bind([pageId]);
    if (!stmt.step()) return null;

    const row = stmt.getAsObject();
    const mime = row.mime;
    const title = row.title;
    const url = row.url;
    stmt.free();
    stmt = null;

    // BLOBを別クエリで取得
    let rawStmt;
    try {
      rawStmt = db.prepare('SELECT content_html FROM pages WHERE id = ?');
      rawStmt.bind([pageId]);
      rawStmt.step();
      const compressed = rawStmt.getAsObject(null)['content_html'];
      rawStmt.free();
      rawStmt = null;

      let html;
      if (compressed instanceof Uint8Array) {
        try {
          const blob = new Blob([compressed]);
          const ds = new DecompressionStream('gzip');
          const decompressed = blob.stream().pipeThrough(ds);
          html = await new Response(decompressed).text();
        } catch (e) {
          html = new TextDecoder().decode(compressed);
        }
      } else {
        html = String(compressed || '');
      }

      return { html, mime, title, url };
    } finally {
      if (rawStmt) rawStmt.free();
    }
  } finally {
    if (stmt) stmt.free();
  }
}

// ページURLから検索（リンクインターセプト用）
async function findPageByUrl(url) {
  const datasets = await dbStore.listMeta();
  await initSQL();

  for (const ds of datasets) {
    const db = await openDataset(ds.name);
    if (!db) continue;

    let stmt;
    try {
      stmt = db.prepare('SELECT id FROM pages WHERE url = ? LIMIT 1');
      stmt.bind([url]);
      if (stmt.step()) {
        const row = stmt.getAsObject();
        return { dataset: ds.name, id: row.id };
      }
    } catch (e) {
      continue;
    } finally {
      if (stmt) stmt.free();
    }
  }
  return null;
}
