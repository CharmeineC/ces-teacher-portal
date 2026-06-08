"""
startup.py — Initializes database on first run.
Called automatically by gunicorn via wsgi.py.
"""
from database import setup_database
setup_database()

from app import app
