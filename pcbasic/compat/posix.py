"""
PC-BASIC - compat.posix
Interface for Unix-like system calls

(c) 2018 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""
"""
PC-BASIC - win32
DLL interface for Windows system libraries

(c) 2018 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import os
import sys
import locale
import select
import subprocess


##############################################################################
# various

SHELL_ENCODING = sys.stdin.encoding

def key_pressed():
    """Return whether a character is ready to be read from the keyboard."""
    return select.select([sys.stdin], [], [], 0)[0] != []

def set_dpi_aware():
    """Enable HiDPI awareness."""

##############################################################################
# file system

def get_free_bytes(path):
    """Return the number of free bytes on the drive."""
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize

def get_short_pathname(native_path):
    """Return Windows short path name or None if not available."""
    return None

def get_unicode_argv():
    """Convert command-line arguments to unicode."""
    # the official parameter should be LC_CTYPE but that's None in my locale
    # on Windows, this would only work if the mbcs CP_ACP includes the characters we need;
    return [arg.decode(locale.getpreferredencoding(), errors='replace') for arg in sys.argv]

##############################################################################
# printing

def command_exists(command):
    """Check if a shell command exists."""
    return subprocess.call(b'command -v %s >/dev/null 2>&1' % (command,), shell=True) == 0

if command_exists('paps'):
    def line_print(printbuf, printer, tempdir):
        """Print the buffer to a LPR printer using PAPS."""
        options = b''
        if printer and printer != b'default':
            options = b'-P %s' % (printer,)
        if printbuf:
            # A4 paper is 595 points wide by 842 points high.
            # Letter paper is 612 by 792 points.
            # the below seems to allow 82 chars horizontally on A4; it appears
            # my PAPS version doesn't quite use cpi correctly as 10cpi should
            # allow 80 chars on A4 with a narrow margin but only does so with a
            # margin of 0.
            pr = subprocess.Popen(
                b'paps --cpi=11 --lpi=6 --left-margin=20 --right-margin=20 '
                '--top-margin=6 --bottom-margin=6 '
                '| lpr %s' % (options,), shell=True, stdin=subprocess.PIPE)
            # PAPS does not recognise CRLF
            printbuf = printbuf.replace(b'\r\n', b'\n')
            pr.stdin.write(printbuf)
            pr.stdin.close()

else:
    def line_print(printbuf, printer, tempdir):
        """Print the buffer to a LPR (CUPS or older UNIX) printer."""
        options = b''
        if printer and printer != b'default':
            options = b'-P %s' % (printer,)
        if printbuf:
            # cups defaults to 10 cpi, 6 lpi.
            pr = subprocess.Popen(b'lpr %s' % (options,), shell=True, stdin=subprocess.PIPE)
            pr.stdin.write(printbuf)
            pr.stdin.close()
