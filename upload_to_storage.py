import http.client, os, uuid, json, sys
sys.stdout.reconfigure(line_buffering=True)

filepath = r"C:\Users\administrator\zukan-bouz-cache.tar"
filename = os.path.basename(filepath)
filesize = os.path.getsize(filepath)
print(f"Uploading {filename} ({filesize / 1024 / 1024:.1f} MB)")

boundary = uuid.uuid4().hex
header = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
    f"Content-Type: application/octet-stream\r\n\r\n"
).encode()
footer = f"\r\n--{boundary}--\r\n".encode()

conn = http.client.HTTPConnection("127.0.0.1", 8005)
conn.connect()
conn.putrequest("POST", "/api/upload")
conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
conn.putheader("Content-Length", str(len(header) + filesize + len(footer)))
conn.endheaders()

conn.send(header)
with open(filepath, "rb") as f:
    sent = 0
    while True:
        chunk = f.read(1048576)
        if not chunk:
            break
        conn.send(chunk)
        sent += len(chunk)
        if sent % (50 * 1048576) < 1048576:
            print(f"  {sent / 1024 / 1024:.0f} MB sent...")
conn.send(footer)
print(f"  Total: {sent / 1024 / 1024:.1f} MB. Waiting for response...")

resp = conn.getresponse()
result = json.loads(resp.read())
print(json.dumps(result, indent=2))
