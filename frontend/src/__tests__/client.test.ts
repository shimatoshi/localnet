import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  apiSearch,
  apiGetSites,
  apiGetCatalog,
  apiCrawl,
  apiGetJob,
  apiGetActiveJobs,
  apiStopJob,
  apiExport,
  apiImport,
  apiResume,
  apiRecrawl,
  apiBuild,
} from '../api/client'

// Mock global fetch
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    blob: () => Promise.resolve(new Blob(['test'])),
  }
}

beforeEach(() => {
  mockFetch.mockReset()
})

describe('apiSearch', () => {
  it('calls /api/search with query and limit', async () => {
    const data = [{ url: 'http://a.com', title: 'A', path: '/', domain: 'a.com' }]
    mockFetch.mockResolvedValue(jsonResponse(data))
    const result = await apiSearch('hello', 10)
    expect(mockFetch).toHaveBeenCalledWith('/api/search?q=hello&limit=10')
    expect(result).toEqual(data)
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValue(jsonResponse(null, 500))
    await expect(apiSearch('fail')).rejects.toThrow('HTTP 500')
  })
})

describe('apiGetSites', () => {
  it('calls /api/sites', async () => {
    const data = [{ domain: 'a.com', file_count: 5, has_catalog: true, page_count: 10 }]
    mockFetch.mockResolvedValue(jsonResponse(data))
    const result = await apiGetSites()
    expect(mockFetch).toHaveBeenCalledWith('/api/sites')
    expect(result).toEqual(data)
  })

  it('throws on error', async () => {
    mockFetch.mockResolvedValue(jsonResponse(null, 404))
    await expect(apiGetSites()).rejects.toThrow('HTTP 404')
  })
})

describe('apiGetCatalog', () => {
  it('calls /api/catalog/:domain', async () => {
    const data = [{ url: 'http://a.com/page', title: 'Page', path: '/page' }]
    mockFetch.mockResolvedValue(jsonResponse(data))
    const result = await apiGetCatalog('a.com')
    expect(mockFetch).toHaveBeenCalledWith('/api/catalog/a.com')
    expect(result).toEqual(data)
  })
})

describe('apiCrawl', () => {
  it('sends POST with correct body', async () => {
    const job = { job_id: '1', status: 'pending', domain: 'a.com', error: null, page_count: 0 }
    mockFetch.mockResolvedValue(jsonResponse(job))
    const result = await apiCrawl('http://a.com', 2, 1, ['/admin'])
    expect(mockFetch).toHaveBeenCalledWith('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: 'http://a.com', depth: 2, delay: 1, exclude: ['/admin'] }),
    })
    expect(result).toEqual(job)
  })
})

describe('apiGetJob', () => {
  it('calls /api/jobs/:id', async () => {
    const job = { job_id: '42', status: 'running', domain: 'b.com', error: null, page_count: 5 }
    mockFetch.mockResolvedValue(jsonResponse(job))
    const result = await apiGetJob('42')
    expect(mockFetch).toHaveBeenCalledWith('/api/jobs/42')
    expect(result).toEqual(job)
  })
})

describe('apiGetActiveJobs', () => {
  it('calls /api/jobs/active', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]))
    const result = await apiGetActiveJobs()
    expect(mockFetch).toHaveBeenCalledWith('/api/jobs/active')
    expect(result).toEqual([])
  })
})

describe('apiStopJob', () => {
  it('sends POST to /api/jobs/:id/stop', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ ok: true }))
    await apiStopJob('99')
    expect(mockFetch).toHaveBeenCalledWith('/api/jobs/99/stop', { method: 'POST' })
  })
})

describe('apiExport', () => {
  it('calls /api/export/:domain and returns a blob', async () => {
    mockFetch.mockResolvedValue(jsonResponse(null))
    const result = await apiExport('a.com')
    expect(mockFetch).toHaveBeenCalledWith('/api/export/a.com')
    expect(result).toBeInstanceOf(Blob)
  })

  it('throws on error status', async () => {
    mockFetch.mockResolvedValue(jsonResponse(null, 500))
    await expect(apiExport('a.com')).rejects.toThrow('HTTP 500')
  })
})

describe('apiImport', () => {
  it('sends file as FormData', async () => {
    const job = { job_id: '1', status: 'pending', domain: null, error: null, page_count: 0 }
    mockFetch.mockResolvedValue(jsonResponse(job))
    const file = new File(['content'], 'test.zip', { type: 'application/zip' })
    const result = await apiImport(file)
    expect(mockFetch).toHaveBeenCalledWith('/api/import', {
      method: 'POST',
      body: expect.any(FormData),
    })
    expect(result).toEqual(job)
  })

  it('throws with error message from response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'Bad file' }),
    })
    await expect(apiImport(new File([], 'x'))).rejects.toThrow('Bad file')
  })
})

describe('apiResume', () => {
  it('sends POST to /api/resume/:domain', async () => {
    const job = { job_id: '2', status: 'running', domain: 'b.com', error: null, page_count: 3 }
    mockFetch.mockResolvedValue(jsonResponse(job))
    const result = await apiResume('b.com')
    expect(mockFetch).toHaveBeenCalledWith('/api/resume/b.com', { method: 'POST' })
    expect(result).toEqual(job)
  })
})

describe('apiRecrawl', () => {
  it('sends POST to /api/recrawl/:domain', async () => {
    const job = { job_id: '3', status: 'pending', domain: 'c.com', error: null, page_count: 0 }
    mockFetch.mockResolvedValue(jsonResponse(job))
    const result = await apiRecrawl('c.com')
    expect(mockFetch).toHaveBeenCalledWith('/api/recrawl/c.com', { method: 'POST' })
    expect(result).toEqual(job)
  })
})

describe('apiBuild', () => {
  it('sends POST to /api/build/:domain', async () => {
    const job = { job_id: '4', status: 'pending', domain: 'd.com', error: null, page_count: 0 }
    mockFetch.mockResolvedValue(jsonResponse(job))
    const result = await apiBuild('d.com')
    expect(mockFetch).toHaveBeenCalledWith('/api/build/d.com', { method: 'POST' })
    expect(result).toEqual(job)
  })
})
