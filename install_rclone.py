import urllib.request, zipfile, os, sys
sys.stdout.reconfigure(line_buffering=True)

dest_zip = r"C:\Users\administrator\rclone.zip"
dest_dir = r"C:\Users\administrator\rclone"

print("Downloading rclone...")
url = "https://github.com/rclone/rclone/releases/latest/download/rclone-current-windows-amd64.zip"
urllib.request.urlretrieve(url, dest_zip)
print(f"Downloaded: {os.path.getsize(dest_zip)} bytes")

print("Extracting...")
with zipfile.ZipFile(dest_zip) as z:
    z.extractall(dest_dir)

for root, dirs, files in os.walk(dest_dir):
    for f in files:
        if f == "rclone.exe":
            print(f"rclone.exe: {os.path.join(root, f)}")
print("Done")
