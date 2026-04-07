[app]

# App metadata
title = Localnet
package.name = localnet
package.domain = net.localnet
version = 2.0
source.dir = .
source.include_exts = py,html,js,css,json,png,jpg,ico,webp,svg,woff,woff2,ttf

# Requirements
requirements = python3,kivy,pyjnius,android,flask,requests,urllib3,beautifulsoup4,certifi

# Android settings
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.api = 34
android.minapi = 26
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a

# App icon
icon.filename = frontend/dist/icon-192.png

# Orientation
orientation = portrait

# Fullscreen
fullscreen = 0

# Android-specific
android.allow_backup = True

# Include these files
source.include_patterns = routes/*,frontend/dist/*,frontend/dist/assets/*

# Exclude heavy stuff
source.exclude_dirs = android,node_modules,frontend/src,frontend/node_modules,.git,cache,sites,docs,.playwright-cli

# Log level
log_level = 2

# p4a
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 0
