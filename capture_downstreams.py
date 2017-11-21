"""
Capture a piece of all downstreams in a channel file and filter them by PID.

Needs recent tshark (use PPA on 16.04) in order to filter. Otherwise the script
does not run (tshark fails & it continues)
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
    accepts pids in *pids*.
    """
    return " || ".join([f"(mp2t.pid == 0x{p:02x})" for p in pids])


def dvb_capture(channel_config: io.StringIO,
                config_file: str,
                verbose: bool = False,
                prefix: str = 'Capture',
                path: str = '.',
                duration: int = 15,
                pids: List[int] = [8191],
                ):
    for channel in read_channels(channel_config):
        freq_mhz = channel.frequency // 10**6
        output_file_name = f"{path}/{prefix}_{channel.name}_{freq_mhz}.ts"

        capture_cmd = ['/usr/bin/dvbv5-zap',
                       '-c', config_file,
                       '-P',
                       '-t', str(duration),
                       channel.name,
                       '-o', 'tmp.ts']
        LOG.info(" ".join(capture_cmd))
        subprocess.call(capture_cmd)

        filter_cmd = ['/usr/bin/tshark',
                      '-r', 'tmp.ts',
                      '-Y', f"{pid_filter(pids)}",  # display filter
                      '-w', output_file_name]
        LOG.info(" ".join(filter_cmd))

        subprocess.call(filter_cmd)
        os.remove('tmp.ts')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Capture DVB stream fragments')
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='verbose output')
    parser.add_argument('-t', '--duration', type=int, default=15,
                        help='Capture duration')
    parser.add_argument('channel_config', type=argparse.FileType('r'),
                        help='channel file in dvbv5-zap format')
    parser.add_argument('--pid', dest='pids', type=int, action='append',
                        help='pid number(s) to keep (can be repeated), default=8191')
    parser.add_argument('--prefix', type=str, default='Capture',
                        help='Prefix for the file names')
    parser.add_argument('--path', type=str, default='.',
                        help='Directory to save files in')

    args = parser.parse_args()

    logging.basicConfig()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    if args:
        dvb_capture(config_file=args.channel_config.name,
                    **{ k:v for k,v in args.__dict__.items() if v})
    else:
        parser.print_help()
