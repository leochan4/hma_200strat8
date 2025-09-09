import json
import os

STATE_FILE = 'state.json'

#helper functions for state.json.

#load_state reads in the .json file for last position state
#write_state saves the position parameters into .json

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    else:
        return {'position': 0, 'entry_type': None, 'entry_price': None}

def write_state(position, entry_type, entry_price):
    state = {
        'position': position,
        'entry_type': entry_type,
        'entry_price': entry_price
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)