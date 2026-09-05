"""Jabbim-next XMPP Client.

Launch: python main.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jabbim.app import run
sys.exit(run())
