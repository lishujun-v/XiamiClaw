#!/usr/bin/env python3
"""Simple sub-agent example"""
import sys

name = sys.argv[1] if len(sys.argv) > 1 else "World"
print(f"Hello, {name}! This is a sub-agent.")
print(f"Arguments: {sys.argv}")
