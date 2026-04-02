"""utils.py のテスト"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import is_valid_domain, detect_charset, detect_mime_from_bytes


# === is_valid_domain ===

class TestIsValidDomain:
    def test_normal_domain(self):
        assert is_valid_domain("example.com") is True

    def test_subdomain(self):
        assert is_valid_domain("sub.example.com") is True

    def test_domain_with_hyphen(self):
        assert is_valid_domain("my-site.co.jp") is True

    def test_domain_with_underscore(self):
        assert is_valid_domain("my_site.com") is True

    def test_empty_string(self):
        assert is_valid_domain("") is False

    def test_domain_with_slash(self):
        assert is_valid_domain("example.com/path") is False

    def test_domain_with_space(self):
        assert is_valid_domain("example .com") is False

    def test_domain_with_colon(self):
        assert is_valid_domain("example.com:8080") is False

    def test_domain_with_special_chars(self):
        assert is_valid_domain("example<script>.com") is False


# === detect_charset ===

class TestDetectCharset:
    def test_meta_charset_utf8(self):
        html = b'<html><head><meta charset="utf-8"></head></html>'
        assert detect_charset(html) == "utf-8"

    def test_meta_charset_shift_jis(self):
        html = b'<html><head><meta charset="shift_jis"></head></html>'
        assert detect_charset(html) == "shift_jis"

    def test_content_type_charset(self):
        html = b'<html><head><meta http-equiv="content-type" content="text/html; charset=euc-jp"></head></html>'
        assert detect_charset(html) == "euc-jp"

    def test_no_charset(self):
        html = b'<html><head><title>test</title></head></html>'
        assert detect_charset(html) is None

    def test_empty_bytes(self):
        assert detect_charset(b'') is None

    def test_charset_without_quotes(self):
        html = b'<html><head><meta charset=utf-8></head></html>'
        assert detect_charset(html) == "utf-8"

    def test_case_insensitive(self):
        html = b'<HTML><HEAD><META CHARSET="UTF-8"></HEAD></HTML>'
        # The function lowercases the head, so it should still match
        assert detect_charset(html) == "utf-8"


# === detect_mime_from_bytes ===

class TestDetectMimeFromBytes:
    def test_png(self):
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        assert detect_mime_from_bytes(data) == "image/png"

    def test_jpeg(self):
        data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        assert detect_mime_from_bytes(data) == "image/jpeg"

    def test_gif(self):
        data = b'GIF89a' + b'\x00' * 100
        assert detect_mime_from_bytes(data) == "image/gif"

    def test_webp(self):
        data = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 100
        assert detect_mime_from_bytes(data) == "image/webp"

    def test_html_tag(self):
        data = b'<!DOCTYPE html><html><body></body></html>'
        assert detect_mime_from_bytes(data) == "text/html"

    def test_html_no_doctype(self):
        data = b'<html><body>hello</body></html>'
        assert detect_mime_from_bytes(data) == "text/html"

    def test_too_short(self):
        assert detect_mime_from_bytes(b'\x89P') is None

    def test_unknown_binary(self):
        data = b'\x00\x01\x02\x03\x04\x05' * 50
        assert detect_mime_from_bytes(data) is None

    def test_webp_too_short(self):
        # RIFF header but not enough bytes for WEBP check
        data = b'RIFF\x00\x00\x00\x00WEB'
        assert detect_mime_from_bytes(data) is None
