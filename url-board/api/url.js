export default function handler(req, res) {
  const services = [
    { name: 'localnet', envUrl: 'TUNNEL_URL', envUpdated: 'TUNNEL_UPDATED' },
    { name: 'shimatubeneo', envUrl: 'TUNNEL_URL_SHIMATUBENEO', envUpdated: 'TUNNEL_UPDATED_SHIMATUBENEO' },
  ];

  const result = services.map(s => ({
    name: s.name,
    url: (process.env[s.envUrl] || '').trim() || null,
    updated: (process.env[s.envUpdated] || '').trim() || null,
  }));

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.json(result);
}
