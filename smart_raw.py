#!/usr/bin/env python3
'''
Munin plugin for monitoring raw SMART values
'''


import glob
import json
import os
import re
import subprocess
import sys
from argparse import Namespace
from shutil import which


# Plugin may be configured via these environment variables,
# sane default are provided for everything
ENV_DRIVES = 'smart_raw_drives'      # Space separated drive names, e.g. "sda sdb"
ENV_PARAMETERS = 'smart_raw_params'  # Space separated list of parameters to monitor, e.g.
                                     # "5 187 188 197 198" as recommended by Backblaze
                                     # https://www.backblaze.com/blog/hard-drive-smart-stats/
ENV_SMARTCTL = 'smart_raw_smartctl'  # Custom path to smartctl executable
ENV_STATEFILE = 'MUNIN_STATEFILE'    # Persistent storage, defined by Munin node


if not os.getenv(ENV_STATEFILE):
    raise ValueError('environment variable not defined: {}'.format(ENV_STATEFILE))


# Output templates
HEADER_CONFIG = (
    'graph_title S.M.A.R.T. Raw Values\n'
    'graph_category disk\n'
    'graph_args --lower-limit 0 --base 1000\n'
)
SMART_CONFIG = (
    'smart_raw_{id}_{device}.label {device}: {name}\n'
    'smart_raw_{id}_{device}.min 0\n'
)
SMART_FETCH = (
    'smart_raw_{id}_{device}.value {raw}\n'
)


# Data point regex
SMART_LINE = re.compile(r'^\s*\d+.*\s+\d{3}\s+\d{3}\s+\d{3}\s+')


def settings():
    '''Read plugin settings from environment'''
    executable = os.getenv(ENV_SMARTCTL, which('smartctl'))
    if not executable:
        raise ValueError('no executable provided for smartctl')

    drives= os.getenv(ENV_DRIVES)
    if drives is None:
        drives = glob.glob('/dev/sd?')
    else:
        drives = ['/dev/{}'.format(d) for d in drives.split()]

    params = os.getenv(ENV_PARAMETERS, '5 187 188 197 198').split()

    return Namespace(
        executable=executable,
        params=params,
        drives=drives,
    )


def smartctl(drive):
    '''Return parsed SMART data for a drive'''
    command = subprocess.run(
                  [Config.executable, '--all', drive, '--device=auto'],
                  capture_output=True,
              )
    output = {}
    for line in command.stdout.decode().splitlines():
        if not SMART_LINE.search(line):
            continue
        words = line.split()
        param_id = words[0]
        if param_id in output:
            continue
        output[param_id] = dict(
            id=words[0],
            name=words[1],
            flag=words[2],
            value=words[3],
            worst=words[4],
            thresh=words[5],
            type=words[6],
            updated=words[7],
            when_failed=words[8],
            raw=words[9],
        )
    return output


def munin_fetch():
    '''Execute plugin and print data for Munin node'''
    response = []
    for drive in Config.drives:
        # Gather SMART data
        smart = smartctl(drive)
        for param in Config.params:
            if param in smart:
                response.append(SMART_FETCH.format(
                    device=os.path.basename(drive),
                    **smart[param],
                ))

        # Update known names database
        known_names = {s['id']:s['name'] for s in smart.values()}
        munin_state(**known_names)

    print('\n'.join(response))


def munin_config():
    '''Print Munin plugin configuration'''
    known_names = munin_state()
    response = []
    response.append(HEADER_CONFIG)
    for drive in Config.drives:
        for param in Config.params:
            response.append(SMART_CONFIG.format(
                id=param,
                name=known_names.get(param, 'Unknown'),
                device=os.path.basename(drive),
            ))
    print('\n'.join(response))


def munin_state(**kw):
    '''Manage Munin state file'''
    try:
        with open(os.getenv(ENV_STATEFILE)) as statefile:
            state = json.load(statefile)
    except Exception:
        state = {}

    modified = False
    for key, value in kw.items():
        if state.get(key) != value:
            state[key] = value
            modified = True

    if modified:
        with open(os.getenv(ENV_STATEFILE), 'w') as statefile:
            json.dump(state, statefile, indent=2, sort_keys=True, ensure_ascii=False)

    return state


def main():
    if len(sys.argv) == 1:
        munin_fetch()
    elif sys.argv[1] == 'config':
        munin_config()
    elif sys.argv[1] == 'autoconf':
        if  os.path.isfile(Config.executable) \
        and os.access(Config.executable, os.X_OK):
            print('yes')
            sys.exit(0)
        else:
            print('no (smartctl not found or not executable)')
            sys.exit(1)
    else:
        raise ValueError('invalid arguments: {}'.format(sys.argv[1:]))


Config = settings()
if __name__ == '__main__':
    main()
