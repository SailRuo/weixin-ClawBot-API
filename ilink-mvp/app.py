#!/usr/bin/env python3
import base64
import hashlib
import os
import random
import threading
import time
import uuid

import pyaes
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

PKCS7_PAD = lambda s: s + (16 - len(s) % 16) * chr(16 - len(s) % 16)
PKCS7_UNPAD = lambda s: s[: -ord(s[-1])]


def aes_encrypt(plaintext: bytes, key: bytes) -> bytes:
    padded = PKCS7_PAD(plaintext.decode("latin-1")).encode("latin-1")
    cipher = pyaes.AES(key)
    return b"".join(bytes(cipher.encrypt(padded[i:i+16])) for i in range(0, len(padded), 16))


class GlobalState:
    def __init__(self):
        self.qrcode = None
        self.qrcode_img_content = None
        self.login_status = "idle"
        self.bot_token = None
        self.ilink_bot_id = None
        self.ilink_user_id = None
        self.base_url = "https://ilinkai.weixin.qq.com"
        self.get_updates_buf = ""
        self.messages = []
        self.typing_ticket = None
        self.is_polling = False
        self.poll_thread = None


state = GlobalState()


def generate_wechat_uin():
    uin = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(uin).encode()).decode()


def build_headers(include_auth=True):
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": "132100",
        "X-WECHAT-UIN": generate_wechat_uin(),
    }
    if include_auth and state.bot_token:
        headers["Authorization"] = f"Bearer {state.bot_token}"
    return headers


def build_base_info():
    return {"channel_version": "2.4.3"}


def iLinkRequest(method, endpoint, payload=None, include_auth=True, timeout=15):
    url = f"{state.base_url}/{endpoint.lstrip('/')}"
    headers = build_headers(include_auth=include_auth)
    if method == "GET":
        r = requests.get(url, headers=headers, timeout=timeout)
    else:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise Exception(f"iLink {endpoint} {r.status_code}: {r.text[:200]}")
    return r.json() if r.text.strip() else {}


@app.route("/")
def index():
    with open("templates/index.html", encoding="utf-8") as f:
        return f.read()


@app.route("/api/get_qrcode", methods=["POST"])
def get_qrcode():
    try:
        state.login_status = "waiting"
        state.qrcode = None
        state.qrcode_img_content = None
        data = iLinkRequest(
            "POST",
            "ilink/bot/get_bot_qrcode?bot_type=3",
            {"local_token_list": []},
            include_auth=False,
        )
        state.qrcode = data.get("qrcode")
        state.qrcode_img_content = data.get("qrcode_img_content")
        return jsonify(
            {
                "success": True,
                "qrcode": state.qrcode,
                "qrcode_img_content": state.qrcode_img_content,
                "login_status": state.login_status,
            }
        )
    except Exception as e:
        state.login_status = "error"
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/poll_status", methods=["POST"])
def poll_status():
    try:
        if not state.qrcode:
            return jsonify({"success": False, "error": "No qrcode"}), 400
        data = iLinkRequest(
            "GET",
            f"ilink/bot/get_qrcode_status?qrcode={state.qrcode}",
            include_auth=False,
            timeout=35,
        )
        status = data.get("status")
        state.login_status = status
        result = {"success": True, "status": status, "login_status": state.login_status}
        if status == "confirmed":
            state.bot_token = data.get("bot_token")
            state.ilink_bot_id = data.get("ilink_bot_id")
            state.ilink_user_id = data.get("ilink_user_id")
            baseurl = data.get("baseurl")
            if baseurl:
                state.base_url = baseurl
            result.update(
                bot_token=state.bot_token,
                ilink_bot_id=state.ilink_bot_id,
                ilink_user_id=state.ilink_user_id,
                base_url=state.base_url,
            )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/login_with_token", methods=["POST"])
def login_with_token():
    data = request.json
    token = data.get("bot_token")
    bot_id = data.get("ilink_bot_id")
    user_id = data.get("ilink_user_id")
    base_url = data.get("base_url")
    if token:
        state.bot_token = token
        state.ilink_bot_id = bot_id
        state.ilink_user_id = user_id
        state.login_status = "confirmed"
        if base_url:
            state.base_url = base_url
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "No token"}), 400


@app.route("/api/logout", methods=["POST"])
def logout():
    state.bot_token = None
    state.ilink_bot_id = None
    state.ilink_user_id = None
    state.login_status = "idle"
    state.messages = []
    state.get_updates_buf = ""
    state.typing_ticket = None
    return jsonify({"success": True})


@app.route("/api/get_config", methods=["POST"])
def get_config():
    try:
        data = request.json
        ilink_user_id = data.get("ilink_user_id")
        context_token = data.get("context_token")
        result = iLinkRequest(
            "POST",
            "ilink/bot/getconfig",
            {
                "ilink_user_id": ilink_user_id,
                "context_token": context_token,
                "base_info": build_base_info(),
            },
        )
        state.typing_ticket = result.get("typing_ticket")
        return jsonify({"success": True, "typing_ticket": state.typing_ticket})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/send_typing", methods=["POST"])
def send_typing():
    try:
        data = request.json
        ilink_user_id = data.get("ilink_user_id")
        status = data.get("status", 1)
        typing_ticket = data.get("typing_ticket") or state.typing_ticket
        iLinkRequest(
            "POST",
            "ilink/bot/sendtyping",
            {
                "ilink_user_id": ilink_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
            },
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/send_message", methods=["POST"])
def send_message():
    try:
        data = request.json
        to_user_id = data.get("to_user_id")
        context_token = data.get("context_token")
        item_list = data.get("item_list")
        if not item_list:
            text = data.get("text", "")
            item_list = [{"type": 1, "text_item": {"text": text}}]
        iLinkRequest(
            "POST",
            "ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": f"bot-{int(time.time() * 1000)}",
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": item_list,
                },
                "base_info": build_base_info(),
            },
        )
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def aes_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    cipher = pyaes.AES(key)
    decrypted = b"".join(bytes(cipher.decrypt(ciphertext[i:i+16])) for i in range(0, len(ciphertext), 16))
    return PKCS7_UNPAD(decrypted.decode("latin-1")).encode("latin-1")


def parse_aes_key(aes_key_str: str) -> bytes:
    # 1. If it's a 32-char hex string, decode directly
    if len(aes_key_str) == 32 and all(c in "0123456789abcdefABCDEF" for c in aes_key_str):
        return bytes.fromhex(aes_key_str)
        
    # 2. Otherwise, assume base64
    decoded = base64.b64decode(aes_key_str)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        try:
            return bytes.fromhex(decoded.decode("ascii"))
        except Exception:
            pass
    raise Exception(f"Invalid AES key length: {len(decoded)}")


def guess_mime_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


@app.route("/api/media", methods=["GET"])
def get_media_proxy():
    try:
        encrypt_query_param = request.args.get("param")
        aes_key_base64 = request.args.get("key")
        full_url = request.args.get("url")
        filename = request.args.get("name")

        if not encrypt_query_param and not full_url:
            return jsonify({"success": False, "error": "Missing param or url"}), 400

        # 1. Download encrypted media from Weixin
        headers = build_headers(include_auth=True)
        if full_url:
            r = requests.get(full_url, headers=headers, timeout=30)
        else:
            # Try CDN download route first
            cdn_base_url = "https://novac2c.cdn.weixin.qq.com/c2c"
            url = f"{cdn_base_url}/download"
            r = requests.get(url, params={"encrypted_query_param": encrypt_query_param}, headers=headers, timeout=30)
            
            # Fallback to Weixin API gateway download route if CDN download fails
            if r.status_code != 200:
                url = f"{state.base_url}/ilink/bot/downloadmedia"
                r = requests.get(url, params={"encrypt_query_param": encrypt_query_param}, headers=headers, timeout=30)

        if r.status_code != 200:
            raise Exception(f"Weixin download failed with status {r.status_code}: {r.text[:200]}")
        
        ciphertext = r.content

        # 2. Decrypt if key is provided
        if aes_key_base64:
            key = parse_aes_key(aes_key_base64)
            plaintext = aes_decrypt(ciphertext, key)
        else:
            plaintext = ciphertext

        mime = guess_mime_type(plaintext)
        
        resp_headers = {}
        if filename:
            import urllib.parse
            safe_filename = urllib.parse.quote(filename)
            resp_headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_filename}"
            
        return Response(plaintext, mimetype=mime, headers=resp_headers)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/upload_media", methods=["POST"])
def upload_media():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "No file"}), 400
        media_type = int(request.form.get("media_type", 1))
        to_user_id = request.form.get("to_user_id", "")
        raw_bytes = file.read()
        file_ext = os.path.splitext(file.filename or "file")[1].lower()
        filekey = uuid.uuid4().hex[:16]
        aes_key = os.urandom(16)
        ciphertext = aes_encrypt(raw_bytes, aes_key)
        raw_md5 = hashlib.md5(raw_bytes).hexdigest()
        cipher_md5 = hashlib.md5(ciphertext).hexdigest()

        # Aligned with openclaw-weixin: always use no_need_thumb = True
        no_need_thumb = True

        url_data = iLinkRequest(
            "POST",
            "ilink/bot/getuploadurl",
            {
                "filekey": filekey,
                "media_type": media_type,
                "to_user_id": to_user_id,
                "rawsize": len(raw_bytes),
                "rawfilemd5": raw_md5,
                "filesize": len(ciphertext),
                "no_need_thumb": no_need_thumb,
                "aeskey": aes_key.hex(),
                "base_info": build_base_info(),
            },
        )

        print("getuploadurl response:", url_data)
        upload_url = url_data.get("upload_full_url")
        if not upload_url:
            upload_param = url_data.get("upload_param")
            if upload_param:
                import urllib.parse
                cdn_base_url = "https://novac2c.cdn.weixin.qq.com/c2c"
                upload_url = f"{cdn_base_url}/upload?encrypted_query_param={urllib.parse.quote(upload_param)}&filekey={urllib.parse.quote(filekey)}"
            else:
                raise Exception(f"No upload_full_url or upload_param in response. Full response: {url_data}")

        cdn_headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(ciphertext)),
        }
        cdn_resp = requests.post(upload_url, data=ciphertext, headers=cdn_headers, timeout=30)
        if cdn_resp.status_code not in (200, 201):
            raise Exception(f"CDN upload failed: {cdn_resp.status_code}")

        download_param = cdn_resp.headers.get("x-encrypted-param") or url_data.get("upload_param", "")

        # Map UploadMediaType (IMAGE=1, VIDEO=2, FILE=3, VOICE=4) to MessageItemType (TEXT=1, IMAGE=2, VOICE=3, FILE=4, VIDEO=5)
        if media_type == 1:
            item_type = 2
        elif media_type == 2:
            item_type = 5
        elif media_type == 4:
            item_type = 3
        else:
            item_type = 4

        msg_item = {
            "type": item_type,
        }

        # Aligned with pic-decrypt.ts:
        # Images: aes_key is base64(raw 16 bytes)
        # Other media: aes_key is base64(hex_string of 16 bytes)
        if media_type == 1:
            msg_item["image_item"] = {
                "media": {
                    "encrypt_query_param": download_param,
                    "aes_key": base64.b64encode(aes_key.hex().encode()).decode(),
                    "encrypt_type": 1,
                },
                "mid_size": len(ciphertext),
            }
        elif media_type == 2:
            msg_item["video_item"] = {
                "media": {
                    "encrypt_query_param": download_param,
                    "aes_key": base64.b64encode(aes_key.hex().encode()).decode(),
                    "encrypt_type": 1,
                },
                "video_size": len(ciphertext),
            }
        elif media_type == 4:
            msg_item["voice_item"] = {
                "media": {
                    "encrypt_query_param": download_param,
                    "aes_key": base64.b64encode(aes_key.hex().encode()).decode(),
                    "encrypt_type": 1,
                },
                "encode_type": 6,
            }
        else:
            msg_item["file_item"] = {
                "media": {
                    "encrypt_query_param": download_param,
                    "aes_key": base64.b64encode(aes_key.hex().encode()).decode(),
                    "encrypt_type": 1,
                },
                "file_name": file.filename or "file",
                "len": str(len(raw_bytes)),
            }

        return jsonify({"success": True, "item": msg_item, "filekey": filekey})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/get_updates", methods=["POST"])
def get_updates():
    return jsonify({"success": True, "msgs": [], "get_updates_buf": state.get_updates_buf})


@app.route("/api/notify_start", methods=["POST"])
def notify_start():
    try:
        iLinkRequest("POST", "ilink/bot/msg/notifystart", {"base_info": build_base_info()})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/notify_stop", methods=["POST"])
def notify_stop():
    try:
        iLinkRequest("POST", "ilink/bot/msg/notifystop", {"base_info": build_base_info()})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify(
        {
            "login_status": state.login_status,
            "bot_token": state.bot_token,
            "ilink_bot_id": state.ilink_bot_id,
            "ilink_user_id": state.ilink_user_id,
            "base_url": state.base_url,
            "message_count": len(state.messages),
            "typing_ticket": state.typing_ticket,
        }
    )


@app.route("/api/messages", methods=["GET"])
def get_messages():
    since = request.args.get("since", "0")
    try:
        since_idx = int(since)
    except ValueError:
        since_idx = 0
    msgs = state.messages[since_idx:]
    return jsonify({"success": True, "messages": msgs, "total": len(state.messages)})


@app.route("/api/clear_messages", methods=["POST"])
def clear_messages():
    state.messages = []
    state.get_updates_buf = ""
    return jsonify({"success": True})


def poll_messages():
    while state.is_polling:
        try:
            if state.bot_token and state.login_status == "confirmed":
                result = iLinkRequest(
                    "POST",
                    "ilink/bot/getupdates",
                    {
                        "get_updates_buf": state.get_updates_buf,
                        "base_info": build_base_info(),
                    },
                    timeout=35,
                )
                new_buf = result.get("get_updates_buf")
                if new_buf:
                    state.get_updates_buf = new_buf
                msgs = result.get("msgs", [])
                for msg in msgs:
                    state.messages.append({"timestamp": time.time(), "message": msg})
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(5)


@app.route("/api/start_polling", methods=["POST"])
def start_polling():
    if state.is_polling:
        return jsonify({"success": True, "message": "Already polling"})
    state.is_polling = True
    state.poll_thread = threading.Thread(target=poll_messages, daemon=True)
    state.poll_thread.start()
    return jsonify({"success": True})


@app.route("/api/stop_polling", methods=["POST"])
def stop_polling():
    state.is_polling = False
    if state.poll_thread:
        state.poll_thread.join(timeout=2)
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
