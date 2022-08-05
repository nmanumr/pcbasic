"""
PC-BASIC - guard
Crash guard

(c) 2013--2022 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import os
import sys
import logging
import platform
import tempfile
import traceback
import webbrowser
import json
from datetime import datetime
from contextlib import contextmanager
from subprocess import check_output, CalledProcessError

from .basic.base import error, signals
from .basic import VERSION, LONG_VERSION
from .compat import BrokenPipeError, is_broken_pipe


LOG_PATTERN = u'crash-%Y%m%d-'
PAUSE_MESSAGE = u'System error. Please file a bug report. Press <Enter> to resume.'


class ExceptionGuard(object):
    """Context manager to handle uncaught exceptions."""

    def __init__(self, interface, log_dir=u'', uargv=()):
        """Initialise crash guard."""
        self._interface = interface
        self._uargv = uargv
        self._log_dir = log_dir
        self._session = None

    def __call__(self, session):
        """Complete initialisation."""
        self._session = session
        return self

    def __enter__(self):
        """Enter context guard."""
        self.exception_handled = None
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        """Handle exceptions."""
        if not exc_type or exc_type == error.Reset:
            return False
        if is_broken_pipe(exc_val):
            # BrokenPipeError may be raised by shell pipes, handled at entry point
            # see docs.python.org/3/library/signal.html#note-on-sigpipe
            return False
        if not self._bluescreen(
            self._session._impl, self._interface,
            self._uargv, self._log_dir,
            exc_type, exc_val, traceback
        ):
            return False
        while True:
            event = self._interface.pause(PAUSE_MESSAGE)
            if event.event_type == signals.QUIT:
                break
            elif event.event_type == signals.KEYB_DOWN and event.params[0] == '\r':
                # add our own attribute to the session object as a flag
                self.exception_handled = exc_val
                break
        return True

    def _bluescreen(self, impl, iface, argv, log_dir, exc_type, exc_value, exc_traceback):
        """Display modal message"""
        if not impl:
            return False
        if iface:
            iface_name = u'%s, %s' % (type(iface._video).__name__, type(iface._audio).__name__)
        else:
            iface_name = u'--'
        # log the standard python error
        stack = traceback.extract_tb(exc_traceback)
        logging.error(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        # obtain statement being executed
        if impl.interpreter.run_mode:
            codestream = impl.program.bytecode
            bytepos = codestream.tell() - 1
            from_line = impl.program.get_line_number(bytepos)
            try:
                codestream.seek(impl.program.line_numbers[from_line]+1)
                _, output, _ = impl.lister.detokenise_line(codestream)
                code_line = bytes(output)
            except KeyError:
                code_line = b'<could not retrieve line number %d>' % from_line
        else:
            impl.interpreter.direct_line.seek(0)
            code_line = bytes(
                impl.lister.detokenise_compound_statement(impl.interpreter.direct_line)[0]
            )
        # don't risk codepage logic here, use cp437
        code_line = code_line.decode('cp437', 'replace')
        # stop program execution
        impl.interpreter.set_pointer(False)
        # create crash log file
        logname = datetime.now().strftime(LOG_PATTERN)
        logfile = tempfile.NamedTemporaryFile(
            mode='wb', suffix='.log', prefix=logname, dir=log_dir, delete=False
        )
        # construct the message
        frozen = getattr(sys, 'frozen', u'') or u''
        message = [
            (0x70, u'PC-BASIC SYSTEM ERROR\n'),
            (0x17, u'version   '),
            (0x1f, LONG_VERSION),
            (0x17, u'\npython    '),
            (0x1f, u'%s [%s] %s' % (
                platform.python_version(), u' '.join(platform.architecture()), frozen
            )),
            (0x17, u'\nplatform  '),
            (0x1f, platform.platform()),
            (0x17, u'\ninterface '),
            (0x1f, iface_name),
            (0x17, u'\nstatement '),
            (0x1f, code_line + u'\n\n'),
        ] + [
            (0x1f, u'{0}:{1}, {2}\n'.format(os.path.split(s[0])[-1], s[1], s[2]))
            for s in stack[-4:]
        ] + [
            (0x1f, u'{0}:'.format(exc_type.__name__)),
            (0x17, u' {0}\n\n'.format(exc_value)),
            (0x70, u'This is a bug in PC-BASIC.\n'),
            (0x17, u'Sorry about that. You can help improve PC-BASIC:\n\n'),
            (0x17, u'- Please file a bug report at '),
            (0x1f, u'https://github.com/robhagemans/pcbasic/issues\n\n'),
            (0x17, u'- Please include the full crash log found here:\n'),
            (0x17, u'  '),
            (0x1f, logfile.name),
        ]
        bottom = (
            (0x70, u'Press <Enter> to resume.'),
            (0x17, u' It is recommended that you save any unsaved work.'),
        )
        # create crash log
        crashlog = [
            u'PC-BASIC crash log',
            u'=' * 100,
            u''.join(text for _, text in message),
            u'\n',
            u'==== Traceback ='.ljust(100, u'='),
            u''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
            u'==== Screen Pages ='.ljust(100, u'='),
            repr(impl.display.text_screen),
            u'==== Scalars ='.ljust(100, u'='),
            repr(impl.scalars),
            u'==== Arrays ='.ljust(100, u'='),
            repr(impl.arrays),
            u'==== Strings ='.ljust(100, u'='),
            repr(impl.strings),
            u'==== Program Buffer ='.ljust(100, u'='),
            repr(impl.program),
        ]
        impl.program.bytecode.seek(1)
        crashlog.append(u'==== Program ='.ljust(100, u'='))
        while True:
            _, line, _ = impl.lister.detokenise_line(impl.program.bytecode)
            if not line:
                break
            crashlog.append(bytes(line).decode('cp437', 'replace'))
        crashlog.append(u'==== Options ='.ljust(100, u'='))
        crashlog.append(repr(argv))
        # clear screen for modal message
        # choose attributes - this should be readable on VGA, MDA, PCjr etc.
        impl.display.screen(0, 0, 0, 0, new_width=80)
        impl.display.set_attr(0x17)
        impl.display.set_border(1)
        impl.display.text_screen.clear()
        # show message on screen
        for attr, text in message:
            impl.display.set_attr(attr)
            impl.console.write(text.encode('cp437', 'replace').replace(b'\n', b'\r'))
        impl.display.text_screen._bottom_row_allowed = True
        impl.display.text_screen.set_pos(25, 1)
        for attr, text in bottom:
            impl.display.set_attr(attr)
            impl.console.write(text.encode('cp437', 'replace'))
        # write crash log
        crashlog = u'\n'.join(
            line.decode('cp437', 'replace') if isinstance(line, bytes) else line
            for line in crashlog
        )
        with logfile as f:
            f.write(crashlog.encode('utf-8', 'replace'))
        # open text file
            webbrowser.open(logfile.name)
        return True
