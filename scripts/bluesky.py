#!/usr/bin/env python3
"""
Bluesky client for a memoriam instance.

Usage:
  python3 scripts/bluesky.py post "text" [--image /path/to/image.png] [--video /path/to/video.mp4] [--alt "alt text"]
  python3 scripts/bluesky.py thread "text1" "text2" "text3"
  python3 scripts/bluesky.py reply URI "text"
  python3 scripts/bluesky.py like URI
  python3 scripts/bluesky.py follow DID_OR_HANDLE
  python3 scripts/bluesky.py unfollow DID_OR_HANDLE
  python3 scripts/bluesky.py dm DID_OR_HANDLE "text"
  python3 scripts/bluesky.py dm-list [--limit N]
  python3 scripts/bluesky.py dm-read DID_OR_HANDLE [--limit N] [--keep-unread]
  python3 scripts/bluesky.py delete AT_URI
  python3 scripts/bluesky.py timeline [--limit N]
  python3 scripts/bluesky.py notifications [--limit N]
  python3 scripts/bluesky.py thread-view URI
  python3 scripts/bluesky.py profile HANDLE
  python3 scripts/bluesky.py my-posts [--limit N]
  python3 scripts/bluesky.py followers [--limit N]
  python3 scripts/bluesky.py following [--limit N]
  python3 scripts/bluesky.py update-profile --name "..." --bio "..."
  python3 scripts/bluesky.py update-avatar /path/to/image
  python3 scripts/bluesky.py interactions [--last N]

All write actions are logged to memory/bluesky-interactions.json.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SECRETS_FILE = REPO_DIR / "secrets.json"
INTERACTIONS_FILE = REPO_DIR / "memory" / "bluesky-interactions.json"
LAST_SEEN_FILE = REPO_DIR / "memory" / "bluesky-last-seen.json"
API_BASE = "https://bsky.social/xrpc"
PUBLIC_API_BASE = "https://public.api.bsky.app/xrpc"

# --- Auth ---

_session = None

def load_secrets():
    with open(SECRETS_FILE) as f:
        return json.load(f)

SESSION_CACHE = os.path.join(os.path.dirname(SECRETS_FILE), "logs", "bluesky-session.json")

def _save_session_cache(sess):
    try:
        os.makedirs(os.path.dirname(SESSION_CACHE), exist_ok=True)
        with open(SESSION_CACHE, "w") as f:
            json.dump(sess, f)
        os.chmod(SESSION_CACHE, 0o600)
    except OSError:
        pass

def create_session():
    """Session with disk cache + refresh. The bluesky-watch cron polls every
    couple of minutes; without reuse it would exhaust Bluesky's createSession
    daily rate limit (2026-06-11)."""
    global _session
    if _session:
        return _session
    # 1. Fresh-enough cached access token
    try:
        age = time.time() - os.stat(SESSION_CACHE).st_mtime
        with open(SESSION_CACHE) as f:
            cached = json.load(f)
        if age < 5400 and cached.get("accessJwt"):
            _session = cached
            return _session
        # 2. Stale: try refreshSession with the refresh token
        if cached.get("refreshJwt"):
            r = subprocess.run(
                ["curl", "-s", "-X", "POST",
                 "-H", f"Authorization: Bearer {cached['refreshJwt']}",
                 f"{API_BASE}/com.atproto.server.refreshSession"],
                capture_output=True, text=True)
            resp = json.loads(r.stdout) if r.stdout else {}
            if resp.get("accessJwt"):
                # keep fields refreshSession does not return (e.g. didDoc)
                merged = {**cached, **resp}
                _session = merged
                _save_session_cache(merged)
                return _session
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    # 3. Full login
    secrets = load_secrets()
    resp = api_call("com.atproto.server.createSession", {
        "identifier": secrets["bluesky_handle"],
        "password": secrets["bluesky_app_password"],
    }, method="post", auth=False)
    _session = resp
    if resp.get("accessJwt"):
        _save_session_cache(resp)
    return _session

def api_call(endpoint, data=None, method="get", auth=True, params=None, public=False):
    base = PUBLIC_API_BASE if public else API_BASE
    url = f"{base}/{endpoint}"
    cmd = ["curl", "-s"]

    if auth:
        session = create_session()
        cmd += ["-H", f"Authorization: Bearer {session['accessJwt']}"]

    if method == "post":
        cmd += ["-X", "POST", "-H", "Content-Type: application/json"]
        if data:
            cmd += ["-d", json.dumps(data)]
        cmd.append(url)
    else:
        if params:
            pairs = [f"{k}={v}" for k, v in params.items()]
            url += "?" + "&".join(pairs)
        cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)

# --- Direct messages (chat service) ---

# Bluesky chat lives on a separate service, reached by sending the normal
# xrpc request to the PDS/entryway with this proxy header set.
CHAT_PROXY = "did:web:api.bsky.chat#bsky_chat"

def chat_call(endpoint, data=None, method="get", params=None):
    """Call a chat.bsky.convo.* endpoint via the chat service proxy.

    Proxied requests must hit the account's real PDS host (from the
    session's didDoc), not the bsky.social entryway, or the entryway
    answers MethodNotImplemented.
    """
    session = create_session()
    pds = session.get("didDoc", {}).get("service", [{}])[0].get(
        "serviceEndpoint", "https://bsky.social").rstrip("/")
    url = f"{pds}/xrpc/{endpoint}"
    cmd = ["curl", "-s",
           "-H", f"Authorization: Bearer {session['accessJwt']}",
           "-H", f"atproto-proxy: {CHAT_PROXY}"]
    if method == "post":
        cmd += ["-X", "POST", "-H", "Content-Type: application/json"]
        if data:
            cmd += ["-d", json.dumps(data)]
        cmd.append(url)
    else:
        if params:
            pairs = [f"{k}={v}" for k, v in params.items()]
            url += "?" + "&".join(pairs)
        cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def do_dm(target, text):
    """Send a direct message to a DID or handle."""
    did = target
    if not target.startswith("did:"):
        resp = api_call("com.atproto.identity.resolveHandle",
                        params={"handle": target}, auth=False)
        did = resp.get("did", "")
        if not did:
            print(f"Error: could not resolve handle '{target}'")
            return
    convo_resp = chat_call("chat.bsky.convo.getConvoForMembers",
                           params={"members": did})
    convo = convo_resp.get("convo")
    if not convo or not convo.get("id"):
        print(f"Error: could not open a conversation with {target}.")
        print("  (They may have DMs disabled or limited to people they follow.)")
        if convo_resp:
            print(f"  Response: {json.dumps(convo_resp)}")
        return
    message = {"text": text}
    facets = detect_facets(text)
    if facets:
        message["facets"] = facets
    resp = chat_call("chat.bsky.convo.sendMessage",
                     data={"convoId": convo["id"], "message": message},
                     method="post")
    if resp.get("id"):
        log_interaction("dm", {"did": did, "handle": target, "text": text[:120]})
        print(f"DM sent to {target} ({did})")
        print(f"  convo: {convo['id']}  message: {resp.get('id')}")
    else:
        print(f"Error sending DM: {json.dumps(resp)}")
    return resp


def _member_handle(member):
    return member.get("handle", member.get("did", "?"))

def do_dm_list(limit=20):
    """List conversations, newest first, with unread counts."""
    session = create_session()
    resp = chat_call("chat.bsky.convo.listConvos", params={"limit": limit})
    if resp.get("error"):
        print(f"Error listing conversations: {json.dumps(resp)}")
        return
    convos = resp.get("convos", [])
    if not convos:
        print("No conversations.")
        return
    for c in convos:
        others = [_member_handle(m) for m in c.get("members", [])
                  if m.get("did") != session["did"]]
        unread = c.get("unreadCount", 0)
        last = c.get("lastMessage", {}) or {}
        snippet = (last.get("text", "") or "").replace("\n", " ")[:80]
        flag = f"[{unread} unread] " if unread else ""
        print(f"{flag}{', '.join(others)}: {snippet}")
    return convos

def do_dm_read(target, limit=30, mark_read=True):
    """Show a conversation's messages (oldest->newest) and mark it read."""
    session = create_session()
    did = target
    if not target.startswith("did:"):
        r = api_call("com.atproto.identity.resolveHandle",
                     params={"handle": target}, auth=False)
        did = r.get("did", "")
        if not did:
            print(f"Error: could not resolve handle '{target}'")
            return
    convo_resp = chat_call("chat.bsky.convo.getConvoForMembers",
                           params={"members": did})
    convo = convo_resp.get("convo")
    if not convo or not convo.get("id"):
        print(f"No conversation with {target}. {json.dumps(convo_resp)}")
        return
    convo_id = convo["id"]
    msgs_resp = chat_call("chat.bsky.convo.getMessages",
                          params={"convoId": convo_id, "limit": limit})
    messages = msgs_resp.get("messages", [])
    for m in reversed(messages):  # API returns newest-first
        who = "me" if m.get("sender", {}).get("did") == session["did"] else target
        sent = (m.get("sentAt", "") or "")[:16].replace("T", " ")
        print(f"[{sent}] {who}: {m.get('text', '')}")
    if mark_read and messages:
        chat_call("chat.bsky.convo.updateRead",
                  data={"convoId": convo_id}, method="post")
    return messages

# --- Interaction log ---

def load_interactions():
    if INTERACTIONS_FILE.exists():
        with open(INTERACTIONS_FILE) as f:
            return json.load(f)
    return []

def load_last_seen():
    if LAST_SEEN_FILE.exists():
        with open(LAST_SEEN_FILE) as f:
            return json.load(f)
    return {}

def save_last_seen(data):
    with open(LAST_SEEN_FILE, "w") as f:
        json.dump(data, f, indent=2)

def log_interaction(action_type, details):
    interactions = load_interactions()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action_type,
        **details,
    }
    interactions.append(entry)
    with open(INTERACTIONS_FILE, "w") as f:
        json.dump(interactions, f, indent=2)
    return entry

# --- Rich text facets ---

def detect_facets(text):
    """Detect mentions and links for Bluesky rich text."""
    import re
    facets = []
    # Detect mentions (@handle.thing)
    for m in re.finditer(r'@([a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+)', text):
        handle = m.group(1)
        # Resolve handle to DID
        resp = api_call("com.atproto.identity.resolveHandle",
                       params={"handle": handle}, auth=False)
        did = resp.get("did")
        if did:
            facets.append({
                "index": {
                    "byteStart": len(text[:m.start()].encode("utf-8")),
                    "byteEnd": len(text[:m.end()].encode("utf-8")),
                },
                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
            })
    # Detect URLs (with or without protocol)
    for m in re.finditer(r'(?:https?://[^\s\)]+|(?<!\w)(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/[^\s\)]*)', text):
        facets.append({
            "index": {
                "byteStart": len(text[:m.start()].encode("utf-8")),
                "byteEnd": len(text[:m.end()].encode("utf-8")),
            },
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)}],
        })
    return facets

# --- Image upload ---

def upload_blob(image_path):
    """Upload an image and return the blob reference."""
    session = create_session()
    ext = image_path.lower().rsplit(".", 1)[-1]
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}
    mime = mime_map.get(ext, "image/png")
    cmd = ["curl", "-s", "-X", "POST",
           "-H", f"Authorization: Bearer {session['accessJwt']}",
           "-H", f"Content-Type: {mime}",
           "--data-binary", f"@{image_path}",
           f"{API_BASE}/com.atproto.repo.uploadBlob"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    blob_resp = json.loads(result.stdout)
    return blob_resp.get("blob", {})

# --- Video upload ---

def upload_video(video_path):
    """Upload a video to Bluesky's video service and return the blob reference."""
    session = create_session()
    did = session["did"]

    # Step 1: Get service auth token for video upload
    # The PDS host from the session's didDoc
    pds_url = session.get("didDoc", {}).get("service", [{}])[0].get("serviceEndpoint", "https://bsky.social")
    pds_host = pds_url.replace("https://", "").replace("http://", "")
    aud = f"did:web:{pds_host}"

    # Get expiry 30 min from now
    exp = int(time.time()) + 1800

    auth_resp = api_call("com.atproto.server.getServiceAuth",
                        params={"aud": aud, "lxm": "com.atproto.repo.uploadBlob", "exp": str(exp)})
    service_token = auth_resp.get("token", "")
    if not service_token:
        print(f"Error getting service auth: {auth_resp}")
        return None

    # Step 2: Upload video to video.bsky.app
    filename = Path(video_path).name
    file_size = os.path.getsize(video_path)
    cmd = ["curl", "-s", "-X", "POST",
           "-H", f"Authorization: Bearer {service_token}",
           "-H", "Content-Type: video/mp4",
           "-H", f"Content-Length: {file_size}",
           "--data-binary", f"@{video_path}",
           f"https://video.bsky.app/xrpc/app.bsky.video.uploadVideo?did={did}&name={filename}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    upload_resp = json.loads(result.stdout)

    if "error" in upload_resp:
        print(f"Video upload error: {upload_resp}")
        return None

    job_id = upload_resp.get("jobId", "")
    if not job_id:
        # Direct blob return (unlikely but possible)
        return upload_resp.get("blob")

    # Step 3: Poll for processing completion.
    # NOTE (2026-06-11): getJobStatus must be asked of video.bsky.app with its
    # own service auth — asking the PDS returns MethodNotImplemented, which made
    # this loop poll blind until it "timed out" on already-finished jobs.
    status_auth = api_call("com.atproto.server.getServiceAuth",
                           params={"aud": "did:web:video.bsky.app",
                                   "lxm": "app.bsky.video.getJobStatus",
                                   "exp": str(int(time.time()) + 1800)})
    status_token = status_auth.get("token", "")
    print(f"Video processing (job {job_id})...")
    for _ in range(90):  # up to ~3 min
        time.sleep(2)
        sr = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {status_token}",
             f"https://video.bsky.app/xrpc/app.bsky.video.getJobStatus?jobId={job_id}"],
            capture_output=True, text=True)
        try:
            status_resp = json.loads(sr.stdout)
        except json.JSONDecodeError:
            status_resp = {}
        state = status_resp.get("jobStatus", {}).get("state", "")
        blob = status_resp.get("jobStatus", {}).get("blob")
        if blob:
            print("Video processed.")
            return blob
        if state == "JOB_STATE_FAILED":
            error = status_resp.get("jobStatus", {}).get("error", "unknown")
            print(f"Video processing failed: {error}")
            return None
        print(f"  ...{state}")

    print("Video processing timed out.")
    return None

# --- Write actions ---

def do_post(text, image_path=None, alt_text="", video_path=None):
    session = create_session()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now,
    }
    facets = detect_facets(text)
    if facets:
        record["facets"] = facets
    if video_path:
        blob = upload_video(video_path)
        if blob:
            record["embed"] = {
                "$type": "app.bsky.embed.video",
                "video": blob,
                "alt": alt_text or "",
            }
        else:
            # Never post a "here is a video" post with no video in it
            # (2026-06-11: this fallback published a broken post once).
            print("Video upload failed; aborting post.")
            return None
    elif image_path:
        blob = upload_blob(image_path)
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [{
                "alt": alt_text or text,
                "image": blob,
            }],
        }
    resp = api_call("com.atproto.repo.createRecord", {
        "repo": session["did"],
        "collection": "app.bsky.feed.post",
        "record": record,
    }, method="post")
    if "error" in resp:
        print(f"Error: {resp.get('error')}: {resp.get('message', '')}")
        return resp
    uri = resp.get("uri", "")
    cid = resp.get("cid", "")
    log_interaction("post", {"uri": uri, "cid": cid, "text": text, **({"video": video_path} if video_path else {"image": image_path} if image_path else {})})
    print(f"Posted: {text[:80]}...")
    print(f"URI: {uri}")
    return resp

def do_thread(texts):
    # Guard against the easy mistake of confusing `thread` (post) with `thread-view` (read).
    # If every "post" looks like an AT URI, the caller almost certainly meant to view a thread.
    if texts and all(t.startswith("at://") for t in texts):
        print("Refusing to post: all texts look like AT URIs.", file=sys.stderr)
        print("Did you mean `thread-view URI` to read a thread?", file=sys.stderr)
        sys.exit(2)

    session = create_session()
    root_uri = None
    root_cid = None
    parent_uri = None
    parent_cid = None

    for i, text in enumerate(texts):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now,
        }
        facets = detect_facets(text)
        if facets:
            record["facets"] = facets
        if parent_uri:
            record["reply"] = {
                "root": {"uri": root_uri, "cid": root_cid},
                "parent": {"uri": parent_uri, "cid": parent_cid},
            }
        resp = api_call("com.atproto.repo.createRecord", {
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        }, method="post")
        uri = resp.get("uri", "")
        cid = resp.get("cid", "")
        if i == 0:
            root_uri = uri
            root_cid = cid
        parent_uri = uri
        parent_cid = cid
        log_interaction("thread_post", {"uri": uri, "cid": cid, "text": text, "thread_index": i})
        print(f"  [{i+1}/{len(texts)}] {text[:60]}...")

    print(f"Thread posted ({len(texts)} posts)")
    return root_uri

def do_reply(parent_uri, text):
    session = create_session()
    # Fetch the parent post to get its CID and root
    post_data = get_post_thread(parent_uri)
    if not post_data:
        print("Error: could not fetch parent post")
        return
    thread = post_data.get("thread", {})
    parent_post = thread.get("post", {})
    parent_cid = parent_post.get("cid", "")

    # Find the root of the thread
    root = thread
    while root.get("parent", {}).get("post"):
        root = root["parent"]
    root_post = root.get("post", parent_post)
    root_uri = root_post.get("uri", parent_uri)
    root_cid = root_post.get("cid", parent_cid)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now,
        "reply": {
            "root": {"uri": root_uri, "cid": root_cid},
            "parent": {"uri": parent_uri, "cid": parent_cid},
        },
    }
    facets = detect_facets(text)
    if facets:
        record["facets"] = facets
    resp = api_call("com.atproto.repo.createRecord", {
        "repo": session["did"],
        "collection": "app.bsky.feed.post",
        "record": record,
    }, method="post")
    uri = resp.get("uri", "")
    log_interaction("reply", {"uri": uri, "parent_uri": parent_uri, "text": text})
    print(f"Replied to {parent_uri}")
    print(f"URI: {uri}")
    return resp

def do_like(subject_uri):
    session = create_session()
    # Need the CID — fetch the post
    resp = api_call("app.bsky.feed.getPosts",
                   params={"uris": subject_uri}, public=True)
    posts = resp.get("posts", [])
    if not posts:
        print("Error: could not fetch post")
        return
    subject_cid = posts[0].get("cid", "")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    resp = api_call("com.atproto.repo.createRecord", {
        "repo": session["did"],
        "collection": "app.bsky.feed.like",
        "record": {
            "$type": "app.bsky.feed.like",
            "subject": {"uri": subject_uri, "cid": subject_cid},
            "createdAt": now,
        },
    }, method="post")
    log_interaction("like", {"uri": subject_uri})
    print(f"Liked: {subject_uri}")
    return resp

def do_follow(target):
    session = create_session()
    # Resolve handle to DID if needed
    did = target
    if not target.startswith("did:"):
        resp = api_call("com.atproto.identity.resolveHandle",
                       params={"handle": target}, auth=False)
        did = resp.get("did", "")
        if not did:
            print(f"Error: could not resolve handle '{target}'")
            return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    resp = api_call("com.atproto.repo.createRecord", {
        "repo": session["did"],
        "collection": "app.bsky.graph.follow",
        "record": {
            "$type": "app.bsky.graph.follow",
            "subject": did,
            "createdAt": now,
        },
    }, method="post")
    log_interaction("follow", {"did": did, "handle": target})
    print(f"Followed: {target} ({did})")
    return resp

def do_unfollow(target):
    session = create_session()
    # Resolve handle to DID if needed
    did = target
    handle = target
    if not target.startswith("did:"):
        resp = api_call("com.atproto.identity.resolveHandle",
                       params={"handle": target}, auth=False)
        did = resp.get("did", "")
        if not did:
            print(f"Error: could not resolve handle '{target}'")
            return

    # Find the follow record
    resp = api_call("app.bsky.graph.getFollows",
                   params={"actor": session["did"], "limit": "100"})
    follows = resp.get("follows", [])
    follow_uri = None
    for f in follows:
        if f.get("did") == did:
            # Need to find the record key — list records
            break

    # Use listRecords to find the follow record
    resp = api_call("com.atproto.repo.listRecords",
                   params={"repo": session["did"],
                           "collection": "app.bsky.graph.follow",
                           "limit": "100"})
    records = resp.get("records", [])
    for r in records:
        if r.get("value", {}).get("subject") == did:
            follow_uri = r.get("uri", "")
            rkey = follow_uri.split("/")[-1]
            break

    if not follow_uri:
        print(f"Error: not following {target}")
        return

    api_call("com.atproto.repo.deleteRecord", {
        "repo": session["did"],
        "collection": "app.bsky.graph.follow",
        "rkey": rkey,
    }, method="post")
    log_interaction("unfollow", {"did": did, "handle": handle})
    print(f"Unfollowed: {target}")

def do_delete_post(post_uri):
    """Delete one of my own posts by AT URI."""
    session = create_session()
    # Extract rkey from URI: at://did/collection/rkey
    parts = post_uri.split("/")
    rkey = parts[-1]
    api_call("com.atproto.repo.deleteRecord", {
        "repo": session["did"],
        "collection": "app.bsky.feed.post",
        "rkey": rkey,
    }, method="post")
    log_interaction("delete_post", {"uri": post_uri})
    print(f"Deleted: {post_uri}")

def do_update_profile(display_name=None, description=None):
    session = create_session()
    # Get current profile record
    resp = api_call("com.atproto.repo.getRecord",
                   params={"repo": session["did"],
                           "collection": "app.bsky.actor.profile",
                           "rkey": "self"})
    record = resp.get("value", {})
    if display_name is not None:
        record["displayName"] = display_name
    if description is not None:
        record["description"] = description
    record["$type"] = "app.bsky.actor.profile"

    api_call("com.atproto.repo.putRecord", {
        "repo": session["did"],
        "collection": "app.bsky.actor.profile",
        "rkey": "self",
        "record": record,
    }, method="post")
    log_interaction("update_profile", {"displayName": display_name, "description": description})
    print("Profile updated.")

def do_update_avatar(image_path):
    session = create_session()
    # Upload the image as a blob
    with open(image_path, "rb") as f:
        image_data = f.read()

    # Determine mime type
    ext = image_path.lower().rsplit(".", 1)[-1]
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}
    mime = mime_map.get(ext, "image/png")

    # Upload blob via curl directly (binary data)
    cmd = ["curl", "-s", "-X", "POST",
           "-H", f"Authorization: Bearer {session['accessJwt']}",
           "-H", f"Content-Type: {mime}",
           "--data-binary", f"@{image_path}",
           f"{API_BASE}/com.atproto.repo.uploadBlob"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    blob_resp = json.loads(result.stdout)
    blob = blob_resp.get("blob", {})

    # Get current profile and update avatar
    resp = api_call("com.atproto.repo.getRecord",
                   params={"repo": session["did"],
                           "collection": "app.bsky.actor.profile",
                           "rkey": "self"})
    record = resp.get("value", {})
    record["$type"] = "app.bsky.actor.profile"
    record["avatar"] = blob

    api_call("com.atproto.repo.putRecord", {
        "repo": session["did"],
        "collection": "app.bsky.actor.profile",
        "rkey": "self",
        "record": record,
    }, method="post")
    log_interaction("update_avatar", {"path": image_path})
    print("Avatar updated.")

# --- Read actions ---

def get_timeline(limit=100, pages=3):
    last_seen = load_last_seen()
    last_timeline_ts = last_seen.get("timeline")
    newest_ts = None
    all_feed = []
    cursor = None
    new_count = 0
    old_count = 0

    for page in range(pages):
        params = {"limit": str(min(limit, 100))}
        if cursor:
            params["cursor"] = cursor
        resp = api_call("app.bsky.feed.getTimeline", params=params)
        feed = resp.get("feed", [])
        if not feed:
            break

        for item in feed:
            post = item.get("post", {})
            record = post.get("record", {})
            post_ts = record.get("createdAt", "")
            reason = item.get("reason", {})
            is_repost = reason.get("$type", "") == "app.bsky.feed.defs#reasonRepost"
            feed_ts = reason.get("indexedAt", post_ts) if is_repost else post.get("indexedAt", post_ts)

            if newest_ts is None or feed_ts > newest_ts:
                newest_ts = feed_ts

            is_old = last_timeline_ts and feed_ts <= last_timeline_ts
            if is_old:
                old_count += 1
            else:
                new_count += 1
            print_feed_item(item, dim=is_old)

        all_feed.extend(feed)
        cursor = resp.get("cursor")
        if not cursor:
            break
        if len(all_feed) >= limit:
            break
        # Stop paginating if we've hit old posts
        if old_count > 0:
            break

    if not all_feed:
        print("Timeline is empty. Follow some accounts to see posts here.")
    else:
        parts = []
        if new_count: parts.append(f"{new_count} new")
        if old_count: parts.append(f"{old_count} seen")
        print(f"--- {', '.join(parts)} ---")

    # Update high-water mark
    if newest_ts:
        last_seen["timeline"] = newest_ts
        save_last_seen(last_seen)

    return all_feed

def get_notifications(limit=30):
    resp = api_call("app.bsky.notification.listNotifications",
                   params={"limit": str(limit)})
    notifs = resp.get("notifications", [])
    for n in notifs:
        reason = n.get("reason", "")
        author = n.get("author", {})
        handle = author.get("handle", "")
        display = author.get("displayName", handle)
        time = n.get("indexedAt", "")[:16]
        record = n.get("record", {})
        text = record.get("text", "")

        if reason == "like":
            print(f"  {time} | {display} (@{handle}) liked your post")
        elif reason == "repost":
            print(f"  {time} | {display} (@{handle}) reposted you")
        elif reason == "follow":
            print(f"  {time} | {display} (@{handle}) followed you")
        elif reason == "reply":
            print(f"  {time} | {display} (@{handle}) replied: {text[:100]}")
        elif reason == "mention":
            print(f"  {time} | {display} (@{handle}) mentioned you: {text[:100]}")
        elif reason == "quote":
            print(f"  {time} | {display} (@{handle}) quoted you: {text[:100]}")
        else:
            print(f"  {time} | {reason} from {display} (@{handle})")
    if not notifs:
        print("No notifications.")
    return notifs

def get_post_thread(uri):
    resp = api_call("app.bsky.feed.getPostThread",
                   params={"uri": uri, "depth": "10", "parentHeight": "10"},
                   public=True)
    return resp

def view_thread(uri):
    resp = get_post_thread(uri)
    thread = resp.get("thread", {})
    # Collect parents (walk up)
    parents = []
    node = thread
    while node.get("parent", {}).get("post"):
        node = node["parent"]
        parents.append(node)
    parents.reverse()

    # Print parent chain
    for p in parents:
        print_thread_post(p.get("post", {}), indent="  ")
        print("    │")

    # Print the target post
    print_thread_post(thread.get("post", {}), indent="▸ ", highlight=True)

    # Print replies
    replies = thread.get("replies", [])
    print_replies(replies, depth=1)

def print_replies(replies, depth=1):
    indent = "  " * depth + "  "
    for r in replies:
        post = r.get("post", {})
        if post:
            print(f"{indent}│")
            print_thread_post(post, indent=indent)
            sub_replies = r.get("replies", [])
            if sub_replies:
                print_replies(sub_replies, depth=depth+1)

def print_thread_post(post, indent="", highlight=False):
    author = post.get("author", {})
    handle = author.get("handle", "")
    display = author.get("displayName", handle)
    record = post.get("record", {})
    text = record.get("text", "")
    created = record.get("createdAt", "")[:16]
    uri = post.get("uri", "")
    likes = post.get("likeCount", 0)
    replies = post.get("replyCount", 0)
    reposts = post.get("repostCount", 0)

    marker = "★ " if highlight else ""
    print(f"{indent}{marker}{display} (@{handle}) — {created}")
    for line in text.split("\n"):
        print(f"{indent}  {line}")
    stats = []
    if likes: stats.append(f"{likes} likes")
    if reposts: stats.append(f"{reposts} reposts")
    if replies: stats.append(f"{replies} replies")
    if stats:
        print(f"{indent}  [{', '.join(stats)}]")
    print(f"{indent}  URI: {uri}")

def view_profile(handle):
    resp = api_call("app.bsky.actor.getProfile",
                   params={"actor": handle}, public=True)
    display = resp.get("displayName", "")
    desc = resp.get("description", "")
    followers = resp.get("followersCount", 0)
    following = resp.get("followsCount", 0)
    posts = resp.get("postsCount", 0)
    h = resp.get("handle", handle)

    print(f"{display} (@{h})")
    if desc:
        for line in desc.split("\n"):
            print(f"  {line}")
    print(f"  {followers} followers · {following} following · {posts} posts")

    # Show recent posts
    feed_resp = api_call("app.bsky.feed.getAuthorFeed",
                        params={"actor": handle, "limit": "10"}, public=True)
    feed = feed_resp.get("feed", [])
    if feed:
        print(f"\n  Recent posts:")
        for item in feed:
            post = item.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "")
            created = record.get("createdAt", "")[:16]
            print(f"    {created} — {text[:100]}")

    return resp

def get_my_posts(limit=20):
    session = create_session()
    resp = api_call("app.bsky.feed.getAuthorFeed",
                   params={"actor": session["did"], "limit": str(limit)},
                   public=True)
    feed = resp.get("feed", [])
    for item in feed:
        print_feed_item(item)
    if not feed:
        print("No posts yet.")
    return feed

def get_followers(limit=50):
    session = create_session()
    resp = api_call("app.bsky.graph.getFollowers",
                   params={"actor": session["did"], "limit": str(limit)})
    followers = resp.get("followers", [])
    for f in followers:
        handle = f.get("handle", "")
        display = f.get("displayName", handle)
        desc = f.get("description", "")
        print(f"  {display} (@{handle})")
        if desc:
            print(f"    {desc[:100]}")
    if not followers:
        print("No followers yet.")
    return followers

def get_following(limit=50):
    session = create_session()
    resp = api_call("app.bsky.graph.getFollows",
                   params={"actor": session["did"], "limit": str(limit)})
    follows = resp.get("follows", [])
    for f in follows:
        handle = f.get("handle", "")
        display = f.get("displayName", handle)
        print(f"  {display} (@{handle})")
    if not follows:
        print("Not following anyone yet.")
    return follows

def view_interactions(last_n=20):
    interactions = load_interactions()
    recent = interactions[-last_n:] if last_n else interactions
    for entry in recent:
        ts = entry.get("timestamp", "")[:16]
        action = entry.get("action", "")
        text = entry.get("text", "")
        uri = entry.get("uri", "")
        handle = entry.get("handle", "")

        if text:
            print(f"  {ts} | {action}: {text[:80]}")
        elif handle:
            print(f"  {ts} | {action}: {handle}")
        elif uri:
            print(f"  {ts} | {action}: {uri}")
        else:
            print(f"  {ts} | {action}")
    if not recent:
        print("No interactions logged yet.")

# --- Feed item display ---

def print_feed_item(item, dim=False):
    post = item.get("post", {})
    author = post.get("author", {})
    handle = author.get("handle", "")
    did = author.get("did", "")
    display = author.get("displayName", handle)
    record = post.get("record", {})
    text = record.get("text", "")
    created = record.get("createdAt", "")[:16]
    uri = post.get("uri", "")
    likes = post.get("likeCount", 0)
    replies_count = post.get("replyCount", 0)

    reason = item.get("reason", {})
    is_repost = reason.get("$type", "") == "app.bsky.feed.defs#reasonRepost"

    prefix = "  (seen) " if dim else "  "

    if is_repost:
        by = reason.get("by", {})
        rp_handle = by.get("handle", "")
        print(f"{prefix}↻ reposted by @{rp_handle}")

    print(f"{prefix}{display} (@{handle} | {did[:20]}…) — {created}")
    for line in text.split("\n"):
        print(f"{prefix}  {line}")

    # Images
    embed = post.get("embed", {})
    embed_type = embed.get("$type", "")
    images = []
    if embed_type == "app.bsky.embed.images#view":
        images = embed.get("images", [])
    for img in images:
        alt = img.get("alt", "")
        if alt:
            print(f"{prefix}  [image: {alt}]")
        else:
            print(f"{prefix}  [image]")

    stats = []
    if likes: stats.append(f"{likes}♡")
    if replies_count: stats.append(f"{replies_count}↩")
    if stats:
        print(f"{prefix}  {' '.join(stats)}")
    print(f"{prefix}  {uri}")
    print()

# --- CLI ---

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "post":
        text = sys.argv[2]
        image_path = None
        video_path = None
        alt_text = ""
        rest = sys.argv[3:]
        i = 0
        while i < len(rest):
            if rest[i] == "--image" and i + 1 < len(rest):
                image_path = rest[i + 1]
                i += 2
            elif rest[i] == "--video" and i + 1 < len(rest):
                video_path = rest[i + 1]
                i += 2
            elif rest[i] == "--alt" and i + 1 < len(rest):
                alt_text = rest[i + 1]
                i += 2
            else:
                i += 1
        do_post(text, image_path=image_path, alt_text=alt_text, video_path=video_path)

    elif cmd == "thread":
        do_thread(sys.argv[2:])

    elif cmd == "reply":
        do_reply(sys.argv[2], sys.argv[3])

    elif cmd == "like":
        do_like(sys.argv[2])

    elif cmd == "follow":
        do_follow(sys.argv[2])

    elif cmd == "unfollow":
        do_unfollow(sys.argv[2])

    elif cmd == "dm":
        do_dm(sys.argv[2], sys.argv[3])

    elif cmd == "dm-list":
        limit = 20
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        do_dm_list(limit)

    elif cmd == "dm-read":
        limit = 30
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        mark_read = "--keep-unread" not in sys.argv
        do_dm_read(sys.argv[2], limit, mark_read)

    elif cmd == "delete":
        do_delete_post(sys.argv[2])

    elif cmd == "timeline":
        limit = 100
        pages = 3
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        if "--pages" in sys.argv:
            pages = int(sys.argv[sys.argv.index("--pages") + 1])
        get_timeline(limit, pages)

    elif cmd == "notifications":
        limit = 30
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        get_notifications(limit)

    elif cmd == "thread-view":
        view_thread(sys.argv[2])

    elif cmd == "profile":
        view_profile(sys.argv[2])

    elif cmd == "my-posts":
        limit = 20
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        get_my_posts(limit)

    elif cmd == "followers":
        limit = 50
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        get_followers(limit)

    elif cmd == "following":
        limit = 50
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        get_following(limit)

    elif cmd == "update-profile":
        name = None
        bio = None
        if "--name" in sys.argv:
            name = sys.argv[sys.argv.index("--name") + 1]
        if "--bio" in sys.argv:
            bio = sys.argv[sys.argv.index("--bio") + 1]
        do_update_profile(name, bio)

    elif cmd == "update-avatar":
        do_update_avatar(sys.argv[2])

    elif cmd == "interactions":
        last_n = 20
        if "--last" in sys.argv:
            last_n = int(sys.argv[sys.argv.index("--last") + 1])
        view_interactions(last_n)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
