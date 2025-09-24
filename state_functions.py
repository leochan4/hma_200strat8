'''import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')

#helper functions for state.json.

#load_state reads in the .json file for last position state
#write_state saves the position parameters into .json

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    else:
        return {'position': 0, 'entry_type': None, 'entry_price': None, 'paused': False}

def write_state(position, entry_type, entry_price, paused):
    state = {
        'position': position,
        'entry_type': entry_type,
        'entry_price': entry_price,
        'paused': paused
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)'''

import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), 'state.json')

DEFAULT = {
    'position': 0,
    'entry_type': None,
    'entry_price': None,
    'paused': False,   # normalized key
}

def _normalize(state: dict) -> dict:
    # map old key -> new key
    if 'paused' not in state and 'pause_state' in state:
        state['paused'] = bool(state['pause_state'])
        state.pop('pause_state', None)

    # fill defaults
    for k, v in DEFAULT.items():
        state.setdefault(k, v)

    # clamp position
    if state['position'] not in (-1, 0, 1):
        state['position'] = 0

    return state

def load_state() -> dict:
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    except FileNotFoundError:
        return DEFAULT.copy()
    except json.JSONDecodeError:
        # corrupted file; start fresh
        try:
            os.replace(STATE_FILE, STATE_FILE + '.corrupt')
        except Exception:
            pass
        return DEFAULT.copy()
    return _normalize(state)

def write_state(position: int, entry_type: str | None, entry_price: float | None, paused: bool) -> None:
    state = _normalize({
        'position': position,
        'entry_type': entry_type,
        'entry_price': entry_price,
        'paused': bool(paused),
    })
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)