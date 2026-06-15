#!/usr/bin/env bash
# Telegram bot interface for memoriam.
# Usage:
#   ./telegram.sh setup                      — discover chat_id after sending /start
#   ./telegram.sh send "message"             — send a message to your maintainer
#   ./telegram.sh receive                    — fetch new messages (offset-tracked)
#   ./telegram.sh receive --since TIMESTAMP  — fetch messages since timestamp

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMMAND="${1:-}"

if [ -z "$COMMAND" ]; then
  echo "Usage: ./telegram.sh {setup|send|receive} [args]"
  exit 1
fi

shift
python3 -c "
import json, subprocess, sys, os
from datetime import datetime, timezone

project_dir = sys.argv[1]
command = sys.argv[2]
args = sys.argv[3:]

secrets_file = os.path.join(project_dir, 'secrets.json')
state_file = os.path.join(project_dir, 'logs', 'telegram-state.json')

def load_secrets():
    with open(secrets_file) as f:
        return json.load(f)

def load_state():
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {'last_update_id': 0}

def save_state(state):
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, 'w') as f:
        json.dump(state, f)

def api_call(token, method, params=None):
    url = f'https://api.telegram.org/bot{token}/{method}'
    cmd = ['curl', '-s', '-X', 'POST', url]
    if params:
        for k, v in params.items():
            cmd.extend(['-d', f'{k}={v}'])
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not data.get('ok'):
        print(f'API error: {data.get(\"description\", \"unknown error\")}')
        sys.exit(1)
    return data.get('result', [])

def format_time(unix_ts):
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%MZ')

def download_file(token, file_id, save_path):
    file_info = api_call(token, 'getFile', {'file_id': file_id})
    file_path = file_info.get('file_path', '')
    if not file_path:
        return None
    url = f'https://api.telegram.org/file/bot{token}/{file_path}'
    subprocess.run(['curl', '-s', '-o', save_path, url], capture_output=True)
    return save_path

img_dir = '/tmp/telegram-images'

if command == 'setup':
    secrets = load_secrets()
    token = secrets.get('telegram_bot_token', '')
    if not token:
        print('Error: telegram_bot_token is empty in secrets.json')
        sys.exit(1)

    print('Polling for messages... (send /start to your bot in Telegram)')
    updates = api_call(token, 'getUpdates')
    if not updates:
        print('No messages found. Make sure you sent /start to the bot.')
        sys.exit(0)

    for update in updates:
        msg = update.get('message', {})
        chat = msg.get('chat', {})
        chat_id = chat.get('id', '')
        username = chat.get('username', '')
        first_name = chat.get('first_name', '')
        text = msg.get('text', '')
        print(f'  Chat ID: {chat_id}')
        print(f'  From: {first_name} (@{username})')
        print(f'  Text: {text}')
        print()

    print('Copy your chat_id into secrets.json as \"telegram_chat_id\".')

elif command == 'send':
    if not args:
        print('Usage: ./telegram.sh send \"message\"')
        sys.exit(1)

    message = args[0]
    secrets = load_secrets()
    token = secrets.get('telegram_bot_token', '')
    chat_id = secrets.get('telegram_chat_id', '')

    if not token or not chat_id:
        print('Error: telegram_bot_token and telegram_chat_id must be set in secrets.json')
        sys.exit(1)

    result = api_call(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': message
    })
    msg_id = result.get('message_id', '?')
    print(f'Sent (message_id: {msg_id})')

elif command == 'send-image':
    if not args:
        print('Usage: ./telegram.sh send-image \"/path/to/image.png\" [\"caption\"]')
        sys.exit(1)

    image_path = args[0]
    caption = args[1] if len(args) > 1 else ''

    if not os.path.exists(image_path):
        print(f'Error: file not found: {image_path}')
        sys.exit(1)

    secrets = load_secrets()
    token = secrets.get('telegram_bot_token', '')
    chat_id = secrets.get('telegram_chat_id', '')

    if not token or not chat_id:
        print('Error: telegram_bot_token and telegram_chat_id must be set in secrets.json')
        sys.exit(1)

    url = f'https://api.telegram.org/bot{token}/sendPhoto'
    cmd = ['curl', '-s', '-X', 'POST', url,
           '-F', f'chat_id={chat_id}',
           '-F', f'photo=@{image_path}']
    if caption:
        cmd.extend(['-F', f'caption={caption}'])

    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not data.get('ok'):
        print(f'API error: {data.get(\"description\", \"unknown error\")}')
        sys.exit(1)
    msg_id = data.get('result', {}).get('message_id', '?')
    print(f'Sent image (message_id: {msg_id})')

elif command == 'receive':
    since = None
    if args and args[0] == '--since' and len(args) > 1:
        since = args[1]

    secrets = load_secrets()
    token = secrets.get('telegram_bot_token', '')
    chat_id = secrets.get('telegram_chat_id', '')

    if not token or not chat_id:
        print('Error: telegram_bot_token and telegram_chat_id must be set in secrets.json')
        sys.exit(1)

    state = load_state()
    last_id = state.get('last_update_id', 0)

    params = {'timeout': '0'}
    if last_id > 0:
        params['offset'] = str(last_id + 1)

    updates = api_call(token, 'getUpdates', params)

    max_id = last_id
    count = 0
    for update in updates:
        update_id = update.get('update_id', 0)
        if update_id > max_id:
            max_id = update_id

        msg = update.get('message', {})
        chat = msg.get('chat', {})
        if str(chat.get('id', '')) != str(chat_id):
            continue

        msg_date = msg.get('date', 0)
        msg_time = format_time(msg_date)

        if since and msg_time < since:
            continue

        text = msg.get('text', '')
        photos = msg.get('photo', [])
        caption = msg.get('caption', '')

        if text or photos:
            count += 1
            print(f'--- MESSAGE | {msg_time} ---')
            if text:
                print(f'  {text}')
            if photos:
                os.makedirs(img_dir, exist_ok=True)
                # Telegram sends multiple sizes; grab the largest
                largest = max(photos, key=lambda p: p.get('file_size', 0))
                file_id = largest.get('file_id', '')
                ext = 'jpg'
                img_path = os.path.join(img_dir, f'tg_{msg_date}_{file_id[:8]}.{ext}')
                saved = download_file(token, file_id, img_path)
                if caption:
                    print(f'  [image: {caption}]')
                else:
                    print(f'  [image]')
                if saved:
                    print(f'  [saved: {saved}]')
            print()

    if count == 0:
        print('No new messages.')

    if max_id > last_id:
        state['last_update_id'] = max_id
        save_state(state)

else:
    print(f'Unknown command: {command}')
    print('Usage: ./telegram.sh {setup|send|receive} [args]')
    sys.exit(1)
" "$PROJECT_DIR" "$COMMAND" "$@"
