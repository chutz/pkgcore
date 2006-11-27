# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Commandline interface to L{pkgcore.ebuild.filter_env}."""


import sys
import optparse

from pkgcore.util import commandline
from pkgcore.ebuild import filter_env


def input_callback(option, opt_str, value, parser):
    if parser.values.input is not None:
        raise optparse.OptionValueError('-i cannot be specified twice')
    try:
        parser.values.input = open(value, 'r')
    except (IOError, OSError), e:
        raise optparse.OptionValueError('error opening %r (%s)' % (value, e))


def append_comma_separated(option, opt_str, value, parser):
    parser.values.ensure_value(option.dest, []).extend(
        v for v in value.split(',') if v)


class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, **kwargs)
        self.add_option(
            '-V', '--var-match', action='store_false', default=True)
        self.add_option(
            '-F', '--func-match', action='store_false', default=True)
        self.add_option(
            '--input', '-i', action='callback', type='string',
            callback=input_callback,
            help='Filename to read the env from (uses stdin if omitted).')
        self.add_option(
            '--funcs', '-f', action='callback', type='string',
            callback=append_comma_separated)
        self.add_option(
            '--vars', '-v', action='callback', type='string',
            callback=append_comma_separated)

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)

        if values.input is None:
            # Hack: use stdin if it is not a tty. No util.commandline
            # support for this kind of thing, so mess around with sys
            # directly.
            if sys.stdin.isatty():
                self.error('No input file supplied (and stdin is a tty).')
            values.input = sys.stdin

        return values, args


def main(options, out, err):
    if options.funcs:
        funcs = filter_env.build_regex_string(options.funcs)
    else:
        funcs = None

    if options.vars:
        vars = filter_env.build_regex_string(options.vars)
    else:
        vars = None

    file_buff = options.input.read() + '\0'

    # Hack: write to the stream directly.
    filter_env.run(out.stream, file_buff, vars, funcs,
                   options.var_match, options.func_match)