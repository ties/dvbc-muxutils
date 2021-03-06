"""
Capture a piece of all downstreams in a channel file and filter them by PID.

This script works for me but it is fragile - error checking is non-existent.

Usage:
```
sudo `which python` capture_downstreams.py raw \
    downstreams.conf \
    --prefix "Recording_`date +%F_%R`" \
    --path /media/recordings \
    -t 45
```
"""
import argparse
import logging
import io
import os

import configparser
import subprocess

from typing import List, NamedTuple, Generator

LOG = logging.getLogger(__name__)


class Channel(NamedTuple):
    """
    A dvb channel config object
    """
    name: str
    delivery_system: str
    # Frequency in Hertz
    frequency: int
    symbol_rate: int
    inner_fec: str
    modulation: str
    inversion: str


def read_channels(channels: io.StringIO) -> Generator[Channel, None, None]:
    """
    Read all the properties of the channels in the file, even though it is
    likely that only name will be used.
    """
    config = configparser.ConfigParser()
    config.read_file(channels)

    for name in config.sections():
        channel = config[name]
        yield Channel(
            name=name,
            delivery_system=channel['DELIVERY_SYSTEM'].lower(),
            frequency=int(channel['FREQUENCY']),
            symbol_rate=int(channel['SYMBOL_RATE']),
            inner_fec=channel['INNER_FEC'],
            modulation=channel['MODULATION'],
            inversion=channel['INVERSION']
        )

    return None


def pid_filter(pids: List[int]) -> str:
    """
    Return a disjunctive filter string to be used in wireshark/tshark that only
    accepts pids in *pids* (if provided)
    """
    return " || ".join([f"(mp2t.pid == 0x{p:02x})" for p in pids])


def dvb_record_raw_channels(channel_config: io.StringIO,
                            config_file: str,
                            verbose: bool = False,
                            prefix: str = 'Capture',
                            path: str = '.',
                            duration: int = 45) -> None:
    """
    Capture raw mpeg ts
    """
    for channel in read_channels(channel_config):
        freq_mhz = channel.frequency // 10**6
        output_file_name = f"{path}/{prefix}_{channel.name}_{freq_mhz}.ts"

        capture_cmd = ['/usr/bin/dvbv5-zap',
                       '-c', config_file,
                       '-P',
                       '-t', str(duration),
                       channel.name,
                       '-o', output_file_name]
        LOG.info(" ".join(capture_cmd))
        subprocess.call(capture_cmd)


def dvb_record_filtered_channels(channel_config: io.StringIO,
                                 config_file: str,
                                 verbose: bool = False,
                                 prefix: str = 'Capture',
                                 path: str = '.',
                                 duration: int = 45,
                                 skip_pids: List[int] = [],
                                 pids: List[int] = []) -> None:
    """
    Capture data and filter it by pid, save as pcapng
    """
    filter_str = ""
    if skip_pids and pids:
        print("--skip_pid and --pid were both used at the same time, this is "
              "not possible, aborting")
        return
    elif skip_pids:
        filter_str = f"!({pid_filter(skip_pids)})"
    else:
        filter_str = f"({pid_filter(pids)})"

    for channel in read_channels(channel_config):
        freq_mhz = channel.frequency // 10**6
        output_file_name = f"{path}/{prefix}_{channel.name}_{freq_mhz}.pcapng"

        capture_cmd = ['/usr/bin/dvbv5-zap',
                       '-c', config_file,
                       '-P',
                       '-t', str(duration),
                       channel.name,
                       '-o', 'tmp.ts']
        LOG.info(" ".join(capture_cmd))
        subprocess.call(capture_cmd)

        # Filter file using tshark
        filter_cmd = ['/usr/bin/tshark',
                      '-r', 'tmp.ts',
                      '-R', filter_str, '-2', # read filter
                      '-w', output_file_name]
        LOG.info(" ".join(filter_cmd))

        subprocess.call(filter_cmd)
        # Remove the temporary file
        os.remove('tmp.ts')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Record part of the DVB-C stream for each mux in a channel'
                    ' file and filter it by pid')

    subs = parser.add_subparsers()

    raw = subs.add_parser('raw', help='Save raw ts')
    raw.set_defaults(func=dvb_record_raw_channels)

    filtered = subs.add_parser('filtered', help='Save a filtered .pcap file')
    filtered.set_defaults(func=dvb_record_filtered_channels)

    filtered.add_argument('--pid', dest='pids', type=int, action='append',
                          help='pid(s) to keep, default=all')
    filtered.add_argument('--skip_pid', dest='skip_pids', type=int,
                          action='append', help='pid(s) to skip, '
                          'pid and skip_pid are mutually exclusive')
    # Add the shared options to both sub-parsers
    for p in [raw, filtered]:
        p.add_argument('channel_config', type=argparse.FileType('r'),
                       help='channel file in dvbv5-zap format')
        p.add_argument('--verbose', action='store_true', default=False,
                       help='verbose output')
        p.add_argument('-t', '--duration', type=int, default=45,
                       help='Capture duration, 45s is needed to ensure that '
                       'two ranging replies are received for cable modems')
        p.add_argument('--prefix', type=str, default='Capture',
                       help='Prefix for the file names')
        p.add_argument('--path', type=str, default='.',
                       help='Directory to save files in')

    args = parser.parse_args()

    logging.basicConfig()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    if args and hasattr(args, 'func'):
        args.func(config_file=args.channel_config.name,
                  **{k: v for k, v in args.__dict__.items()
                     if v and k != 'func'})
    else:
        parser.print_help()
