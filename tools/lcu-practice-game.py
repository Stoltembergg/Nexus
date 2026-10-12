#!/usr/bin/env python3
"""Create a Practice Tool game with a chosen champion through the League client's local API.

Uses the client's own loopback API with the credentials from its lockfile (never printed), the
same way tools/check-riot-vanguard.py reads Vanguard status. Steps: wait until the client is
idle and Vanguard is connected, create a Practice Tool lobby, start champion select, lock the
champion, then report gameflow phases until the game process starts (or --wait seconds pass).
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

import requests
import urllib3

PRACTICE_TOOL_MAP = 11
PRACTICE_TOOL_QUEUE = 3140   # 'Multiplayer Practice Tool Custom' in /lol-game-queues/v1/queues
CHAMPIONS = {'kindred': 203}   # championId by lower-case name; use --champion-id for others


class Client:
    """Re-reads the lockfile on every call: the client writes it before the API listens, may
    rewrite it with a new port/token, and a stale one can survive from the previous run."""
    def __init__(self, lockfile):
        self.lockfile = lockfile
        self.base = self.auth = None
        self.refresh()

    def refresh(self):
        try:
            parts = self.lockfile.read_text().strip().split(':')
            if len(parts) != 5 or parts[4] != 'https':
                return False
            self.base = f'https://127.0.0.1:{int(parts[2])}'
            self.auth = ('riot', parts[3])
            return True
        except (OSError, ValueError):
            return False

    def call(self, method, path, body=None, timeout=15):
        if not self.refresh():
            return RuntimeError('lockfile missing or incomplete')
        try:
            return requests.request(method, self.base + path, json=body, auth=self.auth,
                                    verify=False, timeout=timeout)
        except requests.RequestException as error:
            return error

    def json(self, method, path, body=None):
        response = self.call(method, path, body)
        if isinstance(response, Exception) or response.status_code >= 300:
            return None
        try:
            return response.json()
        except ValueError:
            return None


def log(message):
    print(f'{datetime.now(timezone.utc).strftime("%H:%M:%S")} {message}', flush=True)


def wait_for(description, predicate, timeout, interval=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    log(f'timed out waiting for {description}')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--champion', default='kindred')
    parser.add_argument('--champion-id', type=int)
    parser.add_argument('--wait', type=int, default=180, help='seconds to watch after locking in (champion select runs a 90 s timer first)')
    parser.add_argument('--lockfile', type=Path, default=Path.home() /
                        '.darling/Applications/League of Legends.app/Contents/LoL/lockfile')
    args = parser.parse_args()
    champion = args.champion_id or CHAMPIONS.get(args.champion.lower())
    if not champion:
        parser.error('unknown champion: pass --champion-id')

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    log('waiting for the League client to start')
    if not wait_for('League lockfile', lambda: args.lockfile.exists(), 900, interval=5):
        return 1
    client = Client(args.lockfile)

    def phase():
        value = client.json('GET', '/lol-gameflow/v1/gameflow-phase')
        return value if isinstance(value, str) else None

    log('waiting for the client to finish loading')
    if not wait_for('gameflow API', lambda: phase() is not None, 600):
        return 1
    vanguard = wait_for('Vanguard', lambda: (client.json('GET', '/lol-vanguard/v1/session') or {}).get('state') == 'CONNECTED', 300)
    if not vanguard:
        return 1
    log(f'phase={phase()}, Vanguard CONNECTED')

    if phase() in ('InProgress', 'Reconnect'):
        def running_game():
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    executable = (proc / 'cmdline').read_bytes().split(b'\0')[0].lower()
                except OSError:
                    continue
                if b'leagueoflegends.app/contents/macos/leagueoflegends' in executable:
                    return True
            return False
        if not running_game():
            response = client.call('POST', '/lol-gameflow/v1/reconnect')
            if isinstance(response, Exception) or response.status_code >= 300:
                log('reconnect failed: ' + str(response if isinstance(response, Exception) else response.status_code))
                return 1
            log('reconnecting to the existing match')
        return 0 if wait_for('running game', running_game, 120) else 1

    if phase() not in ('None', 'Lobby'):
        log(f'client is in phase {phase()}; leave it first')
        return 1

    if phase() == 'None':
        lobby = {
            'customGameLobby': {
                'configuration': {'gameMode': 'PRACTICETOOL', 'gameMutator': '', 'gameServerRegion': '',
                                  'mapId': PRACTICE_TOOL_MAP, 'mutators': {'id': 1},
                                  'spectatorPolicy': 'AllAllowed', 'teamSize': 5},
                'lobbyName': 'practice', 'lobbyPassword': None},
            'isCustom': True, 'queueId': PRACTICE_TOOL_QUEUE}
        # Right after login the lobby service answers 423 (locked) until it has initialized
        def create_lobby():
            response = client.call('POST', '/lol-lobby/v2/lobby', lobby)
            if isinstance(response, Exception) or response.status_code >= 300:
                status = response if isinstance(response, Exception) else response.status_code
                log(f'lobby not ready yet: {status}')
                return None
            return response

        if not wait_for('lobby service', create_lobby, 240, interval=8):
            return 1
        log('lobby created')
    if not wait_for('lobby', lambda: phase() == 'Lobby', 60):
        return 1

    response = client.call('POST', '/lol-lobby/v1/lobby/custom/start-champ-select')
    if isinstance(response, Exception) or response.status_code >= 300:
        log(f'could not start champion select: {response if isinstance(response, Exception) else response.status_code}')
        return 1
    if not wait_for('champion select', lambda: phase() == 'ChampSelect', 120):
        return 1
    log('champion select')

    def my_pick():
        session = client.json('GET', '/lol-champ-select/v1/session')
        if not session:
            return None
        cell = session.get('localPlayerCellId')
        for group in session.get('actions', []):
            for action in group:
                if action.get('actorCellId') == cell and action.get('type') == 'pick' and action.get('isInProgress'):
                    return (action['id'],)   # the action id can be 0, so wrap it to stay truthy
        return None

    found = wait_for('pick turn', my_pick, 120, interval=2)
    if found is None:
        return 1
    action = found[0]
    response = client.call('PATCH', f'/lol-champ-select/v1/session/actions/{action}', {'championId': champion})
    if isinstance(response, Exception) or response.status_code >= 300:
        log(f'could not hover champion {champion}: {response if isinstance(response, Exception) else response.status_code}')
        return 1
    response = client.call('POST', f'/lol-champ-select/v1/session/actions/{action}/complete')
    if isinstance(response, Exception) or response.status_code >= 300:
        log(f'could not lock in: {response if isinstance(response, Exception) else response.status_code}')
        return 1
    log(f'locked champion {champion}')

    seen = None
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        current = phase()
        if current != seen:
            log(f'phase={current}')
            seen = current
        time.sleep(2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
