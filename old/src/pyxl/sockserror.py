"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""

#
# Socks Errors
#

class SocksException (Exception):
    """ Class descendants are raised for every fatal error that leads to
        connection close.
    """

class UnexpectedDataError (SocksException):
    pass

class UnhandledStateError (SocksException):
    pass

class LoginTooLongError (SocksException):
    """ According to RFC1929 Login must be 1-255 chars. """

class PasswordTooLongError (SocksException):
    """ According to RFC1929 Password must be 1-255 chars. """

class UnknownMethod (SocksException):
    """ Method is invalid or not implemented. """

class ConnectError (SocksException): 
    """ One of error replies after client issue CONNECT command. """

class UnhandledData (SocksException): 
    """ Server returned data that was not handled properly in our impl. """

class GlobalTimeoutError (SocksException): 
    """ Connection took too long and was interrupted unconditionally. """

# here are SOCKS error codes according to RFC1928
#
SOCKS_errors = [\
    "general SOCKS server failure",
    "connection not allowed by ruleset",
    "Network unreachable",
    "Host unreachable",
    "Connection refused",
    "TTL expired",
    "Command not supported",
    "Address type not supported"]

SOCKS4_errors = {\
    0x90: "No error",
    0x91: "Rejected or failed",
    0x92: "Connection to client ident refused",
    0x93: "Client login and ident reply mismatch"
}

#--- END ---



